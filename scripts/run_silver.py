#!/usr/bin/env python3
"""
Script wrapper para executar o job de processamento Silver.
Usado pelos cron jobs no Hetzner para transformar dados Bronze -> Silver.
"""

import sys
import os
import logging
from datetime import datetime
from pathlib import Path

# Adiciona o diretório pai ao PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.silver_processor import run_silver_processor

# Configuração de logging
LOG_DIR = Path("/var/log/pncp-jobs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
log_file = LOG_DIR / "silver.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


def main():
    """Executa o job de processamento Silver com tratamento de erros."""
    inicio = datetime.now()
    logger.info("=" * 80)
    logger.info(f"🚀 INICIANDO JOB: Silver Processor - {inicio.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 80)
    
    try:
        # Executa o processador silver
        resultado = run_silver_processor()
        
        duracao = (datetime.now() - inicio).total_seconds()
        logger.info("=" * 80)
        logger.info(f"✅ JOB CONCLUÍDO: Silver Processor")
        logger.info(f"⏱️  Duração: {duracao:.2f} segundos ({duracao/60:.2f} minutos)")
        logger.info(f"📊 Resultado: {resultado}")
        logger.info("=" * 80)
        
        return 0  # Código de sucesso
        
    except Exception as e:
        duracao = (datetime.now() - inicio).total_seconds()
        logger.error("=" * 80)
        logger.error(f"❌ JOB FALHOU: Silver Processor")
        logger.error(f"⏱️  Duração até falha: {duracao:.2f} segundos")
        logger.error(f"🔥 Erro: {str(e)}", exc_info=True)
        logger.error("=" * 80)
        
        return 1  # Código de erro


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
