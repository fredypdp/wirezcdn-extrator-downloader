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
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException, ElementClickInterceptedException
from webdriver_manager.firefox import GeckoDriverManager
import threading
import queue
import concurrent.futures
from threading import Semaphore, Lock
import uuid
from contextlib import contextmanager

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(threadName)s] %(message)s')
logger = logging.getLogger(__name__)

# Desabilitar logs excessivos
logging.getLogger('WDM').setLevel(logging.ERROR)
logging.getLogger('urllib3').setLevel(logging.ERROR)

app = Flask(__name__)
CORS(app)

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
        
        # Pre-aquecer pool
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
                logger.info(f"[{driver_id}] Driver obtido do pool (reutilizado)")
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
                except:
                    pass
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
                driver.delete_all_cookies()
                driver.execute_script("window.sessionStorage.clear(); window.localStorage.clear();")
                
                if self.pool.qsize() < self.max_size:
                    self.pool.put_nowait(driver)
                    logger.info(f"[{driver_id}] Driver retornado ao pool")
                else:
                    driver.quit()
                    logger.info(f"[{driver_id}] Driver descartado (pool cheio)")
            else:
                if driver:
                    driver.quit()
                logger.warning(f"[{driver_id}] Driver não saudável descartado")
                
        except Exception as e:
            logger.error(f"[{driver_id}] Erro ao retornar driver: {e}")
            try:
                if driver:
                    driver.quit()
            except:
                pass
    
    def _is_driver_healthy(self, driver):
        try:
            driver.current_url
            driver.execute_script("return document.readyState;")
            return True
        except:
            return False
    
    def _create_driver(self):
        return criar_navegador_firefox_otimizado()
    
    def get_stats(self):
        with self.lock:
            return {
                'pool_size': self.pool.qsize(),
                'active_drivers': len(self.active_drivers),
                'max_concurrent': self.max_concurrent,
                'available_slots': self.semaphore._value
            }

# Pool global
driver_pool = DriverPool(max_size=6, max_concurrent=5)

def criar_navegador_firefox_otimizado():
    """Cria navegador Firefox otimizado com bloqueadores de anúncios"""
    options = Options()
    
    # Configurações básicas
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--width=1920")
    options.add_argument("--height=1080")
    
    # User agent
    options.set_preference("general.useragent.override", 
                          "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0")
    
    # Bloqueadores de popups e anúncios AGRESSIVOS
    options.set_preference("dom.popup_maximum", 0)
    options.set_preference("dom.popup_allowed_events", "")
    options.set_preference("dom.disable_open_during_load", True)
    options.set_preference("privacy.popups.showBrowserMessage", False)
    
    # Bloquear scripts de terceiros suspeitos
    options.set_preference("permissions.default.popup", 2)
    
    # Desabilitar notificações
    options.set_preference("dom.webnotifications.enabled", False)
    options.set_preference("dom.push.enabled", False)
    
    # Configurações anti-detecção
    options.set_preference("dom.webdriver.enabled", False)
    options.set_preference("useAutomationExtension", False)
    
    # Performance
    options.set_preference("browser.cache.disk.enable", False)
    options.set_preference("browser.cache.memory.enable", False)
    options.set_preference("network.http.use-cache", False)
    
    # Timeouts
    options.set_preference("dom.max_script_run_time", 30)
    options.set_preference("dom.max_chrome_script_run_time", 30)
    
    try:
        service = Service(GeckoDriverManager().install())
        service.service_args = ['--log', 'fatal', '--marionette-port', '0']
        
        driver = webdriver.Firefox(service=service, options=options)
        
        driver.set_page_load_timeout(30)
        driver.implicitly_wait(5)
        
        # Injetar script anti-popup AGRESSIVO
        driver.execute_cdp_cmd = lambda cmd, params: None  # Dummy para compatibilidade
        
        logger.info("Driver Firefox com bloqueadores criado!")
        return driver
        
    except Exception as e:
        logger.error(f"Erro ao criar driver: {e}")
        raise

def is_valid_wizercdn_url(url):
    """Valida URL do Wizercdn"""
    try:
        parsed = urlparse(url)
        return 'warezcdn.com' in parsed.netloc.lower() or 'embed.warezcdn.com' in parsed.netloc.lower()
    except:
        return False

def safe_click(driver, element, driver_id, max_attempts=3):
    """Clica em elemento com proteção contra popups"""
    for attempt in range(max_attempts):
        try:
            # Scroll para elemento
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
            time.sleep(0.5)
            
            # Fechar qualquer popup que possa ter aparecido
            close_popups(driver, driver_id)
            
            # Tentar click JavaScript primeiro (mais seguro contra popups)
            try:
                driver.execute_script("arguments[0].click();", element)
                logger.info(f"[{driver_id}] Clique JS executado com sucesso")
                return True
            except:
                # Se falhar, tentar click normal
                element.click()
                logger.info(f"[{driver_id}] Clique normal executado")
                return True
                
        except ElementClickInterceptedException:
            logger.warning(f"[{driver_id}] Clique interceptado, tentativa {attempt+1}/{max_attempts}")
            close_popups(driver, driver_id)
            time.sleep(1)
        except Exception as e:
            logger.error(f"[{driver_id}] Erro ao clicar (tentativa {attempt+1}): {e}")
            time.sleep(1)
    
    return False

def close_popups(driver, driver_id):
    """Fecha todos os popups e janelas indesejadas"""
    try:
        # Fechar alertas JavaScript
        try:
            driver.switch_to.alert.dismiss()
            logger.info(f"[{driver_id}] Alerta JS fechado")
        except:
            pass
        
        # Fechar janelas extras (mantém apenas a principal)
        main_window = driver.current_window_handle
        all_windows = driver.window_handles
        
        for window in all_windows:
            if window != main_window:
                driver.switch_to.window(window)
                driver.close()
                logger.info(f"[{driver_id}] Popup/janela extra fechada")
        
        driver.switch_to.window(main_window)
        
        # Remover overlays via JavaScript
        driver.execute_script("""
            // Remover overlays comuns de anúncios
            var overlays = document.querySelectorAll('[class*="overlay"], [class*="popup"], [id*="popup"], [class*="modal"]');
            overlays.forEach(function(el) {
                if (el && el.parentNode) {
                    el.parentNode.removeChild(el);
                }
            });
            
            // Remover iframes de anúncios
            var iframes = document.querySelectorAll('iframe:not([id*="player"]):not([class*="player"])');
            iframes.forEach(function(iframe) {
                if (iframe && iframe.src && !iframe.src.includes('mixdrop')) {
                    try {
                        iframe.parentNode.removeChild(iframe);
                    } catch(e) {}
                }
            });
        """)
        
    except Exception as e:
        logger.debug(f"[{driver_id}] Erro ao fechar popups: {e}")

def extract_video_from_wizercdn(url, driver_id, timeout=60):
    """Extrai URL do vídeo do Wizercdn seguindo o fluxo especificado"""
    start_time = time.time()
    
    try:
        with driver_pool.get_driver() as (driver, assigned_id):
            logger.info(f"[{assigned_id}] 🎬 Iniciando extração Wizercdn: {url}")
            
            # Passo 1: Navegar para a página
            logger.info(f"[{assigned_id}] 1️⃣ Navegando para a página...")
            driver.get(url)
            time.sleep(3)
            
            # Fechar popups iniciais
            close_popups(driver, assigned_id)
            
            # Passo 2 e 3: Clicar no audio-selector com mixdrop e lang=2
            logger.info(f"[{assigned_id}] 2️⃣ Procurando audio-selector (mixdrop, lang=2)...")
            try:
                audio_selector = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'audio-selector[data-servers="mixdrop"][data-lang="2"]'))
                )
                logger.info(f"[{assigned_id}] ✅ Audio-selector encontrado")
                
                if not safe_click(driver, audio_selector, assigned_id):
                    raise Exception("Falha ao clicar no audio-selector")
                
                time.sleep(2)
                close_popups(driver, assigned_id)
                
                # Verificar se ficou ativo
                has_active = driver.execute_script("""
                    var el = document.querySelector('audio-selector[data-servers="mixdrop"][data-lang="2"]');
                    return el ? el.classList.contains('active') : false;
                """)
                logger.info(f"[{assigned_id}] Audio-selector active: {has_active}")
                
            except TimeoutException:
                logger.error(f"[{assigned_id}] ❌ Audio-selector não encontrado")
                return None
            
            # Passo 4 e 5: Clicar no server-selector com mixdrop e lang=2
            logger.info(f"[{assigned_id}] 3️⃣ Procurando server-selector (mixdrop, lang=2)...")
            try:
                server_selector = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'server-selector[data-servers="mixdrop"][data-lang="2"]'))
                )
                logger.info(f"[{assigned_id}] ✅ Server-selector encontrado")
                
                if not safe_click(driver, server_selector, assigned_id):
                    raise Exception("Falha ao clicar no server-selector")
                
                time.sleep(2)
                close_popups(driver, assigned_id)
                
            except TimeoutException:
                logger.error(f"[{assigned_id}] ❌ Server-selector não encontrado")
                return None
            
            # Passo 6: Aguardar 10 segundos
            logger.info(f"[{assigned_id}] 4️⃣ Aguardando 10 segundos...")
            time.sleep(10)
            close_popups(driver, assigned_id)
            
            # Passo 7: Clicar no player de reprodução
            logger.info(f"[{assigned_id}] 5️⃣ Procurando player de reprodução...")
            
            # Tentar diversos seletores comuns de players
            player_selectors = [
                'div[class*="player"]',
                'div[id*="player"]',
                'video',
                'iframe[src*="mixdrop"]',
                '.video-container',
                '#video-player',
                'button[class*="play"]'
            ]
            
            player_clicked = False
            for selector in player_selectors:
                try:
                    player = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    logger.info(f"[{assigned_id}] ✅ Player encontrado: {selector}")
                    
                    if safe_click(driver, player, assigned_id):
                        player_clicked = True
                        logger.info(f"[{assigned_id}] ✅ Player clicado")
                        break
                except:
                    continue
            
            if not player_clicked:
                logger.warning(f"[{assigned_id}] ⚠️ Player não encontrado, continuando...")
            
            time.sleep(3)
            close_popups(driver, assigned_id)
            
            # Passo 8: Procurar pelo elemento de vídeo com id="videojs_html5_api"
            logger.info(f"[{assigned_id}] 6️⃣ Procurando elemento de vídeo (id=videojs_html5_api)...")
            
            max_wait = 30
            start_search = time.time()
            video_url = None
            
            while time.time() - start_search < max_wait:
                try:
                    # Fechar popups constantemente
                    close_popups(driver, assigned_id)
                    
                    # Buscar vídeo pelo ID específico
                    video_url = driver.execute_script("""
                        var video = document.getElementById('videojs_html5_api');
                        if (video && video.src) {
                            return video.src;
                        }
                        
                        // Fallback: procurar qualquer vídeo com src válida
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
                        logger.info(f"[{assigned_id}] ✅ URL do vídeo encontrada em {elapsed:.2f}s!")
                        logger.info(f"[{assigned_id}] URL: {video_url[:100]}...")
                        return video_url
                    
                    time.sleep(2)
                    
                except Exception as e:
                    logger.debug(f"[{assigned_id}] Erro na busca: {e}")
                    time.sleep(2)
            
            logger.error(f"[{assigned_id}] ❌ URL do vídeo não encontrada após {max_wait}s")
            return None
            
    except Exception as e:
        logger.error(f"[{driver_id}] Erro durante extração: {e}")
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
                'error': 'URL deve ser do domínio warezcdn.com',
                'request_id': request_id
            }), 400
        
        logger.info(f"[{request_id}] 🚀 Nova requisição: {target_url}")
        
        # Verificar disponibilidade
        stats = driver_pool.get_stats()
        if stats['available_slots'] <= 0:
            return jsonify({
                'success': False,
                'error': 'Servidor ocupado. Tente novamente em alguns segundos.',
                'request_id': request_id
            }), 503
        
        # Executar extração
        try:
            future = thread_pool.submit(extract_with_retry, target_url, 2)
            video_url = future.result(timeout=90)
            
        except concurrent.futures.TimeoutError:
            logger.error(f"[{request_id}] Timeout total da operação")
            return jsonify({
                'success': False,
                'error': 'Timeout na operação. Tente novamente.',
                'request_id': request_id
            }), 408
        
        elapsed_time = time.time() - start_time
        
        if video_url:
            logger.info(f"[{request_id}] ✅ Sucesso em {elapsed_time:.2f}s")
            return jsonify({
                'success': True,
                'video_url': video_url,
                'processamento_tempo': f"{elapsed_time:.2f}s",
                'request_id': request_id
            }), 200
        else:
            logger.error(f"[{request_id}] ❌ Falha em {elapsed_time:.2f}s")
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
    stats = driver_pool.get_stats()
    
    return jsonify({
        'status': 'OK',
        'service': 'Wizercdn + Mixdrop Extractor',
        'pool_stats': stats,
        'features': [
            'Bloqueadores agressivos de popups',
            'Suporte a 5 extrações simultâneas',
            'Auto-retry em caso de falha',
            'Proteção contra interceptação de cliques'
        ]
    }), 200

@app.route('/', methods=['GET'])
def index():
    """Página inicial"""
    return jsonify({
        'service': 'API de Extração Wizercdn + Mixdrop 🎬',
        'version': '1.0',
        'provider': 'Wizercdn (Mixdrop)',
        'endpoints': {
            '/extrair?url=<URL>': 'Extrair URL de vídeo',
            '/health': 'Status da API',
            '/': 'Esta página'
        },
        'url_format': {
            'movie': 'https://embed.warezcdn.com/filme/{imdb_id}',
            'tv': 'https://embed.warezcdn.com/serie/{imdb_id}/{season}/{episode}'
        },
        'example': 'http://localhost:5000/extrair?url=https://embed.warezcdn.com/filme/tt1234567',
        'features': [
            '✅ Bloqueio agressivo de popups',
            '✅ Seleção automática Mixdrop + Lang=2',
            '✅ Cliques protegidos contra interceptação',
            '✅ Retry automático',
            '✅ Pool de drivers otimizado'
        ]
    })

# Limpeza
import atexit

def cleanup():
    logger.info("🧹 Limpando recursos...")
    try:
        thread_pool.shutdown(wait=True, timeout=10)
    except:
        pass
    
    try:
        while not driver_pool.pool.empty():
            try:
                driver = driver_pool.pool.get_nowait()
                driver.quit()
            except:
                pass
        
        for driver_info in driver_pool.active_drivers.values():
            try:
                driver_info['driver'].quit()
            except:
                pass
    except:
        pass

atexit.register(cleanup)

if __name__ == "__main__":
    print("🎬 API de Extração Wizercdn + Mixdrop")
    print("=" * 50)
    print("\n🔧 Recursos:")
    print("  • Bloqueadores agressivos de popups")
    print("  • Seleção automática: Mixdrop + Lang=2")
    print("  • Cliques protegidos contra interceptação")
    print("  • Pool de drivers otimizado (5 simultâneas)")
    print("  • Auto-retry em caso de falha")
    print("\n🎯 Endpoint:")
    print("  GET /extrair?url=<URL>")
    print("\n📋 Formato de URL:")
    print("  Filme:  https://embed.warezcdn.com/filme/{imdb_id}")
    print("  Série:  https://embed.warezcdn.com/serie/{imdb_id}/{season}/{episode}")
    print("\n💡 Exemplo:")
    print("  http://localhost:5000/extrair?url=https://embed.warezcdn.com/filme/tt1234567")
    print("\n🚀 Iniciando servidor em http://0.0.0.0:5000")
    print("=" * 50)
    
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False,
        threaded=True
    )