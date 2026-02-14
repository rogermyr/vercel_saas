import requests
import time
import os
import logging
import json
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import create_engine, Column, Integer, String, DateTime, func, text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import IntegrityError
from flask import Flask, jsonify
from pathlib import Path
from dotenv import load_dotenv

# --- CARREGAMENTO DE CONFIGURAÇÕES ----
base_dir = Path(__file__).resolve().parent
env_path = base_dir.parent / '.env'
load_dotenv(dotenv_path=env_path)

DB_CONNECTION_STRING = os.getenv("DATABASE_URL")
# Se estiver no Supabase/Pooler, o SQLAlchemy 2.0+ exige o prefixo postgresql://
if DB_CONNECTION_STRING and DB_CONNECTION_STRING.startswith("postgres://"):
    DB_CONNECTION_STRING = DB_CONNECTION_STRING.replace("postgres://", "postgresql://", 1)

# --- LOGS ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- CONFIGURAÇÕES DO NEGÓCIO ---
MODALIDADES = {
    1: "Leilão Eletrônico",
    2: "Diálogo Competitivo",
    3: "Concurso",
    4: "Concorrência - Eletrônica",
    5: "Concorrência - Presencial",
    6: "Pregão - Eletrônico",
    7: "Pregão - Presencial",
    8: "Dispensa",
    9: "Inexigibilidade",
    10: "Manifestação de Interesse",
    11: "Pré-qualificação",
    12: "Credenciamento",
    13: "Leilão - Presencial",
    14: "Inaplicabilidade da Licitação",
    15: "Chamada pública"
}

MAX_WORKERS = 15  # Aumentado de 3 para 15 para mais paralelização
# Mude para None para baixar TODAS as páginas (Local) ou um número baixo como 2 (Vercel)
LIMITE_PAGINAS_POR_MODALIDADE = None

Base = declarative_base()

# --- MODELOS ---
class BronzeLicitacao(Base):
    __tablename__ = 'bronze_pncp_licitacoes'
    id = Column(Integer, primary_key=True)
    identificador_pncp = Column(String, unique=True, nullable=False, index=True)
    data_publicacao = Column(DateTime, nullable=False, index=True)
    codigo_modalidade = Column(Integer, nullable=False, index=True) 
    payload = Column(JSONB, nullable=False) 
    status_processamento = Column(String, default='PENDING', index=True)
    ingested_at = Column(DateTime, server_default=func.now())

class ProgressoColeta(Base):
    __tablename__ = 'progresso_coleta'
    codigo_modalidade = Column(Integer, primary_key=True) 
    ultima_data_publicacao = Column(DateTime)
    data_atualizacao = Column(DateTime, default=datetime.now, onupdate=datetime.now)

# --- CORE DO CRAWLER ---
class PNCPCrawler:
    def __init__(self, db_string):
        # Otimizado: pool maior para suportar mais workers
        self.engine = create_engine(db_string, pool_size=10, max_overflow=20)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()
        self.base_url = "https://pncp.gov.br/api/consulta/v1/contratacoes/atualizacao"

    def fechar_sessao(self):
        self.session.close()
        
    def obter_ultima_data_banco(self, codigo_modalidade):
        registro = self.session.query(ProgressoColeta).filter_by(codigo_modalidade=codigo_modalidade).first()
        return registro.ultima_data_publicacao if registro else None

    def atualizar_progresso(self, codigo_modalidade, nova_data_maxima):
        registro = self.session.query(ProgressoColeta).filter_by(codigo_modalidade=codigo_modalidade).first()
        if registro:
            if nova_data_maxima and nova_data_maxima > registro.ultima_data_publicacao: 
                registro.ultima_data_publicacao = nova_data_maxima
        elif nova_data_maxima:
            registro = ProgressoColeta(codigo_modalidade=codigo_modalidade, ultima_data_publicacao=nova_data_maxima)
            self.session.add(registro)
        
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()

    def salvar_lote_bronze(self, lista_licitacoes, codigo_modalidade):
        data_maxima_lote = None
        processados_contagem = 0

        # Usar INSERT ... ON CONFLICT para evitar race conditions
        sql_insert_update = text("""
            INSERT INTO bronze_pncp_licitacoes (
                identificador_pncp, data_publicacao, codigo_modalidade, payload, status_processamento
            ) VALUES (
                :identificador_pncp, :data_publicacao, :codigo_modalidade, :payload, 'PENDING'
            )
            ON CONFLICT (identificador_pncp)
            DO UPDATE SET
                payload = EXCLUDED.payload,
                data_publicacao = EXCLUDED.data_publicacao
            WHERE bronze_pncp_licitacoes.payload::text != EXCLUDED.payload::text
        """)

        for item in lista_licitacoes:
            chave_unica = item.get('numeroControlePNCP')
            data_pub_item = datetime.strptime(item['dataPublicacaoPncp'], "%Y-%m-%dT%H:%M:%S")

            if data_maxima_lote is None or data_pub_item > data_maxima_lote:
                data_maxima_lote = data_pub_item

            try:
                # Executar INSERT com ON CONFLICT
                result = self.session.execute(sql_insert_update, {
                    'identificador_pncp': chave_unica,
                    'data_publicacao': data_pub_item,
                    'codigo_modalidade': codigo_modalidade,
                    'payload': json.dumps(item)  # Converter dict para JSON string
                })

                # Verificar se foi insert (1 linha afetada) ou update (1 linha afetada)
                # ON CONFLICT sempre retorna 1 linha afetada
                processados_contagem += 1

            except Exception as e:
                logger.error(f"Erro ao processar {chave_unica}: {e}")
                self.session.rollback()
                continue

        # Commit final
        try:
            self.session.commit()
        except Exception as e:
            self.session.rollback()
            logger.error(f"Erro no commit final: {e}")

        logger.info(f"📦 Processados: {processados_contagem} registros")
        return data_maxima_lote, processados_contagem

    def buscar_dados(self, data_inicial, data_final, codigo_modalidade):
        max_data_encontrada = None
        headers = {'User-Agent': 'Crawler-SaaS/1.0', 'Accept': 'application/json'}

        # FASE 1: Apenas 1 request para descobrir total de páginas e processar página 1
        logger.info(f"🔍 Mod {codigo_modalidade}: Descobrindo total de páginas...")

        pagina = 1
        params = {
            "dataInicial": data_inicial, "dataFinal": data_final,
            'codigoModalidadeContratacao': codigo_modalidade,
            "pagina": pagina, "tamanhoPagina": 50
        }

        try:
            response = requests.get(self.base_url, params=params, headers=headers, timeout=30)
            if response.status_code == 204:
                logger.info(f"📭 Mod {codigo_modalidade}: Nenhuma licitação encontrada")
                return
            if response.status_code != 200:
                logger.error(f"❌ Erro na API (status {response.status_code}) para modalidade {codigo_modalidade}")
                return

            dados = response.json()
            total_paginas = dados.get('totalPaginas', 1)
            resultados = dados.get('data', [])

            logger.info(f"📊 Mod {codigo_modalidade}: Encontradas {total_paginas} páginas totais")

            if not resultados:
                logger.info(f"📭 Mod {codigo_modalidade}: Página 1 vazia")
                return

            # Processar página 1
            data_max_lote, qtd = self.salvar_lote_bronze(resultados, codigo_modalidade)
            logger.info(f"📦 Mod {codigo_modalidade} | Pág {pagina}/{total_paginas} | Novos: {qtd}")

            if data_max_lote and (max_data_encontrada is None or data_max_lote > max_data_encontrada):
                max_data_encontrada = data_max_lote

        except Exception as e:
            logger.error(f"Erro crítico na descoberta de páginas: {e}")
            return

        # FASE 2: Processar páginas restantes em paralelo (se houver)
        if total_paginas > 1:
            paginas_para_processar = list(range(2, total_paginas + 1))  # Páginas 2 até total_paginas

            # Limitar para não sobrecarregar (respeitar LIMITE_PAGINAS_POR_MODALIDADE)
            if LIMITE_PAGINAS_POR_MODALIDADE:
                paginas_para_processar = paginas_para_processar[:LIMITE_PAGINAS_POR_MODALIDADE - 1]

            if paginas_para_processar:
                logger.info(f"⚡ Mod {codigo_modalidade}: Processando {len(paginas_para_processar)} páginas restantes em paralelo...")

                # Usar ThreadPoolExecutor para processar páginas em paralelo
                with ThreadPoolExecutor(max_workers=min(len(paginas_para_processar), 5)) as executor:  # Máximo 5 workers por modalidade
                    futures = []
                    for pag in paginas_para_processar:
                        futures.append(executor.submit(self.processar_pagina, data_inicial, data_final, codigo_modalidade, pag))

                    # Aguardar todas as páginas serem processadas
                    for future in as_completed(futures):
                        try:
                            data_max_pagina = future.result()
                            if data_max_pagina and (max_data_encontrada is None or data_max_pagina > max_data_encontrada):
                                max_data_encontrada = data_max_pagina
                        except Exception as e:
                            logger.error(f"Erro ao processar página em paralelo: {e}")

        if max_data_encontrada:
            self.atualizar_progresso(codigo_modalidade, max_data_encontrada)

    def processar_pagina(self, data_inicial, data_final, codigo_modalidade, pagina):
        """Processa uma página específica em paralelo."""
        headers = {'User-Agent': 'Crawler-SaaS/1.0', 'Accept': 'application/json'}

        params = {
            "dataInicial": data_inicial, "dataFinal": data_final,
            'codigoModalidadeContratacao': codigo_modalidade,
            "pagina": pagina, "tamanhoPagina": 50
        }

        # Criar sessão independente para este worker
        session = self.Session()

        try:
            response = requests.get(self.base_url, params=params, headers=headers, timeout=30)
            if response.status_code == 204:
                return None
            if response.status_code != 200:
                logger.warning(f"Status {response.status_code} na página {pagina}")
                return None

            dados = response.json()
            resultados = dados.get('data', [])

            if not resultados:
                return None

            # Usar método próprio para salvar com sessão independente
            data_max_lote, qtd = self.salvar_lote_bronze_worker(session, resultados, codigo_modalidade)
            logger.info(f"📦 Mod {codigo_modalidade} | Pág {pagina} | Novos: {qtd}")

            return data_max_lote

        except Exception as e:
            logger.error(f"Erro na página {pagina}: {e}")
            return None
        finally:
            session.close()

    def salvar_lote_bronze_worker(self, session, lista_licitacoes, codigo_modalidade):
        """Versão do salvar_lote_bronze para workers paralelos com sessão própria."""
        data_maxima_lote = None
        processados_contagem = 0

        # Usar INSERT ... ON CONFLICT para evitar race conditions
        sql_insert_update = text("""
            INSERT INTO bronze_pncp_licitacoes (
                identificador_pncp, data_publicacao, codigo_modalidade, payload, status_processamento
            ) VALUES (
                :identificador_pncp, :data_publicacao, :codigo_modalidade, :payload, 'PENDING'
            )
            ON CONFLICT (identificador_pncp)
            DO UPDATE SET
                payload = EXCLUDED.payload,
                data_publicacao = EXCLUDED.data_publicacao
            WHERE bronze_pncp_licitacoes.payload::text != EXCLUDED.payload::text
        """)

        for item in lista_licitacoes:
            chave_unica = item.get('numeroControlePNCP')
            data_pub_item = datetime.strptime(item['dataPublicacaoPncp'], "%Y-%m-%dT%H:%M:%S")

            if data_maxima_lote is None or data_pub_item > data_maxima_lote:
                data_maxima_lote = data_pub_item

            try:
                # Executar INSERT com ON CONFLICT
                result = session.execute(sql_insert_update, {
                    'identificador_pncp': chave_unica,
                    'data_publicacao': data_pub_item,
                    'codigo_modalidade': codigo_modalidade,
                    'payload': json.dumps(item)  # Converter dict para JSON string
                })

                processados_contagem += 1

            except Exception as e:
                logger.error(f"Erro ao processar {chave_unica}: {e}")
                session.rollback()
                continue

        # Commit final
        try:
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Erro no commit final: {e}")

        logger.info(f"📦 Processados: {processados_contagem} registros")
        return data_maxima_lote, processados_contagem


def run_process(db_url):
    logger.info("🚀 Iniciando processamento paralelo de modalidades.")
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = []
        for c, n in MODALIDADES.items():
            crawler = PNCPCrawler(db_url)
            agora = datetime.now()
            ultima_data = crawler.obter_ultima_data_banco(c)
            data_ini = ultima_data if ultima_data else (agora - timedelta(days=7))

            futures.append(executor.submit(crawler.buscar_dados, data_ini.strftime("%Y%m%d"), agora.strftime("%Y%m%d"), c))

        for future in as_completed(futures):
            future.result() # Garante que esperamos o fim de cada modalidade

    logger.info("✅ Todas as modalidades processadas.")

def run_crawler_process():
    """Executa o crawler sem retornar resposta Flask (para uso em scripts)."""
    run_process(DB_CONNECTION_STRING)
    return {"status": "success", "message": "Crawler finished"}

def handle_crawler():
    """Handler Flask para a API (mantido para compatibilidade)."""
    run_process(DB_CONNECTION_STRING)
    return jsonify({"status": "success", "message": "Crawler finished"}), 200
