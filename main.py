"""
main.py
-------
Root-level entry point for platforms (like Railway Railpack) that auto-detect
a top-level main.py. Delegates directly to backend.main.app.
"""

from backend.main import app

__all__ = ["app"]

if __name__ == "__main__":
    import os
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
