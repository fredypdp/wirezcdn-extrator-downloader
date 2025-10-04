import json
from extracao_url import extrair_url_video

# Carrega o arquivo JSON
with open('url_extraidas_filmes.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Itera sobre cada objeto no array e extrai a URL
for item in data:
    url = item['url']  # Acessa o campo 'url' de cada objeto
    resultado = extrair_url_video(url, "driver_1")
    
    print(f"URL processada: {url}")
    if resultado['success']:
        print(f"Video URL: {resultado['video_url']}")
        print(f"Do cache: {resultado['from_cache']}")
    else:
        print(f"Erro: {resultado['error']}")
    print("---")  # Separador para melhor visualização