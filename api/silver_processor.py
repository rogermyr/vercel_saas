import os
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from flask import jsonify
from pathlib import Path
from dotenv import load_dotenv

# --- CARREGAMENTO DE CONFIGURAÇÕES ---
base_dir = Path(__file__).resolve().parent
env_path = base_dir.parent / '.env'
load_dotenv(dotenv_path=env_path)

# Configuração de Logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- CONFIGURAÇÕES ---
DB_CONNECTION_STRING = os.getenv("DATABASE_URL")
# Se estiver no Supabase/Pooler, o SQLAlchemy 2.0+ exige o prefixo postgresql://
if DB_CONNECTION_STRING and DB_CONNECTION_STRING.startswith("postgres://"):
    DB_CONNECTION_STRING = DB_CONNECTION_STRING.replace("postgres://", "postgresql://", 1)

# --- FUNÇÕES DE TRANSFORMAÇÃO ---

def transformar_licitacao(session, bronze_id, payload):
    """Normaliza o JSON da Licitação para a tabela Silver (incluindo datas e local)."""
    orgao = payload.get('orgaoEntidade', {}) or {}
    unidade = payload.get('unidadeOrgao', {}) or {}
    
    # Limpeza básica de texto para evitar quebras no layout do React
    objeto = (payload.get('objetoCompra', '') or '').replace('\t', ' ').replace('\n', ' ').strip()

    stmt = text("""
        INSERT INTO silver_licitacoes (
            identificador_pncp, objeto_compra, ano_compra, data_publicacao,
            data_encerramento, municipio_nome, uf_sigla, orgao_razao_social, orgao_cnpj,
            valor_total_estimado, valor_total_homologado, situacao_nome, modalidade_nome
        ) VALUES (
            :id, :objeto, :ano, :data_p, :data_e, :muni, :uf, :razao, :cnpj, :v_est, :v_hom, :situ, :mod
        ) ON CONFLICT (identificador_pncp) DO UPDATE SET
            data_encerramento = EXCLUDED.data_encerramento,
            valor_total_homologado = EXCLUDED.valor_total_homologado,
            situacao_nome = EXCLUDED.situacao_nome,
            objeto_compra = EXCLUDED.objeto_compra;
    """)
    
    session.execute(stmt, {
        "id": payload.get('numeroControlePNCP'),
        "objeto": objeto,
        "ano": payload.get('anoCompra'),
        "data_p": payload.get('dataPublicacaoPncp'),
        "data_e": payload.get('dataEncerramentoProposta'), # EXTRAÇÃO NOVA
        "muni": unidade.get('municipioNome'),
        "uf": unidade.get('ufSigla'),
        "razao": orgao.get('razaoSocial'),
        "cnpj": orgao.get('cnpj'),
        "v_est": payload.get('valorTotalEstimado') or 0,
        "v_hom": payload.get('valorTotalHomologado'),
        "situ": payload.get('situacaoCompraNome'),
        "mod": payload.get('modalidadeNome')
    })
    
    # Marca a linha bronze como processada
    session.execute(text("UPDATE bronze_pncp_licitacoes SET status_processamento = 'PROCESSED' WHERE id = :id"), {"id": bronze_id})


def transformar_item(session, bronze_item_id, identificador_licit, payload):
    """Normaliza o JSON do Item para a tabela Silver com cálculo de valor e truncate."""
    
    # Lógica de cálculo: se a API mandar 0 no total, calculamos manualmente
    qtd = payload.get('quantidade') or 0
    v_uni = payload.get('valorUnitarioEstimado') or 0
    v_tot_api = payload.get('valorTotalEstimado') or 0
    v_tot_final = v_tot_api if v_tot_api > 0 else (qtd * v_uni)

    # Truncate de segurança para unidade_medida (limite de 50 caracteres)
    und_raw = payload.get('unidadeMedida') or ''
    und_clean = str(und_raw)[:50]

    stmt = text("""
        INSERT INTO silver_itens (
            licitacao_identificador, numero_item, descricao, quantidade,
            valor_unitario_estimado, valor_total_estimado, unidade_medida,
            situacao_item_nome, categoria_item_nome
        ) VALUES (
            :licit_id, :num, :desc, :qtd, :v_uni, :v_tot, :und, :situ, :cat
        ) ON CONFLICT DO NOTHING;
    """)
    
    session.execute(stmt, {
        "licit_id": identificador_licit,
        "num": payload.get('numeroItem'),
        "desc": payload.get('descricao'),
        "qtd": qtd,
        "v_uni": v_uni,
        "v_tot": v_tot_final,
        "und": und_clean,
        "situ": payload.get('situacaoItemNome'),
        "cat": payload.get('materialOuServicoNome')
    })
    
    # Marca a linha bronze do item como processada
    session.execute(text("UPDATE bronze_pncp_itens SET status_processamento = 'PROCESSED' WHERE id = :id"), {"id": bronze_item_id})


# --- ORQUESTRADOR ---

class SilverProcessor:
    def __init__(self, db_string):
        # Vercel serverless: use smaller pool sizes to avoid connection issues
        pool_size = 2 if os.getenv("VERCEL") else 5
        max_overflow = 5 if os.getenv("VERCEL") else 10
        self.engine = create_engine(db_string, pool_size=pool_size, max_overflow=max_overflow)
        self.Session = sessionmaker(bind=self.engine)

    def processar_tudo(self):
        """Executa a drenagem das tabelas Bronze em loop até esgotar os pendentes."""
        
        # 1. PROCESSAR LICITAÇÕES
        while True:
            session = self.Session()
            try:
                sql = text("SELECT id, payload FROM bronze_pncp_licitacoes WHERE status_processamento = 'PENDING' LIMIT 500")
                pendentes = session.execute(sql).fetchall()
                if not pendentes: 
                    break
                
                for r in pendentes:
                    transformar_licitacao(session, r[0], r[1])
                
                session.commit()
                logger.info(f"✅ Silver: Lote de {len(pendentes)} licitações normalizado.")
            except Exception as e:
                session.rollback()
                logger.error(f"❌ Erro no processamento de licitações: {e}")
                break 
            finally:
                session.close()

        # 2. PROCESSAR ITENS
        while True:
            session = self.Session()
            try:
                # Query inteligente: apenas processa itens se a licitação pai já existir na Silver
                sql_itens = text("""
                    SELECT T1.id, T1.licitacao_identificador, T1.payload 
                    FROM bronze_pncp_itens T1
                    WHERE T1.status_processamento = 'PENDING'
                    AND EXISTS (SELECT 1 FROM silver_licitacoes T2 WHERE T2.identificador_pncp = T1.licitacao_identificador)
                    LIMIT 2000
                """)
                pendentes_itens = session.execute(sql_itens).fetchall()
                
                if not pendentes_itens: 
                    break

                for r in pendentes_itens:
                    transformar_item(session, r[0], r[1], r[2])
                
                session.commit()
                logger.info(f"✅ Silver: Lote de {len(pendentes_itens)} itens normalizado.")
            except Exception as e:
                session.rollback()
                logger.error(f"❌ Erro no processamento de itens: {e}")
                break
            finally:
                session.close()

        logger.info("🎉 Sincronização Bronze -> Silver finalizada com sucesso.")

def run_silver_processor(db_url=None):
    """Função principal que executa o processamento Silver."""
    if db_url is None:
        db_url = DB_CONNECTION_STRING
    
    processor = SilverProcessor(db_url)
    processor.processar_tudo()

def handle_silver_processor():
    """
    Handler para Vercel serverless/cron jobs.
    Processa lotes menores para evitar timeout (Vercel tem limite de 60s no Hobby).
    """
    try:
        # Configurações adaptadas para Vercel
        db_url = DB_CONNECTION_STRING
        
        if not db_url:
            logger.error("❌ DATABASE_URL não configurada")
            return jsonify({"status": "error", "message": "DATABASE_URL não configurada"}), 500
        
        processor = SilverProcessor(db_url)
        
        # Para Vercel, processamos em lotes menores
        # Em vez de processar tudo de uma vez, podemos limitar o número de iterações
        licitacoes_processadas = 0
        itens_processados = 0
        
        # PROCESSAR LICITAÇÕES (limitado para Vercel)
        max_batches = 10 if os.getenv("VERCEL") else None  # Limita a 10 lotes na Vercel
        batch_count = 0
        
        while True:
            if max_batches and batch_count >= max_batches:
                logger.info(f"⏱️ Limite de lotes atingido ({max_batches}) - Vercel timeout protection")
                break
                
            session = processor.Session()
            try:
                sql = text("SELECT id, payload FROM bronze_pncp_licitacoes WHERE status_processamento = 'PENDING' LIMIT 500")
                pendentes = session.execute(sql).fetchall()
                if not pendentes: 
                    break
                
                for r in pendentes:
                    transformar_licitacao(session, r[0], r[1])
                    licitacoes_processadas += 1
                
                session.commit()
                batch_count += 1
                logger.info(f"✅ Silver: Lote de {len(pendentes)} licitações normalizado.")
            except Exception as e:
                session.rollback()
                logger.error(f"❌ Erro no processamento de licitações: {e}")
                break 
            finally:
                session.close()

        # PROCESSAR ITENS (limitado para Vercel)
        max_item_batches = 10 if os.getenv("VERCEL") else None
        item_batch_count = 0
        
        while True:
            if max_item_batches and item_batch_count >= max_item_batches:
                logger.info(f"⏱️ Limite de lotes de itens atingido ({max_item_batches}) - Vercel timeout protection")
                break
                
            session = processor.Session()
            try:
                sql_itens = text("""
                    SELECT T1.id, T1.licitacao_identificador, T1.payload 
                    FROM bronze_pncp_itens T1
                    WHERE T1.status_processamento = 'PENDING'
                    AND EXISTS (SELECT 1 FROM silver_licitacoes T2 WHERE T2.identificador_pncp = T1.licitacao_identificador)
                    LIMIT 2000
                """)
                pendentes_itens = session.execute(sql_itens).fetchall()
                
                if not pendentes_itens: 
                    break

                for r in pendentes_itens:
                    transformar_item(session, r[0], r[1], r[2])
                    itens_processados += 1
                
                session.commit()
                item_batch_count += 1
                logger.info(f"✅ Silver: Lote de {len(pendentes_itens)} itens normalizado.")
            except Exception as e:
                session.rollback()
                logger.error(f"❌ Erro no processamento de itens: {e}")
                break
            finally:
                session.close()
        
        # Cleanup
        processor.engine.dispose()
        
        logger.info(f"🎉 Processamento Silver concluído: {licitacoes_processadas} licitações, {itens_processados} itens")
        
        return jsonify({
            "status": "success",
            "message": "Silver processor executado com sucesso",
            "licitacoes_processadas": licitacoes_processadas,
            "itens_processados": itens_processados
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Erro no handler Silver: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500