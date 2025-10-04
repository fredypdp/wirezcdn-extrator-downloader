import time
import logging
from urllib.parse import urlparse
from flask import Flask, request, jsonify
from flask_cors import CORS
import uuid
import os

# Importar a função de extração do módulo separado
from extracao_url import extrair_url_video, download_ublock_origin, UBLOCK_XPI

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Desabilitar logs excessivos
logging.getLogger('WDM').setLevel(logging.ERROR)
logging.getLogger('urllib3').setLevel(logging.ERROR)

app = Flask(__name__)
CORS(app)

def is_valid_wizercdn_url(url):
    """Valida URL do Wizercdn"""
    try:
        parsed = urlparse(url)
        return 'warezcdn.cc' in parsed.netloc.lower() or 'embed.warezcdn.cc' in parsed.netloc.lower()
    except:
        return False

# Baixar uBlock Origin na inicialização
download_ublock_origin()

@app.route('/extrair', methods=['GET'])
def extrair_video():
    """Endpoint principal de extração"""
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
        
        if not is_valid_wizercdn_url(target_url):
            return jsonify({
                'success': False,
                'error': 'URL deve ser do domínio warezcdn.cc',
                'request_id': request_id
            }), 400
        
        logger.info(f"[{request_id}] Nova requisição: {target_url}")
        
        # Usar a função do módulo extracao_url
        resultado = extrair_url_video(target_url, request_id)
        elapsed_time = time.time() - start_time
        
        if resultado['success']:
            logger.info(f"[{request_id}] Sucesso em {elapsed_time:.2f}s")
            return jsonify({
                'success': True,
                'video_url': resultado['video_url'],
                'from_cache': resultado.get('from_cache', False),
                'processamento_tempo': f"{elapsed_time:.2f}s",
                'extraction_time': resultado.get('extraction_time', f"{elapsed_time:.2f}s"),
                'request_id': request_id
            }), 200
        else:
            logger.error(f"[{request_id}] Falha em {elapsed_time:.2f}s")
            return jsonify({
                'success': False,
                'error': resultado.get('error', 'Não foi possível extrair a URL do vídeo'),
                'processamento_tempo': f"{elapsed_time:.2f}s",
                'request_id': request_id
            }), 404
    
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error(f"[{request_id}] Erro inesperado: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Erro interno do servidor',
            'details': str(e),
            'processamento_tempo': f"{elapsed_time:.2f}s",
            'request_id': request_id
        }), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    ublock_status = "Instalado" if os.path.exists(UBLOCK_XPI) else "Não instalado"
    
    return jsonify({
        'status': 'OK',
        'service': 'Wizercdn + Mixdrop Extractor',
        'ublock_origin': ublock_status,
        'features': [
            'uBlock Origin integrado',
            'Cliques com emulação de mouse',
            'Verificação de reprodução (vjs-playing)',
            '3 estratégias de clique com retry',
            'Extração via currentSrc',
            'Cache no banco de dados (Supabase)',
            'Remoção de overlays/popups'
        ]
    }), 200

@app.route('/', methods=['GET'])
def index():
    """Página inicial"""
    ublock_status = "Instalado" if os.path.exists(UBLOCK_XPI) else "Não instalado"
    
    return jsonify({
        'service': 'API de Extração Wizercdn + Mixdrop',
        'version': '4.0',
        'provider': 'Wizercdn (Mixdrop)',
        'ublock_origin': ublock_status,
        'endpoints': {
            '/extrair?url=<URL>': 'Extrair URL de vídeo',
            '/health': 'Status da API',
            '/': 'Esta página'
        },
        'url_format': {
            'movie': 'https://embed.warezcdn.cc/filme/{imdb_id}',
            'tv': 'https://embed.warezcdn.cc/serie/{imdb_id}/{season}/{episode}'
        },
        'example': 'http://localhost:5000/extrair?url=https://embed.warezcdn.cc/filme/tt1234567'
    })

if __name__ == "__main__":
    print("API de Extração Wizercdn + Mixdrop")
    print("=" * 50)
    print("\nRecursos:")
    print("  - uBlock Origin integrado")
    print("  - Cliques com ActionChains (emulação real de mouse)")
    print("  - 10s de espera antes de clicar no player")
    print("  - Verificação de vjs-playing")
    print("  - 3 estratégias de clique com retry")
    print("  - Cache no banco de dados (Supabase)")
    print("  - Remoção automática de overlays/popups")
    print("  - Módulo de extração separado")
    print("\nEndpoint:")
    print("  GET /extrair?url=<URL>")
    print("\nIniciando servidor em http://0.0.0.0:5000")
    print("=" * 50)
    
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False,
        threaded=True
    )