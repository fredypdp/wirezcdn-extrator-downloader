import time
import logging
import re
import os
import shutil
from urllib.parse import urlparse
from flask import Flask, request, jsonify
from flask_cors import CORS
import uuid
import requests
from threading import Semaphore, Lock
from concurrent.futures import ThreadPoolExecutor

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Desabilitar logs excessivos
logging.getLogger('urllib3').setLevel(logging.ERROR)

app = Flask(__name__)
CORS(app)

# Configurações de concorrência
MAX_CONCURRENT_DOWNLOADS = 5
download_semaphore = Semaphore(MAX_CONCURRENT_DOWNLOADS)
stats_lock = Lock()

# Estatísticas de download
download_stats = {
    'total_downloads': 0,
    'successful_downloads': 0,
    'failed_downloads': 0,
    'total_mb_downloaded': 0,
    'active_downloads': 0
}

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
        'filepath': os.path.join(folder, filename),
        'type': url_info['type'],
        'id': url_info['id']
    }

def file_already_exists(download_path_info):
    """Verifica se o arquivo já existe"""
    if not download_path_info:
        return False
    
    filepath = download_path_info['filepath']
    if os.path.exists(filepath):
        file_size = os.path.getsize(filepath)
        # Considerar arquivo válido se tiver mais de 1MB
        if file_size > 1024 * 1024:
            return True
    
    return False

def cleanup_on_error(download_path_info, request_id):
    """Remove arquivo e pasta em caso de erro"""
    try:
        if not download_path_info:
            return
        
        filepath = download_path_info['filepath']
        folder = download_path_info['folder']
        content_type = download_path_info['type']
        
        # Remover arquivo se existir
        if os.path.exists(filepath):
            os.remove(filepath)
            logger.info(f"[{request_id}] Arquivo removido: {filepath}")
        
        # Remover arquivo temporário se existir
        temp_filepath = f"{filepath}.tmp"
        if os.path.exists(temp_filepath):
            os.remove(temp_filepath)
            logger.info(f"[{request_id}] Arquivo temporário removido: {temp_filepath}")
        
        # Para filmes, remover toda a pasta do ID
        if content_type == 'movie':
            if os.path.exists(folder) and os.path.isdir(folder):
                files_in_folder = os.listdir(folder)
                if not files_in_folder or all(f.endswith('.tmp') for f in files_in_folder):
                    shutil.rmtree(folder)
                    logger.info(f"[{request_id}] Pasta do filme removida: {folder}")
        
        # Para séries, remover pasta da temporada se estiver vazia
        elif content_type == 'tv':
            if os.path.exists(folder) and os.path.isdir(folder):
                files_in_folder = os.listdir(folder)
                if not files_in_folder or all(f.endswith('.tmp') for f in files_in_folder):
                    shutil.rmtree(folder)
                    logger.info(f"[{request_id}] Pasta da temporada removida: {folder}")
                    
                    # Verificar se a pasta do ID da série está vazia
                    parent_folder = os.path.dirname(folder)
                    if os.path.exists(parent_folder) and os.path.isdir(parent_folder):
                        if not os.listdir(parent_folder):
                            shutil.rmtree(parent_folder)
                            logger.info(f"[{request_id}] Pasta da série removida: {parent_folder}")
    
    except Exception as e:
        logger.error(f"[{request_id}] Erro ao limpar arquivos/pastas: {e}")

def is_valid_warezcdn_url(url):
    """Valida URL do Warezcdn"""
    try:
        parsed = urlparse(url)
        return 'warezcdn.cc' in parsed.netloc.lower() or 'embed.warezcdn.cc' in parsed.netloc.lower()
    except:
        return False

def update_stats(success=False, mb_downloaded=0, increment_active=0):
    """Atualiza estatísticas de download de forma thread-safe"""
    with stats_lock:
        download_stats['active_downloads'] += increment_active
        if increment_active < 0:  # Finalizando download
            download_stats['total_downloads'] += 1
            if success:
                download_stats['successful_downloads'] += 1
                download_stats['total_mb_downloaded'] += mb_downloaded
            else:
                download_stats['failed_downloads'] += 1

def download_video(video_url, filepath, request_id):
    """Faz download do vídeo usando requests com otimizações"""
    temp_filepath = f"{filepath}.tmp"
    
    try:
        logger.info(f"[{request_id}] Iniciando download: {video_url[:80]}...")
        
        # Headers otimizados
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0',
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Referer': 'https://mixdrop.co/'
        }
        
        # Configuração otimizada para downloads
        session = requests.Session()
        session.headers.update(headers)
        
        # Stream download com timeout maior e chunk otimizado
        response = session.get(video_url, stream=True, timeout=120)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        logger.info(f"[{request_id}] Tamanho: {total_size / (1024*1024):.2f} MB")
        
        downloaded_size = 0
        chunk_size = 8 * 1024 * 1024  # 8MB chunks para melhor performance
        last_log_size = 0
        
        with open(temp_filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded_size += len(chunk)
                    
                    # Log de progresso a cada 50MB para reduzir overhead
                    if downloaded_size - last_log_size >= 50 * 1024 * 1024:
                        progress = (downloaded_size / total_size * 100) if total_size > 0 else 0
                        logger.info(f"[{request_id}] Progresso: {progress:.1f}% ({downloaded_size/(1024*1024):.1f}MB)")
                        last_log_size = downloaded_size
        
        # Renomear arquivo temporário para final
        os.rename(temp_filepath, filepath)
        
        size_mb = downloaded_size / (1024 * 1024)
        logger.info(f"[{request_id}] Download concluído: {size_mb:.2f}MB")
        
        return {
            'success': True,
            'filepath': filepath,
            'size_mb': size_mb
        }
        
    except Exception as e:
        logger.error(f"[{request_id}] Erro no download: {e}")
        
        # Remover arquivo temporário se existir
        if os.path.exists(temp_filepath):
            try:
                os.remove(temp_filepath)
            except:
                pass
        
        return {
            'success': False,
            'error': str(e)
        }

def process_download(page_url, video_url, download_path_info, request_id):
    """Processa o download de um vídeo"""
    start_time = time.time()
    
    try:
        # Atualizar estatísticas - download ativo
        update_stats(increment_active=1)
        
        logger.info(f"[{request_id}] Iniciando download...")
        logger.info(f"[{request_id}] Destino: {download_path_info['filepath']}")
        
        # Fazer download
        result = download_video(video_url, download_path_info['filepath'], request_id)
        
        elapsed = time.time() - start_time
        
        if result['success']:
            # Atualizar estatísticas - sucesso
            update_stats(success=True, mb_downloaded=result['size_mb'], increment_active=-1)
            
            logger.info(f"[{request_id}] Concluído em {elapsed:.2f}s - {result['size_mb']:.2f}MB")
            return {
                'success': True,
                'filepath': result['filepath'],
                'size_mb': result['size_mb'],
                'download_time': f"{elapsed:.2f}s",
                'speed_mbps': (result['size_mb'] * 8 / elapsed) if elapsed > 0 else 0
            }
        else:
            # Atualizar estatísticas - falha
            update_stats(success=False, increment_active=-1)
            
            # Limpar em caso de erro
            cleanup_on_error(download_path_info, request_id)
            
            return {
                'success': False,
                'error': result.get('error', 'Erro desconhecido no download')
            }
            
    except Exception as e:
        # Atualizar estatísticas - falha
        update_stats(success=False, increment_active=-1)
        
        logger.error(f"[{request_id}] Erro durante download: {e}")
        cleanup_on_error(download_path_info, request_id)
        return {
            'success': False,
            'error': str(e)
        }

@app.route('/baixar', methods=['POST'])
def baixar_video():
    """Endpoint de download direto"""
    start_time = time.time()
    request_id = str(uuid.uuid4())[:8]
    
    try:
        # Obter dados do request
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'JSON inválido ou vazio',
                'request_id': request_id
            }), 400
        
        page_url = data.get('page_url')
        video_url = data.get('video_url')
        
        if not page_url or not video_url:
            return jsonify({
                'success': False,
                'error': 'Parâmetros "page_url" e "video_url" são obrigatórios',
                'request_id': request_id
            }), 400
        
        # Validar URL da página
        if not is_valid_warezcdn_url(page_url):
            return jsonify({
                'success': False,
                'error': 'page_url deve ser do domínio warezcdn.cc',
                'request_id': request_id
            }), 400
        
        # Parse da URL para extrair informações
        url_info = parse_url_info(page_url)
        if not url_info:
            return jsonify({
                'success': False,
                'error': 'Formato de page_url inválido',
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
        
        # Verificar se o arquivo já existe
        if file_already_exists(download_path_info):
            elapsed_time = time.time() - start_time
            logger.info(f"[{request_id}] Arquivo já existe: {download_path_info['filepath']}")
            
            file_size = os.path.getsize(download_path_info['filepath'])
            
            return jsonify({
                'success': True,
                'message': 'Arquivo já existe',
                'already_exists': True,
                'url_info': url_info,
                'filepath': download_path_info['filepath'],
                'size_mb': file_size / (1024 * 1024),
                'total_time': f"{elapsed_time:.2f}s",
                'request_id': request_id
            }), 200
        
        logger.info(f"[{request_id}] Nova requisição")
        logger.info(f"[{request_id}] Tipo: {url_info['type']}, ID: {url_info['id']}")
        logger.info(f"[{request_id}] Video URL: {video_url[:80]}...")
        
        # Adquirir semáforo (limite de downloads simultâneos)
        logger.info(f"[{request_id}] Aguardando slot (máx. {MAX_CONCURRENT_DOWNLOADS} downloads simultâneos)...")
        with download_semaphore:
            logger.info(f"[{request_id}] Slot adquirido")
            
            result = process_download(page_url, video_url, download_path_info, request_id)
            elapsed_time = time.time() - start_time
            
            if result.get('success'):
                return jsonify({
                    'success': True,
                    'message': 'Download concluído com sucesso',
                    'already_exists': False,
                    'url_info': url_info,
                    'filepath': result.get('filepath'),
                    'size_mb': result.get('size_mb'),
                    'download_time': result.get('download_time'),
                    'speed_mbps': result.get('speed_mbps'),
                    'total_time': f"{elapsed_time:.2f}s",
                    'request_id': request_id
                }), 200
            else:
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

@app.route('/stats', methods=['GET'])
def get_stats():
    """Retorna estatísticas de download"""
    with stats_lock:
        stats = download_stats.copy()
    
    return jsonify({
        'statistics': stats,
        'max_concurrent_downloads': MAX_CONCURRENT_DOWNLOADS
    }), 200

@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    with stats_lock:
        active = download_stats['active_downloads']
    
    return jsonify({
        'status': 'OK',
        'service': 'Warezcdn Video Downloader',
        'downloads_dir': DOWNLOADS_DIR,
        'active_downloads': active,
        'max_concurrent': MAX_CONCURRENT_DOWNLOADS,
        'features': [
            'Download direto via URL do vídeo',
            'Organização automática por tipo/ID/temporada/episódio',
            'Verificação de arquivo existente',
            'Remoção automática em caso de erro',
            'Suporte a múltiplas requisições simultâneas',
            'Estatísticas de download',
            'Otimizado para alta performance'
        ]
    }), 200

@app.route('/', methods=['GET'])
def index():
    """Página inicial"""
    return jsonify({
        'service': 'API de Download Warezcdn',
        'version': '6.0',
        'downloads_dir': DOWNLOADS_DIR,
        'max_concurrent_downloads': MAX_CONCURRENT_DOWNLOADS,
        'endpoints': {
            'POST /baixar': 'Baixar vídeo (requer JSON com page_url e video_url)',
            'GET /stats': 'Estatísticas de download',
            'GET /health': 'Status da API',
            'GET /': 'Esta página'
        },
        'request_format': {
            'method': 'POST',
            'content_type': 'application/json',
            'body': {
                'page_url': 'URL da página warezcdn (para determinar destino)',
                'video_url': 'URL direta do vídeo para download'
            }
        },
        'url_format': {
            'movie': 'https://embed.warezcdn.cc/filme/{id}',
            'tv': 'https://embed.warezcdn.cc/serie/{id}/{season}/{episode}'
        },
        'download_structure': {
            'movie': 'downloads/filmes/{id}/{id}.mp4',
            'tv': 'downloads/tv/{id}/{season}/{episode}.mp4'
        },
        'example': {
            'url': 'http://localhost:5000/baixar',
            'method': 'POST',
            'body': {
                'page_url': 'https://embed.warezcdn.cc/filme/tt1234567',
                'video_url': 'https://example.com/video.mp4'
            }
        }
    })

if __name__ == "__main__":
    print("API de Download Warezcdn")
    print("=" * 60)
    print("\nRecursos:")
    print("  - Download direto via URL do vídeo")
    print("  - Organização automática por tipo/ID/temporada/episódio")
    print("  - Filmes: downloads/filmes/{id}/{id}.mp4")
    print("  - Séries: downloads/tv/{id}/{season}/{episode}.mp4")
    print("  - Verificação de arquivo existente")
    print("  - Remoção automática em caso de erro")
    print(f"  - Máximo de {MAX_CONCURRENT_DOWNLOADS} downloads simultâneos")
    print("  - Chunks de 8MB para alta performance")
    print("  - Estatísticas de download em tempo real")
    print(f"\nDiretório de downloads: {DOWNLOADS_DIR}")
    print("\nEndpoint:")
    print("  POST /baixar")
    print("  Body (JSON): { 'page_url': '...', 'video_url': '...' }")
    print("\nIniciando servidor em http://0.0.0.0:5000")
    print("=" * 60)
    
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False,
        threaded=True
    )