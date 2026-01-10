import os
import logging
from flask import Flask, jsonify
# Importa as funções (certifique-se de ter o __init__.py na pasta api)
from api.crawler import run_process as run_crawler
from api.item_collector import handle_item_collector as run_items

# Configura o logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route('/')
def health_check():
    return "PNCP Crawler Online", 200

@app.route('/api/cron/sync-tudo')
def sync_tudo():
    logger.info("🔄 Iniciando Sincronização Geral")
    try:
        # Pega a URL do banco das variáveis de ambiente da Vercel
        db_url = os.getenv("DATABASE_URL")
        
        # 1. Executa o Crawler
        resultado_crawler = run_crawler(db_url)
        
        # 2. Executa o Coletor
        resultado_items = run_items()
        
        return jsonify({
            "status": "success", 
            "crawler": resultado_crawler,
            "items": resultado_items
        }), 200
    except Exception as e:
        logger.error(f"❌ Erro: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500