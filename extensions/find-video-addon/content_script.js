(function(){
  if(window.__FIND_VIDEO_INITIALIZED) return;
  window.__FIND_VIDEO_INITIALIZED = true;

  window.__FOUND_VIDEO_URLS = [];
  let scanCount = 0;

  function addUrl(u, source){
    if(!u) return;
    if(typeof u !== 'string') u = String(u);
    
    if(u.length < 10) return;
    if(u.startsWith('data:')) return;
    if(u.startsWith('blob:')) return;
    if(u.startsWith('chrome:')) return;
    if(u.startsWith('about:')) return;
    
    if(!window.__FOUND_VIDEO_URLS.includes(u)){
      window.__FOUND_VIDEO_URLS.push(u);
      console.log(`[FindVideo Content] Nova URL [${source}]:`, u);
      
      // Notifica background
      try {
        browser.runtime.sendMessage({
          type: 'addUrl', 
          url: u,
          source: source
        }).catch(() => {});
      } catch(e){}
      
      // Evento customizado
      window.dispatchEvent(new CustomEvent('videoUrlFound', { 
        detail: { url: u, source: source }
      }));
    }
  }

  // Recebe do background
  browser.runtime.onMessage.addListener(msg => {
    if(msg && msg.type === 'videoUrlFound' && msg.url) {
      addUrl(msg.url, 'background');
    }
  });

  // Scan completo do DOM
  function scanDOM(){
    scanCount++;
    try {
      // Todos os elementos de vídeo
      document.querySelectorAll('video, audio, source').forEach(el => {
        try {
          if(el.currentSrc) addUrl(el.currentSrc, 'dom-currentSrc');
          if(el.src) addUrl(el.src, 'dom-src');
          
          // Atributos data-*
          ['data-src', 'data-url', 'data-video-src', 'data-video-url', 
           'data-file', 'data-stream', 'data-source'].forEach(attr => {
            const val = el.getAttribute(attr);
            if(val) addUrl(val, `dom-${attr}`);
          });
        } catch(e){}
      });
      
      // Links de vídeo
      document.querySelectorAll('a[href]').forEach(el => {
        try {
          const href = el.href;
          if(href && /\.(mp4|m3u8|webm|mkv|avi|mov|flv)(\?|#|$)/i.test(href)){
            addUrl(href, 'dom-link');
          }
        } catch(e){}
      });
      
      // iframes (tentar acessar)
      document.querySelectorAll('iframe').forEach(iframe => {
        try {
          if(iframe.src) addUrl(iframe.src, 'dom-iframe');
          // Tentar acessar contentWindow (pode falhar por CORS)
          try {
            const iframeDoc = iframe.contentDocument || iframe.contentWindow?.document;
            if(iframeDoc){
              iframeDoc.querySelectorAll('video, source').forEach(v => {
                if(v.currentSrc) addUrl(v.currentSrc, 'iframe-video');
                if(v.src) addUrl(v.src, 'iframe-video');
              });
            }
          } catch(e){}
        } catch(e){}
      });
      
    } catch(e){
      console.log('[FindVideo Content] Erro no scanDOM:', e);
    }
  }

  // Performance API
  function scanPerformance(){
    try {
      const entries = performance.getEntriesByType('resource') || [];
      entries.forEach(entry => {
        if(entry.name && entry.name.length > 10){
          addUrl(entry.name, 'performance');
        }
      });
    } catch(e){}
  }

  // Injeta hook na página
  function injectPageHook(){
    const script = document.createElement('script');
    script.textContent = `
      (function(){
        console.log('[FindVideo Page] Hook ativo');
        
        // Intercepta fetch
        const origFetch = window.fetch;
        window.fetch = function(...args){
          try {
            const url = args[0];
            if(url) window.postMessage({__fv: 'fetch', url: String(url)}, '*');
          } catch(e){}
          return origFetch.apply(this, args);
        };
        
        // Intercepta XHR
        const origXHROpen = XMLHttpRequest.prototype.open;
        XMLHttpRequest.prototype.open = function(method, url){
          try {
            if(url) window.postMessage({__fv: 'xhr', url: String(url)}, '*');
          } catch(e){}
          return origXHROpen.apply(this, arguments);
        };
        
        // Intercepta createElement('video')
        const origCreateElement = document.createElement;
        document.createElement = function(tagName){
          const el = origCreateElement.call(document, tagName);
          if(tagName && tagName.toLowerCase() === 'video'){
            console.log('[FindVideo Page] Novo elemento video criado');
            setTimeout(() => {
              if(el.src) window.postMessage({__fv: 'video-el', url: el.src}, '*');
              if(el.currentSrc) window.postMessage({__fv: 'video-el', url: el.currentSrc}, '*');
            }, 100);
          }
          return el;
        };
        
        // Intercepta MediaSource
        if(window.MediaSource){
          const origAddSourceBuffer = MediaSource.prototype.addSourceBuffer;
          MediaSource.prototype.addSourceBuffer = function(mimeType){
            console.log('[FindVideo Page] MediaSource:', mimeType);
            window.postMessage({__fv: 'mediasource', mimeType: mimeType}, '*');
            return origAddSourceBuffer.apply(this, arguments);
          };
        }
        
        // Monitora mudanças em src de vídeos
        setInterval(() => {
          document.querySelectorAll('video, audio').forEach(v => {
            if(v.currentSrc) window.postMessage({__fv: 'video-monitor', url: v.currentSrc}, '*');
            if(v.src) window.postMessage({__fv: 'video-monitor', url: v.src}, '*');
          });
        }, 2000);
        
      })();
    `;
    (document.head || document.documentElement).appendChild(script);
    script.remove();
  }

  // Listener de mensagens da página
  window.addEventListener('message', ev => {
    try {
      const data = ev.data;
      if(data && data.__fv && data.url){
        addUrl(data.url, `page-${data.__fv}`);
      }
    } catch(e){}
  });

  // MutationObserver
  const observer = new MutationObserver(() => {
    scanDOM();
    scanPerformance();
  });
  observer.observe(document, { 
    childList: true, 
    subtree: true,
    attributes: true,
    attributeFilter: ['src', 'data-src']
  });

  // Função para Selenium
  window.__getVideoUrlsFromExtension = async function(){
    try {
      const response = await browser.runtime.sendMessage({type: 'getVideoUrls'});
      if(response && Array.isArray(response.urls)){
        // Merge com URLs locais
        response.urls.forEach(url => addUrl(url, 'background-merge'));
      }
      return {
        urls: window.__FOUND_VIDEO_URLS,
        count: window.__FOUND_VIDEO_URLS.length,
        metadata: response.metadata || []
      };
    } catch(e){
      return {
        urls: window.__FOUND_VIDEO_URLS,
        count: window.__FOUND_VIDEO_URLS.length
      };
    }
  };

  // Função para exportar JSON
  window.__exportVideoUrlsJson = async function(){
    try {
      const data = await browser.runtime.sendMessage({type: 'exportJson'});
      return data;
    } catch(e){
      return {
        urls: window.__FOUND_VIDEO_URLS,
        count: window.__FOUND_VIDEO_URLS.length,
        timestamp: new Date().toISOString()
      };
    }
  };

  // Inicialização
  setTimeout(() => {
    injectPageHook();
    scanDOM();
    scanPerformance();
    console.log('[FindVideo Content] Extensão inicializada');
  }, 100);

  // Scans periódicos
  setInterval(() => {
    scanDOM();
    scanPerformance();
  }, 3000);

  // Scan ao final do carregamento
  window.addEventListener('load', () => {
    setTimeout(() => {
      scanDOM();
      scanPerformance();
    }, 1000);
  });

})();