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
UBLOCK_XPI = os.path.join(EXTENSIONS_DIR, 'ublock_origin.xpi')
VIDEO_FINDER_XPI = os.path.join(EXTENSIONS_DIR, 'find-video-addon.xpi')

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

def check_video_finder_extension():
    """Verifica se a extensão find-video-addon.xpi existe"""
    if os.path.exists(VIDEO_FINDER_XPI):
        logger.info(f"Extensão Video Finder encontrada: {VIDEO_FINDER_XPI}")
        return True
    else:
        logger.error(f"ERRO: Extensão Video Finder NÃO encontrada em: {VIDEO_FINDER_XPI}")
        logger.error("Por favor, coloque o arquivo 'find-video-addon.xpi' na pasta 'extensions/'")
        return False

def criar_navegador_firefox_com_extensions():
    """Cria navegador Firefox com uBlock Origin e Video Finder"""
    options = Options()
    
    # options.add_argument("--headless")  # Comentado para debug
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--width=1920")
    options.add_argument("--height=1080")
    
    options.set_preference("general.useragent.override", 
                          "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0")
    
    options.set_preference("dom.webdriver.enabled", False)
    options.set_preference("useAutomationExtension", False)
    
    # Desabilitar cache
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
        
        # Instalar Video Finder PRIMEIRO (mais importante)
        if os.path.exists(VIDEO_FINDER_XPI):
            try:
                driver.install_addon(VIDEO_FINDER_XPI, temporary=True)
                logger.info("Video Finder instalado")
                time.sleep(2)
            except Exception as e:
                logger.warning(f"Erro ao instalar Video Finder: {e}")
        else:
            logger.warning("Video Finder não encontrado, continuando sem ele...")
        
        # Instalar uBlock Origin
        if os.path.exists(UBLOCK_XPI):
            try:
                driver.install_addon(UBLOCK_XPI, temporary=True)
                logger.info("uBlock Origin instalado")
                time.sleep(2)
            except Exception as e:
                logger.warning(f"Erro ao instalar uBlock Origin: {e}")
        
        driver.set_page_load_timeout(30)
        driver.implicitly_wait(5)
        
        logger.info("Driver Firefox criado com extensões")
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
    """Aguarda o vídeo começar a reproduzir"""
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

def get_video_urls_from_extension(driver, driver_id, max_wait=30):
    """Obtém URLs de vídeo capturadas pela extensão Video Finder"""
    logger.info(f"[{driver_id}] Aguardando extensão capturar URLs de vídeo...")
    start_time = time.time()
    
    while time.time() - start_time < max_wait:
        try:
            # Pegar URLs do window.__FOUND_VIDEO_URLS
            urls = driver.execute_script("return window.__FOUND_VIDEO_URLS || []")
            
            if urls and len(urls) > 0:
                logger.info(f"[{driver_id}] Extensão capturou {len(urls)} URL(s)")
                
                # Log de todas as URLs encontradas
                for i, url in enumerate(urls):
                    logger.info(f"[{driver_id}]   URL {i+1}: {url[:100]}...")
                
                # Retornar a primeira URL (geralmente a principal)
                return urls[0]
            
            time.sleep(2)
            
        except Exception as e:
            logger.debug(f"[{driver_id}] Erro ao ler window.__FOUND_VIDEO_URLS: {e}")
            time.sleep(2)
    
    logger.error(f"[{driver_id}] Timeout: extensão não capturou nenhuma URL após {max_wait}s")
    return None

def extract_video_from_wizercdn(url, driver_id):
    """Extrai URL do vídeo do Wizercdn usando extensão Video Finder"""
    start_time = time.time()
    driver = None
    
    try:
        driver = criar_navegador_firefox_com_extensions()
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
                if not mouse_click(server_selector, driver_id):
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
        
        # Passo 6: Aguardar player processar
        logger.info(f"[{driver_id}] 6. Aguardando 10 segundos para o player processar...")
        time.sleep(10)
        
        # Passo 7: Clicar no player
        logger.info(f"[{driver_id}] 7. Tentando clicar no player...")
        video_playing = False
        
        for attempt in range(3):
            logger.info(f"[{driver_id}] Tentativa {attempt + 1} de clicar no player")
            
            if try_click_player(driver, driver_id):
                if wait_for_video_playing(driver, driver_id, max_wait=10):
                    video_playing = True
                    logger.info(f"[{driver_id}] Vídeo reproduzindo após tentativa {attempt + 1}")
                    break
            
            time.sleep(2)
        
        if not video_playing:
            logger.warning(f"[{driver_id}] Vídeo não começou a reproduzir")
        
        # Passo 8: Aguardar extensão capturar URLs (IMPORTANTE: dar tempo)
        logger.info(f"[{driver_id}] 8. Aguardando extensão capturar URLs...")
        time.sleep(5)  # Aguardar requisições acontecerem
        
        # Voltar ao contexto principal para acessar window.__FOUND_VIDEO_URLS
        driver.switch_to.default_content()
        logger.info(f"[{driver_id}] Voltou ao contexto principal")
        
        # Passo 9: Obter URLs da extensão
        logger.info(f"[{driver_id}] 9. Obtendo URLs capturadas pela extensão...")
        video_url = get_video_urls_from_extension(driver, driver_id, max_wait=30)
        
        if video_url:
            elapsed = time.time() - start_time
            logger.info(f"[{driver_id}] URL capturada em {elapsed:.2f}s")
            return video_url
        
        logger.error(f"[{driver_id}] URL não capturada")
        return None
        
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
        
        result = extract_video_from_wizercdn(url, session_id)
        if result:
            return result
    
    logger.error(f"[{session_id}] Todas as tentativas falharam")
    return None

# Inicialização
download_ublock_origin()
check_video_finder_extension()

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
        
        # Verificar se extensão existe
        if not os.path.exists(VIDEO_FINDER_XPI):
            return jsonify({
                'success': False,
                'error': f'Extensão Video Finder não encontrada em: {VIDEO_FINDER_XPI}',
                'help': 'Coloque o arquivo find-video-addon.xpi na pasta extensions/',
                'request_id': request_id
            }), 500
        
        logger.info(f"[{request_id}] Nova requisição: {target_url}")
        
        video_url = extract_with_retry(target_url, 2)
        elapsed_time = time.time() - start_time
        
        if video_url:
            logger.info(f"[{request_id}] Sucesso em {elapsed_time:.2f}s")
            return jsonify({
                'success': True,
                'video_url': video_url,
                'processamento_tempo': f"{elapsed_time:.2f}s",
                'request_id': request_id
            }), 200
        else:
            logger.error(f"[{request_id}] Falha em {elapsed_time:.2f}s")
            return jsonify({
                'success': False,
                'error': 'Não foi possível extrair a URL do vídeo',
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
    video_finder_status = "Instalado" if os.path.exists(VIDEO_FINDER_XPI) else "NÃO ENCONTRADO"
    
    return jsonify({
        'status': 'OK' if os.path.exists(VIDEO_FINDER_XPI) else 'WARNING',
        'service': 'Wizercdn + Mixdrop Extractor (Video Finder Extension)',
        'ublock_origin': ublock_status,
        'video_finder_extension': video_finder_status,
        'video_finder_path': VIDEO_FINDER_XPI,
        'features': [
            'uBlock Origin integrado',
            'Extensão Video Finder customizada',
            'Captura automática via window.__FOUND_VIDEO_URLS',
            'Interceptação de requisições de vídeo',
            'Zero dependência de seletores CSS'
        ]
    }), 200

@app.route('/', methods=['GET'])
def index():
    """Página inicial"""
    ublock_status = "Instalado" if os.path.exists(UBLOCK_XPI) else "Não instalado"
    video_finder_status = "Instalado" if os.path.exists(VIDEO_FINDER_XPI) else "NÃO ENCONTRADO"
    
    return jsonify({
        'service': 'API de Extração Wizercdn + Mixdrop',
        'version': '8.0 - Custom Video Finder Extension',
        'provider': 'Wizercdn (Mixdrop)',
        'ublock_origin': ublock_status,
        'video_finder_extension': video_finder_status,
        'strategy': 'Extensão customizada que intercepta URLs de vídeo',
        'extension_path': VIDEO_FINDER_XPI,
        'setup': {
            'step1': 'Coloque find-video-addon.xpi na pasta extensions/',
            'step2': 'Execute o servidor',
            'step3': 'Faça requisições para /extrair'
        },
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
    print("API de Extração Wizercdn + Mixdrop v8.0")
    print("=" * 50)
    print("\nESTRATÉGIA: Extensão Video Finder Customizada")
    print("\nSetup:")
    print(f"  1. Coloque 'find-video-addon.xpi' em: {EXTENSIONS_DIR}")
    print("  2. A extensão será carregada automaticamente")
    print("  3. URLs serão capturadas via window.__FOUND_VIDEO_URLS")
    print("\nFluxo de Extração:")
    print("  1. Carrega extensão Video Finder")
    print("  2. Navega para página do Wizercdn")
    print("  3. Clica audio-selector e server-selector")
    print("  4. Entra nos iframes")
    print("  5. Clica play no vídeo")
    print("  6. Aguarda 5s (requisições acontecem)")
    print("  7. Lê window.__FOUND_VIDEO_URLS da extensão")
    print("  8. Retorna primeira URL encontrada")
    print("\nRecursos:")
    print("  - uBlock Origin (anti-anúncios)")
    print("  - Video Finder (captura URLs)")
    print("  - Interceptação automática de requisições")
    print("  - Zero dependência de DOM/seletores")
    print("\nStatus das Extensões:")
    print(f"  - uBlock Origin: {'✓ OK' if os.path.exists(UBLOCK_XPI) else '✗ Não encontrado'}")
    print(f"  - Video Finder: {'✓ OK' if os.path.exists(VIDEO_FINDER_XPI) else '✗ NÃO ENCONTRADO'}")
    
    if not os.path.exists(VIDEO_FINDER_XPI):
        print("\n⚠️  ATENÇÃO: Extensão Video Finder NÃO encontrada!")
        print(f"   Coloque 'find-video-addon.xpi' em: {VIDEO_FINDER_XPI}")
    
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