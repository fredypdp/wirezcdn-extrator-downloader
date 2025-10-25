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
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import requests
import platform
import zipfile
import tarfile
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logging.getLogger('urllib3').setLevel(logging.ERROR)

# Diretórios
EXTENSIONS_DIR = os.path.join(os.getcwd(), 'extensions')
UBLOCK_XPI = os.path.join(EXTENSIONS_DIR, 'ublock_origin.xpi')
DRIVERS_DIR = os.path.join(os.getcwd(), 'drivers')
GECKODRIVER_PATH = os.path.join(DRIVERS_DIR, 'geckodriver.exe' if platform.system() == 'Windows' else 'geckodriver')

load_dotenv()

# Configuração Supabase
SUPABASE_URL = "https://forfhjlkrqjpglfbiosd.supabase.co"
SUPABASE_APIKEY = os.getenv("SUPABASE_APIKEY")
SUPABASE_TABLE_FILMES = "filmes_url_warezcdn"
SUPABASE_TABLE_SERIES = "series_url_warezcdn"

# Cache local para evitar chamadas repetidas ao Supabase
_cache_local = {}

# Gerenciador de drivers persistentes
_drivers_pool = {}

if not SUPABASE_APIKEY:
    logger.error("SUPABASE_APIKEY não encontrada!")

def buscar_dados_supabase(url_pagina, tipo='filme', temporada=None, episodio=None):
    """Busca os dados completos do registro no Supabase com cache local"""
    cache_key = f"{url_pagina}_{tipo}_{temporada}_{episodio}"
    
    if cache_key in _cache_local:
        logger.info(f"Retornando do cache local")
        return _cache_local[cache_key]
    
    try:
        headers = {
            "apikey": SUPABASE_APIKEY,
            "Authorization": f"Bearer {SUPABASE_APIKEY}",
            "Content-Type": "application/json"
        }
        
        tabela = SUPABASE_TABLE_SERIES if tipo == 'serie' else SUPABASE_TABLE_FILMES
        
        if tipo == 'serie':
            if temporada is None or episodio is None:
                logger.error("Para séries é necessário informar temporada e episódio")
                return None
            
            params = {
                "select": "url,video_url,dublado,temporada_numero,episodio_numero",
                "url": f"eq.{url_pagina}",
                "temporada_numero": f"eq.{temporada}",
                "episodio_numero": f"eq.{episodio}"
            }
        else:
            params = {
                "select": "url,video_url,dublado",
                "url": f"eq.{url_pagina}"
            }
        
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/{tabela}",
            headers=headers,
            params=params,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                registro = data[0]
                logger.info(f"Registro encontrado no Supabase")
                
                resultado = None
                if registro.get('dublado') is False:
                    logger.info("Registro com dublado=False - pulando extração")
                    resultado = {'skip': True, 'reason': 'dublado=False'}
                elif registro.get('dublado') is True and registro.get('video_url'):
                    logger.info(f"video_url encontrada e dublado=True")
                    resultado = registro.get('video_url')
                elif registro.get('video_url'):
                    logger.info(f"video_url encontrada")
                    resultado = registro.get('video_url')
                else:
                    logger.info("Registro existe mas video_url está vazio")
                    resultado = None
                
                _cache_local[cache_key] = resultado
                return resultado
            else:
                logger.info("URL não encontrada no Supabase")
                return None
        else:
            logger.error(f"Erro ao buscar no Supabase: {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"Erro ao buscar dados no Supabase: {e}")
        return None

def verificar_existe_supabase(url_pagina, tipo='filme', temporada=None, episodio=None):
    """Verifica se o registro existe no Supabase"""
    try:
        headers = {
            "apikey": SUPABASE_APIKEY,
            "Authorization": f"Bearer {SUPABASE_APIKEY}",
            "Content-Type": "application/json"
        }
        
        tabela = SUPABASE_TABLE_SERIES if tipo == 'serie' else SUPABASE_TABLE_FILMES
        
        if tipo == 'serie':
            if temporada is None or episodio is None:
                logger.error("Para séries é necessário informar temporada e episódio")
                return False
            
            params = {
                "select": "url",
                "url": f"eq.{url_pagina}",
                "temporada_numero": f"eq.{temporada}",
                "episodio_numero": f"eq.{episodio}"
            }
        else:
            params = {
                "select": "url",
                "url": f"eq.{url_pagina}"
            }
        
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/{tabela}",
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

def atualizar_supabase(url_pagina, video_url, dublado=True, tipo='filme', temporada=None, episodio=None):
    """Atualiza ou cria registro no Supabase"""
    try:
        headers = {
            "apikey": SUPABASE_APIKEY,
            "Authorization": f"Bearer {SUPABASE_APIKEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal"
        }
        
        tabela = SUPABASE_TABLE_SERIES if tipo == 'serie' else SUPABASE_TABLE_FILMES
        existe = verificar_existe_supabase(url_pagina, tipo, temporada, episodio)
        
        if existe:
            logger.info("Registro existe, usando PATCH para atualizar...")
            
            if tipo == 'serie':
                params = {
                    "url": f"eq.{url_pagina}",
                    "temporada_numero": f"eq.{temporada}",
                    "episodio_numero": f"eq.{episodio}"
                }
            else:
                params = {
                    "url": f"eq.{url_pagina}"
                }
            
            data = {
                "video_url": video_url,
                "dublado": dublado
            }
            
            response = requests.patch(
                f"{SUPABASE_URL}/rest/v1/{tabela}",
                headers=headers,
                params=params,
                json=data,
                timeout=10
            )
            
            if response.status_code in [200, 204]:
                logger.info(f"Registro atualizado no Supabase com sucesso")
                # Limpar cache local
                cache_key = f"{url_pagina}_{tipo}_{temporada}_{episodio}"
                _cache_local.pop(cache_key, None)
                return True
            else:
                logger.error(f"Erro ao atualizar no Supabase: {response.status_code} - {response.text}")
                return False
        else:
            logger.info("Registro não existe, usando POST para criar...")
            
            if tipo == 'serie':
                if temporada is None or episodio is None:
                    logger.error("Para séries é necessário informar temporada e episódio")
                    return False
                
                data = {
                    "url": url_pagina,
                    "video_url": video_url,
                    "dublado": dublado,
                    "temporada_numero": temporada,
                    "episodio_numero": episodio
                }
            else:
                data = {
                    "url": url_pagina,
                    "video_url": video_url,
                    "dublado": dublado
                }
            
            response = requests.post(
                f"{SUPABASE_URL}/rest/v1/{tabela}",
                headers=headers,
                json=data,
                timeout=10
            )
            
            if response.status_code in [200, 201, 204]:
                logger.info(f"Novo registro criado no Supabase com sucesso")
                # Limpar cache local
                cache_key = f"{url_pagina}_{tipo}_{temporada}_{episodio}"
                _cache_local.pop(cache_key, None)
                return True
            else:
                logger.error(f"Erro ao criar no Supabase: {response.status_code} - {response.text}")
                return False
        
    except Exception as e:
        logger.error(f"Erro ao atualizar Supabase: {e}")
        return False

def download_geckodriver():
    """Baixa o geckodriver"""
    if not os.path.exists(DRIVERS_DIR):
        os.makedirs(DRIVERS_DIR)
        logger.info(f"Diretório de drivers criado: {DRIVERS_DIR}")
    
    if os.path.exists(GECKODRIVER_PATH):
        logger.info(f"GeckoDriver já existe: {GECKODRIVER_PATH}")
        return GECKODRIVER_PATH
    
    logger.info("Baixando GeckoDriver...")
    
    try:
        system = platform.system()
        machine = platform.machine().lower()
        
        if system == 'Windows':
            if '64' in machine or 'amd64' in machine:
                url = "https://github.com/mozilla/geckodriver/releases/download/v0.35.0/geckodriver-v0.35.0-win64.zip"
            else:
                url = "https://github.com/mozilla/geckodriver/releases/download/v0.35.0/geckodriver-v0.35.0-win32.zip"
            driver_file = "geckodriver.exe"
        elif system == 'Linux':
            if 'aarch64' in machine or 'arm64' in machine:
                url = "https://github.com/mozilla/geckodriver/releases/download/v0.35.0/geckodriver-v0.35.0-linux-aarch64.tar.gz"
            else:
                url = "https://github.com/mozilla/geckodriver/releases/download/v0.35.0/geckodriver-v0.35.0-linux64.tar.gz"
            driver_file = "geckodriver"
        elif system == 'Darwin':
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
        
        temp_file = os.path.join(DRIVERS_DIR, "geckodriver_temp")
        with open(temp_file, 'wb') as f:
            f.write(response.content)
        
        if url.endswith('.zip'):
            with zipfile.ZipFile(temp_file, 'r') as zip_ref:
                zip_ref.extractall(DRIVERS_DIR)
        else:
            with tarfile.open(temp_file, 'r:gz') as tar_ref:
                tar_ref.extractall(DRIVERS_DIR)
        
        os.remove(temp_file)
        
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

def criar_navegador_firefox_otimizado():
    """Cria navegador Firefox otimizado para velocidade"""
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
    
    # Desabilitar detecção de webdriver
    options.set_preference("dom.webdriver.enabled", False)
    options.set_preference("useAutomationExtension", False)
    
    # OTIMIZAÇÕES DE VELOCIDADE
    # Desabilitar imagens (economia de banda e processamento)
    options.set_preference("permissions.default.image", 2)
    
    # Desabilitar CSS (não necessário para extração)
    options.set_preference("permissions.default.stylesheet", 2)
    
    # Desabilitar cache
    options.set_preference("browser.cache.disk.enable", False)
    options.set_preference("browser.cache.memory.enable", False)
    options.set_preference("network.http.use-cache", False)
    
    # Timeouts agressivos
    options.set_preference("dom.max_script_run_time", 15)
    options.set_preference("dom.max_chrome_script_run_time", 15)
    
    # Desabilitar notificações
    options.set_preference("dom.webnotifications.enabled", False)
    options.set_preference("dom.push.enabled", False)
    
    # Desabilitar áudio
    options.set_preference("media.volume_scale", "0.0")
    options.set_preference("media.default_volume", "0.0")
    
    # Desabilitar plugins desnecessários
    options.set_preference("plugin.state.flash", 0)
    options.set_preference("javascript.options.showInConsole", False)
    
    # Desabilitar prefetch e preconnect
    options.set_preference("network.prefetch-next", False)
    options.set_preference("network.http.speculative-parallel-limit", 0)
    
    try:
        geckodriver_path = download_geckodriver()
        
        service = Service(geckodriver_path)
        service.service_args = ['--log', 'fatal', '--marionette-port', '0']
        
        driver = webdriver.Firefox(service=service, options=options)
        
        # Instalar uBlock se disponível (bloqueia anúncios que atrasam carregamento)
        if os.path.exists(UBLOCK_XPI):
            try:
                driver.install_addon(UBLOCK_XPI, temporary=True)
                logger.info("uBlock Origin instalado")
                time.sleep(1)
            except Exception as e:
                logger.warning(f"Erro ao instalar uBlock Origin: {e}")
        
        driver.set_page_load_timeout(20)
        driver.implicitly_wait(3)
        
        logger.info("Driver Firefox criado")
        return driver
        
    except Exception as e:
        logger.error(f"Erro ao criar driver: {e}")
        raise

def obter_driver_persistente(driver_id):
    """Obtém ou cria um driver persistente para o worker"""
    if driver_id not in _drivers_pool:
        logger.info(f"[{driver_id}] Criando novo driver persistente")
        _drivers_pool[driver_id] = criar_navegador_firefox_otimizado()
    return _drivers_pool[driver_id]

def limpar_driver_persistente(driver_id):
    """Limpa e fecha um driver persistente específico"""
    if driver_id in _drivers_pool:
        try:
            _drivers_pool[driver_id].quit()
            logger.info(f"[{driver_id}] Driver persistente fechado")
        except:
            pass
        del _drivers_pool[driver_id]

def limpar_todos_drivers():
    """Fecha todos os drivers persistentes"""
    for driver_id in list(_drivers_pool.keys()):
        limpar_driver_persistente(driver_id)
    logger.info("Todos os drivers persistentes foram fechados")

def resetar_driver(driver):
    """Reseta o estado do driver para nova extração"""
    try:
        # Limpa cookies e storage
        driver.delete_all_cookies()
        driver.execute_script("window.localStorage.clear();")
        driver.execute_script("window.sessionStorage.clear();")
        
        # Volta ao contexto principal
        driver.switch_to.default_content()
        
        # Navega para página em branco
        driver.get("about:blank")
        
        return True
    except Exception as e:
        logger.warning(f"Erro ao resetar driver: {e}")
        return False

def find_element_fast(driver, selectors, timeout=5):
    """Procura múltiplos seletores e retorna o primeiro encontrado rapidamente"""
    end_time = time.time() + timeout
    
    while time.time() < end_time:
        for selector in selectors:
            try:
                element = driver.find_element(By.CSS_SELECTOR, selector)
                if element:
                    return element
            except:
                continue
        time.sleep(0.5)
    
    return None

def smart_click(driver, element, driver_id):
    """Clica em elemento de forma otimizada"""
    try:
        # Scroll into view
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        
        # Tentar click direto JS (mais rápido)
        driver.execute_script("arguments[0].click();", element)
        logger.info(f"[{driver_id}] Clique JS executado")
        return True
        
    except Exception as e:
        # Fallback para ActionChains
        try:
            actions = ActionChains(driver)
            actions.move_to_element(element).click().perform()
            logger.info(f"[{driver_id}] Clique ActionChains executado")
            return True
        except Exception as e2:
            logger.error(f"[{driver_id}] Falha ao clicar: {e2}")
            return False

def wait_for_page_ready(driver, timeout=10):
    """Aguarda página estar pronta de forma inteligente"""
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        return True
    except:
        return False

def extrair_video_url_rapido(driver, driver_id, max_wait=20):
    """Tenta extrair URL do vídeo rapidamente sem precisar tocar"""
    logger.info(f"[{driver_id}] Tentando extração rápida da URL...")
    
    end_time = time.time() + max_wait
    
    while time.time() < end_time:
        try:
            # Script otimizado para procurar URLs de vídeo
            video_url = driver.execute_script("""
                // Procurar em elementos video
                var videos = document.querySelectorAll('video');
                for (var i = 0; i < videos.length; i++) {
                    if (videos[i].currentSrc && videos[i].currentSrc.length > 20) {
                        return videos[i].currentSrc;
                    }
                    if (videos[i].src && videos[i].src.length > 20) {
                        return videos[i].src;
                    }
                }
                
                // Procurar em source tags
                var sources = document.querySelectorAll('source');
                for (var i = 0; i < sources.length; i++) {
                    if (sources[i].src && sources[i].src.length > 20) {
                        return sources[i].src;
                    }
                }
                
                // Procurar no player Video.js
                if (window.videojs) {
                    var players = videojs.getAllPlayers();
                    if (players.length > 0 && players[0].currentSrc()) {
                        return players[0].currentSrc();
                    }
                }
                
                return null;
            """)
            
            if video_url and len(video_url) > 20:
                logger.info(f"[{driver_id}] URL extraída rapidamente!")
                return video_url
                
        except Exception as e:
            logger.debug(f"[{driver_id}] Erro na extração rápida: {e}")
        
        time.sleep(1)
    
    return None

def extrair_url_video(url, driver_id, tipo='filme', temporada=None, episodio=None, usar_driver_persistente=False):
    """
    Extrai a URL do vídeo de forma OTIMIZADA
    
    Args:
        url: URL da página para extração
        driver_id: Identificador único do driver
        tipo: 'filme' ou 'serie'
        temporada: Número da temporada (obrigatório para séries)
        episodio: Número do episódio (obrigatório para séries)
        usar_driver_persistente: Se True, mantém o driver aberto para próximas extrações
    
    Returns:
        Dicionário com resultado da extração
    """
    
    if tipo == 'serie' and (temporada is None or episodio is None):
        logger.error(f"[{driver_id}] Para séries é necessário informar temporada e episódio")
        return {
            'success': False,
            'error': 'Temporada e episódio são obrigatórios para séries'
        }
    
    identificador = f"T{temporada}E{episodio}" if tipo == 'serie' else "Filme"
    logger.info(f"[{driver_id}] Verificando cache Supabase ({identificador})...")
    
    resultado_busca = buscar_dados_supabase(url, tipo, temporada, episodio)
    
    if isinstance(resultado_busca, dict) and resultado_busca.get('skip'):
        logger.info(f"[{driver_id}] Extração pulada: {resultado_busca.get('reason')}")
        return {
            'success': False,
            'skipped': True,
            'reason': resultado_busca.get('reason'),
            'extraction_time': '0.00s',
            'dublado': False,
            'tipo': tipo,
            'temporada': temporada,
            'episodio': episodio
        }
    
    if resultado_busca and isinstance(resultado_busca, str):
        logger.info(f"[{driver_id}] video_url do cache - {identificador}")
        return {
            'success': True, 
            'video_url': resultado_busca,
            'from_cache': True,
            'extraction_time': '0.00s',
            'dublado': True,
            'tipo': tipo,
            'temporada': temporada,
            'episodio': episodio
        }
    
    logger.info(f"[{driver_id}] Iniciando extração otimizada ({identificador})...")
    start_time = time.time()
    driver = None
    driver_criado_localmente = False
    dublado = None
    
    try:
        # Obter driver (persistente ou criar novo)
        if usar_driver_persistente:
            driver = obter_driver_persistente(driver_id)
            resetar_driver(driver)
        else:
            driver = criar_navegador_firefox_otimizado()
            driver_criado_localmente = True
        
        logger.info(f"[{driver_id}] Navegando: {url}")
        
        driver.get(url)
        wait_for_page_ready(driver, timeout=10)
        time.sleep(2)
        
        # Verificar dublagem
        logger.info(f"[{driver_id}] Verificando dublagem...")
        try:
            playeroptions_audios = driver.find_element(By.CSS_SELECTOR, 'playeroptions-audios')
            classes = playeroptions_audios.get_attribute('class') or ''
            
            if 'hidden' in classes:
                logger.warning(f"[{driver_id}] Conteúdo legendado - pulando")
                dublado = False
                atualizar_supabase(url, None, dublado, tipo, temporada, episodio)
                return {
                    'success': False,
                    'skipped': True,
                    'reason': 'Conteúdo legendado',
                    'extraction_time': f"{time.time() - start_time:.2f}s",
                    'dublado': dublado,
                    'tipo': tipo,
                    'temporada': temporada,
                    'episodio': episodio
                }
        except:
            pass
        
        # Clicar em audio-selector se existir
        logger.info(f"[{driver_id}] Procurando audio-selector...")
        audio_selector = find_element_fast(driver, ['audio-selector[data-lang="2"]'], timeout=3)
        if audio_selector:
            smart_click(driver, audio_selector, driver_id)
            time.sleep(1)
        
        # Procurar server-selector
        logger.info(f"[{driver_id}] Procurando server-selector...")
        server_selectors = [
            'server-selector[data-server="mixdrop"][data-lang="2"]',
            'server-selector[data-lang="2"]'
        ]
        
        server_selector = find_element_fast(driver, server_selectors, timeout=5)
        
        if not server_selector:
            logger.warning(f"[{driver_id}] Server-selector não encontrado")
            dublado = False
            atualizar_supabase(url, None, dublado, tipo, temporada, episodio)
            raise Exception("Server-selector não encontrado")
        
        smart_click(driver, server_selector, driver_id)
        time.sleep(2)
        
        # Aguardar processamento mínimo
        logger.info(f"[{driver_id}] Aguardando iframes...")
        time.sleep(5)
        
        # Entrar nos iframes
        logger.info(f"[{driver_id}] Entrando nos iframes...")
        
        parent_iframe_selectors = [
            'embedcontent.active iframe',
            'embedcontent iframe',
            'iframe[src*="getEmbed"]'
        ]
        
        parent_iframe = find_element_fast(driver, parent_iframe_selectors, timeout=5)
        if not parent_iframe:
            raise Exception("Iframe PAI não encontrado")
        
        driver.switch_to.frame(parent_iframe)
        time.sleep(1)
        
        child_iframe_selectors = [
            'iframe[src*="mixdrop"]',
            'iframe#player',
            'iframe'
        ]
        
        child_iframe = find_element_fast(driver, child_iframe_selectors, timeout=5)
        
        if not child_iframe:
            raise Exception("Iframe FILHO não encontrado")
        
        driver.switch_to.frame(child_iframe)
        time.sleep(2)
        
        # OTIMIZAÇÃO PRINCIPAL: Tentar extração rápida primeiro
        logger.info(f"[{driver_id}] Tentando extração rápida (sem tocar vídeo)...")
        video_url = extrair_video_url_rapido(driver, driver_id, max_wait=10)
        
        # Se não conseguiu pela extração rápida, tentar o método tradicional
        if not video_url:
            logger.info(f"[{driver_id}] Extração rápida falhou, tentando método tradicional...")
            
            # Remover overlays
            try:
                driver.execute_script("""
                    var overlays = document.querySelectorAll('div[style*="position: absolute"][style*="z-index"]');
                    overlays.forEach(o => o.remove());
                """)
            except:
                pass
            
            # Tentar clicar no player
            logger.info(f"[{driver_id}] Procurando botão play...")
            play_button_selectors = [
                'button.vjs-big-play-button',
                '.vjs-play-control',
                'button[aria-label*="Play"]'
            ]
            
            play_button = find_element_fast(driver, play_button_selectors, timeout=5)
            if play_button:
                smart_click(driver, play_button, driver_id)
                time.sleep(3)
            else:
                # Tentar clicar no centro como fallback
                try:
                    width = driver.execute_script("return window.innerWidth")
                    height = driver.execute_script("return window.innerHeight")
                    actions = ActionChains(driver)
                    actions.move_by_offset(width // 2, height // 2).click().perform()
                    actions.move_by_offset(-width // 2, -height // 2).perform()
                    time.sleep(3)
                except:
                    pass
            
            # Procurar URL após tentar tocar
            logger.info(f"[{driver_id}] Procurando URL do vídeo...")
            video_url = extrair_video_url_rapido(driver, driver_id, max_wait=15)
        
        if video_url and len(video_url) > 20:
            elapsed = time.time() - start_time
            logger.info(f"[{driver_id}] ✓ URL encontrada em {elapsed:.2f}s ({identificador})")
            
            dublado = True
            atualizar_supabase(url, video_url, dublado, tipo, temporada, episodio)
            
            return {
                'success': True, 
                'video_url': video_url, 
                'from_cache': False,
                'extraction_time': f"{elapsed:.2f}s",
                'dublado': dublado,
                'tipo': tipo,
                'temporada': temporada,
                'episodio': episodio
            }
        
        return {
            'success': False, 
            'error': 'URL do vídeo não encontrada', 
            'dublado': dublado,
            'extraction_time': f"{time.time() - start_time:.2f}s",
            'tipo': tipo,
            'temporada': temporada,
            'episodio': episodio
        }
        
    except Exception as e:
        logger.error(f"[{driver_id}] Erro durante extração: {e}")
        return {
            'success': False, 
            'error': str(e), 
            'dublado': dublado,
            'extraction_time': f"{time.time() - start_time:.2f}s",
            'tipo': tipo,
            'temporada': temporada,
            'episodio': episodio
        }
    
    finally:
        # Só fecha o driver se não for persistente
        if driver and driver_criado_localmente:
            try:
                driver.quit()
                logger.info(f"[{driver_id}] Driver local fechado")
            except:
                pass

# Inicialização
download_ublock_origin()
download_geckodriver()


# ==========================================
# FUNÇÕES AUXILIARES PARA PROCESSAMENTO EM LOTE
# ==========================================

def processar_lote_urls(urls_info, max_workers=3, usar_drivers_persistentes=True):
    """
    Processa múltiplas URLs em paralelo com opção de drivers persistentes
    
    Args:
        urls_info: Lista de dicionários com 'url', 'tipo', 'temporada', 'episodio'
        max_workers: Número máximo de threads paralelas
        usar_drivers_persistentes: Se True, mantém os drivers abertos durante todo o processo
    
    Returns:
        Lista de resultados
    """
    resultados = []
    
    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            
            for idx, info in enumerate(urls_info):
                driver_id = f"Worker-{idx % max_workers + 1}"
                future = executor.submit(
                    extrair_url_video,
                    info['url'],
                    driver_id,
                    info.get('tipo', 'filme'),
                    info.get('temporada'),
                    info.get('episodio'),
                    usar_drivers_persistentes
                )
                futures[future] = info
            
            for future in as_completed(futures):
                info = futures[future]
                try:
                    resultado = future.result()
                    resultado['url_original'] = info['url']
                    resultados.append(resultado)
                    
                    # Log resumido
                    if resultado.get('success'):
                        cache = " (cache)" if resultado.get('from_cache') else ""
                        logger.info(f"✓ {info['url'][:50]}... - {resultado['extraction_time']}{cache}")
                    elif resultado.get('skipped'):
                        logger.info(f"⊘ {info['url'][:50]}... - {resultado.get('reason')}")
                    else:
                        logger.error(f"✗ {info['url'][:50]}... - {resultado.get('error', 'Erro desconhecido')}")
                        
                except Exception as e:
                    logger.error(f"✗ {info['url'][:50]}... - Exceção: {e}")
                    resultados.append({
                        'success': False,
                        'error': str(e),
                        'url_original': info['url']
                    })
    
    finally:
        # Limpar drivers persistentes ao final
        if usar_drivers_persistentes:
            logger.info("Limpando drivers persistentes...")
            limpar_todos_drivers()
    
    return resultados

def processar_urls_sequencial(urls_info, usar_driver_persistente=True):
    """
    Processa URLs de forma sequencial com um único driver persistente
    Ideal para processar muitas URLs de forma eficiente sem paralelismo
    
    Args:
        urls_info: Lista de dicionários com 'url', 'tipo', 'temporada', 'episodio'
        usar_driver_persistente: Se True, reutiliza o mesmo driver para todas as URLs
    
    Returns:
        Lista de resultados
    """
    resultados = []
    driver_id = "Sequential-Worker"
    
    try:
        for idx, info in enumerate(urls_info, 1):
            logger.info(f"\n{'='*60}")
            logger.info(f"Processando {idx}/{len(urls_info)}")
            logger.info(f"{'='*60}")
            
            resultado = extrair_url_video(
                info['url'],
                driver_id,
                info.get('tipo', 'filme'),
                info.get('temporada'),
                info.get('episodio'),
                usar_driver_persistente
            )
            
            resultado['url_original'] = info['url']
            resultados.append(resultado)
            
            # Log resumido
            if resultado.get('success'):
                cache = " (cache)" if resultado.get('from_cache') else ""
                logger.info(f"✓ {info['url'][:50]}... - {resultado['extraction_time']}{cache}")
            elif resultado.get('skipped'):
                logger.info(f"⊘ {info['url'][:50]}... - {resultado.get('reason')}")
            else:
                logger.error(f"✗ {info['url'][:50]}... - {resultado.get('error', 'Erro desconhecido')}")
            
            # Pequena pausa entre extrações
            if idx < len(urls_info):
                time.sleep(1)
    
    finally:
        # Limpar driver persistente ao final
        if usar_driver_persistente:
            logger.info("Limpando driver persistente...")
            limpar_driver_persistente(driver_id)
    
    return resultados

def limpar_cache_local():
    """Limpa o cache local em memória"""
    global _cache_local
    _cache_local.clear()
    logger.info("Cache local limpo")


# ==========================================
# EXEMPLO DE USO
# ==========================================

if __name__ == "__main__":
    # Exemplo 1: Extrair uma URL única (SEM driver persistente)
    print("\n" + "="*60)
    print("EXEMPLO 1: Extração única sem driver persistente")
    print("="*60)
    resultado = extrair_url_video(
        url="https://exemplo.com/filme",
        driver_id="Main",
        tipo='filme',
        usar_driver_persistente=False
    )
    print(f"Resultado: {resultado}")
    
    # Exemplo 2: Extrair múltiplas URLs em paralelo (COM drivers persistentes)
    print("\n" + "="*60)
    print("EXEMPLO 2: Processamento paralelo com drivers persistentes")
    print("="*60)
    urls_para_processar = [
        {
            'url': 'https://exemplo.com/filme1',
            'tipo': 'filme'
        },
        {
            'url': 'https://exemplo.com/serie1',
            'tipo': 'serie',
            'temporada': 1,
            'episodio': 1
        },
        {
            'url': 'https://exemplo.com/serie1',
            'tipo': 'serie',
            'temporada': 1,
            'episodio': 2
        }
    ]
    
    # Processar com 3 workers paralelos e drivers persistentes
    resultados = processar_lote_urls(
        urls_para_processar, 
        max_workers=3,
        usar_drivers_persistentes=True
    )
    
    # Estatísticas
    sucessos = sum(1 for r in resultados if r.get('success'))
    cache = sum(1 for r in resultados if r.get('from_cache'))
    pulados = sum(1 for r in resultados if r.get('skipped'))
    falhas = len(resultados) - sucessos - pulados
    
    print(f"\n{'='*60}")
    print(f"RESUMO DO PROCESSAMENTO PARALELO")
    print(f"{'='*60}")
    print(f"Total processado: {len(resultados)}")
    print(f"✓ Sucessos: {sucessos} (cache: {cache})")
    print(f"⊘ Pulados: {pulados}")
    print(f"✗ Falhas: {falhas}")
    print(f"{'='*60}\n")
    
    # Exemplo 3: Processamento sequencial (COM driver persistente)
    print("\n" + "="*60)
    print("EXEMPLO 3: Processamento sequencial com driver persistente")
    print("="*60)
    urls_sequenciais = [
        {
            'url': 'https://exemplo.com/filme2',
            'tipo': 'filme'
        },
        {
            'url': 'https://exemplo.com/filme3',
            'tipo': 'filme'
        },
        {
            'url': 'https://exemplo.com/serie2',
            'tipo': 'serie',
            'temporada': 1,
            'episodio': 1
        }
    ]
    
    resultados_seq = processar_urls_sequencial(
        urls_sequenciais,
        usar_driver_persistente=True
    )
    
    # Estatísticas
    sucessos_seq = sum(1 for r in resultados_seq if r.get('success'))
    cache_seq = sum(1 for r in resultados_seq if r.get('from_cache'))
    pulados_seq = sum(1 for r in resultados_seq if r.get('skipped'))
    falhas_seq = len(resultados_seq) - sucessos_seq - pulados_seq
    
    print(f"\n{'='*60}")
    print(f"RESUMO DO PROCESSAMENTO SEQUENCIAL")
    print(f"{'='*60}")
    print(f"Total processado: {len(resultados_seq)}")
    print(f"✓ Sucessos: {sucessos_seq} (cache: {cache_seq})")
    print(f"⊘ Pulados: {pulados_seq}")
    print(f"✗ Falhas: {falhas_seq}")
    print(f"{'='*60}\n")