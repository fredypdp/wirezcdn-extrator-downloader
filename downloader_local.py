import time
import logging
import re
import os
from urllib.parse import urlparse
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS
import uuid
import requests
from extracao_url import extrair_url_video, UBLOCK_XPI

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Desabilitar logs excessivos
logging.getLogger('WDM').setLevel(logging.ERROR)
logging.getLogger('urllib3').setLevel(logging.ERROR)

app = Flask(__name__)
CORS(app)

# Diretórios
DOWNLOADS_DIR = os.path.join(os.getcwd(), 'downloads')

# Criar diretório de downloads
if not os.path.exists(DOWNLOADS_DIR):
    os.makedirs(DOWNLOADS_DIR)
    logger.info(f"Diretório de downloads criado: {DOWNLOADS_DIR}")

def parse_url_info(url):
    """Extrai informações da URL (tipo, id, temporada, episódio)"""
    try:
        # Padrão para filmes: https://embed.warezcdn.cc/filme/{id}
        movie_pattern = r'https?://(?:embed\.)?warezcdn\.cc/filme/([^/]+)'
        # Padrão para séries: https://embed.warezcdn.cc/serie/{id}/{temporada}/{episódio}
        tv_pattern = r'https?://(?:embed\.)?warezcdn\.cc/serie/([^/]+)/(\d+)/(\d+)'
        
        # Tentar match com série primeiro
        tv_match = re.match(tv_pattern, url)
        if tv_match:
            return {
                'type': 'tv',
                'id': tv_match.group(1),
                'season': tv_match.group(2),
                'episode': tv_match.group(3)
            }
        
        # Tentar match com filme
        movie_match = re.match(movie_pattern, url)
        if movie_match:
            return {
                'type': 'movie',
                'id': movie_match.group(1)
            }
        
        return None
        
    except Exception as e:
        logger.error(f"Erro ao fazer parse da URL: {e}")
        return None

def get_download_path(url_info):
    """Define o caminho de download baseado nas informações da URL"""
    if not url_info:
        return None
    
    if url_info['type'] == 'movie':
        # downloads/filmes/{id}/{id}.mp4
        folder = os.path.join(DOWNLOADS_DIR, 'filmes', url_info['id'])
        filename = f"{url_info['id']}.mp4"
        
    elif url_info['type'] == 'tv':
        # downloads/tv/{id}/{season}/{episode}.mp4
        folder = os.path.join(DOWNLOADS_DIR, 'tv', url_info['id'], url_info['season'])
        filename = f"{url_info['episode']}.mp4"
    
    else:
        return None
    
    # Criar pasta se não existir
    os.makedirs(folder, exist_ok=True)
    
    return {
        'folder': folder,
        'filename': filename,
        'filepath': os.path.join(folder, filename)
    }

def is_valid_warezcdn_url(url):
    """Valida URL do Warezcdn"""
    try:
        parsed = urlparse(url)
        return 'warezcdn.cc' in parsed.netloc.lower() or 'embed.warezcdn.cc' in parsed.netloc.lower()
    except:
        return False

def cleanup_failed_download(filepath, driver_id):
    """Remove arquivo em caso de falha"""
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            logger.info(f"[{driver_id}] Arquivo removido após falha: {filepath}")
            return True
    except Exception as e:
        logger.error(f"[{driver_id}] Erro ao remover arquivo: {e}")
    return False

def download_video(video_url, driver_id, filepath):
    """Faz download do vídeo usando requests"""
    temp_filepath = f"{filepath}.tmp"
    
    try:
        logger.info(f"[{driver_id}] Iniciando download: {video_url[:80]}...")
        
        # Headers para simular navegador
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://mixdrop.co/',
            'Origin': 'https://mixdrop.co'
        }
        
        # Stream download para arquivos grandes
        response = requests.get(video_url, headers=headers, stream=True, timeout=60)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        logger.info(f"[{driver_id}] Tamanho do arquivo: {total_size / (1024*1024):.2f} MB")
        
        downloaded_size = 0
        chunk_size = 1024 * 1024  # 1MB chunks
        
        with open(temp_filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded_size += len(chunk)
                    
                    # Log de progresso a cada 10MB
                    if downloaded_size % (10 * 1024 * 1024) < chunk_size:
                        progress = (downloaded_size / total_size * 100) if total_size > 0 else 0
                        logger.info(f"[{driver_id}] Progresso: {progress:.1f}% ({downloaded_size/(1024*1024):.1f}MB)")
        
        # Renomear arquivo temporário para final
        os.rename(temp_filepath, filepath)
        
        logger.info(f"[{driver_id}] Download concluído: {filepath}")
        return {
            'success': True,
            'filepath': filepath,
            'size_mb': downloaded_size / (1024 * 1024)
        }
        
    except Exception as e:
        logger.error(f"[{driver_id}] Erro no download: {e}")
        
        # Remover arquivo temporário se existir
        if os.path.exists(temp_filepath):
            try:
                os.remove(temp_filepath)
                logger.info(f"[{driver_id}] Arquivo temporário removido: {temp_filepath}")
            except Exception as remove_error:
                logger.error(f"[{driver_id}] Erro ao remover arquivo temporário: {remove_error}")
        
        return {
            'success': False,
            'error': str(e)
        }

def extract_and_download(url, driver_id, download_path_info):
    """Extrai URL do vídeo e faz download"""
    start_time = time.time()
    filepath = download_path_info['filepath']
    
    try:
        logger.info(f"[{driver_id}] Iniciando processo: {url}")
        
        # Passo 1: Extrair URL do vídeo
        extraction_result = extrair_url_video(url, driver_id)
        
        if not extraction_result.get('success'):
            logger.error(f"[{driver_id}] Falha na extração: {extraction_result.get('error')}")
            cleanup_failed_download(filepath, driver_id)
            return {
                'success': False,
                'error': extraction_result.get('error', 'Erro na extração')
            }
        
        video_url = extraction_result['video_url']
        logger.info(f"[{driver_id}] URL extraída com sucesso")
        
        # Passo 2: Fazer download do vídeo
        logger.info(f"[{driver_id}] Iniciando download do vídeo...")
        download_result = download_video(video_url, driver_id, download_path_info['filepath'])
        
        if download_result['success']:
            elapsed = time.time() - start_time
            return {
                'success': True,
                'video_url': video_url,
                'filepath': download_result['filepath'],
                'size_mb': download_result['size_mb'],
                'extraction_time': extraction_result.get('extraction_time', 'N/A'),
                'total_time': f"{elapsed:.2f}s"
            }
        else:
            # Download falhou, remover arquivo
            cleanup_failed_download(filepath, driver_id)
            return {
                'success': False,
                'error': download_result.get('error', 'Erro desconhecido no download')
            }
        
    except Exception as e:
        logger.error(f"[{driver_id}] Erro durante processo: {e}")
        # Remover arquivo em caso de erro geral
        cleanup_failed_download(filepath, driver_id)
        return {
            'success': False,
            'error': str(e)
        }

def download_with_retry(url, download_path_info, max_retries=2):
    """Sistema de retry para download"""
    session_id = str(uuid.uuid4())[:8]
    
    # Verificar se o arquivo já existe ANTES de processar
    filepath = download_path_info['filepath']
    if os.path.exists(filepath):
        file_size = os.path.getsize(filepath)
        size_mb = file_size / (1024 * 1024)
        logger.info(f"[{session_id}] Arquivo já existe: {filepath} ({size_mb:.2f} MB)")
        return {
            'success': True,
            'already_exists': True,
            'filepath': filepath,
            'size_mb': size_mb,
            'message': 'Arquivo já foi baixado anteriormente'
        }
    
    # Se não existe, prosseguir com o download
    for attempt in range(max_retries):
        if attempt > 0:
            logger.info(f"[{session_id}] Tentativa {attempt + 1} de {max_retries}")
            time.sleep(2)
        
        result = extract_and_download(url, session_id, download_path_info)
        
        if result and result.get('success'):
            return result
    
    logger.error(f"[{session_id}] Todas as tentativas falharam")
    return {
        'success': False,
        'error': 'Todas as tentativas de download falharam'
    }

@app.route('/baixar', methods=['GET'])
def baixar_video():
    """Endpoint principal de download"""
    start_time = time.time()
    request_id = str(uuid.uuid4())[:8]
    
    try:
        target_url = request.args.get('url')
        
        if not target_url:
            return jsonify({
                'success': False,
                'error': 'Parâmetro "url" é obrigatório',
                'request_id': request_id
            }), 400
        
        if not is_valid_warezcdn_url(target_url):
            return jsonify({
                'success': False,
                'error': 'URL deve ser do domínio warezcdn.cc',
                'request_id': request_id
            }), 400
        
        # Parse da URL para extrair informações
        url_info = parse_url_info(target_url)
        if not url_info:
            return jsonify({
                'success': False,
                'error': 'Formato de URL inválido',
                'request_id': request_id
            }), 400
        
        # Definir caminho de download
        download_path_info = get_download_path(url_info)
        if not download_path_info:
            return jsonify({
                'success': False,
                'error': 'Não foi possível determinar o caminho de download',
                'request_id': request_id
            }), 500
        
        logger.info(f"[{request_id}] Nova requisição: {target_url}")
        logger.info(f"[{request_id}] Tipo: {url_info['type']}, ID: {url_info['id']}")
        logger.info(f"[{request_id}] Caminho: {download_path_info['filepath']}")
        
        result = download_with_retry(target_url, download_path_info, 2)
        elapsed_time = time.time() - start_time
        
        if result.get('success'):
            logger.info(f"[{request_id}] Download concluído com sucesso em {elapsed_time:.2f}s")
            
            response_data = {
                'success': True,
                'url_info': url_info,
                'filepath': result.get('filepath'),
                'size_mb': result.get('size_mb'),
                'total_time': f"{elapsed_time:.2f}s",
                'request_id': request_id
            }
            
            # Adicionar tempo de extração se disponível
            if result.get('extraction_time'):
                response_data['extraction_time'] = result.get('extraction_time')
            
            # Verificar se o arquivo já existia
            if result.get('already_exists'):
                response_data['message'] = 'Arquivo já existe, download não necessário'
                response_data['already_exists'] = True
            else:
                response_data['message'] = 'Download concluído com sucesso'
                response_data['already_exists'] = False
            
            return jsonify(response_data), 200
        else:
            logger.error(f"[{request_id}] Falha no download em {elapsed_time:.2f}s")
            return jsonify({
                'success': False,
                'error': result.get('error', 'Erro desconhecido'),
                'url_info': url_info,
                'total_time': f"{elapsed_time:.2f}s",
                'request_id': request_id
            }), 500
    
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error(f"[{request_id}] Erro inesperado: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Erro interno do servidor',
            'details': str(e),
            'total_time': f"{elapsed_time:.2f}s",
            'request_id': request_id
        }), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    ublock_status = "Instalado" if os.path.exists(UBLOCK_XPI) else "Não instalado"
    
    return jsonify({
        'status': 'OK',
        'service': 'Warezcdn + Mixdrop Video Downloader',
        'ublock_origin': ublock_status,
        'downloads_dir': DOWNLOADS_DIR,
        'features': [
            'Download automático de vídeos',
            'Organização por ID/temporada/episódio',
            'Verificação de arquivo existente',
            'Remoção automática em caso de erro',
            'uBlock Origin integrado',
            'Sistema de retry',
            'Progress logging',
            'Extração separada da URL do vídeo'
        ]
    }), 200

@app.route('/', methods=['GET'])
def index():
    """Página inicial"""
    ublock_status = "Instalado" if os.path.exists(UBLOCK_XPI) else "Não instalado"
    
    return jsonify({
        'service': 'API de Download Warezcdn + Mixdrop',
        'version': '6.0',
        'provider': 'Warezcdn (Mixdrop)',
        'ublock_origin': ublock_status,
        'downloads_dir': DOWNLOADS_DIR,
        'architecture': 'Modular (extração separada)',
        'endpoints': {
            '/baixar?url=<URL>': 'Baixar vídeo',
            '/health': 'Status da API',
            '/': 'Esta página'
        },
        'url_format': {
            'movie': 'https://embed.warezcdn.cc/filme/{id}',
            'tv': 'https://embed.warezcdn.cc/serie/{id}/{season}/{episode}'
        },
        'download_structure': {
            'movie': 'downloads/filmes/{id}/{id}.mp4',
            'tv': 'downloads/tv/{id}/{season}/{episode}.mp4'
        },
        'examples': {
            'movie': 'http://localhost:5000/baixar?url=https://embed.warezcdn.cc/filme/tt1234567',
            'tv': 'http://localhost:5000/baixar?url=https://embed.warezcdn.cc/serie/tt1234567/1/1'
        }
    })

if __name__ == "__main__":
    print("API de Download Warezcdn + Mixdrop")
    print("=" * 60)
    print("\nArquitetura:")
    print("  - extracao.py: Extração da URL do vídeo")
    print("  - downloader_local.py: Download e gerenciamento")
    print("\nRecursos:")
    print("  - Download automático de vídeos")
    print("  - Organização automática por ID/temporada/episódio")
    print("  - Filmes: downloads/filmes/{id}/{id}.mp4")
    print("  - Séries: downloads/tv/{id}/{season}/{episode}.mp4")
    print("  - Verificação de arquivo existente (evita re-download)")
    print("  - Remoção automática de arquivos em caso de erro")
    print("  - uBlock Origin integrado")
    print("  - Sistema de retry (2 tentativas)")
    print("  - Progress logging durante download")
    print(f"\nDiretório de downloads: {DOWNLOADS_DIR}")
    print("\nEndpoint:")
    print("  GET /baixar?url=<URL>")
    print("\nExemplos:")
    print("  Filme: /baixar?url=https://embed.warezcdn.cc/filme/tt1234567")
    print("  Série: /baixar?url=https://embed.warezcdn.cc/serie/tt1234567/1/1")
    print("\nIniciando servidor em http://0.0.0.0:5000")
    print("=" * 60)
    
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False,
        threaded=True
    )