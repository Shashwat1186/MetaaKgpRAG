"""
rag/indexer.py
--------------
Reads chunked JSON files from data/processed/ and indexes them into ChromaDB.
Uses `sentence-transformers/all-MiniLM-L6-v2` for generating local embeddings.
"""

import json
import os
import argparse
from pathlib import Path
from tqdm import tqdm

import chromadb
from sentence_transformers import SentenceTransformer

PROCESSED_DIR = Path('data/processed')
CHROMA_DB_DIR = Path('data/chroma_db')
COLLECTION_NAME = 'metakgp_pages'
EMBEDDING_MODEL = 'all-MiniLM-L6-v2'


def load_chunks():
    """Load all chunks from processed JSON files."""
    files = sorted(PROCESSED_DIR.glob('*.json'))
    all_chunks = []
    
    for fpath in files:
        with open(fpath, encoding='utf-8') as f:
            data = json.load(f)
            
            # Skip if no chunks
            if not data.get('chunks'):
                continue
                
            title = data.get('title', '')
            url = data.get('url', '')
            page_type = data.get('page_type', 'unknown')
            
            for chunk in data['chunks']:
                chunk_id = f"{fpath.stem}_{chunk['index']}"
                all_chunks.append({
                    'id': chunk_id,
                    'text': chunk['text'],
                    'metadata': {
                        'title': title,
                        'url': url,
                        'page_type': page_type,
                        'chunk_index': chunk['index'],
                        'source': fpath.name
                    }
                })
    return all_chunks


def build_index():
    print(f"[Indexer] Loading embedding model: {EMBEDDING_MODEL}")
    model = SentenceTransformer(EMBEDDING_MODEL)
    
    print(f"[Indexer] Initializing ChromaDB at {CHROMA_DB_DIR}")
    CHROMA_DB_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))
    
    # Recreate the collection
    try:
        client.delete_collection(name=COLLECTION_NAME)
        print(f"[Indexer] Deleted existing collection '{COLLECTION_NAME}'")
    except Exception:
        pass
        
    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"} # Use cosine similarity
    )
    
    print(f"[Indexer] Reading chunks from {PROCESSED_DIR}")
    chunks = load_chunks()
    total_chunks = len(chunks)
    print(f"[Indexer] Found {total_chunks} chunks to index")
    
    if total_chunks == 0:
        print("[Indexer] No chunks found! Exiting.")
        return

    # Index in batches
    BATCH_SIZE = 100
    
    print(f"[Indexer] Starting embedding and indexing...")
    for i in tqdm(range(0, total_chunks, BATCH_SIZE)):
        batch = chunks[i:i + BATCH_SIZE]
        
        texts = [item['text'] for item in batch]
        ids = [item['id'] for item in batch]
        metadatas = [item['metadata'] for item in batch]
        
        # Generate embeddings
        embeddings = model.encode(texts, show_progress_bar=False).tolist()
        
        # Add to collection
        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas
        )

    print(f"\n[Indexer] Successfully indexed {total_chunks} chunks into ChromaDB.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Index processed chunks into ChromaDB.')
    args = parser.parse_args()
    
    build_index()
