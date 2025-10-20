import json
import os
import logging
import re
from dotenv import load_dotenv
import requests
import time

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


def detectar_tipo_conteudo(url):
    """Detecta se é filme ou série pela URL"""
    if '/serie/' in url:
        return 'serie'
    elif '/filme/' in url or '/embed/' in url:
        return 'filme'
    return None


def buscar_info_serie_tmdb(imdb_id):
    """Busca informações da série no TMDB usando o IMDb ID"""
    try:
        # Headers com Bearer token
        headers = {
            'Authorization': f'Bearer {TMDB_API_KEY}',
            'Content-Type': 'application/json;charset=utf-8'
        }
        
        # Passo 1: Buscar pelo IMDb ID para obter o TMDB ID
        url_find = f"{TMDB_BASE_URL}/find/{imdb_id}"
        params_find = {
            'external_source': 'imdb_id'
        }
        
        response_find = requests.get(url_find, headers=headers, params=params_find, timeout=10)
        
        if response_find.status_code != 200:
            logger.error(f"Erro ao buscar no TMDB (find): {response_find.status_code} - {response_find.text}")
            return None
        
        data_find = response_find.json()
        
        # Verificar se encontrou resultados de séries
        if not data_find.get('tv_results') or len(data_find['tv_results']) == 0:
            logger.warning(f"Nenhuma série encontrada no TMDB para {imdb_id}")
            return None
        
        serie = data_find['tv_results'][0]
        tmdb_id = serie['id']
        
        logger.info(f"  → TMDB ID: {tmdb_id}")
        
        # Passo 2: Buscar detalhes completos da série usando o TMDB ID
        url_detalhes = f"{TMDB_BASE_URL}/tv/{tmdb_id}"
        
        response_detalhes = requests.get(url_detalhes, headers=headers, timeout=10)
        
        if response_detalhes.status_code != 200:
            logger.error(f"Erro ao buscar detalhes no TMDB: {response_detalhes.status_code} - {response_detalhes.text}")
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
        total_temporadas = detalhes.get('number_of_seasons', len(temporadas))
        
        logger.info(f"  → Nome: {nome_serie}")
        logger.info(f"  → Total de temporadas: {total_temporadas}")
        
        return temporadas
        
    except requests.exceptions.Timeout:
        logger.error(f"Timeout ao buscar info no TMDB para {imdb_id}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro de conexão ao buscar info no TMDB: {e}")
        return None
    except Exception as e:
        logger.error(f"Erro inesperado ao buscar info no TMDB: {e}")
        return None


def carregar_json(arquivo):
    """Carrega o arquivo JSON com as URLs"""
    try:
        if not os.path.exists(arquivo):
            logger.error(f"Arquivo JSON não encontrado: {arquivo}")
            return []
        
        with open(arquivo, 'r', encoding='utf-8') as f:
            data = json.load(f)
            logger.info(f"JSON carregado com {len(data)} registros de {os.path.basename(arquivo)}")
            return data
    except Exception as e:
        logger.error(f"Erro ao carregar JSON: {e}")
        return []


def verificar_existe_filme_supabase(url_pagina):
    """Verifica se o filme existe no Supabase"""
    try:
        headers = {
            "apikey": SUPABASE_APIKEY,
            "Authorization": f"Bearer {SUPABASE_APIKEY}",
            "Content-Type": "application/json"
        }
        
        params = {
            "select": "url,video_repro_url,dublado",
            "url": f"eq.{url_pagina}"
        }
        
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE_FILMES}",
            headers=headers,
            params=params,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                return data[0]
            return None
        else:
            logger.error(f"Erro ao verificar existência: {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"Erro ao verificar existência: {e}")
        return None


def verificar_existe_episodio_supabase(video_url, temporada, episodio):
    """Verifica se o episódio existe no Supabase"""
    try:
        headers = {
            "apikey": SUPABASE_APIKEY,
            "Authorization": f"Bearer {SUPABASE_APIKEY}",
            "Content-Type": "application/json"
        }
        
        params = {
            "select": "video_url,temporada_numero,episodio_numero",
            "video_url": f"eq.{video_url}",
            "temporada_numero": f"eq.{temporada}",
            "episodio_numero": f"eq.{episodio}"
        }
        
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE_SERIES}",
            headers=headers,
            params=params,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            return len(data) > 0
        else:
            logger.error(f"Erro ao verificar episódio: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"Erro ao verificar episódio: {e}")
        return False


def atualizar_registro_filme_supabase(url_pagina, video_repro_url, dublado, registro_existente):
    """Atualiza um registro de filme existente no Supabase"""
    try:
        headers = {
            "apikey": SUPABASE_APIKEY,
            "Authorization": f"Bearer {SUPABASE_APIKEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal"
        }
        
        params = {
            "url": f"eq.{url_pagina}"
        }
        
        data = {}
        campos_atualizados = []
        
        video_url_bd = registro_existente.get('video_repro_url')
        if not video_url_bd and video_repro_url:
            data['video_repro_url'] = video_repro_url
            campos_atualizados.append('video_repro_url')
        
        dublado_bd = registro_existente.get('dublado')
        if dublado_bd is None and dublado is not None:
            data['dublado'] = dublado
            campos_atualizados.append('dublado')
        
        if not data:
            return False
        
        response = requests.patch(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE_FILMES}",
            headers=headers,
            params=params,
            json=data,
            timeout=10
        )
        
        if response.status_code in [200, 204]:
            logger.info(f"✓ Filme atualizado ({', '.join(campos_atualizados)}): {url_pagina[:50]}...")
            return True
        else:
            logger.error(f"✗ Erro ao atualizar: {response.status_code} - {response.text}")
            return False
        
    except Exception as e:
        logger.error(f"✗ Erro ao atualizar filme: {e}")
        return False


def criar_registro_filme_supabase(url_pagina, video_repro_url, dublado):
    """Cria um novo registro de filme no Supabase"""
    try:
        headers = {
            "apikey": SUPABASE_APIKEY,
            "Authorization": f"Bearer {SUPABASE_APIKEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal"
        }
        
        data = {
            "url": url_pagina,
            "video_repro_url": video_repro_url,
            "dublado": dublado
        }
        
        response = requests.post(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE_FILMES}",
            headers=headers,
            json=data,
            timeout=10
        )
        
        if response.status_code in [200, 201, 204]:
            logger.info(f"✓ Novo filme criado: {url_pagina[:50]}...")
            return True
        else:
            logger.error(f"✗ Erro ao criar filme: {response.status_code} - {response.text}")
            return False
        
    except Exception as e:
        logger.error(f"✗ Erro ao criar filme: {e}")
        return False


def criar_episodio_supabase(video_url, temporada, episodio):
    """Cria um registro de episódio no Supabase"""
    try:
        headers = {
            "apikey": SUPABASE_APIKEY,
            "Authorization": f"Bearer {SUPABASE_APIKEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal"
        }
        
        data = {
            "video_url": video_url,
            "temporada_numero": temporada,
            "episodio_numero": episodio
        }
        
        response = requests.post(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE_SERIES}",
            headers=headers,
            json=data,
            timeout=10
        )
        
        if response.status_code in [200, 201, 204]:
            return True
        else:
            logger.error(f"✗ Erro ao criar episódio S{temporada}E{episodio}: {response.status_code}")
            return False
        
    except Exception as e:
        logger.error(f"✗ Erro ao criar episódio S{temporada}E{episodio}: {e}")
        return False


def processar_filme(item, url):
    """Processa um filme"""
    video_repro_url = item.get('video_repro_url')
    dublado = item.get('dublado')
    
    if not video_repro_url:
        video_repro_url = None
    if dublado is None or dublado == '':
        dublado = None
    
    registro_existente = verificar_existe_filme_supabase(url)
    
    if registro_existente:
        video_url_bd = registro_existente.get('video_repro_url')
        dublado_bd = registro_existente.get('dublado')
        
        precisa_atualizar = False
        campos_para_atualizar = []
        
        if not video_url_bd and video_repro_url:
            precisa_atualizar = True
            campos_para_atualizar.append('video_repro_url')
        
        if dublado_bd is None and dublado is not None:
            precisa_atualizar = True
            campos_para_atualizar.append('dublado')
        
        if precisa_atualizar:
            logger.info(f"  → Campos vazios no BD: {', '.join(campos_para_atualizar)}")
            sucesso = atualizar_registro_filme_supabase(url, video_repro_url, dublado, registro_existente)
            return ('atualizados' if sucesso else 'erros', sucesso)
        else:
            logger.info(f"  → Filme já está completo - ignorado")
            return ('ignorados', True)
    else:
        sucesso = criar_registro_filme_supabase(url, video_repro_url, dublado)
        return ('criados' if sucesso else 'erros', sucesso)


def processar_serie(item, url):
    """Processa uma série"""
    imdb_id = extrair_imdb_id(url)
    
    if not imdb_id:
        logger.warning(f"  → Não foi possível extrair IMDb ID da URL")
        return ('erros', False)
    
    logger.info(f"  → IMDb ID: {imdb_id}")
    
    # Buscar informações no TMDB
    temporadas = buscar_info_serie_tmdb(imdb_id)
    
    if not temporadas:
        logger.warning(f"  → Não foi possível obter informações do TMDB")
        return ('erros', False)
    
    # Criar registros para cada episódio
    episodios_criados = 0
    episodios_existentes = 0
    episodios_erro = 0
    
    for temp_info in temporadas:
        temporada = temp_info['numero']
        total_episodios = temp_info['episodios']
        
        logger.info(f"  → Processando Temporada {temporada} ({total_episodios} episódios)...")
        
        for episodio in range(1, total_episodios + 1):
            existe = verificar_existe_episodio_supabase(url, temporada, episodio)
            
            if existe:
                episodios_existentes += 1
            else:
                if criar_episodio_supabase(url, temporada, episodio):
                    episodios_criados += 1
                else:
                    episodios_erro += 1
            
            # Pequena pausa para não sobrecarregar a API
            time.sleep(0.05)
    
    total_episodios = sum(t['episodios'] for t in temporadas)
    logger.info(f"  → Episódios: {episodios_criados} criados, {episodios_existentes} já existiam, {episodios_erro} erros")
    
    if episodios_criados > 0:
        return ('criados', True)
    elif episodios_existentes == total_episodios:
        return ('ignorados', True)
    else:
        return ('erros', False)


def sincronizar_json_com_supabase(processar_filmes=True, processar_series=True):
    """Sincroniza todos os registros do JSON com o Supabase"""
    logger.info("=" * 70)
    logger.info("INICIANDO SINCRONIZAÇÃO JSON → SUPABASE")
    logger.info("=" * 70)
    
    stats = {
        'filmes': {'criados': 0, 'atualizados': 0, 'ignorados': 0, 'erros': 0},
        'series': {'criados': 0, 'atualizados': 0, 'ignorados': 0, 'erros': 0}
    }
    
    # Processar filmes
    if processar_filmes:
        registros_filmes = carregar_json(JSON_FILE_FILMES)
        
        if registros_filmes:
            total_filmes = len(registros_filmes)
            logger.info(f"\n{'='*70}")
            logger.info(f"PROCESSANDO FILMES: {total_filmes} registros")
            logger.info(f"{'='*70}\n")
            
            for i, item in enumerate(registros_filmes, 1):
                url = item.get('url')
                
                if not url:
                    logger.warning(f"[FILME {i}/{total_filmes}] Registro sem URL - ignorado")
                    stats['filmes']['erros'] += 1
                    continue
                
                logger.info(f"[FILME {i}/{total_filmes}] Processando: {url[:60]}...")
                
                chave_stat, sucesso = processar_filme(item, url)
                stats['filmes'][chave_stat] += 1
                
                if i < total_filmes:
                    time.sleep(0.1)
        else:
            logger.warning("Nenhum filme encontrado no JSON")
    
    # Processar séries
    if processar_series:
        registros_series = carregar_json(JSON_FILE_SERIES)
        
        if registros_series:
            total_series = len(registros_series)
            logger.info(f"\n{'='*70}")
            logger.info(f"PROCESSANDO SÉRIES: {total_series} registros")
            logger.info(f"{'='*70}\n")
            
            for i, item in enumerate(registros_series, 1):
                url = item.get('url')
                
                if not url:
                    logger.warning(f"[SÉRIE {i}/{total_series}] Registro sem URL - ignorado")
                    stats['series']['erros'] += 1
                    continue
                
                logger.info(f"[SÉRIE {i}/{total_series}] Processando: {url[:60]}...")
                
                chave_stat, sucesso = processar_serie(item, url)
                stats['series'][chave_stat] += 1
                
                if i < total_series:
                    time.sleep(0.1)
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
        logger.info(f"  Erros:               {stats['filmes']['erros']}")
    
    if processar_series:
        logger.info("\nSÉRIES:")
        logger.info(f"  Novas criadas:       {stats['series']['criados']}")
        logger.info(f"  Atualizadas:         {stats['series']['atualizados']}")
        logger.info(f"  Ignoradas:           {stats['series']['ignorados']}")
        logger.info(f"  Erros:               {stats['series']['erros']}")
    
    logger.info("=" * 70)


def mostrar_menu():
    """Exibe o menu interativo e retorna a escolha do usuário"""
    print("\n" + "=" * 70)
    print("     SINCRONIZAÇÃO WAREZCDN → SUPABASE")
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