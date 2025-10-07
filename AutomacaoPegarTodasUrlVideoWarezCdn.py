import time
import os
import requests
from dotenv import load_dotenv
from extracao_url import extrair_url_video

# Carregar variáveis de ambiente
load_dotenv()

# Configuração Supabase
SUPABASE_URL = "https://forfhjlkrqjpglfbiosd.supabase.co"
SUPABASE_APIKEY = os.getenv("SUPABASE_APIKEY")
SUPABASE_TABLE = "filmes_url_warezcdn"

def buscar_todos_registros_supabase():
    """Busca todos os registros do Supabase onde dublado é nulo com paginação de 1000 em 1000."""
    todos_registros = []
    offset = 0
    limite = 1000
    
    headers = {
        "apikey": SUPABASE_APIKEY,
        "Authorization": f"Bearer {SUPABASE_APIKEY}",
        "Content-Type": "application/json"
    }
    
    print("📄 Buscando registros do Supabase (dublado=null)...")
    
    while True:
        try:
            params = {
                "select": "url,video_url,dublado",
                "dublado": "is.null",
                "offset": offset,
                "limit": limite
            }
            
            response = requests.get(
                f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}",
                headers=headers,
                params=params,
                timeout=30
            )
            
            if response.status_code == 200:
                registros = response.json()
                
                if not registros:
                    # Não há mais registros
                    break
                
                todos_registros.extend(registros)
                print(f"  ✓ Carregados {len(todos_registros)} registros...")
                
                # Se retornou menos que o limite, chegou ao fim
                if len(registros) < limite:
                    break
                
                offset += limite
            else:
                print(f"❌ Erro ao buscar registros: {response.status_code}")
                break
                
        except Exception as e:
            print(f"❌ Erro ao buscar registros: {e}")
            break
    
    print(f"✓ Total de registros carregados: {len(todos_registros)}\n")
    return todos_registros

def obter_intervalo(total_itens):
    """Solicita ao usuário o intervalo de processamento."""
    print(f"\n{'='*50}")
    print(f"Total de itens na tabela: {total_itens}")
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
    # Busca todos os registros do Supabase
    data = buscar_todos_registros_supabase()
    
    if not data:
        print("❌ Nenhum registro encontrado no Supabase!")
        return
    
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
    
    # Estatísticas
    stats = {
        'sucesso_cache': 0,
        'sucesso_extracao': 0,
        'pulados': 0,
        'erros': 0,
        'total': len(itens_selecionados)
    }
    
    # Processa cada item no intervalo
    for idx, item in enumerate(itens_selecionados, start=inicio):
        url = item.get('url', 'URL não encontrada')
        
        print(f"\n[{idx}/{fim}] Processando: {url[:80]}...")
        
        try:
            resultado = extrair_url_video(url, f"driver_{idx}")
            
            # Verifica se foi pulado (dublado=False)
            if resultado.get('skipped'):
                reason = resultado.get('reason', 'Motivo não especificado')
                print(f"⊘ PULADO: {reason}")
                print(f"  Tempo: {resultado.get('extraction_time', 'N/A')}")
                stats['pulados'] += 1
            
            # Verifica se teve sucesso
            elif resultado.get('success'):
                video_url = resultado.get('video_url', '')
                from_cache = resultado.get('from_cache', False)
                extraction_time = resultado.get('extraction_time', 'N/A')
                dublado = resultado.get('dublado', None)
                
                if from_cache:
                    print(f"✓ SUCESSO (Cache)")
                    stats['sucesso_cache'] += 1
                else:
                    print(f"✓ SUCESSO (Extraído)")
                    stats['sucesso_extracao'] += 1
                
                print(f"  Video URL: {video_url[:80]}...")
                print(f"  Dublado: {dublado}")
                print(f"  Tempo: {extraction_time}")
            
            # Se não teve sucesso e não foi pulado
            else:
                error = resultado.get('error', 'Erro não especificado')
                dublado = resultado.get('dublado', None)
                extraction_time = resultado.get('extraction_time', 'N/A')
                
                print(f"✗ ERRO: {error}")
                print(f"  Dublado: {dublado}")
                print(f"  Tempo: {extraction_time}")
                stats['erros'] += 1
        
        except Exception as e:
            print(f"✗ EXCEÇÃO: {str(e)}")
            stats['erros'] += 1
        
        print("-" * 50)
        
        # Pequena pausa entre requisições para não sobrecarregar
        if idx < fim:
            time.sleep(1)
    
    # Exibe estatísticas finais
    print(f"\n{'='*60}")
    print(f"RELATÓRIO FINAL")
    print(f"{'='*60}")
    print(f"Total processado:      {stats['total']}")
    print(f"✓ Sucesso (Cache):     {stats['sucesso_cache']}")
    print(f"✓ Sucesso (Extraído):  {stats['sucesso_extracao']}")
    print(f"⊘ Pulados:             {stats['pulados']}")
    print(f"✗ Erros:               {stats['erros']}")
    print(f"{'='*60}")
    
    # Calcula taxa de sucesso
    total_sucesso = stats['sucesso_cache'] + stats['sucesso_extracao']
    taxa_sucesso = (total_sucesso / stats['total'] * 100) if stats['total'] > 0 else 0
    print(f"Taxa de sucesso: {taxa_sucesso:.1f}%")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    if not SUPABASE_APIKEY:
        print("❌ Erro: SUPABASE_APIKEY não encontrada nas variáveis de ambiente!")
    else:
        try:
            processar_urls()
        except KeyboardInterrupt:
            print("\n\n❌ Processamento interrompido pelo usuário!")
        except Exception as e:
            print(f"\n❌ Erro inesperado: {e}")
            import traceback
            traceback.print_exc()