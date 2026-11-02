"""
backend/config.py
-----------------
Central application configuration loaded from environment variables.
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    load_dotenv(dotenv_path=_env_path)
else:
    load_dotenv()

logger = logging.getLogger("backend.config")

# ── Database ──────────────────────────────────────────────────────────────────
def get_database_url() -> str:
    """Return normalized database URL from environment variable.

    - Reads dynamically from DATABASE_URL (stripping extra quotes or whitespace).
    - If DATABASE_URL is unset, checks cloud and fallback variables.
    - Replaces 'postgres://' with 'postgresql://' for SQLAlchemy 1.4+ / 2.0+ compatibility.
    - In cloud environments (Hugging Face / production), returns empty string instead of
      hanging on localhost:5432.
    """
    url = (
        os.getenv("DATABASE_URL")
        or os.getenv("database_url")
        or os.getenv("DATABASE_PUBLIC_URL")
        or os.getenv("DATABASE_PRIVATE_URL")
        or os.getenv("POSTGRESQL_URL")
        or ""
    ).strip().strip('"').strip("'")

    # Detect if user left the literal template placeholder from .env.example
    is_placeholder = bool(url and ("@host:" in url or "user:password@host" in url))

    # Check for cloud individual connection variables as fallbacks
    alt_url = os.getenv("DATABASE_PRIVATE_URL") or os.getenv("DATABASE_PUBLIC_URL") or os.getenv("POSTGRESQL_URL")
    pghost = os.getenv("POSTGRES_HOST") or os.getenv("PGHOST")

    if alt_url and (not url or is_placeholder):
        url = alt_url.strip().strip('"').strip("'")
        logger.info("Using alternate database URL variable.")
    elif pghost and (not url or is_placeholder):
        pguser = os.getenv("POSTGRES_USER") or os.getenv("PGUSER", "postgres")
        pgpassword = os.getenv("POSTGRES_PASSWORD") or os.getenv("PGPASSWORD", "")
        pgport = os.getenv("POSTGRES_PORT") or os.getenv("PGPORT", "5432")
        pgdb = os.getenv("POSTGRES_DB") or os.getenv("PGDATABASE", "neondb")
        auth = f"{pguser}:{pgpassword}@" if pgpassword else f"{pguser}@"
        url = f"postgresql://{auth}{pghost}:{pgport}/{pgdb}"
        logger.info("Constructed DATABASE_URL from PostgreSQL environment variables.")
    elif is_placeholder:
        logger.error(
            "CONFIGURATION ERROR: DATABASE_URL contains placeholder hostname 'host'. "
            "Please configure your valid Neon PostgreSQL connection string in Settings > Variables and secrets."
        )
    elif not url:
        is_cloud = bool(
            os.getenv("SPACE_ID")
            or os.getenv("PRODUCTION", "").strip().lower() in ("true", "1")
            or os.getenv("RAILWAY_ENVIRONMENT")
        )
        if is_cloud:
            logger.error(
                "DATABASE_URL is not set in cloud environment! "
                "Please configure DATABASE_URL in Hugging Face Space Settings > Variables and secrets."
            )
            return ""
        logger.warning(
            "DATABASE_URL is not set! Defaulting to local PostgreSQL: "
            "postgresql://graphmind:graphmind@localhost:5432/graphmind"
        )
        url = "postgresql://graphmind:graphmind@localhost:5432/graphmind"

    # Normalize dialect schemes
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    elif url and not (url.startswith("postgresql://") or url.startswith("sqlite://")):
        if "@" in url:
            url = f"postgresql://{url}"
            logger.info("Automatically added postgresql:// scheme to DATABASE_URL.")

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
