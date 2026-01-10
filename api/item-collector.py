import requests
import os
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed 
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import create_engine, Column, Integer, String, DateTime, func, text
from sqlalchemy.orm import declarative_base, sessionmaker
from flask import Flask, jsonify
from pathlib import Path
from dotenv import load_dotenv

# --- CARREGAMENTO DE CONFIGURAÇÕES ---
base_dir = Path(__file__).resolve().parent
env_path = base_dir.parent / '.env'
load_dotenv(dotenv_path=env_path)

DB_CONNECTION_STRING = os.getenv("DATABASE_URL")

# --- LOGS ---
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# --- CONFIGURAÇÕES DO LOTE (CRÍTICO PARA VERCEL) ---
# Na Vercel, use lotes pequenos (10-20) para não estourar o timeout de 60s
# No WSL (Local), você pode aumentar para 100 ou 500
LIMIT_LOTE = 20 if os.getenv("VERCEL") else 100
MAX_WORKERS = 10

Base = declarative_base()

# --- MODELOS ---
class BronzeLicitacao(Base):
    __tablename__ = 'bronze_pncp_licitacoes'
    id = Column(Integer, primary_key=True)
    identificador_pncp = Column(String, unique=True, index=True)
    payload = Column(JSONB)
    status_itens = Column(String, default='PENDING')

class BronzeItem(Base):
    __tablename__ = 'bronze_pncp_itens'
    id = Column(Integer, primary_key=True)
    licitacao_identificador = Column(String, index=True) 
    payload = Column(JSONB, nullable=False)
    ingested_at = Column(DateTime, server_default=func.now())

# --- FUNÇÕES AUXILIARES ---

def baixar_itens_api(identificador_pncp, cnpj, ano, sequencial):
    url = f"https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{sequencial}/itens"
    itens_para_inserir = []
    try:
        # Simplificado para o MVP: busca apenas a primeira página de itens
        # (A maioria das licitações tem menos de 50 itens)
        response = requests.get(url, params={"pagina": 1}, timeout=20)
        if response.status_code == 200:
            data = response.json()
            lista = data if isinstance(data, list) else data.get('data', [])
            for item in lista:
                itens_para_inserir.append(BronzeItem(licitacao_identificador=identificador_pncp, payload=item))
    except Exception as e:
        logger.error(f"Erro API Itens {identificador_pncp}: {e}")
    return itens_para_inserir

def processar_licitacao_worker(db_engine, identificador_pncp, payload):
    Session = sessionmaker(bind=db_engine)
    session = Session()
    try:
        cnpj = payload.get('orgaoEntidade', {}).get('cnpj')
        ano = payload.get('anoCompra')
        seq = payload.get('sequencialCompra')

        if not all([cnpj, ano, seq]):
            session.execute(text("UPDATE bronze_pncp_licitacoes SET status_itens = 'SKIP' WHERE identificador_pncp = :id"), {"id": identificador_pncp})
            session.commit()
            return

        itens = baixar_itens_api(identificador_pncp, cnpj, ano, seq)
        
        if itens:
            session.bulk_save_objects(itens)
            logger.info(f"✅ {len(itens)} itens -> {identificador_pncp}")
        
        session.execute(text("UPDATE bronze_pncp_licitacoes SET status_itens = 'COMPLETED' WHERE identificador_pncp = :id"), {"id": identificador_pncp})
        session.commit()
    except Exception as e:
        logger.error(f"Erro no worker {identificador_pncp}: {e}")
        session.rollback()
    finally:
        session.close()


@app.route('/api/cron/items', methods=['GET'])
def handle_item_collector():
    engine = create_engine(DB_CONNECTION_STRING, pool_size=5, max_overflow=10)
    Base.metadata.create_all(engine)
    
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Busca apenas o que está PENDING
        lote = session.execute(
            text("SELECT identificador_pncp, payload FROM bronze_pncp_licitacoes WHERE status_itens = 'PENDING' LIMIT :limit"),
            {"limit": LIMIT_LOTE}
        ).fetchall()
        session.close()

        if not lote:
            return jsonify({"status": "idle", "message": "Fila vazia"}), 200

        logger.info(f"📦 Coletando itens de {len(lote)} licitações...")

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(processar_licitacao_worker, engine, row[0], row[1]) for row in lote]
            for future in as_completed(futures):
                future.result()

        return jsonify({"status": "success", "processed": len(lote)}), 200

    except Exception as e:
        logger.error(f"Falha no coletor: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        engine.dispose()