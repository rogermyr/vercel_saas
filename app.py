import os
from flask import Flask, jsonify
# Importamos as funções de execução dos seus arquivos originais
from api.crawler import run_process as run_crawler
from api.item_collector import handle_item_collector as run_items

app = Flask(__name__)

@app.route('/')
def health_check():
    return "PNCP Crawler Online", 200

@app.route('/api/cron/sync-tudo')
def sync_tudo():
    logger.info("🔄 Iniciando Sincronização Geral")
    # 1. Roda o Crawler
    run_crawler(os.getenv("DATABASE_URL"))
    # 2. Roda o Coletor de Itens
    run_items()
    
    return jsonify({"status": "success", "message": "Crawler e Items finalizados"}), 200

if __name__ == "__main__":
    app.run()
    # app.run(debug=True)