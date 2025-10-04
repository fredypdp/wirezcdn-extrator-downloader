import json
from extracao_url import extrair_url_video

# Carrega o arquivo JSON
with open('filmes_warezcdn_url.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Extrai a lista de URLs
urls = data['urls']

# Itera sobre cada URL e executa a função
for url in urls:
    resultado = extrair_url_video(url, "driver_1")
    
    print(f"URL processada: {url}")
    if resultado['success']:
        print(f"Video URL: {resultado['video_url']}")
        print(f"Do cache: {resultado['from_cache']}")
    else:
        print(f"Erro: {resultado['error']}")
    print("---")  # Separador para melhor visualização