import json
import os
import sys
from pathlib import Path
from typing import List, Dict

# Ensure project root is in sys.path when running `python scraper/indexer.py` directly
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import chromadb
from chromadb.utils import embedding_functions

try:
    from scraper.chunker import chunk_text
except ImportError:
    from chunker import chunk_text

from config.settings import settings


class MetaKGPIndexer:
    def __init__(self):
        self.client = chromadb.PersistentClient(
            path=settings.chroma_persist_dir
        )
        self.ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=settings.embedding_model
        )
        self.collection = self.client.get_or_create_collection(
            name="metakgp_pages",
            embedding_function=self.ef,
            metadata={"hnsw:space": "cosine"},
        )

    def _get_page_chunks(self, page: Dict) -> List[str]:
        """Extract text chunks from page, using pre-computed chunks if available."""
        if page.get("chunks"):
            return [c["text"] for c in page["chunks"] if c.get("text", "").strip()]
        return chunk_text(
            page.get("text", ""),
            title=page.get("title", ""),
            chunk_size=settings.chunk_size,
            overlap=settings.chunk_overlap,
        )

    def index_page(self, page: Dict) -> int:
        """
        Chunk a single page and upsert all its chunks into ChromaDB.
        Returns number of chunks indexed.
        """
        chunks = self._get_page_chunks(page)
        if not chunks:
            return 0

        url = page.get("url") or page.get("title") or "page"
        title = page.get("title", "")
        categories = ", ".join(page.get("categories", []))
        page_type = page.get("page_type", "general")

        ids, docs, metas = [], [], []
        for i, chunk in enumerate(chunks):
            chunk_id = f"{url}#chunk{i}"
            ids.append(chunk_id)
            docs.append(chunk)
            metas.append({
                "url": url,
                "title": title,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "categories": categories,
                "page_type": page_type,
            })

        self.collection.upsert(ids=ids, documents=docs, metadatas=metas)
        return len(chunks)

    def index_all(self, clean_dir: str = None, batch_size: int = 100) -> int:
        clean_dir = clean_dir or settings.clean_data_dir
        files = sorted(Path(clean_dir).glob("*.json"))
        print(f"[Indexer] Indexing {len(files)} pages from {clean_dir} into ChromaDB...")

        batch_ids: List[str] = []
        batch_docs: List[str] = []
        batch_metas: List[Dict] = []
        total_chunks = 0
        pages_processed = 0

        for filepath in files:
            try:
                with open(filepath, encoding="utf-8") as f:
                    page = json.load(f)
            except Exception as e:
                print(f"  ⚠ Skipping {filepath.name}: {e}")
                continue

            chunks = self._get_page_chunks(page)
            if not chunks:
                continue

            url = page.get("url") or page.get("title") or filepath.stem
            title = page.get("title") or filepath.stem
            categories = ", ".join(page.get("categories", []))
            page_type = page.get("page_type", "general")

            for i, chunk in enumerate(chunks):
                chunk_id = f"{url}#chunk{i}"
                batch_ids.append(chunk_id)
                batch_docs.append(chunk)
                batch_metas.append({
                    "url": url,
                    "title": title,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "categories": categories,
                    "page_type": page_type,
                })

            pages_processed += 1

            if len(batch_ids) >= batch_size:
                self.collection.upsert(
                    ids=batch_ids,
                    documents=batch_docs,
                    metadatas=batch_metas,
                )
                total_chunks += len(batch_ids)
                print(f"  [{pages_processed}/{len(files)} pages] Indexed {total_chunks} chunks...")
                batch_ids, batch_docs, batch_metas = [], [], []

        if batch_ids:
            self.collection.upsert(
                ids=batch_ids,
                documents=batch_docs,
                metadatas=batch_metas,
            )
            total_chunks += len(batch_ids)

        count = self.collection.count()
        print(f"[Indexer] Done. {count} total chunks in ChromaDB collection 'metakgp_pages'.")
        return count

    def stats(self) -> Dict:
        return {"total_chunks": self.collection.count()}


if __name__ == "__main__":
    indexer = MetaKGPIndexer()
    indexer.index_all()