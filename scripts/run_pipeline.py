#!/usr/bin/env python3
"""
Script wrapper para executar o pipeline completo de processamento PNCP.
Executa em sequência: Crawler → Item Collector → Silver Processor

Usado pelos cron jobs no Hetzner para processar dados completos.
"""

import sys
import os
import logging
from datetime import datetime
from pathlib import Path

# Adiciona o diretório pai ao PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.crawler import run_crawler_process
from api.item_collector import run_item_collection_process
from api.silver_processor import run_silver_processor

# Configuração de logging
LOG_DIR = Path("/var/log/pncp-jobs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
log_file = LOG_DIR / "pipeline.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


def executar_pipeline():
    """Executa o pipeline completo de processamento."""
    
    # ========== ETAPA 1: CRAWLER ==========
    logger.info("=" * 80)
    logger.info("📥 ETAPA 1/3: CRAWLER - Coletando licitações do PNCP")
    logger.info("=" * 80)
    
    inicio_crawler = datetime.now()
    try:
        resultado_crawler = run_crawler_process()
        duracao_crawler = (datetime.now() - inicio_crawler).total_seconds()
        logger.info(f"✅ Crawler concluído em {duracao_crawler:.2f}s ({duracao_crawler/60:.2f}min)")
        logger.info(f"📊 Resultado: {resultado_crawler}")
    except Exception as e:
        duracao_crawler = (datetime.now() - inicio_crawler).total_seconds()
        logger.error(f"❌ Crawler falhou após {duracao_crawler:.2f}s: {str(e)}", exc_info=True)
        raise  # Para a execução se o crawler falhar
    
    # ========== ETAPA 2: ITEM COLLECTOR ==========
    logger.info("")
    logger.info("=" * 80)
    logger.info("📦 ETAPA 2/3: ITEM COLLECTOR - Coletando itens das licitações")
    logger.info("=" * 80)
    
    inicio_items = datetime.now()
    try:
        resultado_items = run_item_collection_process()
        duracao_items = (datetime.now() - inicio_items).total_seconds()
        logger.info(f"✅ Item Collector concluído em {duracao_items:.2f}s ({duracao_items/60:.2f}min)")
        logger.info(f"📊 Resultado: {resultado_items}")
    except Exception as e:
        duracao_items = (datetime.now() - inicio_items).total_seconds()
        logger.error(f"❌ Item Collector falhou após {duracao_items:.2f}s: {str(e)}", exc_info=True)
        raise  # Para a execução se o item collector falhar
    
    # ========== ETAPA 3: SILVER PROCESSOR ==========
    logger.info("")
    logger.info("=" * 80)
    logger.info("⚙️ ETAPA 3/3: SILVER PROCESSOR - Transformando Bronze → Silver")
    logger.info("=" * 80)
    
    inicio_silver = datetime.now()
    try:
        resultado_silver = run_silver_processor()
        duracao_silver = (datetime.now() - inicio_silver).total_seconds()
        logger.info(f"✅ Silver Processor concluído em {duracao_silver:.2f}s ({duracao_silver/60:.2f}min)")
        logger.info(f"📊 Resultado: {resultado_silver}")
    except Exception as e:
        duracao_silver = (datetime.now() - inicio_silver).total_seconds()
        logger.error(f"❌ Silver Processor falhou após {duracao_silver:.2f}s: {str(e)}", exc_info=True)
        raise  # Para a execução se o silver processor falhar
    
    return {
        "crawler": resultado_crawler,
        "items": resultado_items,
        "silver": resultado_silver,
        "duracao_crawler": duracao_crawler,
        "duracao_items": duracao_items,
        "duracao_silver": duracao_silver,
        "duracao_total": duracao_crawler + duracao_items + duracao_silver
    }


def main():
    """Executa o pipeline completo com tratamento de erros."""
    inicio = datetime.now()
    logger.info("")
    logger.info("=" * 80)
    logger.info("🚀 INICIANDO PIPELINE COMPLETO - " + inicio.strftime('%Y-%m-%d %H:%M:%S'))
    logger.info("=" * 80)
    logger.info("")
    
    try:
        # Executa o pipeline
        resultado = executar_pipeline()
        
        duracao_total = (datetime.now() - inicio).total_seconds()
        
        # Resumo final
        logger.info("")
        logger.info("=" * 80)
        logger.info("🎉 PIPELINE COMPLETO CONCLUÍDO COM SUCESSO")
        logger.info("=" * 80)
        logger.info(f"⏱️  Duração Crawler:  {resultado['duracao_crawler']:.2f}s ({resultado['duracao_crawler']/60:.2f}min)")
        logger.info(f"⏱️  Duração Items:    {resultado['duracao_items']:.2f}s ({resultado['duracao_items']/60:.2f}min)")
        logger.info(f"⏱️  Duração Silver:   {resultado['duracao_silver']:.2f}s ({resultado['duracao_silver']/60:.2f}min)")
        logger.info(f"⏱️  Duração Total:    {duracao_total:.2f}s ({duracao_total/60:.2f}min)")
        logger.info("=" * 80)
        logger.info("")
        
        return 0  # Código de sucesso
        
    except Exception as e:
        duracao_total = (datetime.now() - inicio).total_seconds()
        logger.error("")
        logger.error("=" * 80)
        logger.error("❌ PIPELINE FALHOU")
        logger.error("=" * 80)
        logger.error(f"⏱️  Duração até falha: {duracao_total:.2f}s ({duracao_total/60:.2f}min)")
        logger.error(f"🔥 Erro: {str(e)}", exc_info=True)
        logger.error("=" * 80)
        logger.error("")
        
        return 1  # Código de erro


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
