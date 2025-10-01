import time
import logging
from urllib.parse import urlparse
from flask import Flask, request, jsonify
from flask_cors import CORS
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from webdriver_manager.firefox import GeckoDriverManager
import uuid
import os
import requests
from pathlib import Path

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Desabilitar logs excessivos
logging.getLogger('WDM').setLevel(logging.ERROR)
logging.getLogger('urllib3').setLevel(logging.ERROR)

app = Flask(__name__)
CORS(app)

# Diretórios
EXTENSIONS_DIR = os.path.join(os.getcwd(), 'extensions')
DOWNLOADS_DIR = os.path.join(os.getcwd(), 'downloads')
UBLOCK_XPI = os.path.join(EXTENSIONS_DIR, 'ublock_origin.xpi')

# Criar diretório de downloads
if not os.path.exists(DOWNLOADS_DIR):
    os.makedirs(DOWNLOADS_DIR)
    logger.info(f"Diretório de downloads criado: {DOWNLOADS_DIR}")

def download_ublock_origin():
    """Baixa a extensão uBlock Origin se não existir"""
    if not os.path.exists(EXTENSIONS_DIR):
        os.makedirs(EXTENSIONS_DIR)
        logger.info(f"Diretório de extensões criado: {EXTENSIONS_DIR}")
    
    if os.path.exists(UBLOCK_XPI):
        logger.info("uBlock Origin já está baixado")
        return True
    
    logger.info("Baixando uBlock Origin...")
    
    try:
        url = "https://addons.mozilla.org/firefox/downloads/latest/ublock-origin/latest.xpi"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        with open(UBLOCK_XPI, 'wb') as f:
            f.write(response.content)
        
        logger.info(f"uBlock Origin baixado: {UBLOCK_XPI}")
        return True
        
    except Exception as e:
        logger.error(f"Erro ao baixar uBlock Origin: {e}")
        logger.warning("Continuando sem uBlock Origin...")
        return False

def criar_navegador_firefox_com_ublock():
    """Cria navegador Firefox com uBlock Origin"""
    options = Options()
    
    # options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--width=1920")
    options.add_argument("--height=1080")
    
    options.set_preference("general.useragent.override", 
                          "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0")
    
    options.set_preference("dom.webdriver.enabled", False)
    options.set_preference("useAutomationExtension", False)
    
    options.set_preference("browser.cache.disk.enable", False)
    options.set_preference("browser.cache.memory.enable", False)
    options.set_preference("network.http.use-cache", False)
    
    options.set_preference("dom.max_script_run_time", 30)
    options.set_preference("dom.max_chrome_script_run_time", 30)
    
    options.set_preference("dom.webnotifications.enabled", False)
    options.set_preference("dom.push.enabled", False)
    
    try:
        service = Service(GeckoDriverManager().install())
        service.service_args = ['--log', 'fatal', '--marionette-port', '0']
        
        driver = webdriver.Firefox(service=service, options=options)
        
        if os.path.exists(UBLOCK_XPI):
            try:
                driver.install_addon(UBLOCK_XPI, temporary=True)
                logger.info("uBlock Origin instalado")
                time.sleep(2)
            except Exception as e:
                logger.warning(f"Erro ao instalar uBlock Origin: {e}")
        
        driver.set_page_load_timeout(30)
        driver.implicitly_wait(5)
        
        logger.info("Driver Firefox criado")
        return driver
        
    except Exception as e:
        logger.error(f"Erro ao criar driver: {e}")
        raise

def is_valid_wizercdn_url(url):
    """Valida URL do Wizercdn"""
    try:
        parsed = urlparse(url)
        return 'warezcdn.cc' in parsed.netloc.lower() or 'embed.warezcdn.cc' in parsed.netloc.lower()
    except:
        return False

def mouse_click(driver, element, driver_id):
    """Clica em elemento emulando comportamento real do mouse"""
    try:
        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
        time.sleep(0.5)
        
        actions = ActionChains(driver)
        actions.move_to_element(element).pause(0.3).click().perform()
        logger.info(f"[{driver_id}] Clique com ActionChains executado")
        return True
        
    except Exception as e:
        logger.debug(f"[{driver_id}] ActionChains falhou: {e}, tentando JS click")
        try:
            driver.execute_script("arguments[0].click();", element)
            logger.info(f"[{driver_id}] Clique JS executado")
            return True
        except Exception as e2:
            logger.error(f"[{driver_id}] Ambos os cliques falharam: {e2}")
            return False

def click_center_page(driver, driver_id):
    """Clica exatamente no centro da página"""
    try:
        width = driver.execute_script("return window.innerWidth")
        height = driver.execute_script("return window.innerHeight")
        center_x = width // 2
        center_y = height // 2
        
        actions = ActionChains(driver)
        actions.move_by_offset(center_x, center_y).pause(0.3).click().perform()
        actions.move_by_offset(-center_x, -center_y).perform()
        
        logger.info(f"[{driver_id}] Clique no centro da página ({center_x}, {center_y})")
        return True
    except Exception as e:
        logger.error(f"[{driver_id}] Erro ao clicar no centro: {e}")
        return False

def try_click_player(driver, driver_id):
    """Tenta clicar no player usando 3 estratégias"""
    
    # Estratégia 1: button.vjs-big-play-button
    logger.info(f"[{driver_id}] Estratégia 1: Procurando button.vjs-big-play-button")
    try:
        play_button = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'button.vjs-big-play-button'))
        )
        WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'button.vjs-big-play-button'))
        )
        
        if mouse_click(driver, play_button, driver_id):
            logger.info(f"[{driver_id}] Estratégia 1 funcionou")
            return True
    except Exception as e:
        logger.warning(f"[{driver_id}] Estratégia 1 falhou: {e}")
    
    # Estratégia 2: span com texto "Play Video"
    logger.info(f"[{driver_id}] Estratégia 2: Procurando span 'Play Video'")
    try:
        play_span = driver.find_element(By.XPATH, "//span[contains(text(), 'Play Video')]")
        play_button_parent = play_span.find_element(By.XPATH, "./..")
        
        if mouse_click(driver, play_button_parent, driver_id):
            logger.info(f"[{driver_id}] Estratégia 2 funcionou")
            return True
    except Exception as e:
        logger.warning(f"[{driver_id}] Estratégia 2 falhou: {e}")
    
    # Estratégia 3: Clique no centro
    logger.info(f"[{driver_id}] Estratégia 3: Clicando no centro")
    try:
        if click_center_page(driver, driver_id):
            logger.info(f"[{driver_id}] Estratégia 3 funcionou")
            return True
    except Exception as e:
        logger.warning(f"[{driver_id}] Estratégia 3 falhou: {e}")
    
    return False

def wait_for_video_playing(driver, driver_id, max_wait=15):
    """Aguarda o vídeo começar a reproduzir (classe vjs-playing)"""
    logger.info(f"[{driver_id}] Aguardando vídeo começar a reproduzir...")
    start_wait = time.time()
    
    while time.time() - start_wait < max_wait:
        try:
            player_element = driver.find_element(By.CSS_SELECTOR, '.player.video-js')
            classes = player_element.get_attribute('class')
            
            if 'vjs-playing' in classes:
                logger.info(f"[{driver_id}] Vídeo está reproduzindo (vjs-playing detectado)")
                return True
        except Exception as e:
            logger.debug(f"[{driver_id}] Erro ao verificar vjs-playing: {e}")
        
        time.sleep(1)
    
    logger.warning(f"[{driver_id}] Timeout aguardando vjs-playing")
    return False

def download_video(video_url, driver_id, filename=None):
    """Faz download do vídeo usando requests"""
    try:
        if not filename:
            # Gerar nome do arquivo baseado no timestamp
            timestamp = int(time.time())
            filename = f"video_{timestamp}.mp4"
        
        filepath = os.path.join(DOWNLOADS_DIR, filename)
        
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
        
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded_size += len(chunk)
                    
                    # Log de progresso a cada 10MB
                    if downloaded_size % (10 * 1024 * 1024) < chunk_size:
                        progress = (downloaded_size / total_size * 100) if total_size > 0 else 0
                        logger.info(f"[{driver_id}] Progresso: {progress:.1f}% ({downloaded_size/(1024*1024):.1f}MB)")
        
        logger.info(f"[{driver_id}] Download concluído: {filepath}")
        return {
            'success': True,
            'filepath': filepath,
            'filename': filename,
            'size_mb': downloaded_size / (1024 * 1024)
        }
        
    except requests.exceptions.RequestException as e:
        logger.error(f"[{driver_id}] Erro no download: {e}")
        return {
            'success': False,
            'error': str(e)
        }
    except Exception as e:
        logger.error(f"[{driver_id}] Erro inesperado no download: {e}")
        return {
            'success': False,
            'error': str(e)
        }

def extract_and_download_video(url, driver_id):
    """Extrai URL do vídeo e faz download"""
    start_time = time.time()
    driver = None
    
    try:
        driver = criar_navegador_firefox_com_ublock()
        logger.info(f"[{driver_id}] Iniciando extração: {url}")
        
        # Passo 1: Navegar
        logger.info(f"[{driver_id}] 1. Navegando para a página...")
        driver.get(url)
        time.sleep(3)
        
        # Passo 2: Audio-selector
        logger.info(f"[{driver_id}] 2. Procurando audio-selector (mixdrop, lang=2)...")
        try:
            audio_selectors = [
                'audio-selector[data-servers="mixdrop"][data-lang="2"]',
                'audio-selector[data-server="mixdrop"][data-lang="2"]',
                '[data-servers*="mixdrop"][data-lang="2"]',
                '.audio-selector[data-servers*="mixdrop"]'
            ]
            
            audio_selector = None
            for selector in audio_selectors:
                try:
                    audio_selector = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    logger.info(f"[{driver_id}] Audio-selector encontrado: {selector}")
                    break
                except:
                    continue
            
            if not audio_selector:
                raise Exception("Audio-selector não encontrado")
            
            if not mouse_click(driver, audio_selector, driver_id):
                raise Exception("Falha ao clicar no audio-selector")
            
            time.sleep(2)
            
        except Exception as e:
            logger.error(f"[{driver_id}] Erro com audio-selector: {e}")
            return None
        
        # Passo 3: Server-selector
        logger.info(f"[{driver_id}] 3. Procurando server-selector (mixdrop, lang=2)...")
        try:
            server_selectors = [
                'server-selector[data-servers="mixdrop"][data-lang="2"]',
                'server-selector[data-server="mixdrop"][data-lang="2"]',
                '[data-servers*="mixdrop"][data-lang="2"]',
                '.server-selector[data-servers*="mixdrop"]',
                'li[data-server*="mixdrop"]',
                'button[data-server*="mixdrop"]'
            ]
            
            server_selector = None
            for selector in server_selectors:
                try:
                    server_selector = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    logger.info(f"[{driver_id}] Server-selector encontrado: {selector}")
                    break
                except:
                    continue
            
            if server_selector:
                if not mouse_click(driver, server_selector, driver_id):
                    logger.warning(f"[{driver_id}] Falha ao clicar no server-selector")
            else:
                logger.warning(f"[{driver_id}] Server-selector não encontrado")
            
            time.sleep(2)
            
        except Exception as e:
            logger.warning(f"[{driver_id}] Erro com server-selector: {e}")
        
        # Passo 4: Aguardar
        logger.info(f"[{driver_id}] 4. Aguardando 10 segundos...")
        time.sleep(10)
        
        # Passo 5: Entrar nos iframes
        logger.info(f"[{driver_id}] 5. Procurando iframes aninhados...")
        
        try:
            # Iframe PAI
            logger.info(f"[{driver_id}] Procurando iframe PAI (embedcontent)...")
            parent_iframe_selectors = [
                'embedcontent.active iframe',
                'embedcontent iframe',
                'iframe[src*="getEmbed"]'
            ]
            
            parent_iframe = None
            for selector in parent_iframe_selectors:
                try:
                    parent_iframe = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    logger.info(f"[{driver_id}] Iframe PAI encontrado: {selector}")
                    break
                except:
                    continue
            
            if not parent_iframe:
                raise Exception("Iframe PAI não encontrado")
            
            driver.switch_to.frame(parent_iframe)
            logger.info(f"[{driver_id}] Entrou no iframe PAI")
            time.sleep(2)
            
            # Iframe FILHO
            logger.info(f"[{driver_id}] Procurando iframe FILHO (mixdrop)...")
            child_iframe_selectors = [
                'iframe[src*="mixdrop"]',
                'iframe#player',
                'iframe'
            ]
            
            child_iframe = None
            for selector in child_iframe_selectors:
                try:
                    child_iframe = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    logger.info(f"[{driver_id}] Iframe FILHO encontrado: {selector}")
                    break
                except:
                    continue
            
            if not child_iframe:
                raise Exception("Iframe FILHO não encontrado")
            
            driver.switch_to.frame(child_iframe)
            logger.info(f"[{driver_id}] Entrou no iframe FILHO")
            time.sleep(2)
            
        except Exception as e:
            logger.error(f"[{driver_id}] Erro ao processar iframes: {e}")
            return None
        
        # Passo 6: Aguardar player processar (10 segundos)
        logger.info(f"[{driver_id}] 6. Aguardando 10 segundos para o player processar...")
        time.sleep(10)
        
        # Passo 7: Tentar clicar no player até funcionar
        logger.info(f"[{driver_id}] 7. Tentando clicar no player...")
        video_playing = False
        
        for attempt in range(3):
            logger.info(f"[{driver_id}] Tentativa {attempt + 1} de clicar no player")
            
            if try_click_player(driver, driver_id):
                if wait_for_video_playing(driver, driver_id, max_wait=10):
                    video_playing = True
                    logger.info(f"[{driver_id}] Vídeo reproduzindo após tentativa {attempt + 1}")
                    logger.info(f"[{driver_id}] Aguardando 10 segundos após início da reprodução...")
                    time.sleep(10)
                    break
                else:
                    logger.warning(f"[{driver_id}] Vídeo não reproduziu após tentativa {attempt + 1}")
            
            time.sleep(2)
        
        if not video_playing:
            logger.warning(f"[{driver_id}] Vídeo não começou a reproduzir")
        
        # Passo 8: Buscar URL do vídeo
        logger.info(f"[{driver_id}] 8. Procurando URL do vídeo...")
        
        max_wait = 30
        start_search = time.time()
        video_url = None
        
        while time.time() - start_search < max_wait:
            try:
                video_url = driver.execute_script("""
                    var video = document.getElementById('videojs_html5_api');
                    if (video) {
                        if (video.currentSrc) {
                            return video.currentSrc;
                        }
                        if (video.src) {
                            return video.src;
                        }
                    }
                    
                    var videos = document.querySelectorAll('video');
                    for (var i = 0; i < videos.length; i++) {
                        if (videos[i].currentSrc) {
                            return videos[i].currentSrc;
                        }
                        if (videos[i].src) {
                            return videos[i].src;
                        }
                    }
                    
                    return null;
                """)
                
                if video_url and len(video_url) > 10 and ('http' in video_url or '//' in video_url):
                    elapsed = time.time() - start_time
                    logger.info(f"[{driver_id}] URL encontrada em {elapsed:.2f}s")
                    break
                
                time.sleep(2)
                
            except Exception as e:
                logger.debug(f"[{driver_id}] Erro na busca: {e}")
                time.sleep(2)
        
        if not video_url:
            logger.error(f"[{driver_id}] URL não encontrada")
            return None
        
        # Passo 9: Fazer download do vídeo
        logger.info(f"[{driver_id}] 9. Iniciando download do vídeo...")
        download_result = download_video(video_url, driver_id)
        
        return {
            'video_url': video_url,
            'download': download_result
        }
        
    except Exception as e:
        logger.error(f"[{driver_id}] Erro durante extração: {e}")
        return None
    
    finally:
        if driver:
            try:
                driver.quit()
                logger.info(f"[{driver_id}] Driver fechado")
            except Exception as e:
                logger.error(f"[{driver_id}] Erro ao fechar driver: {e}")

def extract_with_retry(url, max_retries=2):
    """Sistema de retry"""
    session_id = str(uuid.uuid4())[:8]
    
    for attempt in range(max_retries):
        if attempt > 0:
            logger.info(f"[{session_id}] Tentativa {attempt + 1} de {max_retries}")
            time.sleep(2)
        
        result = extract_and_download_video(url, session_id)
        if result:
            return result
    
    logger.error(f"[{session_id}] Todas as tentativas falharam")
    return None

# Baixar uBlock Origin na inicialização
download_ublock_origin()

@app.route('/extrair', methods=['GET'])
def extrair_video():
    """Endpoint principal de extração e download"""
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
        
        result = extract_with_retry(target_url, 2)
        elapsed_time = time.time() - start_time
        
        if result and result.get('download', {}).get('success'):
            logger.info(f"[{request_id}] Sucesso em {elapsed_time:.2f}s")
            return jsonify({
                'success': True,
                'video_url': result.get('video_url'),
                'download': result.get('download'),
                'processamento_tempo': f"{elapsed_time:.2f}s",
                'request_id': request_id
            }), 200
        else:
            logger.error(f"[{request_id}] Falha em {elapsed_time:.2f}s")
            return jsonify({
                'success': False,
                'error': 'Não foi possível extrair e baixar o vídeo',
                'result': result,
                'processamento_tempo': f"{elapsed_time:.2f}s",
                'request_id': request_id
            }), 404
    
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error(f"[{request_id}] Erro inesperado: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Erro interno do servidor',
            'processamento_tempo': f"{elapsed_time:.2f}s",
            'request_id': request_id
        }), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    ublock_status = "Instalado" if os.path.exists(UBLOCK_XPI) else "Não instalado"
    
    return jsonify({
        'status': 'OK',
        'service': 'Wizercdn + Mixdrop Extractor & Downloader',
        'ublock_origin': ublock_status,
        'downloads_dir': DOWNLOADS_DIR,
        'features': [
            'uBlock Origin integrado',
            'Cliques com emulação de mouse',
            'Verificação de reprodução (vjs-playing)',
            '3 estratégias de clique com retry',
            'Extração via currentSrc',
            'Download automático do vídeo',
            'Progress logging durante download'
        ]
    }), 200

@app.route('/', methods=['GET'])
def index():
    """Página inicial"""
    ublock_status = "Instalado" if os.path.exists(UBLOCK_XPI) else "Não instalado"
    
    return jsonify({
        'service': 'API de Extração e Download Wizercdn + Mixdrop',
        'version': '4.0',
        'provider': 'Wizercdn (Mixdrop)',
        'ublock_origin': ublock_status,
        'downloads_dir': DOWNLOADS_DIR,
        'endpoints': {
            '/extrair?url=<URL>': 'Extrair e baixar vídeo',
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
    print("API de Extração e Download Wizercdn + Mixdrop")
    print("=" * 60)
    print("\nRecursos:")
    print("  - uBlock Origin integrado")
    print("  - Cliques com ActionChains (emulação real de mouse)")
    print("  - 10s de espera antes de clicar no player")
    print("  - Verificação de vjs-playing")
    print("  - 3 estratégias de clique com retry")
    print("  - Download automático do vídeo")
    print("  - Progress logging (a cada 10MB)")
    print("  - Sem pool (menor consumo de memória)")
    print(f"\nDiretório de downloads: {DOWNLOADS_DIR}")
    print("\nEndpoint:")
    print("  GET /extrair?url=<URL>")
    print("\nIniciando servidor em http://0.0.0.0:5000")
    print("=" * 60)
    
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False,
        threaded=True
    )