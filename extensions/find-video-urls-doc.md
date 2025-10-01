# 📄 Documentação – Extensão `find-video-urls-debug.xpi`

## 1. O que a extensão faz
- Detecta **todas as URLs de vídeo** (`<video src>`, `source`, `MediaSource`, `XMLHttpRequest` com MIME `video/*`) carregadas na página.  
- Armazena as URLs encontradas em memória.  
- Permite que **seu código Python (via Selenium)** peça as URLs detectadas e receba uma lista.  
- Os logs são exibidos no **console do navegador** (`Ctrl+Shift+J`) para debug.

---

## 2. Estrutura
- **background.js** → gerencia as mensagens e armazenamento de URLs.  
- **content.js** → injeta na página, captura vídeos, envia para o background.  
- **manifest.json** → define permissões e comportamento da extensão.  

---

## 3. Instalação manual (teste rápido)
1. Abra Firefox → `about:debugging#/runtime/this-firefox`.  
2. Clique em **Load Temporary Add-on**.  
3. Selecione o `.xpi`.  
4. Abra um site com vídeo → veja logs no console (`Ctrl+Shift+J`).  

---

## 4. Integração com Python + Selenium

### Passo 1 – Carregar extensão no Selenium
```python
from selenium import webdriver
from selenium.webdriver.firefox.options import Options

# Configurações
options = Options()
options.set_preference("xpinstall.signatures.required", False)  # permite extensões unsigned

# Inicia o Firefox com a extensão
driver = webdriver.Firefox(options=options)
driver.install_addon("find-video-urls-debug.xpi", temporary=True)

driver.get("https://exemplo.com/video")
```

---

### Passo 2 – Obter URLs detectadas
A extensão responde via API `browser.runtime.sendMessage`.  
No Selenium, você injeta JS e espera resposta:

```python
# Executa script no navegador para pegar as URLs detectadas
video_urls = driver.execute_async_script("""
    const callback = arguments[0];
    browser.runtime.sendMessage({type: "getUrls"})
        .then(response => callback(response.urls))
        .catch(err => callback(["ERRO: " + err]));
""")

print("Vídeos encontrados:", video_urls)
```

---

### Passo 3 – Limpar URLs detectadas (opcional)
```python
driver.execute_async_script("""
    const callback = arguments[0];
    browser.runtime.sendMessage({type: "clearUrls"})
        .then(response => callback(response.status))
        .catch(err => callback("ERRO: " + err));
""")
```

---

## 5. Fluxo típico de uso
1. Abra a página com o Selenium.  
2. Aguarde o vídeo carregar.  
3. Rode o `getUrls` para receber os links diretos.  
4. (Opcional) Baixe com `requests`/`wget`/etc.  
5. (Opcional) Use `clearUrls` antes de mudar de página, para não misturar.  

---

## 6. Observações
- Funciona melhor em players HTML5 nativos.  
- Alguns sites usam **MPEG-DASH/HLS (m3u8/ts)** → a extensão captura os fragmentos também.  
- Se a URL vier com token temporário, baixe rápido.  
- Você pode integrar no Selenium de forma automática: abrir página → esperar → chamar `getUrls`.
