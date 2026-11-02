import os
try:
    import spaces
except ImportError:
    class _DummySpaces:
        def GPU(self, fn):
            return fn
    spaces = _DummySpaces()

# Disable Gradio SSR mode to avoid port 7861 conflicts
os.environ["GRADIO_SSR_MODE"] = "false"

import gradio as gr

# ZeroGPU requires explicit @spaces.GPU decorator at the top-level
@spaces.GPU
def predict(query: str):
    from backend.rag_service import rag_service
    return rag_service.chat(query, history=[])

with gr.Blocks(title="GraphMind API — MetaKGP GraphRAG") as demo:
    gr.Markdown(
        """
        # 🧠 GraphMind Backend API
        **Knowledge-Graph-Augmented RAG Agent for MetaKGP / IIT Kharagpur**

        This service hosts the FastAPI backend powering GraphMind.

        ### Quick Links
        - 🌐 **Web Frontend (Vercel):** [https://graphmind-frontend.vercel.app](https://graphmind-frontend.vercel.app)
        - 📚 **Interactive API Docs:** [/docs](/docs)
        - 🩺 **System Health Endpoint:** [/health](/health)
        """
    )
    with gr.Row():
        txt_input = gr.Textbox(label="Test Query", placeholder="e.g. What is the deadline for HMC mess rebate?")
        txt_output = gr.Textbox(label="Agent Response")
    btn = gr.Button("Ask GraphMind")
    btn.click(fn=predict, inputs=txt_input, outputs=txt_output)

# Import backend app AFTER spaces is initialized
from backend.main import app

# Mount Gradio at root "/" with ssr_mode=False
app = gr.mount_gradio_app(app, demo, path="/", ssr_mode=False)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port, reload=False)
