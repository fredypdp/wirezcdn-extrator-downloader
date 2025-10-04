import csv
import json

# Nome do arquivo CSV de entrada
csv_filename = 'filmes_url_warezcdn_rows.csv'

# Lista para armazenar os objetos
data = []

# Abrir o arquivo CSV e ler as linhas
with open(csv_filename, mode='r', encoding='utf-8') as csv_file:
    csv_reader = csv.DictReader(csv_file)
    for row in csv_reader:
        # Extrair apenas as colunas 'url' e 'video_url'
        obj = {
            'url': row['url'],
            'video_url': row['video_url']
        }
        data.append(obj)

# Salvar a lista como JSON no arquivo especificado
with open('url_extraidas_filmes.json', mode='w', encoding='utf-8') as json_file:
    json.dump(data, json_file, indent=4)