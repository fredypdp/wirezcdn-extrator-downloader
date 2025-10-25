import requests
from bs4 import BeautifulSoup
import re
import logging
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

class ExtracaoHibrida:
    """Combina scraping rápido com Selenium quando necessário"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def extrair_com_requests(self, url):
        """
        Tenta extrair URL do vídeo usando apenas requests + BeautifulSoup
        MUITO MAIS RÁPIDO que Selenium (2-3s vs 40-50s)
        """
        try:
            logger.info(f"🚀 Tentando extração rápida para: {url}")
            
            # 1. Buscar página principal
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 2. Procurar server-selector com data-lang="2" (dublado)
            server_selector = soup.find('server-selector', {'data-lang': '2'})
            
            if not server_selector:
                logger.warning("❌ Conteúdo não dublado (server-selector ausente)")
                return {
                    'success': False, 
                    'reason': 'not_dubbed',
                    'video_url': None
                }
            
            # 3. Extrair URL do embed do server-selector
            embed_url = server_selector.get('data-url')
            if not embed_url:
                logger.warning("❌ data-url não encontrado no server-selector")
                return {'success': False, 'reason': 'no_embed_url'}
            
            # Construir URL completo do embed
            if not embed_url.startswith('http'):
                embed_url = urljoin(url, embed_url)
            
            logger.info(f"📡 URL do embed encontrado: {embed_url[:80]}...")
            
            # 4. Buscar página do embed
            embed_response = self.session.get(embed_url, timeout=15)
            embed_soup = BeautifulSoup(embed_response.content, 'html.parser')
            
            # 5. Procurar iframe do Mixdrop
            mixdrop_iframe = embed_soup.find('iframe', src=re.compile(r'mixdrop'))
            
            if not mixdrop_iframe:
                logger.warning("❌ Iframe do Mixdrop não encontrado")
                return {'success': False, 'reason': 'no_mixdrop_iframe'}
            
            mixdrop_url = mixdrop_iframe['src']
            logger.info(f"🎬 URL do Mixdrop: {mixdrop_url[:80]}...")
            
            # 6. Buscar página do Mixdrop e extrair URL do vídeo
            mixdrop_response = self.session.get(mixdrop_url, timeout=15)
            
            # Procurar padrões de URL de vídeo no HTML/JS
            video_url = self._extrair_url_do_mixdrop(mixdrop_response.text)
            
            if video_url:
                logger.info(f"✅ URL do vídeo extraída com sucesso!")
                return {
                    'success': True,
                    'video_url': video_url,
                    'method': 'fast_scraping'
                }
            
            logger.warning("❌ URL do vídeo não encontrada no Mixdrop")
            return {'success': False, 'reason': 'video_url_not_found'}
            
        except Exception as e:
            logger.error(f"❌ Erro na extração rápida: {e}")
            return {'success': False, 'reason': str(e)}
    
    def _extrair_url_do_mixdrop(self, html_content):
        """
        Extrai URL do vídeo do HTML do Mixdrop
        Procura por padrões comuns
        """
        # Padrão 1: URL direta em variável JavaScript
        patterns = [
            r'vsr\s*=\s*["\']([^"\']+)["\']',
            r'MDCore\.wurl\s*=\s*["\']([^"\']+)["\']',
            r'file:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
            r'src:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
            r'https?://[^\s"\']+\.m3u8[^\s"\']*',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html_content)
            if match:
                url = match.group(1) if len(match.groups()) > 0 else match.group(0)
                if url.startswith('http'):
                    return url
        
        # Padrão 2: URL codificada/ofuscada
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Procurar em tags <video>
        video_tags = soup.find_all('video')
        for video in video_tags:
            src = video.get('src') or video.get('data-src')
            if src and ('.m3u8' in src or 'mixdrop' in src):
                return src
        
        # Procurar em <source> dentro de <video>
        source_tags = soup.find_all('source')
        for source in source_tags:
            src = source.get('src')
            if src and ('.m3u8' in src or 'mixdrop' in src):
                return src
        
        return None


def extrair_url_video_otimizado(url, driver_id, usar_selenium_fallback=True):
    """
    Versão otimizada que tenta scraping rápido primeiro
    
    Args:
        url: URL da página do Warezcdn
        driver_id: ID do driver para logging
        usar_selenium_fallback: Se True, usa Selenium como fallback
    
    Returns:
        dict com resultado da extração
    """
    import time
    from extracao_url import extrair_url_video  # Seu código Selenium original
    
    start_time = time.time()
    
    # ETAPA 1: Tentar extração rápida
    logger.info(f"[{driver_id}] 🚀 Iniciando extração híbrida...")
    
    extrator = ExtracaoHibrida()
    resultado = extrator.extrair_com_requests(url)
    
    if resultado['success']:
        elapsed = time.time() - start_time
        logger.info(f"[{driver_id}] ✅ Extração rápida concluída em {elapsed:.2f}s")
        return {
            'success': True,
            'video_repro_url': resultado['video_url'],
            'from_cache': False,
            'extraction_time': f"{elapsed:.2f}s",
            'method': 'fast_scraping',
            'dublado': True
        }
    
    # Se não é dublado, não tenta Selenium
    if resultado.get('reason') == 'not_dubbed':
        logger.info(f"[{driver_id}] ⏭️ Conteúdo não dublado, pulando Selenium")
        return {
            'success': False,
            'skipped': True,
            'reason': 'not_dubbed',
            'extraction_time': f"{time.time() - start_time:.2f}s"
        }
    
    # ETAPA 2: Fallback para Selenium se habilitado
    if usar_selenium_fallback:
        logger.info(f"[{driver_id}] ⚠️ Extração rápida falhou, usando Selenium...")
        logger.info(f"[{driver_id}] Motivo: {resultado.get('reason')}")
        
        return extrair_url_video(url, driver_id)
    
    # Se não usar fallback, retorna falha
    elapsed = time.time() - start_time
    return {
        'success': False,
        'error': resultado.get('reason', 'Extração rápida falhou'),
        'extraction_time': f"{elapsed:.2f}s"
    }


# Exemplo de uso
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    url_teste = "https://exemplo.warezcdn.com/filme"
    resultado = extrair_url_video_otimizado(url_teste, "TEST-001")
    
    print(f"\n{'='*60}")
    print(f"Resultado: {resultado}")
    print(f"{'='*60}")
