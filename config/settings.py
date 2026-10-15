"""
config/settings.py
------------------
Central settings object for the scraper, indexer, and RAG pipeline.
Loaded from environment variables / .env file at the project root.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root (parent of this config/ directory)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


class _Settings:
    # ── Scraper ───────────────────────────────────────────────────────────────
    raw_data_dir: str       = str(_PROJECT_ROOT / "data" / "raw")
    clean_data_dir: str     = str(_PROJECT_ROOT / "data" / "processed")

    # Polite delay between MediaWiki API calls (seconds)
    scrape_delay_seconds: float = float(os.getenv("SCRAPE_DELAY_SECONDS", "0.5"))

    # ── Embeddings / ChromaDB ────────────────────────────────────────────────
    embedding_model: str    = os.getenv(
        "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
    )
    chroma_persist_dir: str = str(_PROJECT_ROOT / "data" / "chroma_db")

    # ── Chunking ─────────────────────────────────────────────────────────────
    chunk_size: int         = int(os.getenv("CHUNK_SIZE", "500"))
    chunk_overlap: int      = int(os.getenv("CHUNK_OVERLAP", "50"))

    # ── Knowledge Graph ───────────────────────────────────────────────────────
    graph_path: str         = str(_PROJECT_ROOT / "data" / "metakgp_graph.gpickle")

    # ── LLM ───────────────────────────────────────────────────────────────────
    gemini_api_key: str     = os.getenv("GEMINI_API_KEY", "")
    llm_model: str          = os.getenv("LLM_MODEL", "gemini-3.8-flash")


settings = _Settings()
