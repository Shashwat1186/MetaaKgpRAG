import logging
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import sessionmaker, declarative_base
from fastapi import HTTPException, status

from backend.config import get_database_url

logger = logging.getLogger("backend.database")

db_url_configured: bool = True


def create_db_engine():
    """Create and return an SQLAlchemy engine.

    Validates DATABASE_URL before creating the engine so that an empty,
    missing, or malformed URL never crashes startup with ArgumentError.
    """
    global db_url_configured
    url = get_database_url()

    try:
        if not url or not isinstance(url, str) or not url.strip():
            raise ArgumentError("DATABASE_URL is empty or missing.")
        parsed = make_url(url.strip())
        if not parsed.drivername:
            raise ArgumentError("DATABASE_URL lacks a driver/dialect.")
        db_url_configured = True
        return create_engine(url.strip(), pool_pre_ping=True)
    except Exception as exc:
        db_url_configured = False
        logger.error(
            f"INVALID DATABASE_URL: {exc}. "
            "Falling back to temporary in-memory engine so the container can boot and pass health checks. "
            "Please configure DATABASE_URL in your deployment environment."
        )
        return create_engine("sqlite:///:memory:", pool_pre_ping=True)


engine = create_db_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency — yields a DB session and closes it when done."""
    if not db_url_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Database is unavailable. DATABASE_URL environment variable is missing, "
                "empty, or improperly formatted. Please set a valid PostgreSQL connection string."
            ),
        )
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
