"""
backend/init_db.py
------------------
Explicit entrypoint script to create all application database tables.
Can be executed standalone:
    python -m backend.init_db
"""

import sys
import logging
from backend.database import engine, Base
import backend.models  # noqa: F401 - ensure models are registered with Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("init_db")


def init_db():
    logger.info("Connecting to database and creating tables...")
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("All tables created successfully.")
    except Exception as exc:
        logger.error(f"Database initialization failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    init_db()
