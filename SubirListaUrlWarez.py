import json
import os
import logging
from dotenv import load_dotenv
import requests

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Carregar variáveis de ambiente
load_dotenv()

# Configuração Supabase
SUPABASE_URL = "https://forfhjlkrqjpglfbiosd.supabase.co"
SUPABASE_APIKEY = os.getenv("SUPABASE_APIKEY")
SUPABASE_TABLE = "filmes_url_warezcdn"

# Arquivo JSON
JSON_FILE = os.path.join(os.getcwd(), 'url_extraidas_filmes.json')

if not SUPABASE_APIKEY:
    logger.error("SUPABASE_APIKEY não encontrada nas variáveis de ambiente!")
    exit(1)


def carregar_json():
    """Carrega o arquivo JSON com as URLs"""
    try:
        if not os.path.exists(JSON_FILE):
            logger.error(f"Arquivo JSON não encontrado: {JSON_FILE}")
            return []
        
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            logger.info(f"JSON carregado com {len(data)} registros")
            return data
    except Exception as e:
        logger.error(f"Erro ao carregar JSON: {e}")
        return []


def verificar_existe_supabase(url_pagina):
    """Verifica se o registro existe no Supabase"""
    try:
        headers = {
            "apikey": SUPABASE_APIKEY,
            "Authorization": f"Bearer {SUPABASE_APIKEY}",
            "Content-Type": "application/json"
        }
        
        params = {
            "select": "url,video_url,dublado",
            "url": f"eq.{url_pagina}"
        }
        
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}",
            headers=headers,
            params=params,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                return data[0]  # Retorna o registro encontrado
            return None
        else:
            logger.error(f"Erro ao verificar existência: {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"Erro ao verificar existência: {e}")
        return None


def atualizar_registro_supabase(url_pagina, video_url, dublado, registro_existente):
    """Atualiza um registro existente no Supabase (apenas campos não preenchidos)"""
    try:
        headers = {
            "apikey": SUPABASE_APIKEY,
            "Authorization": f"Bearer {SUPABASE_APIKEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal"
        }
        
        params = {
            "url": f"eq.{url_pagina}"
        }
        
        # Construir data apenas com campos que precisam ser atualizados
        data = {}
        campos_atualizados = []
        
        # Atualizar video_url apenas se estiver vazio no banco E tiver valor no JSON
        video_url_bd = registro_existente.get('video_url')
        if not video_url_bd and video_url:
            data['video_url'] = video_url
            campos_atualizados.append('video_url')
        
        # Atualizar dublado apenas se estiver vazio no banco E tiver valor no JSON
        dublado_bd = registro_existente.get('dublado')
        if dublado_bd is None and dublado is not None:
            data['dublado'] = dublado
            campos_atualizados.append('dublado')
        
        # Se não há nada para atualizar, retorna
        if not data:
            return False
        
        response = requests.patch(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}",
            headers=headers,
            params=params,
            json=data,
            timeout=10
        )
        
        if response.status_code in [200, 204]:
            logger.info(f"✓ Registro atualizado ({', '.join(campos_atualizados)}): {url_pagina[:50]}...")
            return True
        else:
            logger.error(f"✗ Erro ao atualizar: {response.status_code} - {response.text}")
            return False
        
    except Exception as e:
        logger.error(f"✗ Erro ao atualizar registro: {e}")
        return False


def criar_registro_supabase(url_pagina, video_url, dublado):
    """Cria um novo registro no Supabase"""
    try:
        headers = {
            "apikey": SUPABASE_APIKEY,
            "Authorization": f"Bearer {SUPABASE_APIKEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal"
        }
        
        data = {
            "url": url_pagina,
            "video_url": video_url,
            "dublado": dublado
        }
        
        response = requests.post(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}",
            headers=headers,
            json=data,
            timeout=10
        )
        
        if response.status_code in [200, 201, 204]:
            logger.info(f"✓ Novo registro criado: {url_pagina[:50]}...")
            return True
        else:
            logger.error(f"✗ Erro ao criar: {response.status_code} - {response.text}")
            return False
        
    except Exception as e:
        logger.error(f"✗ Erro ao criar registro: {e}")
        return False


def sincronizar_json_com_supabase():
    """Sincroniza todos os registros do JSON com o Supabase"""
    logger.info("=" * 70)
    logger.info("INICIANDO SINCRONIZAÇÃO JSON → SUPABASE")
    logger.info("=" * 70)
    
    # Carregar dados do JSON
    registros_json = carregar_json()
    
    if not registros_json:
        logger.warning("Nenhum registro encontrado no JSON")
        return
    
    total = len(registros_json)
    criados = 0
    atualizados = 0
    erros = 0
    ignorados = 0
    
    logger.info(f"\nTotal de registros a processar: {total}\n")
    
    for i, item in enumerate(registros_json, 1):
        url = item.get('url')
        video_url = item.get('video_url')
        dublado = item.get('dublado')
        
        # Definir como None (null) se estiverem vazios
        if not video_url:
            video_url = None
        if dublado is None or dublado == '':
            dublado = None
        
        if not url:
            logger.warning(f"[{i}/{total}] Registro sem URL - ignorado")
            ignorados += 1
            continue
        
        logger.info(f"[{i}/{total}] Processando: {url[:60]}...")
        
        # Verifica se existe no Supabase
        registro_existente = verificar_existe_supabase(url)
        
        if registro_existente:
            # Registro existe - verificar se precisa atualizar
            video_url_bd = registro_existente.get('video_url')
            dublado_bd = registro_existente.get('dublado')
            
            # Verificar se há campos vazios no BD que podem ser preenchidos pelo JSON
            precisa_atualizar = False
            campos_para_atualizar = []
            
            if not video_url_bd and video_url:
                precisa_atualizar = True
                campos_para_atualizar.append('video_url')
            
            if dublado_bd is None and dublado is not None:
                precisa_atualizar = True
                campos_para_atualizar.append('dublado')
            
            if precisa_atualizar:
                logger.info(f"  → Campos vazios no BD: {', '.join(campos_para_atualizar)}")
                if atualizar_registro_supabase(url, video_url, dublado, registro_existente):
                    atualizados += 1
                else:
                    erros += 1
            else:
                logger.info(f"  → Registro já está completo - ignorado")
                ignorados += 1
        else:
            # Registro não existe - criar novo
            if criar_registro_supabase(url, video_url, dublado):
                criados += 1
            else:
                erros += 1
        
        # Pequena pausa para não sobrecarregar a API
        if i < total:
            import time
            time.sleep(0.1)
    
    # Relatório final
    logger.info("\n" + "=" * 70)
    logger.info("SINCRONIZAÇÃO CONCLUÍDA")
    logger.info("=" * 70)
    logger.info(f"Total processado:    {total}")
    logger.info(f"Novos criados:       {criados}")
    logger.info(f"Atualizados:         {atualizados}")
    logger.info(f"Ignorados:           {ignorados}")
    logger.info(f"Erros:               {erros}")
    logger.info("=" * 70)


if __name__ == "__main__":
    try:
        sincronizar_json_com_supabase()
    except KeyboardInterrupt:
        logger.info("\n\nSincronização interrompida pelo usuário")
    except Exception as e:
        logger.error(f"\n\nErro fatal: {e}")