"""
backend/rag_service.py
----------------------
A singleton wrapper around the GraphRAG agent that is safe to import
into FastAPI (avoids re-loading models on every request).

The agent is initialised lazily on the first call so the API server can
start quickly even if the ChromaDB / graph files are large.
"""

import sys
import os
from pathlib import Path
from typing import Optional

# ── Make sure the repo root is importable ────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Fix Windows console encoding issues for Unicode characters
if hasattr(sys.stdout, "reconfigure") and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")


class RAGService:
    """Lazy-initialised singleton for the LangGraph RAG agent."""

    _instance: Optional["RAGService"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def _create_llm_and_agent(self, model_name: str):
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langgraph.prebuilt import create_react_agent
        from langchain_core.tools import tool

        @tool
        def search_knowledge_base(query: str) -> str:
            """Useful for when you need to answer questions about MetaKGP, IIT Kharagpur,
            halls, courses, and related entities. Input should be a specific search query."""
            return self._retriever.search_for_agent(query, top_k=10)

        llm = ChatGoogleGenerativeAI(
            model=model_name,
            temperature=0.0,
            google_api_key=self._api_key,
            max_retries=4,
        )
        agent = create_react_agent(
            llm,
            tools=[search_knowledge_base],
            prompt=(
                "You are GraphMind, an AI assistant specialising in MetaKGP and "
                "IIT Kharagpur.\n"
                "Guidelines:\n"
                "1. Always search the knowledge base using search_knowledge_base for questions about IIT Kharagpur, halls, courses, societies, and campus life.\n"
                "2. Strictly ground your answer in the retrieved context. Do NOT hallucinate or extrapolate details that are not provided.\n"
                "3. Be concise, well-formatted, and helpful."
            ),
        )
        return llm, agent

    def _initialize(self):
        if self._initialized:
            return
        print("[RAGService] Loading GraphRAG components…")
        from rag.retriever import GraphRAGRetriever
        from rag.agent import MoEVerification, run_moe_verification

        self._retriever = GraphRAGRetriever()
        self._run_moe = run_moe_verification

        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError(
                "Gemini API key is not set. Please add GEMINI_API_KEY=your_key (or GOOGLE_API_KEY=your_key) to your .env file."
            )
        self._api_key = api_key

        model_name = os.getenv("LLM_MODEL", "gemini-3.5-flash")
        self._model_name = model_name
        self._llm, self._agent = self._create_llm_and_agent(model_name)

        self._MoEVerification = MoEVerification
        self._initialized = True
        print(f"[RAGService] Ready with model: {model_name}.")

    # ── Public API ────────────────────────────────────────────────────────────

    def chat(
        self,
        user_message: str,
        history: list[tuple[str, str]],
        max_retries: int = 2,
    ) -> str:
        """
        Run one turn of the conversation.

        Args:
            user_message: The latest user query.
            history: List of (role, content) tuples for prior turns.
                     role is "user" or "assistant".
            max_retries: MoE self-correction retries (if MoE is enabled).

        Returns:
            The final AI answer as a string.
        """
        import time
        import re
        self._initialize()

        fallback_chain = ["gemini-3.5-flash", "gemini-3.5-flash-lite"]
        if self._model_name not in fallback_chain:
            fallback_chain.insert(0, self._model_name)

        def _safe_call(fn):
            current_model = self._model_name
            while True:
                try:
                    return fn()
                except Exception as e:
                    err = str(e)
                    is_503 = "503" in err or "UNAVAILABLE" in err or "high demand" in err
                    is_429 = "429" in err or "RESOURCE_EXHAUSTED" in err or "Quota exceeded" in err

                    # Find next fallback model if available
                    curr_idx = fallback_chain.index(current_model) if current_model in fallback_chain else -1
                    next_model = fallback_chain[curr_idx + 1] if curr_idx + 1 < len(fallback_chain) else None

                    if (is_503 or is_429) and next_model:
                        reason = "rate limited (429)" if is_429 else "high demand (503)"
                        print(f"[RAGService] {current_model} {reason}. Failing over to {next_model}...")
                        self._model_name = next_model
                        current_model = next_model
                        self._llm, self._agent = self._create_llm_and_agent(next_model)
                        continue

                    # If no next model or all models exhausted, check if we can wait out a 429 quota delay
                    if is_429:
                        delay_match = re.search(r"retry in (\d+(?:\.\d+)?)s", err) or re.search(r"retryDelay':\s*'(\d+)s'", err)
                        wait_sec = float(delay_match.group(1)) if delay_match else 16.0
                        if wait_sec <= 20.0:
                            print(f"[RAGService] 429 quota pause: waiting {wait_sec:.1f}s for free-tier quota reset...")
                            time.sleep(wait_sec + 1.0)
                            try:
                                return fn()
                            except Exception as retry_err:
                                err = str(retry_err)

                        friendly_msg = (
                            "Google Gemini free-tier rate limit reached (5 requests/minute). "
                            "Please wait ~15 seconds before asking your next question, or upgrade your Gemini API key in Google AI Studio."
                        )
                        print(f"[RAGService] {friendly_msg}")
                        return friendly_msg

                    if is_503:
                        return "The Gemini AI model is currently experiencing high demand. Please try again in a few moments."

                    raise e

        def _extract_text(raw_content) -> str:
            if isinstance(raw_content, str):
                return raw_content
            if isinstance(raw_content, list):
                parts = []
                for p in raw_content:
                    if isinstance(p, str):
                        parts.append(p)
                    elif isinstance(p, dict) and "text" in p:
                        parts.append(p["text"])
                    elif hasattr(p, "text"):
                        parts.append(getattr(p, "text"))
                return "\n".join(parts)
            return str(raw_content)

        # Build message list in LangGraph format (tuples of role, content)
        current_messages = list(history) + [("user", user_message)]

        enable_moe = os.getenv("ENABLE_MOE", "false").strip().lower() in ("true", "1")

        if not enable_moe:
            # Streamlined grounded ReAct agent (1-2 LLM calls per query, avoids 429 RPM limit)
            final_state = _safe_call(lambda: self._agent.invoke({"messages": current_messages}))
            if isinstance(final_state, str):
                return final_state
            raw_answer = final_state["messages"][-1].content
            return _extract_text(raw_answer)

        # Full MoE self-correction loop (used when ENABLE_MOE=true)
        last_answer = ""
        for attempt in range(max_retries):
            final_state = _safe_call(lambda: self._agent.invoke({"messages": current_messages}))
            if isinstance(final_state, str):
                return final_state
            raw_answer = final_state["messages"][-1].content
            last_answer = _extract_text(raw_answer)

            # Extract tool context for MoE verification
            contexts = []
            for m in final_state["messages"]:
                if getattr(m, "name", "") == "search_knowledge_base":
                    contexts.append(_extract_text(m.content))
            combined_context = "\n\n".join(contexts) or "No context retrieved."

            verification = _safe_call(lambda: self._run_moe(
                self._llm, user_message, combined_context, last_answer
            ))
            if isinstance(verification, str):
                return last_answer

            if verification.is_valid:
                break
            elif attempt < max_retries - 1:
                current_messages = final_state["messages"]
                current_messages.append((
                    "user",
                    f"Your previous answer failed verification.\n"
                    f"Feedback: {verification.feedback}\n"
                    "Please revise your answer. Do NOT hallucinate.",
                ))

        return last_answer


# Expose a module-level singleton
rag_service = RAGService()

