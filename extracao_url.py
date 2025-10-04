import time
import logging
import os
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from webdriver_manager.firefox import GeckoDriverManager
import requests

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Desabilitar logs excessivos
logging.getLogger('WDM').setLevel(logging.ERROR)
logging.getLogger('urllib3').setLevel(logging.ERROR)

# Diretórios
EXTENSIONS_DIR = os.path.join(os.getcwd(), 'extensions')
UBLOCK_XPI = os.path.join(EXTENSIONS_DIR, 'ublock_origin.xpi')

# Arquivo JSON para armazenar URLs
JSON_FILE = os.path.join(os.getcwd(), 'url_extraidas_filmes.json')

def carregar_json():
    """
    Carrega o arquivo JSON com as URLs extraídas
    
    Returns:
        list: Lista de objetos com url e video_url
    """
    try:
        if os.path.exists(JSON_FILE):
            with open(JSON_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.info(f"JSON carregado com {len(data)} registros")
                return data
        else:
            logger.info("Arquivo JSON não existe, criando novo")
            return []
    except Exception as e:
        logger.error(f"Erro ao carregar JSON: {e}")
        return []

def salvar_json(data):
    """
    Salva os dados no arquivo JSON
    
    Args:
        data: Lista de objetos com url e video_url
        
    Returns:
        bool: True se salvo com sucesso, False caso contrário
    """
    try:
        with open(JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        logger.info(f"JSON salvo com {len(data)} registros")
        return True
    except Exception as e:
        logger.error(f"Erro ao salvar JSON: {e}")
        return False

def verificar_video_url_existente(url_pagina):
    """
    Verifica se a URL da página já possui video_url no arquivo JSON
    
    Args:
        url_pagina: URL da página do Warezcdn
        
    Returns:
        str ou None: video_url se encontrado, None caso contrário
    """
    try:
        data = carregar_json()
        
        for item in data:
            if item.get('url') == url_pagina:
                video_url = item.get('video_url')
                if video_url:
                    logger.info(f"video_url já existe no JSON: {video_url[:80]}...")
                    return video_url
                else:
                    logger.info("Registro encontrado mas video_url está vazio")
                    return None
        
        logger.info("URL não encontrada no JSON")
        return None
            
    except Exception as e:
        logger.error(f"Erro ao verificar video_url no JSON: {e}")
        return None

def atualizar_video_url_json(url_pagina, video_url):
    """
    Atualiza ou adiciona o campo video_url no arquivo JSON
    
    Args:
        url_pagina: URL da página do Warezcdn
        video_url: URL do vídeo extraída
        
    Returns:
        bool: True se atualizado com sucesso, False caso contrário
    """
    try:
        data = carregar_json()
        
        # Procurar se a URL já existe
        encontrado = False
        for item in data:
            if item.get('url') == url_pagina:
                item['video_url'] = video_url
                encontrado = True
                logger.info(f"video_url atualizada no JSON")
                break
        
        # Se não existe, adicionar novo registro
        if not encontrado:
            data.append({
                'url': url_pagina,
                'video_url': video_url
            })
            logger.info(f"Novo registro adicionado ao JSON")
        
        return salvar_json(data)
        
    except Exception as e:
        logger.error(f"Erro ao atualizar video_url no JSON: {e}")
        return False

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

def extrair_url_video(url, driver_id):
    """
    Extrai a URL do vídeo de uma página do Warezcdn
    Verifica primeiro se já existe no arquivo JSON
    
    Args:
        url: URL da página do Warezcdn (filme ou série)
        driver_id: ID para logging
        
    Returns:
        dict: {'success': True, 'video_url': 'url', 'from_cache': bool} ou {'success': False, 'error': 'mensagem'}
    """
    # Verificar primeiro se já existe no JSON
    logger.info(f"[{driver_id}] Verificando se video_url já existe no JSON...")
    video_url_existente = verificar_video_url_existente(url)
    
    if video_url_existente:
        logger.info(f"[{driver_id}] video_url encontrada no cache do JSON")
        return {
            'success': True, 
            'video_url': video_url_existente,
            'from_cache': True,
            'extraction_time': '0.00s'
        }
    
    # Se não existe, fazer extração
    logger.info(f"[{driver_id}] video_url não encontrada, iniciando extração...")
    start_time = time.time()
    driver = None
    
    try:
        driver = criar_navegador_firefox_com_ublock()
        logger.info(f"[{driver_id}] Iniciando extração: {url}")
        
        # Passo 1: Navegar
        logger.info(f"[{driver_id}] 1. Navegando para a página...")
        driver.get(url)
        time.sleep(3)
        
        # Passo 2: Audio-selector (OPCIONAL - se não achar, pula para server-selector)
        logger.info(f"[{driver_id}] 2. Procurando audio-selector (mixdrop, lang=2)...")
        try:
            audio_selectors = [
                'audio-selector[data-lang="2"]',
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
            
            if audio_selector:
                if mouse_click(driver, audio_selector, driver_id):
                    logger.info(f"[{driver_id}] Audio-selector clicado com sucesso")
                    time.sleep(2)
                else:
                    logger.warning(f"[{driver_id}] Falha ao clicar no audio-selector")
            else:
                logger.warning(f"[{driver_id}] Audio-selector não encontrado - pulando para server-selector")
            
        except Exception as e:
            logger.warning(f"[{driver_id}] Erro com audio-selector (não crítico): {e}")
        
        # Passo 3: Server-selector (OBRIGATÓRIO)
        logger.info(f"[{driver_id}] 3. Procurando server-selector (mixdrop, lang=2)...")
        try:
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
                    logger.info(f"[{driver_id}] Server-selector encontrado: {selector}")
                    break
                except:
                    continue
            
            if not server_selector:
                raise Exception("Server-selector não encontrado")
            
            if not mouse_click(driver, server_selector, driver_id):
                raise Exception("Falha ao clicar no server-selector")
            
            time.sleep(2)
            
        except Exception as e:
            logger.error(f"[{driver_id}] Erro com server-selector: {e}")
            return {'success': False, 'error': f'Erro com server-selector: {str(e)}'}
        
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
            return {'success': False, 'error': f'Erro ao processar iframes: {str(e)}'}
        
        # Passo 6: Aguardar player processar (10 segundos)
        logger.info(f"[{driver_id}] 6. Aguardando 10 segundos para o player processar...")
        time.sleep(10)
        
        # Passo 7: Remover elementos de popup/overlay
        logger.info(f"[{driver_id}] 7. Removendo overlays/popups...")
        try:
            removed_count = driver.execute_script("""
                var overlays = document.querySelectorAll('div[style*="position: absolute"][style*="z-index: 2147483646"]');
                var count = overlays.length;
                overlays.forEach(function(overlay) {
                    overlay.remove();
                });
                return count;
            """)
            logger.info(f"[{driver_id}] {removed_count} overlay(s) removido(s)")
            time.sleep(1)
        except Exception as e:
            logger.warning(f"[{driver_id}] Erro ao remover overlays: {e}")
        
        # Passo 8: Tentar clicar no player até funcionar
        logger.info(f"[{driver_id}] 8. Tentando clicar no player...")
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
        
        # Passo 9: Buscar URL do vídeo
        logger.info(f"[{driver_id}] 9. Procurando URL do vídeo...")
        
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
                    logger.info(f"[{driver_id}] URL: {video_url[:80]}...")
                    
                    # Atualizar arquivo JSON
                    logger.info(f"[{driver_id}] Atualizando arquivo JSON...")
                    atualizar_video_url_json(url, video_url)
                    
                    return {
                        'success': True, 
                        'video_url': video_url, 
                        'from_cache': False,
                        'extraction_time': f"{elapsed:.2f}s"
                    }
                
                time.sleep(2)
                
            except Exception as e:
                logger.debug(f"[{driver_id}] Erro na busca: {e}")
                time.sleep(2)
        
        logger.error(f"[{driver_id}] URL não encontrada")
        return {'success': False, 'error': 'URL do vídeo não encontrada'}
        
    except Exception as e:
        logger.error(f"[{driver_id}] Erro durante extração: {e}")
        return {'success': False, 'error': str(e)}
    
    finally:
        if driver:
            try:
                driver.quit()
                logger.info(f"[{driver_id}] Driver fechado")
            except Exception as e:
                logger.error(f"[{driver_id}] Erro ao fechar driver: {e}")

# Baixar uBlock Origin na inicialização do módulo
download_ublock_origin()