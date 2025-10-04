# import time
# import logging
# import re
# import os
# import json
# from urllib.parse import urlparse
# from pathlib import Path
# from flask import Flask, request, jsonify
# from flask_cors import CORS
# import uuid
# import requests
# from extracao_url import extrair_url_video, UBLOCK_XPI

# import threading
# from queue import Queue

# # Configurar logging
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# logger = logging.getLogger(__name__)

# # Desabilitar logs excessivos
# logging.getLogger('WDM').setLevel(logging.ERROR)
# logging.getLogger('urllib3').setLevel(logging.ERROR)

# app = Flask(__name__)
# CORS(app)

# # DiretÃ³rios
# DOWNLOADS_DIR = os.path.join(os.getcwd(), 'downloads')
# URLS_FILE = 'filmes_warezcdn_url.json'

# # VariÃ¡veis dinÃ¢micas (serÃ£o definidas pelo usuÃ¡rio)
# NUM_FILMES = 2  # PadrÃ£o
# MAX_DOWNLOADS_SIMULTANEOS = 2  # PadrÃ£o

# # Criar diretÃ³rio de downloads
# if not os.path.exists(DOWNLOADS_DIR):
#     os.makedirs(DOWNLOADS_DIR)
#     logger.info(f"DiretÃ³rio de downloads criado: {DOWNLOADS_DIR}")

# def load_urls_from_file(num_filmes):
#     """Carrega URLs do arquivo JSON"""
#     try:
#         if not os.path.exists(URLS_FILE):
#             logger.error(f"Arquivo {URLS_FILE} nÃ£o encontrado")
#             return None
        
#         with open(URLS_FILE, 'r', encoding='utf-8') as f:
#             data = json.load(f)
        
#         urls = data.get('urls', [])
#         # Retornar todas as URLs disponÃ­veis para processar atÃ© conseguir N downloads novos
#         return urls
        
#     except Exception as e:
#         logger.error(f"Erro ao carregar arquivo de URLs: {e}")
#         return None

# def parse_url_info(url):
#     """Extrai informaÃ§Ãµes da URL (tipo, id, temporada, episÃ³dio)"""
#     try:
#         # PadrÃ£o para filmes: https://embed.warezcdn.cc/filme/{id}
#         movie_pattern = r'https?://(?:embed\.)?warezcdn\.cc/filme/([^/]+)'
#         # PadrÃ£o para sÃ©ries: https://embed.warezcdn.cc/serie/{id}/{temporada}/{episÃ³dio}
#         tv_pattern = r'https?://(?:embed\.)?warezcdn\.cc/serie/([^/]+)/(\d+)/(\d+)'
        
#         # Tentar match com sÃ©rie primeiro
#         tv_match = re.match(tv_pattern, url)
#         if tv_match:
#             return {
#                 'type': 'tv',
#                 'id': tv_match.group(1),
#                 'season': tv_match.group(2),
#                 'episode': tv_match.group(3)
#             }
        
#         # Tentar match com filme
#         movie_match = re.match(movie_pattern, url)
#         if movie_match:
#             return {
#                 'type': 'movie',
#                 'id': movie_match.group(1)
#             }
        
#         return None
        
#     except Exception as e:
#         logger.error(f"Erro ao fazer parse da URL: {e}")
#         return None

# def get_download_path(url_info):
#     """Define o caminho de download baseado nas informaÃ§Ãµes da URL"""
#     if not url_info:
#         return None
    
#     if url_info['type'] == 'movie':
#         # downloads/filmes/{id}.mp4
#         folder = os.path.join(DOWNLOADS_DIR, 'filmes')
#         filename = f"{url_info['id']}.mp4"
        
#     elif url_info['type'] == 'tv':
#         # downloads/tv/{id}/{season}/{id}-{season}-{episode}.mp4
#         folder = os.path.join(DOWNLOADS_DIR, 'tv', url_info['id'], url_info['season'])
#         filename = f"{url_info['id']}-{url_info['season']}-{url_info['episode']}.mp4"
    
#     else:
#         return None
    
#     # Criar pasta se nÃ£o existir
#     os.makedirs(folder, exist_ok=True)
    
#     return {
#         'folder': folder,
#         'filename': filename,
#         'filepath': os.path.join(folder, filename)
#     }

# def cleanup_failed_download(filepath, driver_id):
#     """Remove arquivo em caso de falha"""
#     try:
#         if os.path.exists(filepath):
#             os.remove(filepath)
#             logger.info(f"[{driver_id}] Arquivo removido apÃ³s falha: {filepath}")
#             return True
#     except Exception as e:
#         logger.error(f"[{driver_id}] Erro ao remover arquivo: {e}")
#     return False

# def download_video(video_url, driver_id, filepath):
#     """Faz download do vÃ­deo usando requests"""
#     temp_filepath = f"{filepath}.tmp"
    
#     try:
#         logger.info(f"[{driver_id}] Iniciando download: {video_url[:80]}...")
        
#         # Headers para simular navegador
#         headers = {
#             'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0',
#             'Accept': '*/*',
#             'Accept-Language': 'en-US,en;q=0.5',
#             'Referer': 'https://mixdrop.co/',
#             'Origin': 'https://mixdrop.co'
#         }
        
#         # Stream download para arquivos grandes
#         response = requests.get(video_url, headers=headers, stream=True, timeout=60)
#         response.raise_for_status()
        
#         total_size = int(response.headers.get('content-length', 0))
#         logger.info(f"[{driver_id}] Tamanho do arquivo: {total_size / (1024*1024):.2f} MB")
        
#         downloaded_size = 0
#         chunk_size = 1024 * 1024  # 1MB chunks
        
#         with open(temp_filepath, 'wb') as f:
#             for chunk in response.iter_content(chunk_size=chunk_size):
#                 if chunk:
#                     f.write(chunk)
#                     downloaded_size += len(chunk)
                    
#                     # Log de progresso a cada 10MB
#                     if downloaded_size % (10 * 1024 * 1024) < chunk_size:
#                         progress = (downloaded_size / total_size * 100) if total_size > 0 else 0
#                         logger.info(f"[{driver_id}] Progresso: {progress:.1f}% ({downloaded_size/(1024*1024):.1f}MB)")
        
#         # Renomear arquivo temporÃ¡rio para final
#         os.rename(temp_filepath, filepath)
        
#         logger.info(f"[{driver_id}] Download concluÃ­do: {filepath}")
#         return {
#             'success': True,
#             'filepath': filepath,
#             'size_mb': downloaded_size / (1024 * 1024)
#         }
        
#     except Exception as e:
#         logger.error(f"[{driver_id}] Erro no download: {e}")
        
#         # Remover arquivo temporÃ¡rio se existir
#         if os.path.exists(temp_filepath):
#             try:
#                 os.remove(temp_filepath)
#                 logger.info(f"[{driver_id}] Arquivo temporÃ¡rio removido: {temp_filepath}")
#             except Exception as remove_error:
#                 logger.error(f"[{driver_id}] Erro ao remover arquivo temporÃ¡rio: {remove_error}")
        
#         return {
#             'success': False,
#             'error': str(e)
#         }

# def extract_video_url(url, driver_id):
#     """Extrai apenas a URL do vÃ­deo"""
#     try:
#         logger.info(f"[{driver_id}] Extraindo URL do vÃ­deo: {url}")
#         extraction_result = extrair_url_video(url, driver_id)
        
#         if not extraction_result.get('success'):
#             logger.error(f"[{driver_id}] Falha na extraÃ§Ã£o: {extraction_result.get('error')}")
#             return {
#                 'success': False,
#                 'error': extraction_result.get('error', 'Erro na extraÃ§Ã£o'),
#                 'url': url
#             }
        
#         video_url = extraction_result['video_url']
#         logger.info(f"[{driver_id}] URL extraÃ­da com sucesso: {video_url[:80]}...")
        
#         return {
#             'success': True,
#             'url': url,
#             'video_url': video_url,
#             'extraction_time': extraction_result.get('extraction_time', 'N/A')
#         }
        
#     except Exception as e:
#         logger.error(f"[{driver_id}] Erro durante extraÃ§Ã£o: {e}")
#         return {
#             'success': False,
#             'url': url,
#             'error': str(e)
#         }

# def download_video_thread(video_url, driver_id, filepath, results_queue):
#     """Faz download do vÃ­deo em thread separada"""
#     result = download_video(video_url, driver_id, filepath)
#     result['driver_id'] = driver_id
#     results_queue.put(result)

# def download_videos_parallel(extraction_results, download_infos, max_simultaneos):
#     """Faz download de mÃºltiplos vÃ­deos em paralelo com limite de simultaneidade"""
#     results_queue = Queue()
#     all_results = []
    
#     # Filtrar apenas extraÃ§Ãµes bem-sucedidas
#     valid_extractions = [(i, e) for i, e in enumerate(extraction_results) if e.get('success')]
    
#     logger.info(f"Iniciando downloads com limite de {max_simultaneos} simultÃ¢neos...")
#     logger.info(f"Total de vÃ­deos para download: {len(valid_extractions)}")
    
#     # Processar em lotes de acordo com o limite
#     for batch_start in range(0, len(valid_extractions), max_simultaneos):
#         batch_end = min(batch_start + max_simultaneos, len(valid_extractions))
#         batch = valid_extractions[batch_start:batch_end]
        
#         logger.info(f"\n{'='*60}")
#         logger.info(f"LOTE {batch_start//max_simultaneos + 1}: Baixando {len(batch)} vÃ­deos simultÃ¢neos")
#         logger.info(f"{'='*60}")
        
#         threads = []
        
#         for idx, extraction in batch:
#             video_url = extraction['video_url']
#             driver_id = extraction['driver_id']
#             filepath = download_infos[idx]['filepath']
            
#             # Criar thread para download
#             thread = threading.Thread(
#                 target=download_video_thread,
#                 args=(video_url, driver_id, filepath, results_queue)
#             )
#             thread.start()
#             threads.append(thread)
        
#         # Aguardar todas as threads do lote terminarem
#         for thread in threads:
#             thread.join()
        
#         # Coletar resultados do lote
#         batch_results = []
#         while not results_queue.empty():
#             batch_results.append(results_queue.get())
#         all_results.extend(batch_results)
        
#         logger.info(f"Lote {batch_start//max_simultaneos + 1} concluÃ­do: {len(batch_results)} downloads finalizados")
    
#     logger.info(f"\nTodos os {len(all_results)} downloads concluÃ­dos")
#     return all_results

# @app.route('/', methods=['GET'])
# def index():
#     """PÃ¡gina inicial"""
#     ublock_status = "Instalado" if os.path.exists(UBLOCK_XPI) else "NÃ£o instalado"
#     urls_file_exists = os.path.exists(URLS_FILE)
    
#     return jsonify({
#         'service': 'API de Download Warezcdn + Mixdrop',
#         'version': '8.1 - Terminal Only',
#         'provider': 'Warezcdn (Mixdrop)',
#         'ublock_origin': ublock_status,
#         'downloads_dir': DOWNLOADS_DIR,
#         'urls_file': URLS_FILE,
#         'urls_file_exists': urls_file_exists,
#         'config': {
#             'num_filmes': NUM_FILMES,
#             'max_downloads_simultaneos': MAX_DOWNLOADS_SIMULTANEOS
#         },
#         'architecture': 'Processamento via terminal + downloads paralelos controlados',
#         'download_structure': {
#             'movie': 'downloads/filmes/{id}/{id}.mp4',
#             'tv': 'downloads/tv/{id}/{season}/{id}-{season}-{episode}.mp4'
#         },
#         'note': 'Configure os downloads atravÃ©s do terminal ao iniciar o programa'
#     })

# def processar_downloads_terminal():
#     """Processa downloads diretamente pelo terminal"""
#     start_time = time.time()
#     request_id = str(uuid.uuid4())[:8]
    
#     try:
#         logger.info(f"[{request_id}] Iniciando processamento de URLs do arquivo {URLS_FILE}")
#         logger.info(f"[{request_id}] ConfiguraÃ§Ã£o: {NUM_FILMES} filmes, {MAX_DOWNLOADS_SIMULTANEOS} downloads simultÃ¢neos")
        
#         # Carregar URLs do arquivo
#         urls = load_urls_from_file(NUM_FILMES)
        
#         if urls is None:
#             print(f"\nâŒ Erro: NÃ£o foi possÃ­vel carregar o arquivo {URLS_FILE}")
#             return
        
#         if len(urls) == 0:
#             print("\nâŒ Erro: Nenhuma URL encontrada no arquivo")
#             return
        
#         logger.info(f"[{request_id}] {len(urls)} URLs carregadas do arquivo")
        
#         # FASE 1: Extrair todas as URLs sequencialmente
#         print("\n" + "="*60)
#         print(f"FASE 1: EXTRAÃ‡ÃƒO DE URLs")
#         print("="*60)
#         extraction_results = []
#         download_infos = []
#         downloads_needed = 0  # Contador de downloads necessÃ¡rios
        
#         for i, url in enumerate(urls, 1):
#             # Parar se jÃ¡ conseguimos o nÃºmero de downloads solicitados
#             if downloads_needed >= NUM_FILMES:
#                 print(f"\nâœ“ Meta de {NUM_FILMES} downloads atingida. Parando processamento.")
#                 break
                
#             print(f"\n[{i}/{len(urls)}] Extraindo: {url}")
            
#             # Parse da URL
#             url_info = parse_url_info(url)
#             if not url_info:
#                 extraction_results.append({
#                     'success': False,
#                     'url': url,
#                     'error': 'Formato de URL invÃ¡lido'
#                 })
#                 print(f"  âŒ Formato de URL invÃ¡lido")
#                 continue
            
#             # Definir caminho de download
#             download_path_info = get_download_path(url_info)
#             if not download_path_info:
#                 extraction_results.append({
#                     'success': False,
#                     'url': url,
#                     'error': 'NÃ£o foi possÃ­vel determinar o caminho de download'
#                 })
#                 print(f"  âŒ Erro ao determinar caminho de download")
#                 continue
            
#             # Verificar se o arquivo jÃ¡ existe
#             filepath = download_path_info['filepath']
#             if os.path.exists(filepath):
#                 file_size = os.path.getsize(filepath)
#                 size_mb = file_size / (1024 * 1024)
#                 extraction_results.append({
#                     'success': True,
#                     'url': url,
#                     'already_exists': True,
#                     'filepath': filepath,
#                     'size_mb': size_mb,
#                     'url_info': url_info
#                 })
#                 print(f"  â­ï¸  Arquivo jÃ¡ existe ({size_mb:.2f} MB) - nÃ£o conta na meta")
#                 continue
            
#             # Extrair URL do vÃ­deo
#             session_id = str(uuid.uuid4())[:8]
#             extraction = extract_video_url(url, session_id)
#             extraction['url_info'] = url_info
#             extraction['driver_id'] = session_id
#             extraction_results.append(extraction)
#             download_infos.append(download_path_info)
            
#             if extraction.get('success'):
#                 downloads_needed += 1
#                 print(f"  âœ“ URL extraÃ­da com sucesso ({downloads_needed}/{NUM_FILMES})")
#             else:
#                 print(f"  âŒ Falha na extraÃ§Ã£o: {extraction.get('error')}")
            
#             # Pequena pausa entre extraÃ§Ãµes
#             if i < len(urls):
#                 time.sleep(1)
        
#         extraction_time = time.time() - start_time
#         print(f"\nâœ“ Fase 1 concluÃ­da em {extraction_time:.2f}s")
        
#         # FASE 2: Fazer download dos vÃ­deos em paralelo
#         print("\n" + "="*60)
#         print(f"FASE 2: DOWNLOAD DE VÃDEOS")
#         print("="*60)
        
#         # Filtrar apenas extraÃ§Ãµes bem-sucedidas que precisam de download
#         videos_to_download = [e for e in extraction_results if e.get('success') and not e.get('already_exists')]
#         download_infos_filtered = [download_infos[i] for i, e in enumerate(extraction_results) if e.get('success') and not e.get('already_exists') and i < len(download_infos)]
        
#         if videos_to_download:
#             download_results = download_videos_parallel(videos_to_download, download_infos_filtered, MAX_DOWNLOADS_SIMULTANEOS)
            
#             # Combinar resultados
#             final_results = []
#             download_idx = 0
            
#             for extraction in extraction_results:
#                 if extraction.get('already_exists'):
#                     final_results.append({
#                         'success': True,
#                         'url': extraction['url'],
#                         'already_exists': True,
#                         'filepath': extraction['filepath'],
#                         'size_mb': extraction['size_mb'],
#                         'url_info': extraction['url_info'],
#                         'message': 'Arquivo jÃ¡ existe'
#                     })
#                 elif not extraction.get('success'):
#                     final_results.append({
#                         'success': False,
#                         'url': extraction['url'],
#                         'error': extraction.get('error'),
#                         'phase': 'extraction'
#                     })
#                 else:
#                     download_result = download_results[download_idx] if download_idx < len(download_results) else None
#                     download_idx += 1
                    
#                     if download_result and download_result.get('success'):
#                         final_results.append({
#                             'success': True,
#                             'url': extraction['url'],
#                             'video_url': extraction['video_url'],
#                             'filepath': download_result['filepath'],
#                             'size_mb': download_result['size_mb'],
#                             'url_info': extraction['url_info'],
#                             'extraction_time': extraction.get('extraction_time'),
#                             'message': 'Download concluÃ­do'
#                         })
#                     else:
#                         final_results.append({
#                             'success': False,
#                             'url': extraction['url'],
#                             'error': download_result.get('error') if download_result else 'Erro no download',
#                             'phase': 'download'
#                         })
#         else:
#             final_results = extraction_results
        
#         # Calcular e exibir estatÃ­sticas
#         total_time = time.time() - start_time
#         successful = sum(1 for r in final_results if r.get('success'))
#         failed = len(final_results) - successful
#         already_existed = sum(1 for r in final_results if r.get('already_exists'))
#         downloaded = successful - already_existed
        
#         print("\n" + "="*60)
#         print("ESTATÃSTICAS FINAIS")
#         print("="*60)
#         print(f"Total de URLs processadas: {len(extraction_results)}")
#         print(f"âœ“ Sucessos: {successful}")
#         print(f"  - JÃ¡ existiam: {already_existed}")
#         print(f"  - Baixados agora: {downloaded}")
#         print(f"âœ— Falhas: {failed}")
#         print(f"Tempo de extraÃ§Ã£o: {extraction_time:.2f}s")
#         print(f"Tempo total: {total_time:.2f}s")
#         print("="*60 + "\n")
        
#         # Listar erros se houver
#         if failed > 0:
#             print("DETALHES DOS ERROS:")
#             print("-" * 60)
#             for i, result in enumerate(final_results, 1):
#                 if not result.get('success'):
#                     print(f"{i}. {result.get('url')}")
#                     print(f"   Erro: {result.get('error')}")
#                     print(f"   Fase: {result.get('phase', 'N/A')}")
#             print("-" * 60 + "\n")
        
#     except Exception as e:
#         elapsed_time = time.time() - start_time
#         logger.error(f"[{request_id}] Erro inesperado: {str(e)}")
#         print(f"\nâŒ Erro inesperado: {str(e)}")

# def configurar_parametros():
#     """Terminal interativo para configurar parÃ¢metros"""
#     global NUM_FILMES, MAX_DOWNLOADS_SIMULTANEOS
    
#     print("\n" + "="*60)
#     print("CONFIGURAÃ‡ÃƒO DE DOWNLOAD")
#     print("="*60)
    
#     # Configurar nÃºmero de filmes
#     while True:
#         try:
#             resposta = input(f"\nQuantos filmes deseja baixar? [padrÃ£o: {NUM_FILMES}]: ").strip()
#             if resposta == "":
#                 break
#             num = int(resposta)
#             if num > 0:
#                 NUM_FILMES = num
#                 break
#             else:
#                 print("âŒ Por favor, insira um nÃºmero maior que 0")
#         except ValueError:
#             print("âŒ Por favor, insira um nÃºmero vÃ¡lido")
    
#     # Configurar downloads simultÃ¢neos
#     while True:
#         try:
#             resposta = input(f"Quantos downloads simultÃ¢neos? [padrÃ£o: {MAX_DOWNLOADS_SIMULTANEOS}, mÃ¡x: 5]: ").strip()
#             if resposta == "":
#                 break
#             num = int(resposta)
#             if 1 <= num <= 5:
#                 MAX_DOWNLOADS_SIMULTANEOS = num
#                 break
#             else:
#                 print("âŒ Por favor, insira um nÃºmero entre 1 e 5")
#         except ValueError:
#             print("âŒ Por favor, insira um nÃºmero vÃ¡lido")
    
#     print("\n" + "="*60)
#     print("CONFIGURAÃ‡ÃƒO CONFIRMADA")
#     print("="*60)
#     print(f"âœ“ Filmes para baixar: {NUM_FILMES}")
#     print(f"âœ“ Downloads simultÃ¢neos: {MAX_DOWNLOADS_SIMULTANEOS}")
#     print("="*60 + "\n")
    
#     # Perguntar se deseja iniciar downloads
#     while True:
#         resposta = input("Deseja iniciar os downloads agora? (s/n): ").strip().lower()
#         if resposta in ['s', 'sim', 'y', 'yes']:
#             return True
#         elif resposta in ['n', 'nÃ£o', 'nao', 'no']:
#             return False
#         else:
#             print("âŒ Por favor, responda com 's' ou 'n'")

# if __name__ == "__main__":
#     print("\n" + "="*60)
#     print("API DE DOWNLOAD WAREZCDN + MIXDROP")
#     print("VersÃ£o 8.1 - Modo Terminal")
#     print("="*60)
    
#     # ConfiguraÃ§Ã£o interativa
#     iniciar_downloads = configurar_parametros()
    
#     if iniciar_downloads:
#         print("\nðŸš€ Iniciando processo de download...\n")
#         processar_downloads_terminal()
#         print("\nâœ… Processo concluÃ­do!")
#         print("\n" + "="*60)
#         print("O que deseja fazer agora?")
#         print("="*60)
#         print("1. Encerrar programa")
#         print("2. Iniciar servidor Flask (API)")
        
#         while True:
#             escolha = input("\nEscolha uma opÃ§Ã£o (1 ou 2): ").strip()
#             if escolha == "1":
#                 print("\nðŸ‘‹ Encerrando programa. AtÃ© logo!")
#                 exit(0)
#             elif escolha == "2":
#                 break
#             else:
#                 print("âŒ OpÃ§Ã£o invÃ¡lida. Digite 1 ou 2")
        
#         print("\n" + "="*60)
#         print("INICIANDO SERVIDOR FLASK")
#         print("="*60)
#         print(f"Arquivo de URLs: {URLS_FILE}")
#         print(f"ConfiguraÃ§Ã£o: {NUM_FILMES} filmes, {MAX_DOWNLOADS_SIMULTANEOS} downloads simultÃ¢neos")
#         print(f"DiretÃ³rio: {DOWNLOADS_DIR}")
#         print("\nEndpoint disponÃ­vel:")
#         print("  - GET / (informaÃ§Ãµes da API)")
#         print("\nServidor: http://0.0.0.0:5000")
#         print("Pressione Ctrl+C para encerrar")
#         print("="*60 + "\n")
#     else:
#         print("\nâ­ï¸  Downloads nÃ£o iniciados.")
#         print("\n" + "="*60)
#         print("INICIANDO SERVIDOR FLASK")
#         print("="*60)
#         print(f"Arquivo de URLs: {URLS_FILE}")
#         print(f"ConfiguraÃ§Ã£o: {NUM_FILMES} filmes, {MAX_DOWNLOADS_SIMULTANEOS} downloads simultÃ¢neos")
#         print(f"DiretÃ³rio: {DOWNLOADS_DIR}")
#         print("\nEndpoint disponÃ­vel:")
#         print("  - GET / (informaÃ§Ãµes da API)")
#         print("\nServidor: http://0.0.0.0:5000")
#         print("Pressione Ctrl+C para encerrar")
#         print("="*60 + "\n")
    
#     # Iniciar servidor Flask
#     app.run(
#         host='0.0.0.0',
#         port=5000,
#         debug=False,
#         threaded=True
#     )