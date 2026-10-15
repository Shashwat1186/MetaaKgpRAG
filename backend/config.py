"""
backend/config.py
-----------------
Central application configuration loaded from environment variables.
"""

import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("backend.config")

# ── Database ──────────────────────────────────────────────────────────────────
def get_database_url() -> str:
    """Return normalized database URL from environment variable.

    - Reads dynamically from DATABASE_URL.
    - If DATABASE_URL is unset or contains the template placeholder '@host:',
      attempts to construct it from individual POSTGRES_* or PG* environment variables.
    - Replaces 'postgres://' with 'postgresql://' for SQLAlchemy 1.4+ / 2.0+ compatibility.
    - Defaults to localhost only when no database configuration is present.
    """
    url = os.getenv("DATABASE_URL", "").strip()

    # Detect if user left the literal template placeholder from .env.example
    is_placeholder = bool(url and ("@host:" in url or "user:password@host" in url))

    # Check for Railway / cloud individual connection variables as fallbacks
    pghost = os.getenv("POSTGRES_HOST") or os.getenv("PGHOST")
    if pghost and (not url or is_placeholder):
        pguser = os.getenv("POSTGRES_USER") or os.getenv("PGUSER", "postgres")
        pgpassword = os.getenv("POSTGRES_PASSWORD") or os.getenv("PGPASSWORD", "")
        pgport = os.getenv("POSTGRES_PORT") or os.getenv("PGPORT", "5432")
        pgdb = os.getenv("POSTGRES_DB") or os.getenv("PGDATABASE", "railway")
        auth = f"{pguser}:{pgpassword}@" if pgpassword else f"{pguser}@"
        url = f"postgresql://{auth}{pghost}:{pgport}/{pgdb}"
        logger.info("Constructed DATABASE_URL from Railway PostgreSQL environment variables.")
    elif is_placeholder:
        logger.error(
            "CONFIGURATION ERROR: DATABASE_URL contains placeholder hostname 'host'. "
            "Please set DATABASE_URL in your Railway service variables to your real PostgreSQL connection URL!"
        )
    elif not url:
        logger.warning(
            "DATABASE_URL is not set! Defaulting to local PostgreSQL: "
            "postgresql://graphmind:graphmind@localhost:5432/graphmind"
        )
        url = "postgresql://graphmind:graphmind@localhost:5432/graphmind"

    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    return url


DATABASE_URL: str = get_database_url()

# ── JWT Auth ──────────────────────────────────────────────────────────────────
SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-in-production-please")
ALGORITHM: str = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
    os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
)

# ── Google OAuth ──────────────────────────────────────────────────────────────
GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI: str = os.getenv(
    "GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback"
)

# ── App ───────────────────────────────────────────────────────────────────────
FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")
