"""
backend/database.py
-------------------
SQLAlchemy engine, session factory, and Base class.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from backend.config import get_database_url


def create_db_engine():
    """Create and return a new SQLAlchemy engine using the dynamic database URL."""
    return create_engine(get_database_url(), pool_pre_ping=True)


engine = create_db_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency — yields a DB session and closes it when done."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
