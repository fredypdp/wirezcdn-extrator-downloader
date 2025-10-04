import json
import requests
from dotenv import load_dotenv
import os

# Carregar as variáveis de ambiente do arquivo .env
load_dotenv()

# Obter a chave API da variável de ambiente
api_key = os.getenv('SUPABASE_APIKEY')

# Verificar se a chave API foi carregada corretamente
if not api_key:
    raise ValueError("A variável de ambiente SUPABASE_APIKEY não foi encontrada no arquivo .env")

# Carregar o arquivo JSON
with open('series_warezcdn_url.json', 'r') as f:
    data = json.load(f)

# Extrair a lista de URLs
urls = data['urls']

# Preparar os dados para inserção (lista de dicionários)
insert_data = [{"url": url} for url in urls]

# Endpoint da API Supabase
endpoint = 'https://forfhjlkrqjpglfbiosd.supabase.co/rest/v1/filmes_url_warezcdn'

# Cabeçalhos da requisição
headers = {
    "apikey": api_key,
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal"
}

# Enviar a requisição POST para inserir todos os dados de uma vez
response = requests.post(endpoint, headers=headers, json=insert_data)

# Exibir o status e a resposta
print(f"Status Code: {response.status_code}")
if response.status_code == 201:
    print("Dados inseridos com sucesso!")
else:
    print(f"Erro ao inserir dados: {response.text}")