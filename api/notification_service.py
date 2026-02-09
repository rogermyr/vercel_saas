"""
Serviço de notificações por e-mail para licitações.
Busca licitações que correspondem aos perfis dos usuários e envia notificações.
"""

import os
import re
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class NotificationService:
    """
    Serviço responsável por buscar licitações que correspondem aos perfis
    dos usuários e preparar dados para envio de e-mails.
    """
    
    def __init__(self, db_url: str = None):
        """
        Inicializa o serviço de notificações.
        
        Args:
            db_url: URL de conexão com o banco de dados
        """
        if not db_url:
            db_url = os.getenv("DATABASE_URL")
        
        # Tratamento para URL do Supabase/PostgreSQL
        if db_url and db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        
        # Otimizado para servidor dedicado (Hetzner)
        self.engine = create_engine(db_url, pool_size=10, max_overflow=20)
        self.Session = sessionmaker(bind=self.engine)
    
    def parse_keywords(self, keywords_str: str) -> List[str]:
        """
        Parse string de palavras-chave separadas por vírgula.
        
        Args:
            keywords_str: String com palavras separadas por vírgula
            
        Returns:
            Lista de palavras-chave com espaços removidos
        """
        if not keywords_str:
            return []
        
        return [keyword.strip() for keyword in keywords_str.split(',') if keyword.strip()]
    
    def parse_estados(self, estados_str: str) -> List[str]:
        """
        Parse string JSON de estados ["DF", "GO", "MG"] para lista Python.
        
        Args:
            estados_str: String JSON array com siglas de estados
            
        Returns:
            Lista de siglas de estados (strings de 2 letras maiúsculas)
        """
        if not estados_str:
            return []
        
        try:
            import json
            estados = json.loads(estados_str)
            if isinstance(estados, list):
                # Retorna apenas strings válidas (2 caracteres)
                return [str(estado).strip().upper() for estado in estados 
                       if isinstance(estado, str) and len(estado.strip()) == 2]
            return []
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Erro ao parsear estados '{estados_str}': {e}")
            return []
    
    def extract_sequencial(self, identificador_pncp: str) -> str:
        """
        Extrai o número sequencial do identificador PNCP.
        
        O identificador segue o padrão: cnpj-1-seq/ano
        Exemplo: 00394684000153-1-000909/2024
        
        Args:
            identificador_pncp: Identificador completo do PNCP
            
        Returns:
            String com o número sequencial (ex: '000909')
        """
        if not identificador_pncp:
            return ''
        
        try:
            # Remove a parte do ano (após a barra)
            parte_principal = identificador_pncp.split('/')[0]
            # Pega o terceiro elemento após split por hífen (índice 2)
            partes = parte_principal.split('-')
            if len(partes) >= 3:
                return partes[2]
            return ''
        except Exception as e:
            logger.warning(f"Erro ao extrair sequencial de '{identificador_pncp}': {e}")
            return ''
    
    def find_matches_for_config(self, config_id: int, user_id: int) -> List[Dict[str, Any]]:
        """
        Busca licitações que correspondem a um perfil específico.
        
        Args:
            config_id: ID do perfil (cliente_configs)
            user_id: ID do usuário
            
        Returns:
            Lista de dicionários com dados das licitações encontradas
        """
        session = self.Session()
        
        try:
            # Busca o perfil do usuário
            config_query = text("""
                SELECT id, nome_perfil, palavras_chave, palavras_negativas, estados_padrao
                FROM cliente_configs
                WHERE id = :config_id AND user_id = :user_id
            """)
            
            config_result = session.execute(
                config_query,
                {'config_id': config_id, 'user_id': user_id}
            ).fetchone()
            
            if not config_result:
                logger.warning(f"Config {config_id} não encontrado para usuário {user_id}")
                return []
            
            config_id, nome_perfil, palavras_chave, palavras_negativas, estados_padrao = config_result
            
            # Parse das palavras-chave
            positive_keywords = self.parse_keywords(palavras_chave)
            negative_keywords = self.parse_keywords(palavras_negativas) if palavras_negativas else []
            
            # Parse dos estados
            estados_list = self.parse_estados(estados_padrao) if estados_padrao else []
            
            if not estados_list:
                logger.warning(f"Nenhum estado configurado no perfil {nome_perfil} (user_id={user_id})")
                return []
            
            if not positive_keywords:
                logger.warning(f"Nenhuma palavra-chave positiva no perfil {nome_perfil}")
                return []
            
            # Prepara os padrões ILIKE para PostgreSQL
            positive_patterns = [f"%{kw}%" for kw in positive_keywords]
            negative_patterns = [f"%{kw}%" for kw in negative_keywords] if negative_keywords else []
            
            # Monta a query principal - retorna itens individuais
            query = text("""
                WITH ranked_items AS (
                    SELECT
                        sl.identificador_pncp,
                        sl.objeto_compra,
                        sl.ano_compra,
                        sl.data_publicacao,
                        sl.data_encerramento,
                        sl.municipio_nome,
                        sl.uf_sigla,
                        sl.orgao_razao_social,
                        sl.orgao_cnpj,
                        sl.valor_total_estimado,
                        sl.valor_total_homologado,
                        sl.situacao_nome,
                        sl.modalidade_nome,
                        si.id as item_id,
                        si.numero_item,
                        si.descricao as item_descricao,
                        si.categoria_item_nome,
                        -- Verifica se este item específico deu match
                        CASE
                            WHEN si.descricao ILIKE ANY(:positive_patterns) THEN true
                            ELSE false
                        END as item_matched,
                        -- Verifica se o objeto da licitação deu match
                        CASE
                            WHEN sl.objeto_compra ILIKE ANY(:positive_patterns) THEN true
                            ELSE false
                        END as objeto_matched,
                        ROW_NUMBER() OVER (
                            PARTITION BY sl.identificador_pncp
                            ORDER BY 
                                CASE WHEN si.descricao ILIKE ANY(:positive_patterns) THEN 0 ELSE 1 END,
                                si.numero_item NULLS LAST
                        ) as item_rank
                    FROM silver_licitacoes sl
                    LEFT JOIN silver_itens si ON si.licitacao_identificador = sl.identificador_pncp
                    WHERE
                        -- Filtra licitações ativas (não encerradas)
                        (sl.data_encerramento IS NULL OR sl.data_encerramento >= CURRENT_DATE)
                        
                        -- Filtra apenas licitações com status "Divulgada no PNCP"
                        AND sl.situacao_nome = 'Divulgada no PNCP'
                        
                        -- Filtra por estados configurados no perfil
                        AND sl.uf_sigla = ANY(:estados_array)
                        
                        -- Match de palavras-chave positivas (objeto_compra ou descrição dos itens)
                        AND (
                            sl.objeto_compra ILIKE ANY(:positive_patterns)
                            OR si.descricao ILIKE ANY(:positive_patterns)
                        )
                        
                        -- Exclui palavras-chave negativas
                        AND NOT (
                            CASE WHEN :has_negatives THEN
                                sl.objeto_compra ILIKE ANY(:negative_patterns)
                                OR si.descricao ILIKE ANY(:negative_patterns)
                            ELSE FALSE END
                        )
                        
                        -- Exclui licitações já enviadas para este usuário
                        AND NOT EXISTS (
                            SELECT 1
                            FROM email_notifications en
                            WHERE en.user_id = :user_id
                            AND en.licitacao_identificador = sl.identificador_pncp
                        )
                )
                SELECT *
                FROM ranked_items
                WHERE item_rank <= 3 OR objeto_matched OR item_id IS NULL
                ORDER BY valor_total_estimado DESC NULLS LAST, data_publicacao DESC, identificador_pncp, item_rank
                LIMIT 200
            """)
            
            # Executa a query
            results = session.execute(
                query,
                {
                    'positive_patterns': positive_patterns,
                    'negative_patterns': negative_patterns if negative_patterns else [''],
                    'has_negatives': len(negative_patterns) > 0,
                    'user_id': user_id,
                    'estados_array': estados_list
                }
            ).fetchall()
            
            # Agrupa resultados por licitação e processa itens
            licitacoes_dict = {}
            
            for row in results:
                lic_id = row.identificador_pncp
                
                # Se é a primeira vez que vemos esta licitação, cria o registro
                if lic_id not in licitacoes_dict:
                    licitacoes_dict[lic_id] = {
                        'identificador_pncp': row.identificador_pncp,
                        'objeto_compra': row.objeto_compra,
                        'ano_compra': row.ano_compra,
                        'data_publicacao': row.data_publicacao,
                        'data_encerramento': row.data_encerramento,
                        'municipio_nome': row.municipio_nome,
                        'uf_sigla': row.uf_sigla,
                        'orgao_razao_social': row.orgao_razao_social,
                        'orgao_cnpj': row.orgao_cnpj,
                        'sequencial': self.extract_sequencial(row.identificador_pncp),
                        'valor_total_estimado': float(row.valor_total_estimado) if row.valor_total_estimado else None,
                        'valor_total_homologado': float(row.valor_total_homologado) if row.valor_total_homologado else None,
                        'situacao_nome': row.situacao_nome,
                        'modalidade_nome': row.modalidade_nome,
                        'config_id': config_id,
                        'nome_perfil': nome_perfil,
                        'matched_keywords': set(),
                        'matched_items': [],
                        'objeto_matched': row.objeto_matched
                    }
                
                # Se tem item e o item deu match, processa
                if row.item_id and row.item_matched and len(licitacoes_dict[lic_id]['matched_items']) < 3:
                    item_descricao = row.item_descricao or ''
                    
                    # Identifica quais palavras-chave deram match neste item
                    item_keywords = []
                    for kw in positive_keywords:
                        if kw.lower() in item_descricao.lower():
                            item_keywords.append(kw)
                            licitacoes_dict[lic_id]['matched_keywords'].add(kw)
                    
                    # Destaca palavras-chave em negrito na descrição
                    highlighted_descricao = item_descricao
                    for kw in item_keywords:
                        # Usa regex case-insensitive para encontrar e substituir
                        pattern = re.compile(re.escape(kw), re.IGNORECASE)
                        highlighted_descricao = pattern.sub(f'<strong>{kw}</strong>', highlighted_descricao)
                    
                    licitacoes_dict[lic_id]['matched_items'].append({
                        'numero_item': row.numero_item,
                        'descricao': highlighted_descricao,
                        'descricao_original': item_descricao,
                        'categoria_item': row.categoria_item_nome,
                        'matched_keywords': item_keywords
                    })
                
                # Adiciona keywords que deram match no objeto
                if row.objeto_matched:
                    for kw in positive_keywords:
                        if kw.lower() in (row.objeto_compra or '').lower():
                            licitacoes_dict[lic_id]['matched_keywords'].add(kw)
            
            # Converte para lista e transforma set de keywords em lista
            matches = []
            for lic in licitacoes_dict.values():
                lic['matched_keywords'] = list(lic['matched_keywords'])
                matches.append(lic)
            
            # Ordena por valor estimado
            matches.sort(key=lambda x: (x['valor_total_estimado'] or 0, x['data_publicacao'] or ''), reverse=True)
            
            # Limita a 50 licitações
            matches = matches[:50]
            
            logger.info(f"✅ Encontradas {len(matches)} licitações para perfil '{nome_perfil}' (user_id={user_id})")
            return matches
            
        except Exception as e:
            logger.error(f"❌ Erro ao buscar matches para config {config_id}: {str(e)}")
            raise
        finally:
            session.close()
    
    def get_active_configs(self) -> List[Dict[str, Any]]:
        """
        Busca todos os perfis ativos com seus respectivos usuários.
        
        Returns:
            Lista de dicionários com dados dos perfis e usuários
        """
        session = self.Session()
        
        try:
            query = text("""
                SELECT 
                    cc.id as config_id,
                    cc.user_id,
                    cc.nome_perfil,
                    cc.palavras_chave,
                    cc.palavras_negativas,
                    cc.estados_padrao,
                    u.username as email,
                    u.nome_completo
                FROM cliente_configs cc
                INNER JOIN usuarios u ON cc.user_id = u.id
                WHERE cc.palavras_chave IS NOT NULL
                AND cc.palavras_chave != ''
                AND cc.estados_padrao IS NOT NULL
                AND cc.estados_padrao != ''
                AND cc.estados_padrao != '[]'
                ORDER BY u.id, cc.id
            """)
            
            results = session.execute(query).fetchall()
            
            configs = []
            for row in results:
                configs.append({
                    'config_id': row.config_id,
                    'user_id': row.user_id,
                    'nome_perfil': row.nome_perfil,
                    'palavras_chave': row.palavras_chave,
                    'palavras_negativas': row.palavras_negativas,
                    'estados_padrao': row.estados_padrao,
                    'email': row.email,
                    'nome_completo': row.nome_completo
                })
            
            logger.info(f"✅ Encontrados {len(configs)} perfis ativos")
            return configs
            
        except Exception as e:
            logger.error(f"❌ Erro ao buscar perfis ativos: {str(e)}")
            raise
        finally:
            session.close()
    
    def log_email_sent(self, user_id: int, config_id: int, licitacao_identificador: str, 
                      matched_keywords: List[str], status: str = 'sent', 
                      error_message: str = None):
        """
        Registra o envio de um e-mail na tabela de rastreamento.
        
        Args:
            user_id: ID do usuário
            config_id: ID do perfil
            licitacao_identificador: Identificador da licitação
            matched_keywords: Lista de palavras-chave que deram match
            status: Status do envio (sent, failed, bounced)
            error_message: Mensagem de erro se aplicável
        """
        session = self.Session()
        
        try:
            insert_query = text("""
                INSERT INTO email_notifications 
                (user_id, config_id, licitacao_identificador, matched_keywords, status, error_message)
                VALUES (:user_id, :config_id, :licitacao_identificador, :matched_keywords, :status, :error_message)
                ON CONFLICT (user_id, licitacao_identificador) DO NOTHING
            """)
            
            session.execute(
                insert_query,
                {
                    'user_id': user_id,
                    'config_id': config_id,
                    'licitacao_identificador': licitacao_identificador,
                    'matched_keywords': ', '.join(matched_keywords) if matched_keywords else None,
                    'status': status,
                    'error_message': error_message
                }
            )
            session.commit()
            
        except Exception as e:
            session.rollback()
            logger.error(f"❌ Erro ao registrar envio de e-mail: {str(e)}")
            raise
        finally:
            session.close()


if __name__ == "__main__":
    # Teste do serviço
    service = NotificationService()
    
    print("🧪 Testando busca de perfis ativos...")
    configs = service.get_active_configs()
    print(f"Encontrados {len(configs)} perfis")
    
    if configs:
        print(f"\n🧪 Testando busca de licitações para o primeiro perfil...")
        config = configs[0]
        matches = service.find_matches_for_config(config['config_id'], config['user_id'])
        print(f"Encontradas {len(matches)} licitações")
