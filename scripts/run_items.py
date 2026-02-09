#!/usr/bin/env python3
"""
Script wrapper para executar o job de coleta de itens do PNCP.
Usado pelos cron jobs no Hetzner para coletar itens das licitações.
"""

import sys
import os
import logging
from datetime import datetime
from pathlib import Path

# Adiciona o diretório pai ao PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.item_collector import handle_item_collector

# Configuração de logging
LOG_DIR = Path("/var/log/pncp-jobs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
log_file = LOG_DIR / "items.log"

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
    """Executa o job de coleta de itens com tratamento de erros."""
    inicio = datetime.now()
    logger.info("=" * 80)
    logger.info(f"🚀 INICIANDO JOB: Coletor de Itens - {inicio.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 80)
    
    try:
        # Executa o coletor de itens
        resultado = handle_item_collector()
        
        duracao = (datetime.now() - inicio).total_seconds()
        logger.info("=" * 80)
        logger.info(f"✅ JOB CONCLUÍDO: Coletor de Itens")
        logger.info(f"⏱️  Duração: {duracao:.2f} segundos ({duracao/60:.2f} minutos)")
        logger.info(f"📊 Resultado: {resultado}")
        logger.info("=" * 80)
        
        return 0  # Código de sucesso
        
    except Exception as e:
        duracao = (datetime.now() - inicio).total_seconds()
        logger.error("=" * 80)
        logger.error(f"❌ JOB FALHOU: Coletor de Itens")
        logger.error(f"⏱️  Duração até falha: {duracao:.2f} segundos")
        logger.error(f"🔥 Erro: {str(e)}", exc_info=True)
        logger.error("=" * 80)
        
        return 1  # Código de erro


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
