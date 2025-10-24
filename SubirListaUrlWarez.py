import json
import os
import logging
import re
from dotenv import load_dotenv
import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Carregar variáveis de ambiente
load_dotenv()

# Configuração Supabase
SUPABASE_URL = "https://forfhjlkrqjpglfbiosd.supabase.co"
SUPABASE_APIKEY = os.getenv("SUPABASE_APIKEY")
SUPABASE_TABLE_FILMES = "filmes_url_warezcdn"
SUPABASE_TABLE_SERIES = "series_url_warezcdn"

# Configuração TMDB
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_BASE_URL = "https://api.themoviedb.org/3"

# Arquivos JSON
JSON_FILE_FILMES = os.path.join(os.getcwd(), 'url_extraidas_filmes.json')
JSON_FILE_SERIES = os.path.join(os.getcwd(), 'url_extraidas_series.json')

if not SUPABASE_APIKEY:
    logger.error("SUPABASE_APIKEY não encontrada nas variáveis de ambiente!")
    exit(1)

if not TMDB_API_KEY:
    logger.error("TMDB_API_KEY não encontrada nas variáveis de ambiente!")
    exit(1)


def extrair_imdb_id(url):
    """Extrai o ID do IMDb da URL"""
    match = re.search(r'tt\d+', url)
    return match.group(0) if match else None


def buscar_info_serie_tmdb(imdb_id, url, indice):
    """Busca informações da série no TMDB usando o IMDb ID"""
    try:
        headers = {
            'Authorization': f'Bearer {TMDB_API_KEY}',
            'Content-Type': 'application/json;charset=utf-8'
        }
        
        # Passo 1: Buscar pelo IMDb ID para obter o TMDB ID
        url_find = f"{TMDB_BASE_URL}/find/{imdb_id}"
        params_find = {'external_source': 'imdb_id'}
        
        response_find = requests.get(url_find, headers=headers, params=params_find, timeout=10)
        
        if response_find.status_code != 200:
            logger.error(f"[{indice}] Erro ao buscar no TMDB: {response_find.status_code}")
            return None
        
        data_find = response_find.json()
        
        if not data_find.get('tv_results') or len(data_find['tv_results']) == 0:
            logger.warning(f"[{indice}] Nenhuma série encontrada no TMDB para {imdb_id}")
            return None
        
        serie = data_find['tv_results'][0]
        tmdb_id = serie['id']
        
        # Passo 2: Buscar detalhes completos da série
        url_detalhes = f"{TMDB_BASE_URL}/tv/{tmdb_id}"
        response_detalhes = requests.get(url_detalhes, headers=headers, timeout=10)
        
        if response_detalhes.status_code != 200:
            logger.error(f"[{indice}] Erro ao buscar detalhes no TMDB: {response_detalhes.status_code}")
            return None
        
        detalhes = response_detalhes.json()
        
        # Extrair informações das temporadas
        temporadas = []
        seasons_data = detalhes.get('seasons', [])
        
        for temporada in seasons_data:
            season_number = temporada.get('season_number', 0)
            episode_count = temporada.get('episode_count', 0)
            
            # Ignorar temporada 0 (especiais)
            if season_number == 0:
                continue
            
            temporadas.append({
                'numero': season_number,
                'episodios': episode_count
            })
        
        nome_serie = detalhes.get('name', 'Desconhecida')
        
        return {
            'url': url,
            'nome': nome_serie,
            'temporadas': temporadas,
            'indice': indice
        }
        
    except Exception as e:
        logger.error(f"[{indice}] Erro ao buscar info no TMDB: {e}")
        return None


def carregar_json(arquivo):
    """Carrega o arquivo JSON com as URLs"""
    try:
        if not os.path.exists(arquivo):
            logger.error(f"Arquivo JSON não encontrado: {arquivo}")
            return []
        
        with open(arquivo, 'r', encoding='utf-8') as f:
            data = json.load(f)
            logger.info(f"JSON carregado com {len(data)} registros")
            return data
    except Exception as e:
        logger.error(f"Erro ao carregar JSON: {e}")
        return []


def buscar_todos_filmes_supabase():
    """Busca TODOS os filmes do Supabase com paginação (1000 por vez)"""
    logger.info("\n🔍 Buscando TODOS os filmes existentes no Supabase...")
    
    todos_filmes = {}
    offset = 0
    limite = 1000
    pagina = 1
    tentativas_erro = 0
    max_tentativas = 3
    
    try:
        headers = {
            "apikey": SUPABASE_APIKEY,
            "Authorization": f"Bearer {SUPABASE_APIKEY}",
            "Content-Type": "application/json"
        }
        
        while True:
            params = {
                "select": "url,video_repro_url,dublado",
                "limit": limite,
                "offset": offset
            }
            
            logger.info(f"  → Buscando página {pagina} (offset {offset})...")
            
            try:
                response = requests.get(
                    f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE_FILMES}",
                    headers=headers,
                    params=params,
                    timeout=30
                )
                
                if response.status_code != 200:
                    logger.error(f"  ❌ Erro ao buscar página {pagina}: {response.status_code}")
                    tentativas_erro += 1
                    if tentativas_erro >= max_tentativas:
                        logger.error(f"  ❌ Máximo de tentativas alcançado. Abortando busca.")
                        return None  # Retorna None para indicar erro crítico
                    time.sleep(2)
                    continue
                
                filmes = response.json()
                tentativas_erro = 0  # Reseta contador em caso de sucesso
                
                if not filmes:
                    logger.info(f"  ✅ Fim da paginação (página {pagina} vazia)")
                    break
                
                # Adicionar ao dicionário indexado por URL
                for filme in filmes:
                    todos_filmes[filme['url']] = filme
                
                logger.info(f"  ✓ Página {pagina}: {len(filmes)} filmes carregados")
                
                # Se retornou menos que o limite, não há mais páginas
                if len(filmes) < limite:
                    break
                
                offset += limite
                pagina += 1
                time.sleep(0.1)  # Pequena pausa entre requisições
                
            except requests.exceptions.RequestException as e:
                logger.error(f"  ❌ Erro de conexão na página {pagina}: {e}")
                tentativas_erro += 1
                if tentativas_erro >= max_tentativas:
                    logger.error(f"  ❌ Não foi possível conectar ao Supabase após {max_tentativas} tentativas")
                    return None  # Retorna None para indicar erro crítico
                time.sleep(2)
                continue
        
        logger.info(f"\n  ✅ Total: {len(todos_filmes)} filmes carregados do Supabase")
        return todos_filmes
        
    except Exception as e:
        logger.error(f"  ❌ Erro crítico ao buscar filmes: {e}")
        return None


def buscar_episodios_existentes_supabase(url):
    """Busca todos os episódios existentes de uma série no Supabase"""
    try:
        headers = {
            "apikey": SUPABASE_APIKEY,
            "Authorization": f"Bearer {SUPABASE_APIKEY}",
            "Content-Type": "application/json"
        }
        
        params = {
            "select": "url,temporada_numero,episodio_numero,video_url",
            "url": f"eq.{url}"
        }
        
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE_SERIES}",
            headers=headers,
            params=params,
            timeout=30
        )
        
        if response.status_code == 200:
            episodios = response.json()
            # Criar dicionário indexado por (temporada, episodio)
            return {(ep['temporada_numero'], ep['episodio_numero']): ep for ep in episodios}
        else:
            logger.error(f"Erro ao buscar episódios: {response.status_code}")
            return {}
            
    except Exception as e:
        logger.error(f"Erro ao buscar episódios existentes: {e}")
        return {}


def buscar_todas_series_tmdb(registros_json, max_workers=5):
    """Busca informações de todas as séries no TMDB em paralelo"""
    logger.info("\n🔍 FASE 1: Buscando informações de TODAS as séries no TMDB...")
    
    series_validas = []
    series_com_erro = []
    
    # Preparar lista de tarefas
    tarefas = []
    for i, item in enumerate(registros_json, 1):
        url = item.get('url')
        if not url:
            continue
        
        imdb_id = extrair_imdb_id(url)
        if not imdb_id:
            logger.warning(f"[{i}/{len(registros_json)}] IMDb ID não encontrado: {url[:60]}")
            series_com_erro.append(url)
            continue
        
        tarefas.append((imdb_id, url, i))
    
    logger.info(f"  → {len(tarefas)} séries para processar")
    
    # Executar em paralelo
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(buscar_info_serie_tmdb, imdb_id, url, indice): (imdb_id, url, indice)
            for imdb_id, url, indice in tarefas
        }
        
        processadas = 0
        for future in as_completed(futures):
            processadas += 1
            resultado = future.result()
            
            if resultado:
                series_validas.append(resultado)
                logger.info(f"  ✓ [{processadas}/{len(tarefas)}] {resultado['nome']} - {len(resultado['temporadas'])} temporadas")
            else:
                imdb_id, url, indice = futures[future]
                series_com_erro.append(url)
                logger.warning(f"  ✗ [{processadas}/{len(tarefas)}] Erro ao processar série")
    
    logger.info(f"\n  ✅ {len(series_validas)} séries encontradas no TMDB")
    logger.info(f"  ❌ {len(series_com_erro)} séries com erro")
    
    return series_validas, series_com_erro


def buscar_todos_episodios_supabase(series_info, max_workers=5):
    """Busca episódios existentes de todas as séries no Supabase em paralelo"""
    logger.info("\n🔍 FASE 2: Buscando episódios existentes de TODAS as séries no Supabase...")
    
    episodios_por_serie = {}
    
    urls = [serie['url'] for serie in series_info]
    
    # Executar em paralelo
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(buscar_episodios_existentes_supabase, url): url
            for url in urls
        }
        
        processadas = 0
        for future in as_completed(futures):
            processadas += 1
            url = futures[future]
            episodios = future.result()
            episodios_por_serie[url] = episodios
            logger.info(f"  ✓ [{processadas}/{len(urls)}] {len(episodios)} episódios encontrados")
    
    total_episodios = sum(len(eps) for eps in episodios_por_serie.values())
    logger.info(f"\n  ✅ Total: {total_episodios} episódios existentes no Supabase")
    
    return episodios_por_serie


def preparar_dados_filmes(registros_json, filmes_existentes):
    """Prepara dados de filmes antes de enviar ao Supabase"""
    logger.info("\n📋 Preparando dados de filmes...")
    
    filmes_para_criar = []
    filmes_para_atualizar = []
    filmes_ignorados = []
    
    for item in registros_json:
        url = item.get('url')
        if not url:
            continue
        
        video_repro_url = item.get('video_repro_url') or None
        dublado = item.get('dublado')
        if dublado == '':
            dublado = None
        
        filme_existente = filmes_existentes.get(url)
        
        if filme_existente:
            # Verificar se precisa atualizar
            precisa_atualizar = False
            dados_atualizacao = {}
            
            if not filme_existente.get('video_repro_url') and video_repro_url:
                dados_atualizacao['video_repro_url'] = video_repro_url
                precisa_atualizar = True
            
            if filme_existente.get('dublado') is None and dublado is not None:
                dados_atualizacao['dublado'] = dublado
                precisa_atualizar = True
            
            if precisa_atualizar:
                filmes_para_atualizar.append({
                    'url': url,
                    'dados': dados_atualizacao
                })
            else:
                filmes_ignorados.append(url)
        else:
            # Criar novo registro
            filmes_para_criar.append({
                'url': url,
                'video_repro_url': video_repro_url,
                'dublado': dublado
            })
    
    logger.info(f"  ✓ {len(filmes_para_criar)} filmes para criar")
    logger.info(f"  ✓ {len(filmes_para_atualizar)} filmes para atualizar")
    logger.info(f"  ✓ {len(filmes_ignorados)} filmes já completos (ignorados)")
    
    return filmes_para_criar, filmes_para_atualizar, filmes_ignorados


def preparar_dados_series(series_info, episodios_por_serie):
    """Prepara dados de séries comparando TMDB com Supabase"""
    logger.info("\n📋 FASE 3: Comparando dados e preparando listas...")
    
    episodios_para_criar = []
    episodios_para_atualizar = []
    episodios_ignorados = []
    
    for serie in series_info:
        url = serie['url']
        nome = serie['nome']
        temporadas = serie['temporadas']
        indice = serie['indice']
        
        episodios_existentes = episodios_por_serie.get(url, {})
        
        logger.info(f"\n[{indice}] {nome}")
        logger.info(f"  → {len(temporadas)} temporadas")
        
        criar_count = 0
        atualizar_count = 0
        ignorar_count = 0
        
        # Preparar lista de episódios
        for temp_info in temporadas:
            temporada = temp_info['numero']
            total_episodios = temp_info['episodios']
            
            for episodio in range(1, total_episodios + 1):
                chave = (temporada, episodio)
                
                if chave in episodios_existentes:
                    episodio_existente = episodios_existentes[chave]
                    
                    # Verificar se video_url está vazio
                    if not episodio_existente.get('video_url'):
                        # Episódio existe mas video_url está vazio
                        episodios_para_atualizar.append({
                            'url': url,
                            'temporada_numero': temporada,
                            'episodio_numero': episodio
                        })
                        atualizar_count += 1
                    else:
                        # Episódio já tem video_url - ignorar
                        episodios_ignorados.append({
                            'url': url,
                            'temporada': temporada,
                            'episodio': episodio
                        })
                        ignorar_count += 1
                else:
                    # Episódio não existe - precisa ser criado
                    episodios_para_criar.append({
                        'url': url,
                        'temporada_numero': temporada,
                        'episodio_numero': episodio
                    })
                    criar_count += 1
        
        logger.info(f"  → Criar: {criar_count} | Atualizar: {atualizar_count} | Ignorar: {ignorar_count}")
    
    logger.info(f"\n{'='*70}")
    logger.info(f"RESUMO GERAL:")
    logger.info(f"  ✓ {len(episodios_para_criar)} episódios para criar")
    logger.info(f"  ✓ {len(episodios_para_atualizar)} episódios para atualizar (video_url vazio)")
    logger.info(f"  ✓ {len(episodios_ignorados)} episódios já completos")
    logger.info(f"{'='*70}")
    
    return episodios_para_criar, episodios_para_atualizar, episodios_ignorados


def criar_filmes_lote_supabase(filmes, tamanho_lote=500):
    """Cria múltiplos filmes no Supabase em lotes"""
    if not filmes:
        return 0
    
    total_filmes = len(filmes)
    logger.info(f"\n📤 Criando {total_filmes} filmes no Supabase (lotes de {tamanho_lote})...")
    
    sucesso_total = 0
    
    for i in range(0, total_filmes, tamanho_lote):
        lote = filmes[i:i + tamanho_lote]
        lote_num = (i // tamanho_lote) + 1
        total_lotes = (total_filmes + tamanho_lote - 1) // tamanho_lote
        
        try:
            headers = {
                "apikey": SUPABASE_APIKEY,
                "Authorization": f"Bearer {SUPABASE_APIKEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal"
            }
            
            response = requests.post(
                f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE_FILMES}",
                headers=headers,
                json=lote,
                timeout=30
            )
            
            if response.status_code in [200, 201, 204]:
                sucesso_total += len(lote)
                logger.info(f"  ✅ Lote {lote_num}/{total_lotes}: {len(lote)} filmes criados")
            else:
                logger.error(f"  ❌ Erro no lote {lote_num}/{total_lotes}: {response.status_code}")
                logger.error(f"     {response.text[:200]}")
            
            # Pausa entre lotes
            time.sleep(0.5)
            
        except Exception as e:
            logger.error(f"  ❌ Erro ao criar lote {lote_num}: {e}")
    
    logger.info(f"\n  ✅ Total: {sucesso_total}/{total_filmes} filmes criados com sucesso")
    return sucesso_total


def atualizar_filmes_supabase(filmes_para_atualizar):
    """Atualiza filmes existentes no Supabase"""
    if not filmes_para_atualizar:
        return 0
    
    logger.info(f"\n📤 Atualizando {len(filmes_para_atualizar)} filmes no Supabase...")
    
    sucesso = 0
    
    for filme in filmes_para_atualizar:
        try:
            headers = {
                "apikey": SUPABASE_APIKEY,
                "Authorization": f"Bearer {SUPABASE_APIKEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal"
            }
            
            params = {"url": f"eq.{filme['url']}"}
            
            response = requests.patch(
                f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE_FILMES}",
                headers=headers,
                params=params,
                json=filme['dados'],
                timeout=10
            )
            
            if response.status_code in [200, 204]:
                sucesso += 1
            else:
                logger.error(f"  ❌ Erro ao atualizar {filme['url'][:50]}: {response.status_code}")
            
            time.sleep(0.05)
            
        except Exception as e:
            logger.error(f"  ❌ Erro ao atualizar filme: {e}")
    
    logger.info(f"  ✅ {sucesso}/{len(filmes_para_atualizar)} filmes atualizados")
    return sucesso


def atualizar_episodios_supabase(episodios_para_atualizar):
    """Atualiza episódios existentes no Supabase (apenas se video_url estiver vazio)"""
    if not episodios_para_atualizar:
        return 0
    
    logger.info(f"\n📤 Processando {len(episodios_para_atualizar)} episódios com video_url vazio...")
    
    # Nota: Como estamos apenas marcando que o episódio existe (sem video_url),
    # não há dados para atualizar. Se precisar atualizar outros campos no futuro,
    # implementar aqui a lógica de PATCH
    
    # Por enquanto, apenas contabilizar como "já processados"
    logger.info(f"  ℹ️  {len(episodios_para_atualizar)} episódios existem mas sem video_url")
    logger.info(f"     (Aguardando video_url para atualização futura)")
    
    return len(episodios_para_atualizar)


def criar_episodios_lote_supabase(episodios, tamanho_lote=100):
    """Cria episódios no Supabase em lotes"""
    if not episodios:
        return 0
    
    total_episodios = len(episodios)
    logger.info(f"\n📤 FASE 4: Criando {total_episodios} episódios no Supabase (lotes de {tamanho_lote})...")
    
    sucesso_total = 0
    
    for i in range(0, total_episodios, tamanho_lote):
        lote = episodios[i:i + tamanho_lote]
        lote_num = (i // tamanho_lote) + 1
        total_lotes = (total_episodios + tamanho_lote - 1) // tamanho_lote
        
        try:
            headers = {
                "apikey": SUPABASE_APIKEY,
                "Authorization": f"Bearer {SUPABASE_APIKEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal"
            }
            
            response = requests.post(
                f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE_SERIES}",
                headers=headers,
                json=lote,
                timeout=30
            )
            
            if response.status_code in [200, 201, 204]:
                sucesso_total += len(lote)
                logger.info(f"  ✅ Lote {lote_num}/{total_lotes}: {len(lote)} episódios criados")
            else:
                logger.error(f"  ❌ Erro no lote {lote_num}: {response.status_code}")
                logger.error(f"     {response.text}")
            
            # Pausa entre lotes
            time.sleep(0.5)
            
        except Exception as e:
            logger.error(f"  ❌ Erro ao criar lote {lote_num}: {e}")
    
    logger.info(f"\n  ✅ Total: {sucesso_total}/{total_episodios} episódios criados")
    return sucesso_total


def sincronizar_json_com_supabase(processar_filmes=True, processar_series=True):
    """Sincroniza todos os registros do JSON com o Supabase"""
    logger.info("=" * 70)
    logger.info("SINCRONIZAÇÃO JSON → SUPABASE (OTIMIZADO COM BATCH)")
    logger.info("=" * 70)
    
    stats = {
        'filmes': {'criados': 0, 'atualizados': 0, 'ignorados': 0},
        'series': {'criados': 0, 'atualizados': 0, 'ignorados': 0, 'erros': 0}
    }
    
    # Processar filmes
    if processar_filmes:
        registros_filmes = carregar_json(JSON_FILE_FILMES)
        
        if registros_filmes:
            logger.info(f"\n{'='*70}")
            logger.info(f"PROCESSANDO FILMES: {len(registros_filmes)} registros")
            logger.info(f"{'='*70}")
            
            # BUSCAR TODOS OS FILMES DO SUPABASE (PAGINADO)
            filmes_existentes = buscar_todos_filmes_supabase()
            
            # Verificar se houve erro crítico na busca
            if filmes_existentes is None:
                logger.error("\n❌ ERRO CRÍTICO: Não foi possível buscar filmes existentes do Supabase")
                logger.error("   Abortando processamento de filmes para evitar duplicatas")
                logger.error("   Verifique sua conexão com a internet e tente novamente")
            else:
                # Preparar dados
                filmes_criar, filmes_atualizar, filmes_ignorar = preparar_dados_filmes(
                    registros_filmes, filmes_existentes
                )
                
                # Enviar ao Supabase
                stats['filmes']['criados'] = criar_filmes_lote_supabase(filmes_criar)
                stats['filmes']['atualizados'] = atualizar_filmes_supabase(filmes_atualizar)
                stats['filmes']['ignorados'] = len(filmes_ignorar)
        else:
            logger.warning("Nenhum filme encontrado no JSON")
    
    # Processar séries
    if processar_series:
        registros_series = carregar_json(JSON_FILE_SERIES)
        
        if registros_series:
            logger.info(f"\n{'='*70}")
            logger.info(f"PROCESSANDO SÉRIES: {len(registros_series)} registros")
            logger.info(f"{'='*70}")
            
            # FASE 1: Buscar todas as séries no TMDB em paralelo
            series_info, series_erro = buscar_todas_series_tmdb(registros_series, max_workers=5)
            
            if series_info:
                # FASE 2: Buscar todos os episódios existentes em paralelo
                episodios_por_serie = buscar_todos_episodios_supabase(series_info, max_workers=10)
                
                # FASE 3: Comparar e preparar dados
                episodios_criar, episodios_atualizar, episodios_ignorar = preparar_dados_series(
                    series_info, episodios_por_serie
                )
                
                # FASE 4: Enviar ao Supabase
                stats['series']['criados'] = criar_episodios_lote_supabase(episodios_criar)
                stats['series']['atualizados'] = atualizar_episodios_supabase(episodios_atualizar)
                stats['series']['ignorados'] = len(episodios_ignorar)
            
            stats['series']['erros'] = len(series_erro)
        else:
            logger.warning("Nenhuma série encontrada no JSON")
    
    # Relatório final
    logger.info("\n" + "=" * 70)
    logger.info("SINCRONIZAÇÃO CONCLUÍDA")
    logger.info("=" * 70)
    
    if processar_filmes:
        logger.info("\nFILMES:")
        logger.info(f"  Novos criados:       {stats['filmes']['criados']}")
        logger.info(f"  Atualizados:         {stats['filmes']['atualizados']}")
        logger.info(f"  Ignorados:           {stats['filmes']['ignorados']}")
    
    if processar_series:
        logger.info("\nSÉRIES (EPISÓDIOS):")
        logger.info(f"  Novos criados:       {stats['series']['criados']}")
        logger.info(f"  Atualizados:         {stats['series']['atualizados']}")
        logger.info(f"  Ignorados:           {stats['series']['ignorados']}")
        logger.info(f"  Erros:               {stats['series']['erros']}")
    
    logger.info("=" * 70)


def mostrar_menu():
    """Exibe o menu interativo e retorna a escolha do usuário"""
    print("\n" + "=" * 70)
    print("     SINCRONIZAÇÃO WAREZCDN → SUPABASE (BATCH PARALELO)")
    print("=" * 70)
    print("\nO que você deseja sincronizar?\n")
    print("  [1] Apenas FILMES")
    print("  [2] Apenas SÉRIES")
    print("  [3] FILMES e SÉRIES")
    print("  [0] Sair")
    print("\n" + "=" * 70)
    
    while True:
        try:
            escolha = input("\nDigite sua escolha [0-3]: ").strip()
            
            if escolha in ['0', '1', '2', '3']:
                return escolha
            else:
                print("❌ Opção inválida! Por favor, escolha entre 0 e 3.")
        except KeyboardInterrupt:
            print("\n\n⚠️  Operação cancelada pelo usuário.")
            return '0'
        except Exception as e:
            print(f"❌ Erro ao ler entrada: {e}")


if __name__ == "__main__":
    try:
        escolha = mostrar_menu()
        
        if escolha == '0':
            logger.info("Programa encerrado pelo usuário")
            exit(0)
        
        processar_filmes = escolha in ['1', '3']
        processar_series = escolha in ['2', '3']
        
        sincronizar_json_com_supabase(processar_filmes, processar_series)
        
    except KeyboardInterrupt:
        logger.info("\n\n⚠️  Sincronização interrompida pelo usuário")
    except Exception as e:
        logger.error(f"\n\n❌ Erro fatal: {e}")