import time
import os
import requests
from dotenv import load_dotenv
from extracao_url import extrair_url_video, limpar_driver_persistente

# Carregar variáveis de ambiente
load_dotenv()

# Configuração Supabase
SUPABASE_URL = "https://forfhjlkrqjpglfbiosd.supabase.co"
SUPABASE_APIKEY = os.getenv("SUPABASE_APIKEY")

# Configuração de tabelas
TABELAS = {
    'filmes': 'filmes_url_warezcdn',
    'series': 'series_url_warezcdn'
}

def escolher_tipo_conteudo():
    """Permite o usuário escolher entre filmes e séries."""
    print(f"\n{'='*50}")
    print("TIPO DE CONTEÚDO")
    print(f"{'='*50}")
    print("1 - Filmes")
    print("2 - Séries")
    print(f"{'='*50}\n")
    
    while True:
        try:
            escolha = input("Escolha o tipo de conteúdo (1 ou 2): ").strip()
            if escolha == '1':
                return 'filmes'
            elif escolha == '2':
                return 'series'
            else:
                print("❌ Escolha inválida! Digite 1 para Filmes ou 2 para Séries.")
        except Exception as e:
            print(f"❌ Erro: {e}")

def escolher_modo_driver():
    """Permite o usuário escolher o modo de operação do driver."""
    print(f"\n{'='*50}")
    print("MODO DE OPERAÇÃO DO NAVEGADOR")
    print(f"{'='*50}")
    print("1 - Driver Persistente (Recomendado)")
    print("    Mantém o navegador aberto, apenas alternando páginas")
    print("    Mais rápido e eficiente para múltiplas extrações")
    print("")
    print("2 - Driver Novo a Cada Extração")
    print("    Abre e fecha o navegador para cada URL")
    print("    Mais lento, mas isola cada extração")
    print(f"{'='*50}\n")
    
    while True:
        try:
            escolha = input("Escolha o modo (1 ou 2): ").strip()
            if escolha == '1':
                return True
            elif escolha == '2':
                return False
            else:
                print("❌ Escolha inválida! Digite 1 ou 2.")
        except Exception as e:
            print(f"❌ Erro: {e}")

def buscar_todos_registros_supabase(tipo_conteudo):
    """Busca todos os registros do Supabase onde dublado é nulo com paginação de 1000 em 1000."""
    tabela = TABELAS[tipo_conteudo]
    todos_registros = []
    offset = 0
    limite = 1000
    
    headers = {
        "apikey": SUPABASE_APIKEY,
        "Authorization": f"Bearer {SUPABASE_APIKEY}",
        "Content-Type": "application/json"
    }
    
    print(f"\n📄 Buscando registros de {tipo_conteudo} do Supabase (dublado=null)...")
    
    while True:
        try:
            # Define os campos de seleção baseado no tipo
            if tipo_conteudo == 'filmes':
                select_fields = "url,video_repro_url,dublado"
            else:  # series
                select_fields = "url,video_repro_url,dublado,temporada_numero,episodio_numero"
            
            params = {
                "select": select_fields,
                "dublado": "is.null",
                "offset": offset,
                "limit": limite
            }
            
            # Para séries, ordena por url, temporada e episódio para facilitar identificação
            if tipo_conteudo == 'series':
                params["order"] = "url.asc,temporada_numero.asc,episodio_numero.asc"
            
            response = requests.get(
                f"{SUPABASE_URL}/rest/v1/{tabela}",
                headers=headers,
                params=params,
                timeout=30
            )
            
            if response.status_code == 200:
                registros = response.json()
                
                if not registros:
                    # Não há mais registros
                    break
                
                todos_registros.extend(registros)
                print(f"  ✓ Carregados {len(todos_registros)} registros...")
                
                # Se retornou menos que o limite, chegou ao fim
                if len(registros) < limite:
                    break
                
                offset += limite
            else:
                print(f"❌ Erro ao buscar registros: {response.status_code}")
                break
                
        except Exception as e:
            print(f"❌ Erro ao buscar registros: {e}")
            break
    
    # Remove duplicatas para séries (mesma url + temporada + episódio)
    if tipo_conteudo == 'series':
        registros_unicos = []
        vistos = set()
        
        for reg in todos_registros:
            chave = (reg['url'], reg.get('temporada_numero'), reg.get('episodio_numero'))
            if chave not in vistos:
                vistos.add(chave)
                registros_unicos.append(reg)
        
        duplicatas = len(todos_registros) - len(registros_unicos)
        if duplicatas > 0:
            print(f"⚠️  Removidas {duplicatas} duplicatas (mesma URL + temporada + episódio)")
        
        todos_registros = registros_unicos
    
    print(f"✓ Total de registros únicos carregados: {len(todos_registros)}\n")
    return todos_registros

def atualizar_registro_supabase(tipo_conteudo, url_base, video_repro_url, dublado, temporada=None, episodio=None):
    """Atualiza um registro no Supabase na tabela correta."""
    tabela = TABELAS[tipo_conteudo]
    
    headers = {
        "apikey": SUPABASE_APIKEY,
        "Authorization": f"Bearer {SUPABASE_APIKEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }
    
    # Monta os dados de atualização
    dados_atualizacao = {
        "video_repro_url": video_repro_url,
        "dublado": dublado
    }
    
    # Monta os parâmetros de filtro baseado no tipo
    if tipo_conteudo == 'filmes':
        params = {"url": f"eq.{url_base}"}
    else:  # series
        params = {
            "url": f"eq.{url_base}",
            "temporada_numero": f"eq.{temporada}",
            "episodio_numero": f"eq.{episodio}"
        }
    
    try:
        response = requests.patch(
            f"{SUPABASE_URL}/rest/v1/{tabela}",
            headers=headers,
            params=params,
            json=dados_atualizacao,
            timeout=30
        )
        
        if response.status_code in [200, 204]:
            return True, None
        else:
            return False, f"Status {response.status_code}: {response.text}"
    
    except Exception as e:
        return False, str(e)

def obter_intervalo(total_itens):
    """Solicita ao usuário o intervalo de processamento."""
    print(f"\n{'='*50}")
    print(f"Total de itens na tabela: {total_itens}")
    print(f"{'='*50}\n")
    
    while True:
        try:
            inicio = int(input(f"Digite a posição inicial (1 a {total_itens}): "))
            if 1 <= inicio <= total_itens:
                break
            else:
                print(f"❌ Valor inválido! Digite um número entre 1 e {total_itens}")
        except ValueError:
            print("❌ Por favor, digite um número válido!")
    
    while True:
        try:
            fim = int(input(f"Digite a posição final ({inicio} a {total_itens}): "))
            if inicio <= fim <= total_itens:
                break
            else:
                print(f"❌ Valor inválido! Digite um número entre {inicio} e {total_itens}")
        except ValueError:
            print("❌ Por favor, digite um número válido!")
    
    return inicio, fim

def construir_url_serie(url_base, temporada, episodio):
    """Constrói a URL completa para um episódio de série."""
    # Remove barra final se existir
    url_base = url_base.rstrip('/')
    return f"{url_base}/{temporada}/{episodio}"

def processar_urls():
    """Processa as URLs no intervalo especificado."""
    # Escolhe o tipo de conteúdo
    tipo_conteudo = escolher_tipo_conteudo()
    
    # Escolhe o modo de operação do driver
    usar_driver_persistente = escolher_modo_driver()
    
    # Busca todos os registros do Supabase
    data = buscar_todos_registros_supabase(tipo_conteudo)
    
    if not data:
        print(f"❌ Nenhum registro de {tipo_conteudo} encontrado no Supabase!")
        return
    
    total_itens = len(data)
    
    # Obtém o intervalo do usuário
    inicio, fim = obter_intervalo(total_itens)
    
    # Converte para índice do array (subtrai 1 pois array começa em 0)
    indice_inicio = inicio - 1
    indice_fim = fim  # fim já está correto para slice
    
    # Seleciona o intervalo
    itens_selecionados = data[indice_inicio:indice_fim]
    
    modo_texto = "PERSISTENTE (reutiliza navegador)" if usar_driver_persistente else "NORMAL (abre/fecha navegador)"
    
    print(f"\n{'='*60}")
    print(f"Processando {tipo_conteudo} de {inicio} até {fim} ({len(itens_selecionados)} itens)")
    print(f"Tabela: {TABELAS[tipo_conteudo]}")
    print(f"Modo: {modo_texto}")
    print(f"{'='*60}\n")
    
    # Estatísticas
    stats = {
        'sucesso_cache': 0,
        'sucesso_extracao': 0,
        'pulados': 0,
        'erros': 0,
        'erros_atualizacao': 0,
        'total': len(itens_selecionados)
    }
    
    # ID do driver para modo persistente
    driver_id = "Main-Persistent"
    
    try:
        # Processa cada item no intervalo
        for idx, item in enumerate(itens_selecionados, start=inicio):
            url_base = item.get('url', 'URL não encontrada')
            
            # Para séries, constrói a URL completa com temporada e episódio
            if tipo_conteudo == 'series':
                temporada = item.get('temporada_numero', '')
                episodio = item.get('episodio_numero', '')
                url_extracao = construir_url_serie(url_base, temporada, episodio)
                print(f"\n[{idx}/{fim}] Série T{temporada}E{episodio}")
                print(f"  URL Base: {url_base[:60]}...")
                print(f"  URL Extração: {url_extracao[:80]}...")
            else:
                url_extracao = url_base
                temporada = None
                episodio = None
                print(f"\n[{idx}/{fim}] Processando filme: {url_extracao[:80]}...")
            
            try:
                # Chama extrair_url_video com o parâmetro de driver persistente
                resultado = extrair_url_video(
                    url_extracao, 
                    driver_id,
                    tipo='serie' if tipo_conteudo == 'series' else 'filme',
                    temporada=temporada,
                    episodio=episodio,
                    usar_driver_persistente=usar_driver_persistente
                )
                
                # Verifica se foi pulado (dublado=False)
                if resultado.get('skipped'):
                    reason = resultado.get('reason', 'Motivo não especificado')
                    print(f"⊘ PULADO: {reason}")
                    print(f"  Tempo: {resultado.get('extraction_time', 'N/A')}")
                    stats['pulados'] += 1
                    
                    # Atualiza o registro mesmo se pulado (dublado=False)
                    dublado = resultado.get('dublado', False)
                    sucesso, erro = atualizar_registro_supabase(
                        tipo_conteudo, url_base, "", dublado, temporada, episodio
                    )
                    
                    if sucesso:
                        print(f"  ✓ Registro atualizado na tabela {TABELAS[tipo_conteudo]}")
                    else:
                        print(f"  ✗ Erro ao atualizar: {erro}")
                        stats['erros_atualizacao'] += 1
                
                # Verifica se teve sucesso
                elif resultado.get('success'):
                    video_repro_url = resultado.get('video_url', '')
                    from_cache = resultado.get('from_cache', False)
                    extraction_time = resultado.get('extraction_time', 'N/A')
                    dublado = resultado.get('dublado', None)
                    
                    if from_cache:
                        print(f"✓ SUCESSO (Cache)")
                        stats['sucesso_cache'] += 1
                    else:
                        print(f"✓ SUCESSO (Extraído)")
                        stats['sucesso_extracao'] += 1
                    
                    print(f"  Video URL: {video_repro_url[:80]}...")
                    print(f"  Dublado: {dublado}")
                    print(f"  Tempo: {extraction_time}")
                    
                    # Atualiza o registro no Supabase na tabela correta
                    sucesso, erro = atualizar_registro_supabase(
                        tipo_conteudo, url_base, video_repro_url, dublado, temporada, episodio
                    )
                    
                    if sucesso:
                        print(f"  ✓ Registro atualizado na tabela {TABELAS[tipo_conteudo]}")
                    else:
                        print(f"  ✗ Erro ao atualizar: {erro}")
                        stats['erros_atualizacao'] += 1
                
                # Se não teve sucesso e não foi pulado
                else:
                    error = resultado.get('error', 'Erro não especificado')
                    dublado = resultado.get('dublado', None)
                    extraction_time = resultado.get('extraction_time', 'N/A')
                    
                    print(f"✗ ERRO: {error}")
                    print(f"  Dublado: {dublado}")
                    print(f"  Tempo: {extraction_time}")
                    stats['erros'] += 1
            
            except Exception as e:
                print(f"✗ EXCEÇÃO: {str(e)}")
                stats['erros'] += 1
            
            print("-" * 50)
            
            # Pequena pausa entre requisições para não sobrecarregar
            if idx < fim:
                time.sleep(1)
    
    finally:
        # IMPORTANTE: Limpar driver persistente ao final
        if usar_driver_persistente:
            print(f"\n🧹 Fechando navegador persistente...")
            limpar_driver_persistente(driver_id)
    
    # Exibe estatísticas finais
    print(f"\n{'='*60}")
    print(f"RELATÓRIO FINAL - {tipo_conteudo.upper()}")
    print(f"Tabela: {TABELAS[tipo_conteudo]}")
    print(f"Modo: {modo_texto}")
    print(f"{'='*60}")
    print(f"Total processado:      {stats['total']}")
    print(f"✓ Sucesso (Cache):     {stats['sucesso_cache']}")
    print(f"✓ Sucesso (Extraído):  {stats['sucesso_extracao']}")
    print(f"⊘ Pulados:             {stats['pulados']}")
    print(f"✗ Erros extração:      {stats['erros']}")
    print(f"✗ Erros atualização:   {stats['erros_atualizacao']}")
    print(f"{'='*60}")
    
    # Calcula taxa de sucesso
    total_sucesso = stats['sucesso_cache'] + stats['sucesso_extracao']
    taxa_sucesso = (total_sucesso / stats['total'] * 100) if stats['total'] > 0 else 0
    print(f"Taxa de sucesso: {taxa_sucesso:.1f}%")
    
    # Calcula economia de tempo (estimativa)
    if usar_driver_persistente and stats['sucesso_extracao'] > 0:
        # Estima-se que cada abertura/fechamento de navegador leva ~5-8 segundos
        tempo_economizado = (stats['sucesso_extracao'] + stats['pulados']) * 6  # média de 6 segundos
        minutos = tempo_economizado // 60
        segundos = tempo_economizado % 60
        print(f"⚡ Tempo economizado (estimado): {minutos}min {segundos}s")
    
    print(f"{'='*60}\n")

if __name__ == "__main__":
    if not SUPABASE_APIKEY:
        print("❌ Erro: SUPABASE_APIKEY não encontrada nas variáveis de ambiente!")
    else:
        try:
            processar_urls()
        except KeyboardInterrupt:
            print("\n\n❌ Processamento interrompido pelo usuário!")
            # Tentar limpar drivers ao interromper
            try:
                from extracao_url import limpar_todos_drivers
                print("🧹 Limpando drivers persistentes...")
                limpar_todos_drivers()
            except:
                pass
        except Exception as e:
            print(f"\n❌ Erro inesperado: {e}")
            import traceback
            traceback.print_exc()
            # Tentar limpar drivers em caso de erro
            try:
                from extracao_url import limpar_todos_drivers
                print("🧹 Limpando drivers persistentes...")
                limpar_todos_drivers()
            except:
                pass