import time
import logging
import os
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
import requests
import platform
import zipfile
import tarfile

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Desabilitar logs excessivos
logging.getLogger('urllib3').setLevel(logging.ERROR)

# Diretórios
EXTENSIONS_DIR = os.path.join(os.getcwd(), 'extensions')
UBLOCK_XPI = os.path.join(EXTENSIONS_DIR, 'ublock_origin.xpi')
DRIVERS_DIR = os.path.join(os.getcwd(), 'drivers')
GECKODRIVER_PATH = os.path.join(DRIVERS_DIR, 'geckodriver.exe' if platform.system() == 'Windows' else 'geckodriver')

# Carregar as variáveis de ambiente do arquivo .env
load_dotenv()

# Configuração Supabase
SUPABASE_URL = "https://forfhjlkrqjpglfbiosd.supabase.co"
SUPABASE_APIKEY = os.getenv("SUPABASE_APIKEY")
SUPABASE_TABLE = "filmes_url_warezcdn"

if not SUPABASE_APIKEY:
    logger.error("SUPABASE_APIKEY não encontrada nas variáveis de ambiente!")

def buscar_dados_supabase(url_pagina):
    """Busca os dados completos do registro no Supabase pela URL da página"""
    try:
        headers = {
            "apikey": SUPABASE_APIKEY,
            "Authorization": f"Bearer {SUPABASE_APIKEY}",
            "Content-Type": "application/json"
        }
        
        params = {
            "select": "url,video_url,dublado",
            "url": f"eq.{url_pagina}"
        }
        
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}",
            headers=headers,
            params=params,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                registro = data[0]
                logger.info(f"Registro encontrado no Supabase")
                
                # CASO 1: dublado=False - sempre pula
                if registro.get('dublado') is False:
                    logger.info("Registro com dublado=False - pulando extração")
                    return {'skip': True, 'reason': 'dublado=False'}
                
                # CASO 2: dublado=True E video_url preenchido - pula e retorna URL do cache
                if registro.get('dublado') is True and registro.get('video_url'):
                    logger.info(f"video_url encontrada e dublado=True: {registro.get('video_url')[:80]}...")
                    return registro.get('video_url')
                
                # CASO 3: video_url existe mas dublado não é True (None ou outro valor)
                # Retorna o video_url existente
                if registro.get('video_url'):
                    logger.info(f"video_url encontrada: {registro.get('video_url')[:80]}...")
                    return registro.get('video_url')
                
                # CASO 4: registro existe mas video_url está vazio - permite extração
                logger.info("Registro existe mas video_url está vazio - permitindo extração")
                return None
            else:
                logger.info("URL não encontrada no Supabase")
                return None
        else:
            logger.error(f"Erro ao buscar no Supabase: {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"Erro ao buscar dados no Supabase: {e}")
        return None
            
    except Exception as e:
        logger.error(f"Erro ao buscar dados no Supabase: {e}")
        return None

def verificar_existe_supabase(url_pagina):
    """Verifica se o registro existe no Supabase"""
    try:
        headers = {
            "apikey": SUPABASE_APIKEY,
            "Authorization": f"Bearer {SUPABASE_APIKEY}",
            "Content-Type": "application/json"
        }
        
        params = {
            "select": "url",
            "url": f"eq.{url_pagina}"
        }
        
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}",
            headers=headers,
            params=params,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            existe = data and len(data) > 0
            logger.info(f"Registro {'existe' if existe else 'não existe'} no Supabase")
            return existe
        else:
            logger.error(f"Erro ao verificar existência no Supabase: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"Erro ao verificar existência no Supabase: {e}")
        return False

def atualizar_supabase(url_pagina, video_url, dublado=True):
    """Atualiza ou cria registro no Supabase"""
    try:
        headers = {
            "apikey": SUPABASE_APIKEY,
            "Authorization": f"Bearer {SUPABASE_APIKEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal"
        }
        
        # Verifica se o registro existe
        existe = verificar_existe_supabase(url_pagina)
        
        if existe:
            # Registro existe - usa PATCH para atualizar
            logger.info("Registro existe, usando PATCH para atualizar...")
            params = {
                "url": f"eq.{url_pagina}"
            }
            
            data = {
                "video_url": video_url,
                "dublado": dublado
            }
            
            response = requests.patch(
                f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}",
                headers=headers,
                params=params,
                json=data,
                timeout=10
            )
            
            if response.status_code in [200, 204]:
                logger.info(f"Registro atualizado no Supabase com sucesso")
                return True
            else:
                logger.error(f"Erro ao atualizar no Supabase: {response.status_code} - {response.text}")
                return False
        else:
            # Registro não existe - usa POST para criar
            logger.info("Registro não existe, usando POST para criar...")
            data = {
                "url": url_pagina,
                "video_url": video_url,
                "dublado": dublado
            }
            
            response = requests.post(
                f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}",
                headers=headers,
                json=data,
                timeout=10
            )
            
            if response.status_code in [200, 201, 204]:
                logger.info(f"Novo registro criado no Supabase com sucesso")
                return True
            else:
                logger.error(f"Erro ao criar no Supabase: {response.status_code} - {response.text}")
                return False
        
    except Exception as e:
        logger.error(f"Erro ao atualizar Supabase: {e}")
        return False

def download_geckodriver():
    """Baixa o geckodriver diretamente sem usar a API do GitHub"""
    if not os.path.exists(DRIVERS_DIR):
        os.makedirs(DRIVERS_DIR)
        logger.info(f"Diretório de drivers criado: {DRIVERS_DIR}")
    
    if os.path.exists(GECKODRIVER_PATH):
        logger.info(f"GeckoDriver já existe: {GECKODRIVER_PATH}")
        return GECKODRIVER_PATH
    
    logger.info("Baixando GeckoDriver...")
    
    try:
        # Detectar sistema operacional
        system = platform.system()
        machine = platform.machine().lower()
        
        # URL direta para a versão 0.35.0 (última estável)
        if system == 'Windows':
            if '64' in machine or 'amd64' in machine:
                url = "https://github.com/mozilla/geckodriver/releases/download/v0.35.0/geckodriver-v0.35.0-win64.zip"
                driver_file = "geckodriver.exe"
            else:
                url = "https://github.com/mozilla/geckodriver/releases/download/v0.35.0/geckodriver-v0.35.0-win32.zip"
                driver_file = "geckodriver.exe"
        elif system == 'Linux':
            if 'aarch64' in machine or 'arm64' in machine:
                url = "https://github.com/mozilla/geckodriver/releases/download/v0.35.0/geckodriver-v0.35.0-linux-aarch64.tar.gz"
            else:
                url = "https://github.com/mozilla/geckodriver/releases/download/v0.35.0/geckodriver-v0.35.0-linux64.tar.gz"
            driver_file = "geckodriver"
        elif system == 'Darwin':  # macOS
            if 'arm64' in machine:
                url = "https://github.com/mozilla/geckodriver/releases/download/v0.35.0/geckodriver-v0.35.0-macos-aarch64.tar.gz"
            else:
                url = "https://github.com/mozilla/geckodriver/releases/download/v0.35.0/geckodriver-v0.35.0-macos.tar.gz"
            driver_file = "geckodriver"
        else:
            raise Exception(f"Sistema operacional não suportado: {system}")
        
        logger.info(f"Baixando de: {url}")
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        
        # Salvar arquivo temporário
        temp_file = os.path.join(DRIVERS_DIR, "geckodriver_temp")
        with open(temp_file, 'wb') as f:
            f.write(response.content)
        
        # Extrair arquivo
        if url.endswith('.zip'):
            with zipfile.ZipFile(temp_file, 'r') as zip_ref:
                zip_ref.extractall(DRIVERS_DIR)
        else:
            with tarfile.open(temp_file, 'r:gz') as tar_ref:
                tar_ref.extractall(DRIVERS_DIR)
        
        # Remover arquivo temporário
        os.remove(temp_file)
        
        # Dar permissão de execução no Linux/macOS
        if system != 'Windows':
            os.chmod(GECKODRIVER_PATH, 0o755)
        
        logger.info(f"GeckoDriver baixado com sucesso: {GECKODRIVER_PATH}")
        return GECKODRIVER_PATH
        
    except Exception as e:
        logger.error(f"Erro ao baixar GeckoDriver: {e}")
        raise

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

    # Mutar o áudio do navegador
    options.set_preference("media.volume_scale", "0.0")
    options.set_preference("media.default_volume", "0.0")
    
    try:
        # Baixar geckodriver se necessário
        geckodriver_path = download_geckodriver()
        
        service = Service(geckodriver_path)
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
    
    logger.info(f"[{driver_id}] Estratégia 2: Procurando span 'Play Video'")
    try:
        play_span = driver.find_element(By.XPATH, "//span[contains(text(), 'Play Video')]")
        play_button_parent = play_span.find_element(By.XPATH, "./..")
        
        if mouse_click(driver, play_button_parent, driver_id):
            logger.info(f"[{driver_id}] Estratégia 2 funcionou")
            return True
    except Exception as e:
        logger.warning(f"[{driver_id}] Estratégia 2 falhou: {e}")
    
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
                logger.info(f"[{driver_id}] Vídeo está reproduzindo")
                return True
        except Exception as e:
            logger.debug(f"[{driver_id}] Erro ao verificar vjs-playing: {e}")
        
        time.sleep(1)
    
    logger.warning(f"[{driver_id}] Timeout aguardando vjs-playing")
    return False

def extrair_url_video(url, driver_id):
    """Extrai a URL do vídeo de uma página do Warezcdn"""
    
    logger.info(f"[{driver_id}] Verificando se video_url já existe no Supabase...")
    resultado_busca = buscar_dados_supabase(url)
    
    # Se é um dict com 'skip', não extrai
    if isinstance(resultado_busca, dict) and resultado_busca.get('skip'):
        logger.info(f"[{driver_id}] Extração pulada: {resultado_busca.get('reason')}")
        return {
            'success': False,
            'skipped': True,
            'reason': resultado_busca.get('reason'),
            'extraction_time': '0.00s'
        }
    
    # Se encontrou video_url válida
    if resultado_busca and isinstance(resultado_busca, str):
        logger.info(f"[{driver_id}] video_url encontrada no Supabase (cache)")
        return {
            'success': True, 
            'video_url': resultado_busca,
            'from_cache': True,
            'extraction_time': '0.00s'
        }
    
    logger.info(f"[{driver_id}] video_url não encontrada, iniciando extração...")
    start_time = time.time()
    driver = None
    dublado = None  # Padrão é nulo
    
    try:
        driver = criar_navegador_firefox_com_ublock()
        logger.info(f"[{driver_id}] Iniciando extração: {url}")
        
        logger.info(f"[{driver_id}] 1. Navegando para a página...")
        driver.get(url)
        time.sleep(3)
        
        logger.info(f"[{driver_id}] 2. Procurando audio-selector...")
        try:
            audio_selectors = ['audio-selector[data-lang="2"]']
            audio_selector = None
            for selector in audio_selectors:
                try:
                    audio_selector = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    logger.info(f"[{driver_id}] Audio-selector encontrado")
                    break
                except:
                    continue
            
            if audio_selector:
                if mouse_click(driver, audio_selector, driver_id):
                    logger.info(f"[{driver_id}] Audio-selector clicado")
                    time.sleep(2)
        except Exception as e:
            logger.warning(f"[{driver_id}] Erro com audio-selector: {e}")
        
        logger.info(f"[{driver_id}] 3. Procurando server-selector...")
        server_selectors = [
            'server-selector[data-server="mixdrop"][data-lang="2"]',
            'server-selector[data-lang="2"]'
        ]
        
        server_selector = None
        for selector in server_selectors:
            try:
                server_selector = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                logger.info(f"[{driver_id}] Server-selector encontrado")
                break
            except:
                continue
        
        if not server_selector:
            logger.warning(f"[{driver_id}] Server-selector não encontrado - conteúdo não dublado")
            # Marca como False no Supabase para não tentar extrair novamente
            dublado = False
            atualizar_supabase(url, None, dublado)
            raise Exception("Server-selector não encontrado - não dublado")
        
        if not mouse_click(driver, server_selector, driver_id):
            raise Exception("Falha ao clicar no server-selector")
        
        time.sleep(2)
        
        logger.info(f"[{driver_id}] 4. Aguardando 10 segundos...")
        time.sleep(10)
        
        logger.info(f"[{driver_id}] 5. Entrando nos iframes...")
        
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
                break
            except:
                continue
        
        if not parent_iframe:
            raise Exception("Iframe PAI não encontrado")
        
        driver.switch_to.frame(parent_iframe)
        time.sleep(2)
        
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
                break
            except:
                continue
        
        if not child_iframe:
            raise Exception("Iframe FILHO não encontrado")
        
        driver.switch_to.frame(child_iframe)
        time.sleep(2)
        
        logger.info(f"[{driver_id}] 6. Aguardando player processar...")
        time.sleep(10)
        
        logger.info(f"[{driver_id}] 7. Removendo overlays...")
        try:
            removed = driver.execute_script("""
                var overlays = document.querySelectorAll('div[style*="position: absolute"][style*="z-index: 2147483646"]');
                var count = overlays.length;
                overlays.forEach(o => o.remove());
                return count;
            """)
            logger.info(f"[{driver_id}] {removed} overlay(s) removido(s)")
        except Exception as e:
            logger.warning(f"[{driver_id}] Erro ao remover overlays: {e}")
        
        logger.info(f"[{driver_id}] 8. Tentando clicar no player...")
        for attempt in range(3):
            if try_click_player(driver, driver_id):
                if wait_for_video_playing(driver, driver_id):
                    time.sleep(10)
                    break
            time.sleep(2)
        
        logger.info(f"[{driver_id}] 9. Procurando URL do vídeo...")
        
        max_wait = 30
        start_search = time.time()
        
        while time.time() - start_search < max_wait:
            try:
                video_url = driver.execute_script("""
                    var video = document.getElementById('videojs_html5_api');
                    if (video && (video.currentSrc || video.src)) {
                        return video.currentSrc || video.src;
                    }
                    var videos = document.querySelectorAll('video');
                    for (var i = 0; i < videos.length; i++) {
                        if (videos[i].currentSrc || videos[i].src) {
                            return videos[i].currentSrc || videos[i].src;
                        }
                    }
                    return null;
                """)
                
                if video_url and len(video_url) > 10:
                    elapsed = time.time() - start_time
                    logger.info(f"[{driver_id}] URL encontrada!")
                    
                    # Marca como dublado apenas quando extrai a URL com sucesso
                    dublado = True
                    
                    # Salva no Supabase
                    atualizar_supabase(url, video_url, dublado)
                    
                    return {
                        'success': True, 
                        'video_url': video_url, 
                        'from_cache': False,
                        'extraction_time': f"{elapsed:.2f}s",
                        'dublado': dublado
                    }
                
                time.sleep(2)
            except Exception as e:
                time.sleep(2)
        
        return {'success': False, 'error': 'URL do vídeo não encontrada', 'dublado': dublado}
        
    except Exception as e:
        logger.error(f"[{driver_id}] Erro durante extração: {e}")
        return {'success': False, 'error': str(e), 'dublado': dublado}
    
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass

# Inicialização
download_ublock_origin()
download_geckodriver()