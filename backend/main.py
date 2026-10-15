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
from backend.database import engine, Base
from backend.routers import auth_router, conversations_router, chat_router

# ── Create all tables on startup (safe to run multiple times) ─────────────────
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="GraphMind API",
    description=(
        "GraphRAG-powered conversational AI for MetaKGP / IIT Kharagpur. "
        "Supports multi-turn conversations, user accounts, and conversation history."
    ),
    version="1.0.0",
)

# Session middleware needed by Authlib's OAuth flow
# same_site="lax" allows the session cookie to be sent on top-level GET redirects
# (which is exactly what happens on the OAuth callback).
# https_only=False is required for local http:// dev servers.
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    same_site="lax",
    https_only=False,
    max_age=300,   # 5 minutes – enough time to complete the OAuth dance
)

# CORS – allow the React dev-server and any configured production frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",      # Vite dev server (localhost)
        "http://127.0.0.1:5173",      # Vite dev server (127.0.0.1)
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        FRONTEND_URL,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth_router.router)
app.include_router(conversations_router.router)
app.include_router(chat_router.router)


@app.get("/", tags=["health"])
def health():
    return {"status": "ok", "service": "GraphMind API"}
