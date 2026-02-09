import os
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from flask import jsonify
from pathlib import Path
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed

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

    # Filtrar apenas itens com situação 'Em andamento'
    situacao = payload.get('situacaoCompraItemNome')
    if situacao != 'Em andamento':
        logger.debug(f"⏭️ Item {identificador_licit}-{payload.get('numeroItem')} ignorado (situação: {situacao})")
        # Ainda marca como processado para não reprocessar
        session.execute(text("UPDATE bronze_pncp_itens SET status_processamento = 'PROCESSED' WHERE id = :id"), {"id": bronze_item_id})
        return

    # Lógica de cálculo: se a API mandar 0 no total, calculamos manualmente
    qtd = payload.get('quantidade') or 0
    v_uni = payload.get('valorUnitarioEstimado') or 0
    v_tot_api = payload.get('valorTotal') or 0
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
        );
    """)

    try:
        session.execute(stmt, {
            "licit_id": identificador_licit,
            "num": payload.get('numeroItem'),
            "desc": payload.get('descricao'),
            "qtd": qtd,
            "v_uni": v_uni,
            "v_tot": v_tot_final,
            "und": und_clean,
            "situ": situacao,
            "cat": payload.get('materialOuServicoNome')
        })
        logger.debug(f"➕ Item {identificador_licit}-{payload.get('numeroItem')} inserido")
    except Exception as e:
        # Se der erro de violação de chave única, significa que já existe
        logger.debug(f"🔄 Item {identificador_licit}-{payload.get('numeroItem')} já existe (chave duplicada)")

    # Marca a linha bronze do item como processada
    session.execute(text("UPDATE bronze_pncp_itens SET status_processamento = 'PROCESSED' WHERE id = :id"), {"id": bronze_item_id})


# --- ORQUESTRADOR ---

class SilverProcessor:
    def __init__(self, db_string):
        # Otimizado para servidor dedicado (Hetzner)
        pool_size = 10
        max_overflow = 20
        self.engine = create_engine(db_string, pool_size=pool_size, max_overflow=max_overflow)
        self.Session = sessionmaker(bind=self.engine)

    def processar_batch_licitacoes(self, batch_data):
        """Processa um lote de licitações em paralelo."""
        session = self.Session()
        try:
            pendentes, offset = batch_data

            # BULK INSERT: preparar dados para inserção em lote
            licitacoes_data = []
            ids_para_update = []

            for r in pendentes:
                bronze_id, payload = r[0], r[1]
                ids_para_update.append(bronze_id)

                # Preparar dados para bulk insert
                orgao = payload.get('orgaoEntidade', {}) or {}
                unidade = payload.get('unidadeOrgao', {}) or {}
                objeto = (payload.get('objetoCompra', '') or '').replace('\t', ' ').replace('\n', ' ').strip()

                licitacoes_data.append({
                    "id": payload.get('numeroControlePNCP'),
                    "objeto": objeto,
                    "ano": payload.get('anoCompra'),
                    "data_p": payload.get('dataPublicacaoPncp'),
                    "data_e": payload.get('dataEncerramentoProposta'),
                    "muni": unidade.get('municipioNome'),
                    "uf": unidade.get('ufSigla'),
                    "razao": orgao.get('razaoSocial'),
                    "cnpj": orgao.get('cnpj'),
                    "v_est": payload.get('valorTotalEstimado') or 0,
                    "v_hom": payload.get('valorTotalHomologado'),
                    "situ": payload.get('situacaoCompraNome'),
                    "mod": payload.get('modalidadeNome')
                })

            # Bulk insert licitações
            if licitacoes_data:
                stmt_licit = text("""
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
                session.execute(stmt_licit, licitacoes_data)

                # Bulk update status
                if ids_para_update:
                    stmt_update = text("UPDATE bronze_pncp_licitacoes SET status_processamento = 'PROCESSED' WHERE id = ANY(:ids)")
                    session.execute(stmt_update, {"ids": ids_para_update})

            session.commit()
            return len(pendentes)
        except Exception as e:
            session.rollback()
            logger.error(f"❌ Erro no processamento paralelo de licitações: {e}")
            return 0
        finally:
            session.close()

    def processar_batch_itens(self, batch_data):
        """Processa um lote de itens em paralelo."""
        session = self.Session()
        try:
            pendentes_itens, offset = batch_data

            # Log de progresso do lote
            logger.info(f"📦 Processando lote de {len(pendentes_itens)} itens (offset: {offset})")

            # BULK INSERT: preparar dados para inserção em lote
            itens_data = []
            ids_para_update = []

            for r in pendentes_itens:
                bronze_item_id, identificador_licit, payload = r[0], r[1], r[2]
                ids_para_update.append(bronze_item_id)

                # Preparar dados para bulk insert
                qtd = payload.get('quantidade') or 0

                # Tentar diferentes nomes para valor unitário
                v_uni = (payload.get('valorUnitarioEstimado') or
                        payload.get('valorUnitario') or
                        payload.get('valor_unitario') or 0)

                v_tot_api = payload.get('valorTotal') or 0
                v_tot_final = v_tot_api if v_tot_api > 0 else (qtd * v_uni)

                # Tentar diferentes nomes para unidade de medida
                und_raw = (payload.get('unidadeMedida') or
                          payload.get('unidadeFornecimento') or
                          payload.get('unidade_medida') or '')

                und_clean = str(und_raw)[:50]

                itens_data.append({
                    "licit_id": identificador_licit,
                    "num": payload.get('numeroItem'),
                    "desc": payload.get('descricao'),
                    "qtd": qtd,
                    "v_uni": v_uni,
                    "v_tot": v_tot_final,
                    "und": und_clean,
                    "situ": payload.get('situacaoCompraItemNome'),
                    "cat": payload.get('materialOuServicoNome')
                })

            # Bulk insert itens
            if itens_data:
                stmt_itens = text("""
                    INSERT INTO silver_itens (
                        licitacao_identificador, numero_item, descricao, quantidade,
                        valor_unitario_estimado, valor_total_estimado, unidade_medida,
                        situacao_item_nome, categoria_item_nome
                    ) VALUES (
                        :licit_id, :num, :desc, :qtd, :v_uni, :v_tot, :und, :situ, :cat
                    ) ON CONFLICT (licitacao_identificador, numero_item) DO NOTHING;
                """)
                session.execute(stmt_itens, itens_data)

                # Bulk update status
                if ids_para_update:
                    stmt_update = text("UPDATE bronze_pncp_itens SET status_processamento = 'PROCESSED' WHERE id = ANY(:ids)")
                    session.execute(stmt_update, {"ids": ids_para_update})

            session.commit()
            logger.info(f"✅ Lote processado: {len(pendentes_itens)} itens inseridos/atualizados")
            return len(pendentes_itens)
        except Exception as e:
            session.rollback()
            logger.error(f"❌ Erro no processamento paralelo de itens: {e}")
            return 0
        finally:
            session.close()

    def limpar_licitacoes_vencidas(self):
        """Remove licitações cuja data de encerramento já passou."""
        session = self.Session()
        try:
            stmt = text("""
                DELETE FROM silver_licitacoes
                WHERE data_encerramento IS NOT NULL
                AND data_encerramento < CURRENT_DATE;
            """)
            result = session.execute(stmt)
            session.commit()
            
            deleted_count = result.rowcount
            logger.info(f"🗑️ {deleted_count} licitações vencidas removidas")
            return deleted_count
        except Exception as e:
            session.rollback()
            logger.error(f"❌ Erro ao limpar licitações vencidas: {e}")
            return 0
        finally:
            session.close()

    def processar_tudo(self):
        """Executa a drenagem das tabelas Bronze em loop até esgotar os pendentes com processamento paralelo."""

        # Número de workers paralelos (ajuste baseado na CPU/memória disponível)
        num_workers = 4  # Pode ser ajustado: 2-8 dependendo do hardware

        # 1. PROCESSAR LICITAÇÕES COM PARALELISMO
        total_licitacoes_processadas = 0
        batch_size_licit = 5000

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            while True:
                # Coletar múltiplos lotes para processamento paralelo
                batches = []
                session = self.Session()
                try:
                    for i in range(num_workers):
                        sql = text(f"SELECT id, payload FROM bronze_pncp_licitacoes WHERE status_processamento = 'PENDING' LIMIT {batch_size_licit}")
                        pendentes = session.execute(sql).fetchall()
                        if not pendentes:
                            break
                        batches.append((pendentes, i * batch_size_licit))
                finally:
                    session.close()

                if not batches:
                    break

                # Processar lotes em paralelo
                futures = [executor.submit(self.processar_batch_licitacoes, batch) for batch in batches]
                batch_results = []
                for future in as_completed(futures):
                    result = future.result()
                    batch_results.append(result)
                    total_licitacoes_processadas += result

                logger.info(f"✅ Silver: {len(batch_results)} lotes paralelos processados - {sum(batch_results)} licitações (bulk).")

        logger.info(f"✅ Total licitações processadas: {total_licitacoes_processadas}")

        # 2. PROCESSAR ITENS COM PARALELISMO
        total_itens_processados = 0
        batch_size_itens = 10000

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            while True:
                # Coletar múltiplos lotes para processamento paralelo
                batches = []
                session = self.Session()
                try:
                    for i in range(num_workers):
                        sql_itens = text(f"""
                            SELECT T1.id, T1.licitacao_identificador, T1.payload
                            FROM bronze_pncp_itens T1
                            INNER JOIN silver_licitacoes T2 ON T2.identificador_pncp = T1.licitacao_identificador
                            WHERE T1.status_processamento = 'PENDING'
                            LIMIT {batch_size_itens}
                        """)
                        pendentes_itens = session.execute(sql_itens).fetchall()
                        if not pendentes_itens:
                            break
                        batches.append((pendentes_itens, i * batch_size_itens))
                finally:
                    session.close()

                if not batches:
                    break

                # Processar lotes em paralelo
                futures = [executor.submit(self.processar_batch_itens, batch) for batch in batches]
                batch_results = []
                for future in as_completed(futures):
                    result = future.result()
                    batch_results.append(result)
                    total_itens_processados += result

                logger.info(f"✅ Silver: {len(batch_results)} lotes paralelos processados - {sum(batch_results)} itens (bulk).")

        logger.info(f"✅ Total itens processados: {total_itens_processados}")
        logger.info("🎉 Sincronização Bronze -> Silver finalizada com sucesso.")
        
        # LIMPEZA: Remover licitações vencidas
        self.limpar_licitacoes_vencidas()

    def processar_apenas_itens(self):
        """Processa apenas os itens Silver (assume licitações já processadas)."""
        logger.info("🔄 Iniciando processamento APENAS de itens Silver...")

        # Verificar total inicial de itens pendentes
        session = self.Session()
        try:
            total_pendentes_inicial = session.execute(text("""
                SELECT COUNT(*) FROM bronze_pncp_itens
                WHERE status_processamento = 'PENDING'
                AND EXISTS (SELECT 1 FROM silver_licitacoes WHERE identificador_pncp = bronze_pncp_itens.licitacao_identificador)
            """)).scalar()
            logger.info(f"📊 Total de itens PENDING para processar: {total_pendentes_inicial}")
        finally:
            session.close()

        # Número de workers paralelos
        num_workers = 4

        # PROCESSAR APENAS ITENS COM PARALELISMO
        total_itens_processados = 0
        batch_size_itens = 1000  # Lotes menores para melhor controle de progresso
        lote_count = 0

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            while True:
                # Coletar múltiplos lotes para processamento paralelo REAL
                batches = []
                session = self.Session()
                try:
                    # Verificar se ainda há itens pendentes
                    total_pendentes_atual = session.execute(text("""
                        SELECT COUNT(*) FROM bronze_pncp_itens
                        WHERE status_processamento = 'PENDING'
                        AND EXISTS (SELECT 1 FROM silver_licitacoes WHERE identificador_pncp = bronze_pncp_itens.licitacao_identificador)
                    """)).scalar()

                    if total_pendentes_atual == 0:
                        break

                    # Cada worker pega um lote diferente usando OFFSET
                    for i in range(num_workers):
                        offset = i * batch_size_itens
                        sql_itens = text(f"""
                            SELECT T1.id, T1.licitacao_identificador, T1.payload
                            FROM bronze_pncp_itens T1
                            INNER JOIN silver_licitacoes T2 ON T2.identificador_pncp = T1.licitacao_identificador
                            WHERE T1.status_processamento = 'PENDING'
                            ORDER BY T1.id  -- Ordenação consistente para OFFSET
                            LIMIT {batch_size_itens} OFFSET {offset}
                        """)
                        pendentes_itens = session.execute(sql_itens).fetchall()
                        if pendentes_itens:  # Só adiciona se há itens
                            batches.append((pendentes_itens, offset))
                finally:
                    session.close()

                if not batches:
                    break

                lote_count += 1
                # Contar itens únicos (não somar workers)
                itens_no_lote = sum(len(batch[0]) for batch in batches)
                logger.info(f"🔄 Lote {lote_count}: Processando {itens_no_lote} itens únicos em {len(batches)} workers")

                # Processar lotes em paralelo
                futures = [executor.submit(self.processar_batch_itens, batch) for batch in batches]
                batch_results = []
                for future in as_completed(futures):
                    result = future.result()
                    batch_results.append(result)
                    total_itens_processados += result

                logger.info(f"✅ Lote {lote_count} concluído: {sum(batch_results)} itens processados por {len(batch_results)} workers")

                # Log de progresso a cada 5 lotes (mais frequente com lotes menores)
                if lote_count % 5 == 0:
                    progresso_percentual_atual = (total_itens_processados / total_pendentes_inicial * 100) if total_pendentes_inicial > 0 else 0
                    logger.info(f"📊 Progresso geral: {total_itens_processados}/{total_pendentes_inicial} itens ({progresso_percentual_atual:.1f}%)")

        # Calcular progresso final
        progresso_final = (total_itens_processados / total_pendentes_inicial * 100) if total_pendentes_inicial > 0 else 100
        logger.info(f"✅ Total itens processados: {total_itens_processados}/{total_pendentes_inicial} ({progresso_final:.1f}%)")
        logger.info("🎉 Processamento de itens Silver finalizado com sucesso!")
        
        # LIMPEZA: Remover licitações vencidas
        self.limpar_licitacoes_vencidas()

def run_silver_processor(db_url=None):
    """Função principal que executa o processamento Silver."""
    if db_url is None:
        db_url = DB_CONNECTION_STRING

    processor = SilverProcessor(db_url)
    processor.processar_tudo()

# def run_silver_itens_only(db_url=None):
#     """Processa apenas os itens Silver (assume licitações já processadas)."""
#     if db_url is None:
#         db_url = DB_CONNECTION_STRING
#
#     processor = SilverProcessor(db_url)
#     processor.processar_apenas_itens()

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
        
        # PROCESSAR LICITAÇÕES (sem limites no servidor dedicado)
        max_batches = None  # Sem limite de batches no Hetzner
        batch_count = 0
        
        while True:
            if max_batches and batch_count >= max_batches:
                logger.info(f"⏱️ Limite de lotes atingido ({max_batches})")
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

        # PROCESSAR ITENS (sem limites no servidor dedicado)
        max_item_batches = None  # Sem limite de batches no Hetzner
        item_batch_count = 0
        
        while True:
            if max_item_batches and item_batch_count >= max_item_batches:
                logger.info(f"⏱️ Limite de lotes de itens atingido ({max_item_batches})")
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
        
        # LIMPEZA: Remover licitações vencidas
        licitacoes_removidas = processor.limpar_licitacoes_vencidas()
        
        # Cleanup
        processor.engine.dispose()
        
        logger.info(f"🎉 Processamento Silver concluído: {licitacoes_processadas} licitações, {itens_processados} itens, {licitacoes_removidas} licitações vencidas removidas")
        
        return jsonify({
            "status": "success",
            "message": "Silver processor executado com sucesso",
            "licitacoes_processadas": licitacoes_processadas,
            "itens_processados": itens_processados,
            "licitacoes_removidas": licitacoes_removidas
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Erro no handler Silver: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
