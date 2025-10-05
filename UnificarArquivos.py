import json

# Carregar os dois arquivos JSON
with open('url_extraidas_filmes.json', 'r', encoding='utf-8') as f:
    filmes1 = json.load(f)

with open('url_extraidas_filmes2.json', 'r', encoding='utf-8') as f:
    filmes2 = json.load(f)

# Criar um dicionário de referência do arquivo 2 (url -> video_url)
ref_dict = {item['url']: item['video_url'] for item in filmes2 if item.get('video_url')}

# Atualizar os itens do arquivo 1 que têm video_url vazio
atualizados = 0
for item in filmes1:
    # Verificar se video_url está vazio ou None
    if not item.get('video_url') or item['video_url'].strip() == '':
        # Buscar no dicionário de referência
        if item['url'] in ref_dict:
            item['video_url'] = ref_dict[item['url']]
            atualizados += 1
            print(f"Atualizado: {item['url']}")

# Salvar o arquivo atualizado
with open('url_extraidas_filmes.json', 'w', encoding='utf-8') as f:
    json.dump(filmes1, f, ensure_ascii=False, indent=4)

print(f"\n✓ Processo concluído!")
print(f"Total de video_url atualizados: {atualizados}")
print(f"Arquivo salvo como: url_extraidas_filmes.json")