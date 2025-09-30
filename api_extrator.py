import time
import logging
from urllib.parse import urlparse, parse_qs
from flask import Flask, request, jsonify
from flask_cors import CORS
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from webdriver_manager.firefox import GeckoDriverManager
import threading
import queue
import concurrent.futures
from threading import Semaphore, Lock
import uuid
from contextlib import contextmanager
import os
import requests

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(threadName)s] %(message)s')
logger = logging.getLogger(__name__)

# Desabilitar logs excessivos
logging.getLogger('WDM').setLevel(logging.ERROR)
logging.getLogger('urllib3').setLevel(logging.ERROR)

app = Flask(__name__)
CORS(app)

# Diretório para extensões
EXTENSIONS_DIR = os.path.join(os.getcwd(), 'extensions')
UBLOCK_XPI = os.path.join(EXTENSIONS_DIR, 'ublock_origin.xpi')

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

# Pool de drivers otimizado
class DriverPool:
    def __init__(self, max_size=6, max_concurrent=5):
        self.pool = queue.Queue(maxsize=max_size)
        self.max_size = max_size
        self.max_concurrent = max_concurrent
        self.lock = Lock()
        self.active_drivers = {}
        self.semaphore = Semaphore(max_concurrent)
        self.creation_lock = Lock()
        
        self._preheat_pool(min(3, max_size))
    
    def _preheat_pool(self, count):
        logger.info(f"Pre-aquecendo pool com {count} drivers...")
        for i in range(count):
            try:
                driver = self._create_driver()
                self.pool.put_nowait(driver)
                logger.info(f"Driver {i+1}/{count} pre-aquecido")
            except Exception as e:
                logger.error(f"Erro ao pre-aquecer driver {i+1}: {e}")
    
    @contextmanager
    def get_driver(self):
        driver_id = None
        driver = None
        
        if not self.semaphore.acquire(timeout=30):
            raise TimeoutException("Timeout aguardando slot de driver disponível")
        
        try:
            with self.lock:
                driver_id = str(uuid.uuid4())[:8]
                logger.info(f"[{driver_id}] Obtendo driver do pool...")
            
            try:
                driver = self.pool.get_nowait()
                try:
                    driver.title
                    logger.info(f"[{driver_id}] Driver obtido do pool (reutilizado)")
                except:
                    logger.warning(f"[{driver_id}] Driver do pool não funcional, criando novo...")
                    try:
                        driver.quit()
                    except:
                        pass
                    with self.creation_lock:
                        driver = self._create_driver()
                        logger.info(f"[{driver_id}] Novo driver criado")
            except queue.Empty:
                with self.creation_lock:
                    logger.info(f"[{driver_id}] Pool vazio, criando novo driver...")
                    driver = self._create_driver()
                    logger.info(f"[{driver_id}] Novo driver criado")
            
            with self.lock:
                self.active_drivers[driver_id] = {
                    'driver': driver,
                    'start_time': time.time(),
                    'thread': threading.current_thread().name
                }
            
            try:
                driver.current_url
                yield driver, driver_id
            except:
                logger.warning(f"[{driver_id}] Driver corrompido, criando novo...")
                try:
                    driver.quit()
                except Exception as e:
                    logger.error(f"[{driver_id}] Erro ao fechar driver corrompido: {e}")
                driver = self._create_driver()
                yield driver, driver_id
            
        finally:
            if driver and driver_id:
                with self.lock:
                    if driver_id in self.active_drivers:
                        del self.active_drivers[driver_id]
                
                self._return_driver(driver, driver_id)
            
            self.semaphore.release()
    
    def _return_driver(self, driver, driver_id):
        try:
            if driver and self._is_driver_healthy(driver):
                try:
                    driver.delete_all_cookies()
                    driver.execute_script("window.sessionStorage.clear(); window.localStorage.clear();")
                except:
                    logger.warning(f"[{driver_id}] Erro ao limpar cookies/storage")
                
                if self.pool.qsize() < self.max_size:
                    self.pool.put_nowait(driver)
                    logger.info(f"[{driver_id}] Driver retornado ao pool")
                else:
                    try:
                        driver.quit()
                        logger.info(f"[{driver_id}] Driver descartado (pool cheio)")
                    except Exception as e:
                        logger.error(f"[{driver_id}] Erro ao fechar driver: {e}")
            else:
                try:
                    if driver:
                        driver.quit()
                        logger.warning(f"[{driver_id}] Driver não saudável descartado")
                except Exception as e:
                    logger.error(f"[{driver_id}] Erro ao fechar driver não saudável: {e}")
                
        except Exception as e:
            logger.error(f"[{driver_id}] Erro ao retornar driver: {e}")
            try:
                if driver:
                    driver.quit()
            except Exception as quit_error:
                logger.error(f"[{driver_id}] Erro ao fechar driver na exceção: {quit_error}")
    
    def _is_driver_healthy(self, driver):
        try:
            driver.current_url
            driver.title
            return True
        except:
            return False
    
    def _create_driver(self):
        return criar_navegador_firefox_com_ublock()
    
    def get_stats(self):
        with self.lock:
            return {
                'pool_size': self.pool.qsize(),
                'active_drivers': len(self.active_drivers),
                'max_concurrent': self.max_concurrent,
                'available_slots': self.semaphore._value
            }
    
    def force_cleanup_driver(self, driver):
        """Força o fechamento de um driver com múltiplas tentativas"""
        try:
            driver.quit()
            logger.info("Driver fechado normalmente")
            return True
        except Exception as e:
            logger.warning(f"Primeira tentativa de fechar driver falhou: {e}")
            
        try:
            if hasattr(driver, 'service') and driver.service:
                driver.service.stop()
                logger.info("Driver service parado")
        except Exception as e:
            logger.warning(f"Erro ao parar service: {e}")
        
        try:
            import signal
            if hasattr(driver, 'service') and hasattr(driver.service, 'process'):
                driver.service.process.send_signal(signal.SIGTERM)
                logger.info("Processo do driver terminado via SIGTERM")
        except Exception as e:
            logger.warning(f"Erro ao enviar SIGTERM: {e}")
        
        return False

def criar_navegador_firefox_com_ublock():
    """Cria navegador Firefox com uBlock Origin"""
    options = Options()
    
    options.add_argument("--headless")
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
    
    if os.path.exists(UBLOCK_XPI):
        logger.info("Carregando uBlock Origin...")
    
    try:
        service = Service(GeckoDriverManager().install())
        service.service_args = ['--log', 'fatal', '--marionette-port', '0']
        
        driver = webdriver.Firefox(service=service, options=options)
        
        if os.path.exists(UBLOCK_XPI):
            try:
                driver.install_addon(UBLOCK_XPI, temporary=True)
                logger.info("uBlock Origin instalado com sucesso")
                time.sleep(2)
            except Exception as e:
                logger.warning(f"Erro ao instalar uBlock Origin: {e}")
        
        driver.set_page_load_timeout(30)
        driver.implicitly_wait(5)
        
        logger.info("Driver Firefox com uBlock Origin criado")
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

def safe_click(driver, element, driver_id, max_attempts=3):
    """Clica em elemento de forma simples"""
    for attempt in range(max_attempts):
        try:
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
            time.sleep(0.5)
            
            try:
                driver.execute_script("arguments[0].click();", element)
                logger.info(f"[{driver_id}] Clique JS executado com sucesso")
                return True
            except:
                element.click()
                logger.info(f"[{driver_id}] Clique normal executado")
                return True
                
        except Exception as e:
            logger.error(f"[{driver_id}] Erro ao clicar (tentativa {attempt+1}): {e}")
            time.sleep(1)
    
    return False

def click_center_page(driver, driver_id):
    """Clica exatamente no centro da página"""
    try:
        width = driver.execute_script("return window.innerWidth")
        height = driver.execute_script("return window.innerHeight")
        center_x = width // 2
        center_y = height // 2
        
        driver.execute_script(f"""
            var evt = new MouseEvent('click', {{
                view: window,
                bubbles: true,
                cancelable: true,
                clientX: {center_x},
                clientY: {center_y}
            }});
            document.elementFromPoint({center_x}, {center_y}).dispatchEvent(evt);
        """)
        logger.info(f"[{driver_id}] Clique no centro da página ({center_x}, {center_y})")
        return True
    except Exception as e:
        logger.error(f"[{driver_id}] Erro ao clicar no centro: {e}")
        return False

def extract_video_from_wizercdn(url, driver_id, timeout=60):
    """Extrai URL do vídeo do Wizercdn seguindo o fluxo especificado"""
    start_time = time.time()
    driver = None
    assigned_id = None
    
    try:
        with driver_pool.get_driver() as (driver, assigned_id):
            logger.info(f"[{assigned_id}] Iniciando extração Wizercdn: {url}")
            
            # Passo 1: Navegar para a página
            logger.info(f"[{assigned_id}] 1. Navegando para a página...")
            driver.get(url)
            time.sleep(3)
            
            # Passo 2 e 3: Clicar no audio-selector
            logger.info(f"[{assigned_id}] 2. Procurando audio-selector (mixdrop, lang=2)...")
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
                        logger.info(f"[{assigned_id}] Audio-selector encontrado com: {selector}")
                        break
                    except:
                        continue
                
                if not audio_selector:
                    raise Exception("Audio-selector não encontrado")
                
                if not safe_click(driver, audio_selector, assigned_id):
                    raise Exception("Falha ao clicar no audio-selector")
                
                time.sleep(2)
                
            except Exception as e:
                logger.error(f"[{assigned_id}] Erro com audio-selector: {e}")
                return None
            
            # Passo 4 e 5: Clicar no server-selector
            logger.info(f"[{assigned_id}] 3. Procurando server-selector (mixdrop, lang=2)...")
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
                        logger.info(f"[{assigned_id}] Server-selector encontrado com: {selector}")
                        break
                    except:
                        continue
                
                if server_selector:
                    if not safe_click(driver, server_selector, assigned_id):
                        logger.warning(f"[{assigned_id}] Falha ao clicar no server-selector")
                else:
                    logger.warning(f"[{assigned_id}] Server-selector não encontrado")
                
                time.sleep(2)
                
            except Exception as e:
                logger.warning(f"[{assigned_id}] Erro com server-selector: {e}")
            
            # Passo 6: Aguardar
            logger.info(f"[{assigned_id}] 4. Aguardando 10 segundos...")
            time.sleep(10)
            
            # Passo 7: Mudar para os iframes (pai e filho) e clicar no botão de play
            logger.info(f"[{assigned_id}] 5. Procurando iframes aninhados do player...")
            
            player_clicked = False
            
            try:
                # PRIMEIRO: Entrar no iframe PAI (embedcontent > iframe com getEmbed.php)
                logger.info(f"[{assigned_id}] Procurando iframe PAI (embedcontent)...")
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
                        logger.info(f"[{assigned_id}] Iframe PAI encontrado com: {selector}")
                        break
                    except:
                        continue
                
                if not parent_iframe:
                    raise Exception("Iframe PAI (embedcontent) não encontrado")
                
                # Entrar no iframe PAI
                driver.switch_to.frame(parent_iframe)
                logger.info(f"[{assigned_id}] Entrou no iframe PAI")
                time.sleep(2)
                
                # SEGUNDO: Entrar no iframe FILHO (mixdrop player dentro do iframe pai)
                logger.info(f"[{assigned_id}] Procurando iframe FILHO (mixdrop player)...")
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
                        logger.info(f"[{assigned_id}] Iframe FILHO encontrado com: {selector}")
                        break
                    except:
                        continue
                
                if not child_iframe:
                    raise Exception("Iframe FILHO (mixdrop) não encontrado")
                
                # Entrar no iframe FILHO
                driver.switch_to.frame(child_iframe)
                logger.info(f"[{assigned_id}] Entrou no iframe FILHO (mixdrop)")
                time.sleep(2)
                
                # Agora procurar o botão de play dentro do iframe filho
                logger.info(f"[{assigned_id}] Procurando botão de play dentro do iframe filho...")
                
                # Estratégia 1: Procurar pelo botão vjs-big-play-button
                try:
                    play_button = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'button.vjs-big-play-button'))
                    )
                    logger.info(f"[{assigned_id}] Botão vjs-big-play-button encontrado")
                    
                    WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, 'button.vjs-big-play-button'))
                    )
                    
                    # CLICAR 2 VEZES com intervalo de 5 segundos
                    if safe_click(driver, play_button, assigned_id):
                        logger.info(f"[{assigned_id}] Primeiro clique no botão de play")
                        time.sleep(5)
                        if safe_click(driver, play_button, assigned_id):
                            logger.info(f"[{assigned_id}] Segundo clique no botão de play")
                            player_clicked = True
                        
                except Exception as e:
                    logger.warning(f"[{assigned_id}] Botão vjs-big-play-button não encontrado: {e}")
                
                # Estratégia 2: Procurar por span com texto "Play Video"
                if not player_clicked:
                    logger.info(f"[{assigned_id}] Procurando span com texto 'Play Video'...")
                    try:
                        play_span = driver.find_element(By.XPATH, "//span[contains(text(), 'Play Video')]")
                        play_button_parent = play_span.find_element(By.XPATH, "./..")
                        
                        # CLICAR 2 VEZES com intervalo de 5 segundos
                        if safe_click(driver, play_button_parent, assigned_id):
                            logger.info(f"[{assigned_id}] Primeiro clique no 'Play Video'")
                            time.sleep(5)
                            if safe_click(driver, play_button_parent, assigned_id):
                                logger.info(f"[{assigned_id}] Segundo clique no 'Play Video'")
                                player_clicked = True
                    except Exception as e:
                        logger.warning(f"[{assigned_id}] Span 'Play Video' não encontrado: {e}")
                
                # Estratégia 3: Clicar exatamente no centro da página
                if not player_clicked:
                    logger.info(f"[{assigned_id}] Tentando clicar no centro exato da página...")
                    # CLICAR 2 VEZES com intervalo de 5 segundos
                    if click_center_page(driver, assigned_id):
                        logger.info(f"[{assigned_id}] Primeiro clique no centro")
                        time.sleep(5)
                        if click_center_page(driver, assigned_id):
                            logger.info(f"[{assigned_id}] Segundo clique no centro")
                            player_clicked = True
                    else:
                        logger.warning(f"[{assigned_id}] Falha ao clicar no centro")
                
                if not player_clicked:
                    logger.warning(f"[{assigned_id}] Não foi possível clicar em nenhum player no iframe")
                
                # PERMANECER no contexto do iframe filho para buscar o vídeo
                logger.info(f"[{assigned_id}] Permanecendo no iframe filho para buscar URL do vídeo...")
                
            except Exception as e:
                logger.error(f"[{assigned_id}] Erro ao processar iframes: {e}")
                # Se houver erro, tentar voltar ao contexto principal
                try:
                    driver.switch_to.default_content()
                    logger.warning(f"[{assigned_id}] Voltou ao contexto principal após erro")
                except:
                    pass
                return None
            
            time.sleep(3)
            
            # Passo 8: Buscar URL do vídeo (permanecendo no iframe filho)
            logger.info(f"[{assigned_id}] 6. Procurando elemento de vídeo dentro do iframe filho...")
            
            max_wait = 30
            start_search = time.time()
            video_url = None
            
            while time.time() - start_search < max_wait:
                try:
                    # Buscar dentro do iframe filho (mixdrop) onde está o video
                    video_url = driver.execute_script("""
                        var video = document.getElementById('videojs_html5_api');
                        if (video && video.src) {
                            return video.src;
                        }
                        
                        var videos = document.querySelectorAll('video');
                        for (var i = 0; i < videos.length; i++) {
                            if (videos[i].src && (videos[i].src.includes('.mp4') || 
                                                   videos[i].src.includes('.m3u8') || 
                                                   videos[i].src.includes('mixdrop'))) {
                                return videos[i].src;
                            }
                        }
                        
                        return null;
                    """)
                    
                    if video_url:
                        elapsed = time.time() - start_time
                        logger.info(f"[{assigned_id}] URL encontrada em {elapsed:.2f}s")
                        return video_url
                    
                    time.sleep(2)
                    
                except Exception as e:
                    logger.debug(f"[{assigned_id}] Erro na busca: {e}")
                    time.sleep(2)
            
            logger.error(f"[{assigned_id}] URL não encontrada após {max_wait}s")
            return None
    
    except KeyboardInterrupt:
        logger.warning(f"[{driver_id}] Interrupção do usuário detectada")
        if driver:
            try:
                driver_pool.force_cleanup_driver(driver)
            except:
                pass
        raise
            
    except Exception as e:
        logger.error(f"[{driver_id}] Erro durante extração: {e}")
        if driver and assigned_id:
            logger.info(f"[{assigned_id}] Tentando fechar driver após erro...")
            try:
                driver_pool.force_cleanup_driver(driver)
            except Exception as cleanup_error:
                logger.error(f"[{assigned_id}] Erro ao limpar driver: {cleanup_error}")
        return None

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

# Thread pool
thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=5, thread_name_prefix="WizerExtractor")

# Baixar uBlock Origin na inicialização
download_ublock_origin()

# Pool global
driver_pool = DriverPool(max_size=6, max_concurrent=5)

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
        
        stats = driver_pool.get_stats()
        if stats['available_slots'] <= 0:
            return jsonify({
                'success': False,
                'error': 'Servidor ocupado. Tente novamente.',
                'request_id': request_id
            }), 503
        
        try:
            future = thread_pool.submit(extract_with_retry, target_url, 2)
            video_url = future.result(timeout=120)
            
        except concurrent.futures.TimeoutError:
            logger.error(f"[{request_id}] Timeout")
            return jsonify({
                'success': False,
                'error': 'Timeout na operação',
                'request_id': request_id
            }), 408
        
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

@app.route('/cleanup', methods=['POST'])
def force_cleanup():
    """Força limpeza de todos os drivers"""
    try:
        cleanup()
        return jsonify({
            'success': True,
            'message': 'Limpeza forçada executada'
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    stats = driver_pool.get_stats()
    ublock_status = "Instalado" if os.path.exists(UBLOCK_XPI) else "Não instalado"
    
    return jsonify({
        'status': 'OK',
        'service': 'Wizercdn + Mixdrop Extractor',
        'ublock_origin': ublock_status,
        'pool_stats': stats,
        'features': [
            'uBlock Origin integrado',
            'Suporte a 5 extrações simultâneas',
            'Auto-retry em caso de falha',
            'Navegação em iframes aninhados',
            'Duplo clique no player'
        ]
    }), 200

@app.route('/', methods=['GET'])
def index():
    """Página inicial"""
    ublock_status = "Instalado" if os.path.exists(UBLOCK_XPI) else "Não instalado"
    
    return jsonify({
        'service': 'API de Extração Wizercdn + Mixdrop',
        'version': '2.1',
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
        'example': 'http://localhost:5000/extrair?url=https://embed.warezcdn.cc/filme/tt1234567',
        'features': [
            'uBlock Origin integrado',
            'Bloqueio automático de anúncios',
            'Seleção automática Mixdrop + Lang=2',
            'Navegação em iframes aninhados (pai > filho)',
            'Duplo clique no player (5s de intervalo)',
            'Pool de drivers otimizado'
        ]
    })

# Limpeza
import atexit

def cleanup():
    logger.info("Limpando recursos...")
    
    # Fechar thread pool
    try:
        thread_pool.shutdown(wait=True, timeout=10)
        logger.info("Thread pool encerrado")
    except Exception as e:
        logger.error(f"Erro ao fechar thread pool: {e}")
    
    # Fechar todos os drivers do pool
    closed_count = 0
    try:
        while not driver_pool.pool.empty():
            try:
                driver = driver_pool.pool.get_nowait()
                driver.quit()
                closed_count += 1
                logger.info(f"Driver do pool fechado ({closed_count})")
            except Exception as e:
                logger.error(f"Erro ao fechar driver do pool: {e}")
    except Exception as e:
        logger.error(f"Erro ao processar pool: {e}")
    
    # Fechar drivers ativos
    active_count = 0
    try:
        active_drivers_copy = dict(driver_pool.active_drivers)
        for driver_id, driver_info in active_drivers_copy.items():
            try:
                driver_info['driver'].quit()
                active_count += 1
                logger.info(f"Driver ativo fechado: {driver_id} ({active_count})")
            except Exception as e:
                logger.error(f"Erro ao fechar driver ativo {driver_id}: {e}")
    except Exception as e:
        logger.error(f"Erro ao processar drivers ativos: {e}")
    
    logger.info(f"Limpeza concluída: {closed_count} do pool + {active_count} ativos = {closed_count + active_count} drivers fechados")
    
    # Tentar matar processos Firefox que possam ter ficado órfãos
    try:
        import psutil
        firefox_count = 0
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if 'firefox' in proc.info['name'].lower() or 'geckodriver' in proc.info['name'].lower():
                    proc.kill()
                    firefox_count += 1
            except:
                pass
        if firefox_count > 0:
            logger.info(f"{firefox_count} processos Firefox/Geckodriver órfãos eliminados")
    except ImportError:
        logger.warning("psutil não instalado - não foi possível limpar processos órfãos")
    except Exception as e:
        logger.error(f"Erro ao limpar processos: {e}")

atexit.register(cleanup)

if __name__ == "__main__":
    print("API de Extração Wizercdn + Mixdrop")
    print("=" * 50)
    print("\nuBlock Origin:")
    if os.path.exists(UBLOCK_XPI):
        print("  Instalado e ativo")
    else:
        print("  Não encontrado - baixando...")
    print("\nRecursos:")
    print("  - uBlock Origin para bloqueio de anúncios")
    print("  - Seleção automática: Mixdrop + Lang=2")
    print("  - Navegação em iframes aninhados (pai > filho)")
    print("  - Duplo clique no player (5s de intervalo)")
    print("  - Pool de drivers otimizado (5 simultâneas)")
    print("  - Auto-retry em caso de falha")
    print("\nEndpoint:")
    print("  GET /extrair?url=<URL>")
    print("\nFormato de URL:")
    print("  Filme:  https://embed.warezcdn.cc/filme/{imdb_id}")
    print("  Série:  https://embed.warezcdn.cc/serie/{imdb_id}/{season}/{episode}")
    print("\nExemplo:")
    print("  http://localhost:5000/extrair?url=https://embed.warezcdn.cc/filme/tt1234567")
    print("\nIniciando servidor em http://0.0.0.0:5000")
    print("=" * 50)
    
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False,
        threaded=True
    )