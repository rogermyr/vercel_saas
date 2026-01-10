import requests
import time
import os
import logging
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed 
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import create_engine, Column, Integer, String, DateTime, func
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import IntegrityError
from flask import Flask, jsonify
from pathlib import Path
from dotenv import load_dotenv

# --- CARREGAMENTO DE CONFIGURAÇÕES ---
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
    6: "Pregão - Eletrônico", 
    8: "Dispensa", 
    9: "Inexigibilidade"
}

MAX_WORKERS = 3 
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
        self.engine = create_engine(db_string, pool_size=2, max_overflow=5)
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
        novos_contagem = 0
        for item in lista_licitacoes:
            chave_unica = item.get('numeroControlePNCP')
            data_pub_item = datetime.strptime(item['dataPublicacaoPncp'], "%Y-%m-%dT%H:%M:%S")
            
            if data_maxima_lote is None or data_pub_item > data_maxima_lote:
                data_maxima_lote = data_pub_item

            nova_licitacao = BronzeLicitacao(
                identificador_pncp=chave_unica,
                data_publicacao=data_pub_item,
                codigo_modalidade=codigo_modalidade, 
                payload=item
            )
            self.session.add(nova_licitacao) 
            try:
                self.session.commit()
                novos_contagem += 1
            except IntegrityError:
                self.session.rollback() 
            except Exception as e:
                self.session.rollback()
                logger.error(f"Erro ao inserir {chave_unica}: {e}")
        return data_maxima_lote, novos_contagem

    def buscar_dados(self, data_inicial, data_final, codigo_modalidade):
        pagina = 1
        total_paginas = 1
        max_data_encontrada = None
        headers = {'User-Agent': 'Crawler-SaaS/1.0', 'Accept': 'application/json'}

        while pagina <= total_paginas:
            # Se houver um limite definido (Vercel), respeita. Se for None (Local), ignora.
            if LIMITE_PAGINAS_POR_MODALIDADE and pagina > LIMITE_PAGINAS_POR_MODALIDADE:
                break

            params = {
                "dataInicial": data_inicial, "dataFinal": data_final,
                'codigoModalidadeContratacao': codigo_modalidade,
                "pagina": pagina, "tamanhoPagina": 50 
            }
            
            try:
                response = requests.get(self.base_url, params=params, headers=headers, timeout=30)
                if response.status_code == 204: break
                if response.status_code != 200: break
                
                dados = response.json()
                total_paginas = dados.get('totalPaginas', 1)
                resultados = dados.get('data', [])
                
                if not resultados: break

                data_max_lote, qtd = self.salvar_lote_bronze(resultados, codigo_modalidade)
                logger.info(f"📦 Mod {codigo_modalidade} | Pág {pagina}/{total_paginas} | Novos: {qtd}")

                if data_max_lote and (max_data_encontrada is None or data_max_lote > max_data_encontrada):
                    max_data_encontrada = data_max_lote
                
                pagina += 1
                time.sleep(0.2)

            except Exception as e:
                logger.error(f"Erro crítico na página {pagina}: {e}")
                break
        
        if max_data_encontrada:
            self.atualizar_progresso(codigo_modalidade, max_data_encontrada)

# --- FLASK APP ---
app = Flask(__name__)

def run_process(db_url):
    logger.info("🚀 Iniciando processamento de threads.")
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

@app.route('/api/cron/crawler', methods=['GET'])
def handle_crawler():
    run_process(DB_CONNECTION_STRING)
    return jsonify({"status": "success", "message": "Crawler finished"}), 200

if __name__ == "__main__":
    import sys
    if len(sys.argv) == 1:
        print(f"🖥️ Execução Local. DB: {DB_CONNECTION_STRING}")
        with app.app_context():
            run_process(DB_CONNECTION_STRING)
            print("🎉 Fim da carga local.")
    else:
        app.run(debug=True)