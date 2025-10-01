// Script injetado diretamente na página (acesso total ao DOM)

(function() {
  'use strict';
  
  console.log('[AUTO VIDEO DOWNLOADER] Script injetado na página');
  
  // Interceptar XMLHttpRequest para capturar URLs
  const originalOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(method, url) {
    if (isVideoUrl(url)) {
      console.log('[AUTO VIDEO DOWNLOADER] XHR detectado:', url);
      window.postMessage({
        type: 'VIDEO_URL_FOUND',
        url: url,
        source: 'XMLHttpRequest'
      }, '*');
    }
    return originalOpen.apply(this, arguments);
  };
  
  // Interceptar fetch para capturar URLs
  const originalFetch = window.fetch;
  window.fetch = function(url, options) {
    if (typeof url === 'string' && isVideoUrl(url)) {
      console.log('[AUTO VIDEO DOWNLOADER] Fetch detectado:', url);
      window.postMessage({
        type: 'VIDEO_URL_FOUND',
        url: url,
        source: 'fetch'
      }, '*');
    }
    return originalFetch.apply(this, arguments);
  };
  
  // Função para verificar se é URL de vídeo
  function isVideoUrl(url) {
    if (typeof url !== 'string') return false;
    
    const patterns = [
      /\.mp4/i,
      /\.mkv/i,
      /\.webm/i,
      /\.m3u8/i,
      /\.ts$/i,
      /video/i,
      /stream/i,
      /mixdrop/i
    ];
    
    return patterns.some(pattern => pattern.test(url));
  }
  
  // Monitorar elementos de vídeo adicionados dinamicamente
  const observer = new MutationObserver(mutations => {
    mutations.forEach(mutation => {
      mutation.addedNodes.forEach(node => {
        if (node.tagName === 'VIDEO') {
          checkVideoElement(node);
        }
        if (node.querySelectorAll) {
          node.querySelectorAll('video').forEach(checkVideoElement);
        }
      });
    });
  });
  
  observer.observe(document.documentElement, {
    childList: true,
    subtree: true
  });
  
  // Verificar elemento de vídeo
  function checkVideoElement(video) {
    // Event listener para quando vídeo começar a carregar
    video.addEventListener('loadstart', function() {
      if (this.currentSrc) {
        console.log('[AUTO VIDEO DOWNLOADER] Video loadstart:', this.currentSrc);
        window.postMessage({
          type: 'VIDEO_URL_FOUND',
          url: this.currentSrc,
          source: 'video.loadstart'
        }, '*');
      }
    });
    
    // Event listener para quando vídeo estiver pronto
    video.addEventListener('canplay', function() {
      if (this.currentSrc) {
        console.log('[AUTO VIDEO DOWNLOADER] Video canplay:', this.currentSrc);
        window.postMessage({
          type: 'VIDEO_URL_FOUND',
          url: this.currentSrc,
          source: 'video.canplay'
        }, '*');
      }
    });
    
    // Verificar imediatamente
    if (video.currentSrc) {
      console.log('[AUTO VIDEO DOWNLOADER] Video já carregado:', video.currentSrc);
      window.postMessage({
        type: 'VIDEO_URL_FOUND',
        url: video.currentSrc,
        source: 'video.immediate'
      }, '*');
    }
  }
  
  // Verificar vídeos existentes
  document.querySelectorAll('video').forEach(checkVideoElement);
  
})();