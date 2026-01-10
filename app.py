import os
import logging
from flask import Flask, jsonify, request, abort
# Importa as funções (certifique-se de ter o __init__.py na pasta api)
from api.crawler import run_process as run_crawler
from api.item_collector import handle_item_collector as run_items
from api.silver_processor import handle_silver_processor

# Configura o logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

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