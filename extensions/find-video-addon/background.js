const videoUrls = new Set();
const urlMetadata = new Map(); // Armazena metadados das URLs

function looksLikeMedia(u){
  if(!u) return false;
  try {
    const low = u.toLowerCase();
    // Aceita QUALQUER URL que pareça ser mídia
    return /\.(m3u8|mpd|mp4|m4v|webm|mkv|ts|hls|avi|mov|flv|wmv|3gp|mp3|aac|ogg|wav)(\?|#|$)/i.test(low) 
           || /playlist|manifest|segment|chunk|video|stream|media|cdn|blob/i.test(low)
           || low.includes('/v/') 
           || low.includes('/media/')
           || low.includes('/stream/');
  } catch(e){ 
    return false; 
  }
}

function recordUrl(url, source, tabId){
  if(!url || url.startsWith('data:') || url.startsWith('blob:')) return;
  
  if(!videoUrls.has(url)){
    videoUrls.add(url);
    urlMetadata.set(url, {
      url: url,
      source: source,
      timestamp: Date.now(),
      tabId: tabId
    });
    
    console.log(`[FindVideo] Nova URL [${source}]:`, url);
    
    // Broadcast para todas as abas
    broadcastToAllTabs(url);
  }
}

function broadcastToAllTabs(url){
  browser.tabs.query({}).then(tabs => {
    tabs.forEach(tab => {
      browser.tabs.sendMessage(tab.id, {
        type: 'videoUrlFound', 
        url: url
      }).catch(() => {});
    });
  });
}

// Intercepta TODAS as requisições
browser.webRequest.onBeforeRequest.addListener(
  details => {
    const url = details.url;
    if(looksLikeMedia(url)) {
      recordUrl(url, 'webRequest', details.tabId);
    }
  },
  { urls: ["<all_urls>"] },
  []
);

// Intercepta headers de resposta
browser.webRequest.onHeadersReceived.addListener(
  details => {
    const headers = details.responseHeaders || [];
    const contentType = headers.find(h => 
      h.name.toLowerCase() === 'content-type'
    );
    
    if(contentType && contentType.value){
      const val = contentType.value.toLowerCase();
      if(val.startsWith('video/') || 
         val.startsWith('audio/') ||
         val.includes('mpegurl') || 
         val.includes('dash') || 
         val.includes('mp4') ||
         val.includes('stream')){
        recordUrl(details.url, 'headers', details.tabId);
      }
    }
  },
  { urls: ["<all_urls>"] },
  ["responseHeaders"]
);

// Monitora downloads e CAPTURA a URL antes de cancelar
browser.downloads.onCreated.addListener(downloadItem => {
  const url = downloadItem.url;
  const mime = downloadItem.mime || '';
  
  console.log('[FindVideo] Download detectado:', {
    url: url,
    mime: mime,
    filename: downloadItem.filename
  });
  
  // Captura a URL do download
  if(url && (looksLikeMedia(url) || mime.startsWith('video/') || mime.startsWith('audio/'))){
    recordUrl(url, 'download', null);
    
    // Cancela e remove o download
    browser.downloads.cancel(downloadItem.id).then(() => {
      browser.downloads.erase({id: downloadItem.id}).catch(() => {});
      console.log('[FindVideo] Download cancelado e URL capturada');
    }).catch(() => {});
  }
});

// API de mensagens
browser.runtime.onMessage.addListener((msg, sender) => {
  if(!msg) return;
  
  if(msg.type === 'getVideoUrls'){
    const urls = Array.from(videoUrls);
    console.log('[FindVideo] Retornando', urls.length, 'URLs');
    return Promise.resolve({
      urls: urls,
      count: urls.length,
      metadata: Array.from(urlMetadata.values())
    });
  }
  
  if(msg.type === 'clearUrls'){
    const count = videoUrls.size;
    videoUrls.clear();
    urlMetadata.clear();
    console.log('[FindVideo] Limpou', count, 'URLs');
    return Promise.resolve({status: 'cleared', count: count});
  }
  
  if(msg.type === 'addUrl' && msg.url){
    recordUrl(msg.url, msg.source || 'content', sender.tab?.id);
    return Promise.resolve({status: 'added'});
  }
  
  // NOVO: Exportar URLs para JSON
  if(msg.type === 'exportJson'){
    const data = {
      timestamp: new Date().toISOString(),
      count: videoUrls.size,
      urls: Array.from(videoUrls),
      metadata: Array.from(urlMetadata.values())
    };
    return Promise.resolve(data);
  }
});

// Log periódico
setInterval(() => {
  if(videoUrls.size > 0){
    console.log('[FindVideo] Total de URLs capturadas:', videoUrls.size);
  }
}, 15000);

console.log('[FindVideo Background] Inicializado');