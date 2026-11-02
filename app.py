"""
app.py
------
Root entry-point for Hugging Face Spaces (Gradio SDK) and standalone execution.

Mounts the FastAPI backend (backend.main.app) alongside a lightweight Gradio
dashboard interface. This allows hosting on Hugging Face's free 16 GB RAM Gradio
tier while preserving all REST API endpoints (/chat, /auth, /conversations, /docs).
"""

import os
import gradio as gr
from backend.main import app

# Build a clean dashboard interface for the Space landing page
with gr.Blocks(title="GraphMind API — MetaKGP GraphRAG") as demo:
    gr.Markdown(
        """
        # 🧠 GraphMind Backend API
        **Knowledge-Graph-Augmented RAG Agent for MetaKGP / IIT Kharagpur**

        This Hugging Face Space hosts the FastAPI backend powering GraphMind.

        ### Quick Links
        - 🌐 **Web Frontend (Vercel):** [https://graphmind-frontend.vercel.app](https://graphmind-frontend.vercel.app)
        - 📚 **Interactive Swagger API Docs:** [/docs](/docs)
        - 🩺 **System Health Endpoint:** [/health](/health)
        """
    )

# Mount Gradio at root "/" so visiting the Hugging Face Space shows the dashboard.
# Existing FastAPI routes (/chat, /auth, /conversations, /health, /docs) take precedence.
app = gr.mount_gradio_app(app, demo, path="/")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 7860))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)

