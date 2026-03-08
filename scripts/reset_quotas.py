#!/usr/bin/env python3
"""
Task #10: reseta cotas diarias de busca dos usuarios.
"""

import logging
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

# Carrega o .env na raiz do projeto, mesmo quando executado de outro diretório.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=ENV_PATH)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

RESET_QUOTAS_SQL = text(
    "UPDATE usuarios "
    "SET daily_search_count = 0, last_search_date = CURRENT_DATE;"
)


def reset_daily_quotas() -> int:
    """Reseta as cotas diarias dos usuarios e retorna um codigo de saida."""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        logger.error("DATABASE_URL nao encontrada no arquivo .env")
        return 1

    engine = None
    started_at = datetime.now()
    logger.info("Iniciando reset de quotas diarias...")

    try:
        engine = create_engine(db_url)

        # engine.begin() faz commit em sucesso e rollback em erro.
        with engine.begin() as conn:
            result = conn.execute(RESET_QUOTAS_SQL)
            affected_rows = (
                result.rowcount if result.rowcount is not None else 0
            )

        elapsed_seconds = (datetime.now() - started_at).total_seconds()
        logger.info("Reset concluido com sucesso.")
        logger.info("Usuarios afetados: %s", affected_rows)
        logger.info("Tempo total: %.2fs", elapsed_seconds)
        return 0

    except SQLAlchemyError:
        logger.exception("Erro de banco ao resetar quotas.")
        return 1
    except Exception:
        logger.exception("Erro inesperado ao resetar quotas.")
        return 1
    finally:
        if engine is not None:
            engine.dispose()
            logger.info("Conexao com o banco finalizada.")


if __name__ == "__main__":
    raise SystemExit(reset_daily_quotas())
