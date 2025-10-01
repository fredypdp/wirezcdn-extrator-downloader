// Array para armazenar URLs de vídeo capturadas
let capturedVideoUrls = [];
let downloadedUrls = [];

// Padrões para identificar URLs de vídeo
const VIDEO_PATTERNS = [
  /\.mp4/i,
  /\.mkv/i,
  /\.webm/i,
  /\.m3u8/i,
  /\.ts$/i,
  /\.avi/i,
  /\.mov/i,
  /\.flv/i,
  /video/i,
  /stream/i,
  /mixdrop.*\.(php|co)/i,
  /get_video/i,
  /player.*\.(php|asp)/i
];

// Função para verificar se URL é de vídeo
function isVideoUrl(url) {
  return VIDEO_PATTERNS.some(pattern => pattern.test(url));
}

// Interceptar requisições de vídeo
browser.webRequest.onBeforeRequest.addListener(
  function(details) {
    const url = details.url;
    
    // Verificar se é URL de vídeo
    if (isVideoUrl(url) && details.type === 'media') {
      console.log('[AUTO VIDEO DOWNLOADER] Vídeo detectado:', url);
      
      // Adicionar à lista se não existir
      if (!capturedVideoUrls.includes(url)) {
        capturedVideoUrls.push(url);
        
        // Salvar no storage para acesso via content script
        browser.storage.local.set({ 
          capturedVideoUrls: capturedVideoUrls 
        });
        
        // Iniciar download automático
        startDownload(url);
      }
    }
    
    return {};
  },
  {urls: ["<all_urls>"]},
  ["blocking"]
);

// Também capturar via onCompleted para pegar outras requisições
browser.webRequest.onCompleted.addListener(
  function(details) {
    const url = details.url;
    
    // Verificar padrões mais abrangentes
    if (isVideoUrl(url)) {
      console.log('[AUTO VIDEO DOWNLOADER] Requisição de vídeo completada:', url);
      
      if (!capturedVideoUrls.includes(url)) {
        capturedVideoUrls.push(url);
        browser.storage.local.set({ 
          capturedVideoUrls: capturedVideoUrls 
        });
        
        // Tentar download
        startDownload(url);
      }
    }
  },
  {urls: ["<all_urls>"]}
);

// Função para iniciar download
function startDownload(url) {
  console.log('[AUTO VIDEO DOWNLOADER] Iniciando download:', url);
  
  // Gerar nome único baseado em timestamp
  const timestamp = Date.now();
  const filename = `video_${timestamp}.mp4`;
  
  browser.downloads.download({
    url: url,
    filename: filename,
    saveAs: false,  // Não mostrar diálogo
    conflictAction: 'uniquify'
  })
  .then(downloadId => {
    console.log('[AUTO VIDEO DOWNLOADER] Download iniciado, ID:', downloadId);
    
    // Salvar associação entre downloadId e URL
    downloadedUrls.push({
      id: downloadId,
      url: url,
      timestamp: timestamp
    });
    
    browser.storage.local.set({ 
      downloadedUrls: downloadedUrls 
    });
    
    // Aguardar um pouco e cancelar download (só queremos a URL)
    setTimeout(() => {
      cancelDownload(downloadId, url);
    }, 2000);
  })
  .catch(error => {
    console.error('[AUTO VIDEO DOWNLOADER] Erro ao iniciar download:', error);
  });
}

// Função para cancelar download
function cancelDownload(downloadId, url) {
  browser.downloads.cancel(downloadId)
    .then(() => {
      console.log('[AUTO VIDEO DOWNLOADER] Download cancelado:', downloadId);
      
      // Remover arquivo parcial
      browser.downloads.removeFile(downloadId)
        .catch(err => console.log('Erro ao remover arquivo:', err));
      
      // Remover do histórico
      browser.downloads.erase({ id: downloadId })
        .catch(err => console.log('Erro ao apagar do histórico:', err));
      
      console.log('[AUTO VIDEO DOWNLOADER] URL capturada e salva:', url);
    })
    .catch(error => {
      console.log('[AUTO VIDEO DOWNLOADER] Erro ao cancelar (pode já ter terminado):', error);
    });
}

// Listener para mudanças nos downloads
browser.downloads.onChanged.addListener(function(delta) {
  if (delta.state && delta.state.current === 'in_progress') {
    // Buscar URL associada a este download
    const download = downloadedUrls.find(d => d.id === delta.id);
    if (download) {
      console.log('[AUTO VIDEO DOWNLOADER] Download em progresso:', download.url);
    }
  }
});

// Expor função para content script acessar URLs
browser.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'getVideoUrls') {
    sendResponse({ urls: capturedVideoUrls });
  } else if (message.action === 'getDownloadedUrls') {
    sendResponse({ downloads: downloadedUrls });
  } else if (message.action === 'clearUrls') {
    capturedVideoUrls = [];
    downloadedUrls = [];
    browser.storage.local.set({ 
      capturedVideoUrls: [],
      downloadedUrls: []
    });
    sendResponse({ success: true });
  }
  return true;
});

console.log('[AUTO VIDEO DOWNLOADER] Background script carregado e monitorando');