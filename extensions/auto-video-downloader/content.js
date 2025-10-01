// Content script que roda em todas as páginas e iframes

// Injetar script na página para capturar vídeos via DOM
const script = document.createElement('script');
script.src = browser.runtime.getURL('injected.js');
script.onload = function() {
  this.remove();
};
(document.head || document.documentElement).appendChild(script);

// Expor URLs capturadas no window para acesso via Selenium
function exposeUrlsToWindow() {
  browser.storage.local.get(['capturedVideoUrls', 'downloadedUrls']).then(result => {
    const urls = result.capturedVideoUrls || [];
    const downloads = result.downloadedUrls || [];
    
    // Criar objeto global acessível via Selenium
    window.__FOUND_VIDEO_URLS = urls;
    window.__DOWNLOAD_URLS = downloads.map(d => d.url);
    
    // Log para debug
    if (urls.length > 0) {
      console.log('[AUTO VIDEO DOWNLOADER] URLs disponíveis:', urls);
    }
  });
}

// Atualizar a cada 1 segundo
setInterval(exposeUrlsToWindow, 1000);

// Também monitorar elementos de vídeo no DOM
function monitorVideoElements() {
  const videos = document.querySelectorAll('video');
  
  videos.forEach(video => {
    // Verificar currentSrc
    if (video.currentSrc && video.currentSrc.length > 10) {
      notifyVideoFound(video.currentSrc, 'video.currentSrc');
    }
    
    // Verificar src
    if (video.src && video.src.length > 10) {
      notifyVideoFound(video.src, 'video.src');
    }
    
    // Verificar source elements
    const sources = video.querySelectorAll('source');
    sources.forEach(source => {
      if (source.src && source.src.length > 10) {
        notifyVideoFound(source.src, 'source.src');
      }
    });
  });
}

// Notificar background script sobre vídeo encontrado
function notifyVideoFound(url, source) {
  console.log(`[AUTO VIDEO DOWNLOADER] Vídeo encontrado via ${source}:`, url);
  
  // Enviar para background script processar
  browser.runtime.sendMessage({
    action: 'videoFound',
    url: url,
    source: source
  });
}

// Monitorar a cada 2 segundos
setInterval(monitorVideoElements, 2000);

// Executar imediatamente
exposeUrlsToWindow();
monitorVideoElements();

console.log('[AUTO VIDEO DOWNLOADER] Content script carregado');