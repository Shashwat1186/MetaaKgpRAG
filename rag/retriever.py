"""
rag/retriever.py
----------------
A lightweight GraphRAG retriever that combines ChromaDB vector search with NetworkX graph traversal.
Uses ONNX runtime for embedding inference by default (<50MB RAM) with SentenceTransformer fallback.
"""

import argparse
import pickle
import re
from pathlib import Path
from typing import List, Optional

import chromadb
import networkx as nx

# Resolve paths relative to the REPO ROOT (two levels up from this file)
_REPO_ROOT = Path(__file__).resolve().parent.parent
CHROMA_DB_DIR = _REPO_ROOT / 'data' / 'chroma_db'
GRAPH_PATH = _REPO_ROOT / 'data' / 'metakgp_graph.gpickle'
COLLECTION_NAME = 'metakgp_pages'   # must match scraper/indexer.py
EMBEDDING_MODEL = 'all-MiniLM-L6-v2'

# Acronym expansion dictionary for IIT Kharagpur campus terminology
ACRONYMS = {
    "TFPS": "Technology Film and Photography Society",
    "TLS": "Technology Literary Society",
    "TSG": "Technology Students' Gymkhana",
    "Gymkhana": "Technology Students' Gymkhana",
    "RP Hall": "Rajendra Prasad Hall of Residence",
    "RP": "Rajendra Prasad Hall",
    "RK Hall": "Radhakrishnan Hall of Residence",
    "RK": "Radhakrishnan Hall",
    "HMC": "Hall Management Centre",
    "VP": "Vice President",
    "GSec": "General Secretary",
}

try:
    from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
    _HAS_ONNX = True
except ImportError:
    _HAS_ONNX = False

try:
    from sentence_transformers import SentenceTransformer
    _HAS_ST = True
except ImportError:
    _HAS_ST = False


class GraphRAGRetriever:
    def __init__(self):
        # 1. Initialize lightweight ONNX embedding function (<50MB RAM) to run within Render's 512MB limit
        if _HAS_ONNX:
            try:
                self._onnx_ef = ONNXMiniLM_L6_V2()
            except Exception as e:
                print(f"[Retriever] ONNX embedding init notice: {e}")

        # 2. Local fallback if SentenceTransformer is installed
        if _HAS_ST:
            try:
                self._st_model = SentenceTransformer(EMBEDDING_MODEL)
            except Exception as e:
                print(f"[Retriever] SentenceTransformer fallback not loaded: {e}")

        if not hasattr(self, "_onnx_ef") and not hasattr(self, "_st_model"):
            raise RuntimeError(
                "No embedding backend found. Please ensure chromadb or sentence_transformers is installed."
            )

        print(f"[Retriever] Connecting to ChromaDB at {CHROMA_DB_DIR}...")
        self.client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))
        # Use get_or_create so the server starts even before data is ingested
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

        print(f"[Retriever] Loading Knowledge Graph from {GRAPH_PATH}...")
        if GRAPH_PATH.exists():
            with open(GRAPH_PATH, 'rb') as f:
                self.graph = pickle.load(f)
        else:
            print(f"[Retriever] WARNING: {GRAPH_PATH} not found. Graph expansion disabled.")
            self.graph = None

    def _has_cached_onnx_model(self) -> bool:
        if not hasattr(self, "_onnx_ef"):
            return False
        model_file = (
            Path(self._onnx_ef.DOWNLOAD_PATH)
            / self._onnx_ef.EXTRACTED_FOLDER_NAME
            / "model.onnx"
        )
        return model_file.exists()

    def expand_acronyms(self, query: str) -> str:
        """Expand campus acronyms before vector search."""
        expanded = query
        for acronym, full_name in ACRONYMS.items():
            expanded = re.sub(rf'\b{re.escape(acronym)}\b', full_name, expanded, flags=re.IGNORECASE)
        return expanded

    def _encode_query(self, query: str) -> list[float]:
        """Encode a single query string into a 384-dimensional vector."""
        # Use ONNX if cached on disk or if SentenceTransformer is not installed
        if hasattr(self, "_onnx_ef") and (self._has_cached_onnx_model() or not hasattr(self, "_st_model")):
            try:
                embeddings = self._onnx_ef([query])
                emb = embeddings[0]
                return emb.tolist() if hasattr(emb, "tolist") else list(emb)
            except Exception as exc:
                if hasattr(self, "_st_model"):
                    emb = self._st_model.encode(query)
                    return emb.tolist() if hasattr(emb, "tolist") else list(emb)
                raise
        elif hasattr(self, "_st_model"):
            emb = self._st_model.encode(query)
            return emb.tolist() if hasattr(emb, "tolist") else list(emb)
        else:
            raise RuntimeError("No embedding model available to encode query.")

    def search(self, query: str, top_k: int = 3, expand_graph: bool = True):
        query = self.expand_acronyms(query)
        print(f"\n[Retriever] Query: '{query}'")

        # 1. Vector Search
        query_embedding = self._encode_query(query)
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k
        )

        if not results['ids'] or not results['ids'][0]:
            print("No results found in Vector DB.")
            return

        print("\n--- [Phase 1] Vector Search Results ---")
        primary_urls = set()

        for i in range(len(results['ids'][0])):
            distance = results['distances'][0][i]
            metadata = results['metadatas'][0][i]
            url = metadata.get('url')

            print(f"  [{i+1}] {metadata.get('title')} (Score: {distance:.4f})")
            if url:
                primary_urls.add(url)

        if not expand_graph:
            return

        # 2. Graph Expansion
        if self.graph is None:
            print("[Retriever] Graph not available — skipping expansion.")
            return
        print("\n--- [Phase 2] Graph Expansion Neighbors ---")
        expanded_urls = set()

        for url in primary_urls:
            if not self.graph.has_node(url):
                continue

            # Find neighbors (both outgoing and incoming edges if possible)
            neighbors = list(self.graph.successors(url)) + list(self.graph.predecessors(url))

            for neighbor in neighbors:
                if neighbor in primary_urls or neighbor in expanded_urls:
                    continue

                # Skip category nodes for retrieval context
                if self.graph.nodes[neighbor].get('type') == 'category':
                    continue

                expanded_urls.add(neighbor)
                title = self.graph.nodes[neighbor].get('title', neighbor)
                print(f"  (+) Discovered linked context: {title}")

        print(f"\n[Summary] Retrieved {len(primary_urls)} primary chunks and {len(expanded_urls)} related pages via Graph.")

    def search_for_agent(self, query: str, top_k: int = 3) -> str:
        """Helper function for the LangChain agent. Returns formatted context."""
        if self.collection.count() == 0:
            return (
                "The knowledge base is currently empty. "
                "Please run the data pipeline first: "
                "scrape → ingest → index."
            )

        expanded_query = self.expand_acronyms(query)
        query_embedding = self._encode_query(expanded_query)
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=['metadatas', 'documents', 'distances']
        )

        if not results['ids'] or not results['ids'][0]:
            return "No results found."

        # Graph expansion: fetch additional context from linked pages
        context = []
        seen_urls: set[str] = set()
        for i in range(len(results['ids'][0])):
            metadata = results['metadatas'][0][i]
            document = results['documents'][0][i]
            title = metadata.get('title', 'Unknown')
            url = metadata.get('url', 'Unknown')
            seen_urls.add(url)
            chunk_text = f"Source: {title} ({url})\nContent: {document}\n"
            context.append(chunk_text)

        # Graph expansion
        if self.graph is not None:
            expanded_docs: list[str] = []
            for url in list(seen_urls):
                if not self.graph.has_node(url):
                    continue
                neighbors = (
                    list(self.graph.successors(url))
                    + list(self.graph.predecessors(url))
                )
                for neighbor in neighbors[:3]:   # cap to 3 per node
                    if neighbor in seen_urls:
                        continue
                    if self.graph.nodes[neighbor].get('type') == 'category':
                        continue
                    seen_urls.add(neighbor)
                    neighbor_title = self.graph.nodes[neighbor].get('title', neighbor)
                    expanded_docs.append(f"Related page: {neighbor_title} ({neighbor})")
            if expanded_docs:
                context.append("\n".join(expanded_docs))

        return "\n---\n".join(context)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='GraphRAG Retriever for MetaKGP.')
    parser.add_argument('query', type=str, help='The search query')
    parser.add_argument('--k', type=int, default=3, help='Number of vector results to return')
    parser.add_argument('--no-graph', action='store_true', help='Disable graph expansion')

    args = parser.parse_args()

    if not CHROMA_DB_DIR.exists() or not GRAPH_PATH.exists():
        print(f"Error: Ensure {CHROMA_DB_DIR} and {GRAPH_PATH} exist.")
        exit(1)

    retriever = GraphRAGRetriever()
    retriever.search(args.query, top_k=args.k, expand_graph=not args.no_graph)
