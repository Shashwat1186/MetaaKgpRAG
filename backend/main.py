"""
backend/main.py
---------------
FastAPI application entry-point.

Run with:
    uvicorn backend.main:app --reload --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from backend.config import SECRET_KEY, FRONTEND_URL
from backend.database import engine, Base, db_url_configured
from backend.routers import auth_router, conversations_router, chat_router

import os
import re
import time
import logging
from pathlib import Path
from contextlib import asynccontextmanager

logger = logging.getLogger("backend")
db_connected: bool = False

# Detect production environment (set PRODUCTION=true on Railway/Render)
IS_PRODUCTION = os.getenv("PRODUCTION", "false").strip().lower() in ("true", "1")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan handler: manages startup and shutdown events.

    Executes database table verification and creation safely inside the application
    lifecycle instead of during module import, with retry logic for container environments.
    """
    logger.info("Application starting up...")

    # Ensure models are imported and registered with Base metadata
    import backend.models  # noqa: F401

    global db_connected
    db_connected = False

    if not db_url_configured:
        logger.error(
            "DATABASE STARTUP WARNING: DATABASE_URL is missing, empty, or invalid. "
            "Skipping table creation. Please configure a valid PostgreSQL connection URL."
        )
    else:
        max_retries = 5
        retry_delay = 2  # seconds

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(
                    f"Verifying and creating database tables (attempt {attempt}/{max_retries})..."
                )
                Base.metadata.create_all(bind=engine)
                logger.info("Database tables initialized successfully.")
                db_connected = True
                break
            except Exception as exc:
                logger.warning(
                    f"Database connection attempt {attempt} failed: {exc}. "
                    + (f"Retrying in {retry_delay}s..." if attempt < max_retries else "")
                )
                if attempt < max_retries:
                    time.sleep(retry_delay)
                else:
                    logger.error(
                        "DATABASE CONNECTION FAILED: "
                        f"{exc}\n"
                        "--> NOTE: The server will still start so health checks pass, "
                        "but database features require setting DATABASE_URL correctly."
                    )

    # Pre-warm GraphRAG retriever (lightweight ONNX model, ~30MB RAM)
    try:
        from backend.rag_service import rag_service
        logger.info("Pre-warming GraphRAG retriever...")
        rag_service._initialize()
        logger.info("GraphRAG retriever pre-warmed successfully.")
    except Exception as exc:
        logger.warning(f"RAG service warmup notice (will load on first request): {exc}")

    yield
    logger.info("Application shutting down...")


app = FastAPI(
    title="GraphMind API",
    description=(
        "GraphRAG-powered conversational AI for MetaKGP / IIT Kharagpur. "
        "Supports multi-turn conversations, user accounts, and conversation history."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Normalize duplicate slashes in URL paths (e.g. //chat -> /chat)
@app.middleware("http")
async def clean_path_middleware(request, call_next):
    if "//" in request.scope.get("path", ""):
        request.scope["path"] = re.sub(r"/+", "/", request.scope["path"])
    return await call_next(request)

# Session middleware needed by Authlib's OAuth flow
# same_site="lax" allows the session cookie to be sent on top-level GET redirects
# (which is exactly what happens on the OAuth callback).
# https_only must be True in production (serves HTTPS) but False for local http:// dev.
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    same_site="lax",
    https_only=IS_PRODUCTION,
    max_age=300,   # 5 minutes – enough time to complete the OAuth dance
)

# Collect all allowed origins: local dev + any configured production frontend
_allowed_origins = [
    "http://localhost:5173",      # Vite dev server (localhost)
    "http://127.0.0.1:5173",      # Vite dev server (127.0.0.1)
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://graphmind-frontend.vercel.app",
    "https://metaakgprag.onrender.com",
]
# Add production frontend URL (from env, e.g. https://metakgprag.vercel.app)
if FRONTEND_URL and FRONTEND_URL not in _allowed_origins:
    _allowed_origins.append(FRONTEND_URL)

# CORS – allow the React dev-server and any configured production frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_origin_regex=r"^https:\/\/.*\.onrender\.com$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers (mounted at root and /api for versatile frontend compatibility) ──
for prefix in ["", "/api"]:
    app.include_router(auth_router.router, prefix=prefix)
    app.include_router(conversations_router.router, prefix=prefix)
    app.include_router(chat_router.router, prefix=prefix)


@app.api_route("/health", methods=["GET", "HEAD"], tags=["health"])
def health():
    return {
        "status": "ok" if db_connected else "degraded",
        "service": "GraphMind API",
        "database": "connected" if db_connected else "disconnected",
    }


# Check if frontend static files exist (enables single-service Render hosting)
frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if frontend_dist.exists() and (frontend_dist / "index.html").exists():
    from fastapi.staticfiles import StaticFiles
    from starlette.responses import FileResponse

    if (frontend_dist / "assets").exists():
        app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

    @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
    async def serve_root():
        return FileResponse(frontend_dist / "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        target = frontend_dist / full_path
        if full_path and target.exists() and target.is_file():
            return FileResponse(target)
        return FileResponse(frontend_dist / "index.html")
else:
    @app.api_route("/", methods=["GET", "HEAD"], tags=["health"])
    def root_health():
        return health()
