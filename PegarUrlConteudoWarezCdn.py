import time
import json
import logging
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from webdriver_manager.firefox import GeckoDriverManager
import os

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Desabilitar logs excessivos
logging.getLogger('WDM').setLevel(logging.ERROR)
logging.getLogger('urllib3').setLevel(logging.ERROR)

class WarezcdnScraper:
    def __init__(self):
        self.driver = None
        self.base_url = "https://warezcdn.cc"
        self.filmes_url = f"{self.base_url}/conteudo/filmes"
        self.series_url = f"{self.base_url}/conteudo/series"
        
        # Estatísticas globais
        self.stats = {
            "filmes": {
                "total_urls": 0,
                "urls_novas": 0,
                "urls_duplicadas": 0,
                "paginas_processadas": 0,
                "erros": 0,
                "tempo_inicio": None,
                "tempo_fim": None
            },
            "series": {
                "total_urls": 0,
                "urls_novas": 0,
                "urls_duplicadas": 0,
                "paginas_processadas": 0,
                "erros": 0,
                "tempo_inicio": None,
                "tempo_fim": None
            }
        }
        
    def carregar_urls_existentes(self, tipo):
        """Carrega URLs já extraídas do arquivo JSON"""
        if tipo == "filmes":
            arquivo = "url_extraidas_filmes.json"
        else:
            arquivo = "url_extraidas_series.json"
        
        if not os.path.exists(arquivo):
            logger.info(f"   ℹ️ Arquivo {arquivo} não encontrado. Iniciando extração do zero.")
            return []
        
        try:
            with open(arquivo, 'r', encoding='utf-8') as f:
                dados = json.load(f)
                
                # Se for um array direto
                if isinstance(dados, list):
                    urls_existentes = [item.get("url") for item in dados if item.get("url")]
                # Se for objeto com campo "urls"
                elif isinstance(dados, dict) and "urls" in dados:
                    urls_existentes = [item.get("url") for item in dados["urls"] if item.get("url")]
                else:
                    urls_existentes = []
                
                logger.info(f"   📂 Carregadas {len(urls_existentes)} URLs existentes de {arquivo}")
                return urls_existentes
        except Exception as e:
            logger.warning(f"   ⚠️ Erro ao carregar {arquivo}: {e}")
            return []
    
    def criar_navegador_firefox(self):
        """Cria navegador Firefox otimizado"""
        options = Options()
        
        # Configurações para máxima velocidade
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-plugins")
        
        # Tamanho de janela
        options.add_argument("--width=1920")
        options.add_argument("--height=1080")
        
        # User agent
        options.set_preference(
            "general.useragent.override",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0"
        )
        
        # Otimizações
        options.set_preference("dom.ipc.plugins.enabled", False)
        options.set_preference("media.volume_scale", "0.0")
        options.set_preference("media.autoplay.default", 0)
        
        # Configurações de rede otimizadas
        options.set_preference("network.http.max-connections", 100)
        options.set_preference("network.http.max-connections-per-server", 20)
        
        # Anti-detecção
        options.set_preference("dom.webdriver.enabled", False)
        options.set_preference("useAutomationExtension", False)
        
        try:
            service = Service(GeckoDriverManager().install())
            service.service_args = ['--log', 'fatal']
            
            driver = webdriver.Firefox(service=service, options=options)
            driver.set_page_load_timeout(30)
            driver.implicitly_wait(5)
            
            logger.info("✅ Driver Firefox criado com sucesso!")
            return driver
            
        except Exception as e:
            logger.error(f"❌ Erro ao criar driver Firefox: {e}")
            raise
    
    def extrair_urls_pagina(self, urls_existentes_set):
        """Extrai URLs da página atual, pulando as já existentes"""
        urls_novas = []
        urls_duplicadas = 0
        
        try:
            # Aguardar carregamento dos posters
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_all_elements_located((By.CLASS_NAME, "poster"))
            )
            
            # Buscar todas as divs com classe "poster"
            posters = self.driver.find_elements(By.CLASS_NAME, "poster")
            logger.info(f"   📦 Encontrados {len(posters)} posters na página")
            
            for poster in posters:
                try:
                    # Buscar div "hover" dentro do poster
                    hover_div = poster.find_element(By.CLASS_NAME, "hover")
                    
                    # Buscar elemento "a" dentro do hover
                    link = hover_div.find_element(By.TAG_NAME, "a")
                    
                    # Extrair href
                    href = link.get_attribute("href")
                    
                    if href:
                        # Verificar se já existe
                        if href in urls_existentes_set:
                            urls_duplicadas += 1
                        else:
                            urls_novas.append(href)
                            urls_existentes_set.add(href)
                        
                except NoSuchElementException:
                    continue
                except Exception as e:
                    logger.warning(f"   ⚠️ Erro ao extrair URL de um poster: {e}")
                    continue
            
            logger.info(f"   ✅ URLs novas: {len(urls_novas)} | Duplicadas: {urls_duplicadas}")
            return urls_novas, urls_duplicadas
            
        except TimeoutException:
            logger.error("   ❌ Timeout ao aguardar carregamento dos posters")
            return [], 0
        except Exception as e:
            logger.error(f"   ❌ Erro ao extrair URLs: {e}")
            return [], 0
    
    def ir_proxima_pagina(self):
        """Navega para a próxima página usando o botão 'next'"""
        try:
            # Buscar div de paginação
            pagination = self.driver.find_element(By.ID, "pagination")
            
            # Buscar botão "next"
            next_button = pagination.find_element(By.CLASS_NAME, "next")
            
            # Verificar se está desabilitado (última página)
            is_disabled = next_button.get_attribute("disabled")
            
            if is_disabled:
                logger.info("   ℹ️ Última página alcançada (botão desabilitado)")
                return False
            
            # Clicar no botão next
            next_button.click()
            
            # Aguardar um pouco para carregar a próxima página
            time.sleep(2)
            
            # Aguardar nova página carregar
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "poster"))
            )
            
            return True
            
        except NoSuchElementException:
            logger.error("   ❌ Botão 'next' não encontrado")
            return False
        except Exception as e:
            logger.error(f"   ❌ Erro ao ir para próxima página: {e}")
            return False
    
    def obter_pagina_atual(self):
        """Obtém o número da página atual"""
        try:
            pagination = self.driver.find_element(By.ID, "pagination")
            active_button = pagination.find_element(By.CLASS_NAME, "active")
            return active_button.text
        except:
            return "?"
    
    def scrape(self, tipo="filmes", max_paginas=None):
        """
        Executa o scraping
        
        Args:
            tipo: "filmes" ou "series"
            max_paginas: Número máximo de páginas (None = todas)
        """
        urls_coletadas = []
        erros = []
        
        # Iniciar timer
        self.stats[tipo]["tempo_inicio"] = time.time()
        
        try:
            # Carregar URLs já existentes
            urls_existentes_lista = self.carregar_urls_existentes(tipo)
            urls_existentes_set = set(urls_existentes_lista)
            
            # Criar driver
            self.driver = self.criar_navegador_firefox()
            
            # Definir URL base
            url_base = self.filmes_url if tipo == "filmes" else self.series_url
            
            logger.info(f"\n🎬 Iniciando scraping de {tipo.upper()}")
            logger.info(f"🔗 URL: {url_base}")
            logger.info(f"📄 Páginas: {'Todas' if max_paginas is None else max_paginas}\n")
            
            # Navegar para a página inicial
            self.driver.get(url_base)
            time.sleep(3)
            
            pagina = 1
            
            while True:
                try:
                    pagina_atual = self.obter_pagina_atual()
                    logger.info(f"📄 Processando página {pagina_atual}...")
                    
                    # Extrair URLs da página atual
                    urls, duplicadas = self.extrair_urls_pagina(urls_existentes_set)
                    urls_coletadas.extend(urls)
                    
                    # Atualizar estatísticas
                    self.stats[tipo]["urls_novas"] += len(urls)
                    self.stats[tipo]["urls_duplicadas"] += duplicadas
                    self.stats[tipo]["paginas_processadas"] += 1
                    
                    total_geral = len(urls_existentes_set)
                    logger.info(f"   📊 Total geral no arquivo: {total_geral} URLs\n")
                    
                    # Verificar limite de páginas
                    if max_paginas and pagina >= max_paginas:
                        logger.info(f"✅ Limite de {max_paginas} páginas alcançado")
                        break
                    
                    # Tentar ir para próxima página
                    if not self.ir_proxima_pagina():
                        break
                    
                    pagina += 1
                    
                except Exception as e:
                    erro_msg = f"Erro na página {pagina}: {str(e)}"
                    logger.error(f"   ❌ {erro_msg}")
                    erros.append({
                        "pagina": pagina,
                        "erro": str(e),
                        "timestamp": datetime.now().isoformat()
                    })
                    self.stats[tipo]["erros"] += 1
                    break
            
            # Finalizar timer
            self.stats[tipo]["tempo_fim"] = time.time()
            
            # Total de URLs
            self.stats[tipo]["total_urls"] = len(urls_existentes_set)
            
            # Resultados finais
            tempo_decorrido = self.stats[tipo]["tempo_fim"] - self.stats[tipo]["tempo_inicio"]
            
            logger.info(f"\n{'='*60}")
            logger.info(f"📊 RESUMO DO SCRAPING - {tipo.upper()}")
            logger.info(f"{'='*60}")
            logger.info(f"🆕 URLs novas coletadas: {self.stats[tipo]['urls_novas']}")
            logger.info(f"⭐️ URLs duplicadas (puladas): {self.stats[tipo]['urls_duplicadas']}")
            logger.info(f"📁 Total de URLs no arquivo: {self.stats[tipo]['total_urls']}")
            logger.info(f"📄 Páginas processadas: {self.stats[tipo]['paginas_processadas']}")
            logger.info(f"❌ Erros: {len(erros)}")
            logger.info(f"⏱️ Tempo decorrido: {tempo_decorrido:.2f}s")
            logger.info(f"{'='*60}\n")
            
            return urls_coletadas, erros
            
        except Exception as e:
            logger.error(f"❌ Erro fatal: {e}")
            erros.append({
                "tipo": "fatal",
                "erro": str(e),
                "timestamp": datetime.now().isoformat()
            })
            self.stats[tipo]["erros"] += 1
            
            if self.stats[tipo]["tempo_inicio"]:
                self.stats[tipo]["tempo_fim"] = time.time()
            
            return urls_coletadas, erros
            
        finally:
            if self.driver:
                self.driver.quit()
                logger.info("🔒 Driver fechado\n")
    
    def salvar_resultados(self, tipo, urls_novas, erros):
        """Salva os resultados em arquivos JSON (adiciona as novas URLs no INÍCIO)"""
        try:
            # Definir nome do arquivo
            if tipo == "filmes":
                arquivo_urls = "url_extraidas_filmes.json"
            else:
                arquivo_urls = "url_extraidas_series.json"
            
            arquivo_erros = f"{tipo}_warezcdn_erros.json"
            
            # Carregar dados existentes
            urls_existentes = []
            if os.path.exists(arquivo_urls):
                try:
                    with open(arquivo_urls, 'r', encoding='utf-8') as f:
                        dados_antigos = json.load(f)
                        
                        # Se for um array direto
                        if isinstance(dados_antigos, list):
                            urls_existentes = dados_antigos
                        # Se for objeto com campo "urls"
                        elif isinstance(dados_antigos, dict) and "urls" in dados_antigos:
                            urls_existentes = dados_antigos["urls"]
                except Exception as e:
                    logger.warning(f"   ⚠️ Erro ao carregar arquivo existente: {e}")
            
            # Criar novos objetos para as URLs coletadas
            novos_objetos = []
            for url in urls_novas:
                if tipo == "filmes":
                    novos_objetos.append({
                        "url": url,
                        "video_repro_url": "",
                        "dublado": ""
                    })
                else:  # series
                    novos_objetos.append({
                        "url": url,
                        "video_repro_url": "",
                        "temporadas": []
                    })
            
            # ADICIONAR NOVAS URLs NO INÍCIO (mais recentes primeiro)
            urls_totais = novos_objetos + urls_existentes
            
            # Salvar array direto (sem wrapper)
            with open(arquivo_urls, 'w', encoding='utf-8') as f:
                json.dump(urls_totais, f, indent=4, ensure_ascii=False)
            
            logger.info(f"💾 URLs salvas em: {arquivo_urls}")
            logger.info(f"   📊 Total de registros: {len(urls_totais)}")
            logger.info(f"   🆕 Novos registros adicionados: {len(novos_objetos)}")
            
            # Salvar/atualizar erros (se houver)
            if erros:
                erros_existentes = []
                if os.path.exists(arquivo_erros):
                    try:
                        with open(arquivo_erros, 'r', encoding='utf-8') as f:
                            dados_erros_antigos = json.load(f)
                            erros_existentes = dados_erros_antigos.get("erros", [])
                    except:
                        pass
                
                erros_existentes.extend(erros)
                
                dados_erros = {
                    "tipo": tipo,
                    "total": len(erros_existentes),
                    "ultima_atualizacao": datetime.now().isoformat(),
                    "erros": erros_existentes
                }
                
                with open(arquivo_erros, 'w', encoding='utf-8') as f:
                    json.dump(dados_erros, f, indent=2, ensure_ascii=False)
                logger.info(f"💾 Erros salvos em: {arquivo_erros}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Erro ao salvar resultados: {e}")
            return False
    
    def exibir_estatisticas_finais(self):
        """Exibe estatísticas completas ao final da execução"""
        print("\n" + "="*70)
        print("📊 ESTATÍSTICAS FINAIS DA SESSÃO")
        print("="*70)
        
        total_urls_novas = 0
        total_urls_duplicadas = 0
        total_paginas = 0
        total_erros = 0
        tempo_total = 0
        
        for tipo in ["filmes", "series"]:
            stats = self.stats[tipo]
            
            tempo = 0
            if stats["tempo_inicio"] and stats["tempo_fim"]:
                tempo = stats["tempo_fim"] - stats["tempo_inicio"]
                tempo_total += tempo
            
            total_urls_novas += stats["urls_novas"]
            total_urls_duplicadas += stats["urls_duplicadas"]
            total_paginas += stats["paginas_processadas"]
            total_erros += stats["erros"]
            
            if stats["paginas_processadas"] > 0:
                print(f"\n🎬 {tipo.upper()}")
                print(f"   🆕 URLs novas: {stats['urls_novas']}")
                print(f"   ⭐️ URLs duplicadas: {stats['urls_duplicadas']}")
                print(f"   📁 Total no arquivo: {stats['total_urls']}")
                print(f"   📄 Páginas: {stats['paginas_processadas']}")
                print(f"   ❌ Erros: {stats['erros']}")
                if tempo > 0:
                    print(f"   ⏱️ Tempo: {tempo:.2f}s")
                    if stats['paginas_processadas'] > 0:
                        print(f"   ⚡ Velocidade: {tempo/stats['paginas_processadas']:.2f}s/página")
        
        if total_paginas > 0:
            print(f"\n{'─'*70}")
            print(f"📈 TOTAIS GERAIS")
            print(f"   🆕 URLs novas coletadas: {total_urls_novas}")
            print(f"   ⭐️ URLs duplicadas (puladas): {total_urls_duplicadas}")
            print(f"   📄 Total de páginas processadas: {total_paginas}")
            print(f"   ❌ Total de erros: {total_erros}")
            if tempo_total > 0:
                print(f"   ⏱️ Tempo total: {tempo_total:.2f}s ({tempo_total/60:.2f} minutos)")
                if total_paginas > 0:
                    print(f"   ⚡ Velocidade média: {tempo_total/total_paginas:.2f}s/página")
        
        print("="*70 + "\n")


def menu_interativo():
    """Menu interativo para executar o scraper"""
    scraper = WarezcdnScraper()
    
    print("\n" + "="*60)
    print("🎬 WAREZCDN URL EXTRACTOR")
    print("="*60)
    
    try:
        while True:
            print("\n📋 OPÇÕES:")
            print("1. Extrair URLs de FILMES")
            print("2. Extrair URLs de SÉRIES")
            print("3. Extrair URLs de FILMES E SÉRIES")
            print("4. Sair")
            
            try:
                opcao = input("\n👉 Escolha uma opção (1-4): ").strip()
                
                if opcao == "4":
                    print("\n👋 Encerrando...")
                    break
                
                if opcao not in ["1", "2", "3"]:
                    print("❌ Opção inválida! Tente novamente.")
                    continue
                
                print("\n📄 Quantas páginas deseja processar?")
                max_pag = input("   (deixe em branco para processar TODAS): ").strip()
                
                max_paginas = None
                if max_pag:
                    try:
                        max_paginas = int(max_pag)
                        if max_paginas <= 0:
                            print("❌ Número inválido! Processando todas as páginas.")
                            max_paginas = None
                    except ValueError:
                        print("❌ Número inválido! Processando todas as páginas.")
                        max_paginas = None
                
                if opcao == "1":
                    urls, erros = scraper.scrape("filmes", max_paginas)
                    scraper.salvar_resultados("filmes", urls, erros)
                    
                elif opcao == "2":
                    urls, erros = scraper.scrape("series", max_paginas)
                    scraper.salvar_resultados("series", urls, erros)
                    
                elif opcao == "3":
                    print("\n" + "="*60)
                    print("PROCESSANDO FILMES")
                    print("="*60)
                    urls_f, erros_f = scraper.scrape("filmes", max_paginas)
                    scraper.salvar_resultados("filmes", urls_f, erros_f)
                    
                    print("\n" + "="*60)
                    print("PROCESSANDO SÉRIES")
                    print("="*60)
                    urls_s, erros_s = scraper.scrape("series", max_paginas)
                    scraper.salvar_resultados("series", urls_s, erros_s)
                
                print("\n✅ Processo concluído!")
                print("\nDeseja fazer outra extração?")
                
            except KeyboardInterrupt:
                print("\n\n⚠️ Operação cancelada pelo usuário")
                break
            except Exception as e:
                print(f"\n❌ Erro: {e}")
                continue
    
    finally:
        scraper.exibir_estatisticas_finais()
    
    print("👋 Até logo!\n")


if __name__ == "__main__":
    menu_interativo()