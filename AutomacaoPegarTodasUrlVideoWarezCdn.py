import json
from extracao_url import extrair_url_video

def obter_intervalo(total_itens):
    """Solicita ao usuário o intervalo de processamento."""
    print(f"\n{'='*50}")
    print(f"Total de itens no arquivo: {total_itens}")
    print(f"{'='*50}\n")
    
    while True:
        try:
            inicio = int(input(f"Digite a posição inicial (1 a {total_itens}): "))
            if 1 <= inicio <= total_itens:
                break
            else:
                print(f"❌ Valor inválido! Digite um número entre 1 e {total_itens}")
        except ValueError:
            print("❌ Por favor, digite um número válido!")
    
    while True:
        try:
            fim = int(input(f"Digite a posição final ({inicio} a {total_itens}): "))
            if inicio <= fim <= total_itens:
                break
            else:
                print(f"❌ Valor inválido! Digite um número entre {inicio} e {total_itens}")
        except ValueError:
            print("❌ Por favor, digite um número válido!")
    
    return inicio, fim

def processar_urls():
    """Processa as URLs no intervalo especificado."""
    # Carrega o arquivo JSON
    with open('url_extraidas_filmes.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    total_itens = len(data)
    
    # Obtém o intervalo do usuário
    inicio, fim = obter_intervalo(total_itens)
    
    # Converte para índice do array (subtrai 1 pois array começa em 0)
    indice_inicio = inicio - 1
    indice_fim = fim  # fim já está correto para slice
    
    # Seleciona o intervalo
    itens_selecionados = data[indice_inicio:indice_fim]
    
    print(f"\n{'='*50}")
    print(f"Processando itens de {inicio} até {fim} ({len(itens_selecionados)} itens)")
    print(f"{'='*50}\n")
    
    # Processa cada item no intervalo
    for idx, item in enumerate(itens_selecionados, start=inicio):
        url = item['url']
        resultado = extrair_url_video(url, "driver_1")
        
        print(f"[{idx}/{fim}] URL processada: {url}")
        if resultado['success']:
            print(f"✓ Video URL: {resultado['video_url']}")
            print(f"  Do cache: {resultado['from_cache']}")
        else:
            print(f"✗ Erro: {resultado['error']}")
        print("---")
    
    print(f"\n{'='*50}")
    print(f"✓ Processamento concluído!")
    print(f"{'='*50}\n")

if __name__ == "__main__":
    try:
        processar_urls()
    except FileNotFoundError:
        print("❌ Erro: Arquivo 'url_extraidas_filmes.json' não encontrado!")
    except KeyboardInterrupt:
        print("\n\n❌ Processamento interrompido pelo usuário!")
    except Exception as e:
        print(f"\n❌ Erro inesperado: {e}")