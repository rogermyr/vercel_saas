import os
import logging
from flask import Flask, jsonify, request, abort, render_template
from flask_mail import Mail, Message
# Importa as funções (certifique-se de ter o __init__.py na pasta api)
from api.crawler import run_process as run_crawler
from api.item_collector import handle_item_collector as run_items
from api.silver_processor import handle_silver_processor
from api.notification_service import NotificationService

# Configura o logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuração do Flask-Mail
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True').lower() == 'true'
app.config['MAIL_USE_SSL'] = os.getenv('MAIL_USE_SSL', 'False').lower() == 'true'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER', os.getenv('MAIL_USERNAME'))

mail = Mail(app)


# Filtro customizado para formatação de moeda brasileira
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


@app.route('/')
def health_check():
    return "PNCP Crawler Online", 200

@app.route('/debug-vars')
def debug_vars():
    # Isso vai te mostrar se a Vercel carregou a variável
    return f"Status da Secret: {'Configurada' if os.getenv('CRON_SECRET') else 'Vazia'}"

@app.route('/api/cron/sync-tudo')
def sync_tudo():
    logger.info("🔄 Iniciando Sincronização Geral")
    try:
        db_url = os.getenv("DATABASE_URL")
        
        # Rodamos as funções. 
        # Se elas retornam um Response do Flask, usamos .get_json() ou apenas chamamos
        run_crawler(db_url)
        run_items()
        
        return jsonify({
            "status": "success", 
            "message": "Crawler e Items processados com sucesso. Verifique o banco de dados."
        }), 200
    except Exception as e:
        logger.error(f"❌ Erro: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/cron/process-silver')
def process_silver():
    """Endpoint para processar dados Bronze -> Silver via cron job."""
    logger.info("🔄 Iniciando Processamento Silver")
    return handle_silver_processor()


@app.route('/api/cron/send-email-notifications')
def send_email_notifications():
    """
    Endpoint para enviar notificações por e-mail sobre novas licitações.
    Busca licitações que correspondem aos perfis dos usuários e envia e-mails personalizados.
    """
    logger.info("📧 Iniciando envio de notificações por e-mail")
    
    # Verifica autenticação via CRON_SECRET
    auth_header = request.headers.get('Authorization', '')
    expected_secret = os.getenv('CRON_SECRET', '')
    
    if not auth_header.startswith('Bearer ') or auth_header[7:] != expected_secret:
        logger.warning("⚠️ Tentativa de acesso não autorizado ao endpoint de notificações")
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    
    try:
        # Inicializa o serviço de notificações
        notification_service = NotificationService()
        
        # Busca todos os perfis ativos
        configs = notification_service.get_active_configs()
        
        if not configs:
            logger.info("ℹ️ Nenhum perfil ativo encontrado")
            return jsonify({
                "status": "success",
                "message": "Nenhum perfil ativo para processar",
                "emails_sent": 0,
                "configs_processed": 0
            }), 200
        
        emails_sent = 0
        emails_failed = 0
        configs_processed = 0
        # Sem limite de emails no servidor dedicado (Hetzner)
        
        logger.info(f"📊 Processando {len(configs)} perfis...")
            
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
                msg = Message(
                    subject=subject,
                    recipients=[email],
                    html=html_body
                )
                
                mail.send(msg)
                
                logger.info(f"✅ E-mail enviado para {email} com {len(matches)} licitações")
                emails_sent += 1
                configs_processed += 1
                
                # Registra cada licitação como enviada
                for match in matches:
                    try:
                        notification_service.log_email_sent(
                            user_id=user_id,
                            config_id=config_id,
                            licitacao_identificador=match['identificador_pncp'],
                            matched_keywords=match['matched_keywords'],
                            status='sent'
                        )
                    except Exception as log_error:
                        logger.error(f"⚠️ Erro ao registrar envio: {str(log_error)}")
                
            except Exception as e:
                logger.error(f"❌ Erro ao processar perfil {config.get('nome_perfil')}: {str(e)}")
                emails_failed += 1
                
                # Tenta registrar a falha
                try:
                    if matches:
                        for match in matches:
                            notification_service.log_email_sent(
                                user_id=config['user_id'],
                                config_id=config['config_id'],
                                licitacao_identificador=match['identificador_pncp'],
                                matched_keywords=match.get('matched_keywords', []),
                                status='failed',
                                error_message=str(e)
                            )
                except:
                    pass
        
        logger.info(f"✅ Processamento concluído: {emails_sent} e-mails enviados, {emails_failed} falhas")
        
        return jsonify({
            "status": "success",
            "message": f"Processamento concluído",
            "emails_sent": emails_sent,
            "emails_failed": emails_failed,
            "configs_processed": configs_processed,
            "total_configs": len(configs)
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Erro no processamento de notificações: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
