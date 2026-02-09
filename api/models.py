"""
Modelos de banco de dados para o sistema de notificações por e-mail.
"""

from sqlalchemy import create_engine, Column, Integer, String, Text, TIMESTAMP, ForeignKey, UniqueConstraint, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import func
import os
from dotenv import load_dotenv

load_dotenv()

Base = declarative_base()


class EmailNotification(Base):
    """
    Tabela para rastrear e-mails enviados aos usuários sobre licitações.
    Evita envios duplicados e mantém histórico de notificações.
    """
    __tablename__ = 'email_notifications'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, comment='FK para usuarios.id')
    config_id = Column(Integer, nullable=True, comment='FK para cliente_configs.id')
    licitacao_identificador = Column(String, nullable=False, comment='FK para silver_licitacoes.identificador_pncp')
    
    # Detalhes do envio
    sent_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    status = Column(String(50), default='sent', nullable=False, comment='sent, failed, bounced')
    matched_keywords = Column(Text, nullable=True, comment='Palavras-chave que deram match')
    error_message = Column(Text, nullable=True, comment='Mensagem de erro se falhou')
    
    # Constraint para evitar duplicatas
    __table_args__ = (
        UniqueConstraint('user_id', 'licitacao_identificador', name='uq_user_licitacao'),
        Index('idx_email_notifications_user', 'user_id'),
        Index('idx_email_notifications_licitacao', 'licitacao_identificador'),
        Index('idx_email_notifications_config', 'config_id'),
        Index('idx_email_notifications_sent_at', 'sent_at'),
    )

    def __repr__(self):
        return f"<EmailNotification(user_id={self.user_id}, licitacao={self.licitacao_identificador}, status={self.status})>"


def init_db():
    """
    Inicializa o banco de dados criando as tabelas necessárias.
    """
    db_url = os.getenv("DATABASE_URL")
    
    # Tratamento para URL do Supabase/PostgreSQL
    if db_url and db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    
    # Otimizado para servidor dedicado (Hetzner)
    engine = create_engine(db_url, pool_size=10, max_overflow=20)
    
    # Cria a tabela se não existir
    Base.metadata.create_all(engine)
    
    return engine


def get_session():
    """
    Retorna uma sessão do SQLAlchemy para operações no banco.
    """
    engine = init_db()
    Session = sessionmaker(bind=engine)
    return Session()


if __name__ == "__main__":
    # Para criar a tabela manualmente, execute: python api/models.py
    print("🔧 Criando tabelas no banco de dados...")
    init_db()
    print("✅ Tabela email_notifications criada com sucesso!")
