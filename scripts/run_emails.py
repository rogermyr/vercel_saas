#!/usr/bin/env python3
"""
Script wrapper para executar o job de envio de emails.
Usado pelos cron jobs no Hetzner para enviar notificações aos usuários.
"""

import sys
import os
import logging
import time
from datetime import datetime
from pathlib import Path

# Adiciona o diretório pai ao PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

# Carrega variáveis de ambiente
base_dir = Path(__file__).resolve().parent.parent
env_path = base_dir / '.env'
load_dotenv(dotenv_path=env_path)

# Configuração de logging
LOG_DIR = Path("/var/log/pncp-jobs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
log_file = LOG_DIR / "emails.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


def enviar_notificacoes():
    """
    Envia notificações por email.
    Importa e executa a lógica de envio de emails do app Flask.
    """
    from flask import Flask
    from flask_mail import Mail
    from api.notification_service import NotificationService
    from flask import render_template
    
    # Configura Flask app temporário para envio de emails
    app = Flask(
        __name__,
        template_folder=str(base_dir / 'templates')
    )
    
    # Registra filtro customizado para formatação de moeda brasileira
    @app.template_filter('currency_br')
    def currency_br_filter(value):
        """
        Formata um número como moeda brasileira (R$ 1.234.567,89)
        """
        if value is None:
            return "R$ 0,00"
        
        try:
            # Converte para float se necessário
            value = float(value)
            
            # Formata com 2 casas decimais e separador de milhar
            formatted = f"{value:,.2f}"
            
            # Substitui vírgula e ponto (formato americano) para formato brasileiro
            # 1,234,567.89 -> 1.234.567,89
            formatted = formatted.replace(',', 'TEMP').replace('.', ',').replace('TEMP', '.')
            
            return f"R$ {formatted}"
        except (ValueError, TypeError):
            return "R$ 0,00"
    
    # Configurações de email do .env
    app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'sandbox.smtp.mailtrap.io')
    app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 2525))
    app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True').lower() == 'true'
    app.config['MAIL_USE_SSL'] = os.getenv('MAIL_USE_SSL', 'False').lower() == 'true'
    app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
    app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER', 'noreply@pncp.com')
    
    mail = Mail(app)
    notification_service = NotificationService()
    
    with app.app_context():
        # Busca todos os perfis ativos
        configs = notification_service.get_active_configs()
        
        if not configs:
            logger.info("ℹ️ Nenhum perfil ativo encontrado")
            return {"status": "success", "emails_sent": 0, "configs_processed": 0}
        
        emails_sent = 0
        emails_failed = 0
        configs_processed = 0
        
        logger.info(f"📊 Processando {len(configs)} perfis...")
        
        for config in configs:
            try:
                config_id = config['config_id']
                user_id = config['user_id']
                nome_perfil = config['nome_perfil']
                email = config['email']
                nome_completo = config['nome_completo']
                
                logger.info(f"🔍 Processando perfil '{nome_perfil}' (user_id={user_id})")
                
                # Busca licitações que correspondem ao perfil
                matches = notification_service.find_matches_for_config(config_id, user_id)
                
                if not matches:
                    logger.info(f"ℹ️ Nenhuma licitação nova para o perfil '{nome_perfil}'")
                    configs_processed += 1
                    continue
                
                # Prepara o e-mail
                subject = f"Novas licitações para o perfil {nome_perfil}"
                
                # Renderiza o template HTML
                html_body = render_template(
                    'emails/perfil_matches.html',
                    nome_perfil=nome_perfil,
                    nome_usuario=nome_completo or email.split('@')[0],
                    licitacoes=matches
                )
                
                # Envia o e-mail
                from flask_mail import Message
                msg = Message(
                    subject=subject,
                    recipients=[email],
                    html=html_body
                )
                
                mail.send(msg)
                
                logger.info(f"✅ Email enviado para {email} ({len(matches)} licitações)")
                emails_sent += 1
                configs_processed += 1
                
                # Registra cada licitação como enviada
                for match in matches:
                    try:
                        notification_service.log_email_sent(
                            user_id=user_id,
                            config_id=config_id,
                            licitacao_identificador=match['identificador_pncp'],
                            matched_keywords=match.get('matched_keywords', []),
                            status='sent'
                        )
                    except Exception as log_error:
                        logger.error(f"⚠️ Erro ao registrar envio: {str(log_error)}")
                
                # Delay para evitar rate limit do Mailtrap (2 emails por segundo no plano free)
                time.sleep(0.6)
                
            except Exception as e:
                emails_failed += 1
                logger.error(f"❌ Erro ao processar perfil {nome_perfil}: {str(e)}")
                
                # Tenta registrar a falha no banco
                try:
                    if matches:
                        for match in matches:
                            notification_service.log_email_sent(
                                user_id=user_id,
                                config_id=config_id,
                                licitacao_identificador=match['identificador_pncp'],
                                matched_keywords=match.get('matched_keywords', []),
                                status='failed',
                                error_message=str(e)
                            )
                except Exception as log_error:
                    logger.error(f"⚠️ Erro ao registrar falha: {str(log_error)}")
                
                continue
        
        logger.info(f"📧 Resumo: {emails_sent} emails enviados, {emails_failed} falhas, {configs_processed} perfis processados")
        
        return {
            "status": "success",
            "emails_sent": emails_sent,
            "emails_failed": emails_failed,
            "configs_processed": configs_processed
        }


def main():
    """Executa o job de envio de emails com tratamento de erros."""
    inicio = datetime.now()
    logger.info("=" * 80)
    logger.info(f"🚀 INICIANDO JOB: Envio de Emails - {inicio.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 80)
    
    try:
        # Executa o envio de notificações
        resultado = enviar_notificacoes()
        
        duracao = (datetime.now() - inicio).total_seconds()
        logger.info("=" * 80)
        logger.info(f"✅ JOB CONCLUÍDO: Envio de Emails")
        logger.info(f"⏱️  Duração: {duracao:.2f} segundos ({duracao/60:.2f} minutos)")
        logger.info(f"📊 Resultado: {resultado}")
        logger.info("=" * 80)
        
        return 0  # Código de sucesso
        
    except Exception as e:
        duracao = (datetime.now() - inicio).total_seconds()
        logger.error("=" * 80)
        logger.error(f"❌ JOB FALHOU: Envio de Emails")
        logger.error(f"⏱️  Duração até falha: {duracao:.2f} segundos")
        logger.error(f"🔥 Erro: {str(e)}", exc_info=True)
        logger.error("=" * 80)
        
        return 1  # Código de erro


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
