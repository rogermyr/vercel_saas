import os
from flask import Flask, jsonify
# Importamos as funções de execução dos seus arquivos originais
from crawler import run_process as run_crawler
from item_collector import handle_item_collector as run_items

app = Flask(__name__)

@app.route('/')
def health_check():
    return "PNCP Crawler Online", 200

@app.route('/api/cron/crawler')
def route_crawler():
    return run_crawler(os.getenv("DATABASE_URL"))

@app.route('/api/cron/items')
def route_items():
    return run_items()

if __name__ == "__main__":
    app.run()
    # app.run(debug=True)