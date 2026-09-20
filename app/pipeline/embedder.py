"""
Embedder — Lightweight query-time embeddings using HuggingFace Inference API.

For indexing (Colab), we use local sentence-transformers.
For serving (Render), we use the free HuggingFace Inference API 
to avoid loading 500MB+ of PyTorch into memory.
"""

import os
import pickle
import time
import json
from pathlib import Path
from urllib.request import Request, urlopen

import faiss
import numpy as np
from langchain_core.documents import Document
from app.config import settings, INDEX_DIR

# HuggingFace Inference API (free, no key needed for public models)
HF_INFERENCE_URL = "https://api-inference.huggingface.co/pipeline/feature-extraction/sentence-transformers/all-MiniLM-L6-v2"


import requests

def embed_query_via_api(text: str) -> list[float]:
    """Embed a single query using HuggingFace free Inference API.
    
    This avoids loading sentence-transformers + PyTorch locally,
    saving ~500MB of RAM on Render's free tier.
    """
    payload = {"inputs": text, "options": {"wait_for_model": True}}
    headers = {"Content-Type": "application/json"}
    
    try:
        response = requests.post(HF_INFERENCE_URL, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        result = response.json()
        
        # The API returns a list of floats for a single string input
        if isinstance(result, list) and isinstance(result[0], float):
            return result
        elif isinstance(result, list) and isinstance(result[0], list):
            return result[0]
        return result
    except Exception as e:
        print(f"HF API embedding failed: {e}")
        # Fallback empty vector (will yield bad search results but won't crash)
        return [0.0] * 384


class LightweightEmbeddings:
    """Drop-in replacement for HuggingFaceEmbeddings that uses the Inference API."""
    
    def embed_query(self, text: str) -> list[float]:
        return embed_query_via_api(text)
    
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [embed_query_via_api(t) for t in texts]


def get_embeddings_model():
    """Return a lightweight embeddings model that uses HF Inference API.
    
    No local model loading — perfect for memory-constrained servers.
    """
    return LightweightEmbeddings()


def embed_documents(
    chunks: list[Document],
    batch_size: int = 256,
    verbose: bool = True,
) -> tuple[np.ndarray, list[Document]]:
    """Embed a list of document chunks.
    
    NOTE: For bulk indexing, use the Colab notebook instead.
    This function is kept for API compatibility.
    """
    embeddings_model = get_embeddings_model()
    texts = [chunk.page_content for chunk in chunks]
    
    if verbose:
        print(f"  Embedding {len(texts)} chunks via API...")
        
    all_embeddings = embeddings_model.embed_documents(texts)
    
    if verbose:
        print(f"  Embedding complete: {len(all_embeddings)} vectors")
    
    return np.array(all_embeddings, dtype=np.float32), chunks


def build_faiss_index(embeddings: np.ndarray) -> faiss.IndexFlatIP:
    """Build a FAISS index from embedding vectors."""
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatIP(dimension)
    faiss.normalize_L2(embeddings)
    index.add(embeddings)
    return index


def save_index(
    index: faiss.IndexFlatIP,
    chunks: list[Document],
    index_path: str | None = None,
) -> None:
    """Save FAISS index and document metadata to disk."""
    index_path = index_path or settings.FAISS_INDEX_PATH
    os.makedirs(os.path.dirname(index_path), exist_ok=True)
    faiss.write_index(index, f"{index_path}.faiss")
    with open(f"{index_path}.pkl", "wb") as f:
        pickle.dump(chunks, f)
    print(f"  Index saved: {index_path}.faiss ({index.ntotal} vectors)")
    print(f"  Chunks saved: {index_path}.pkl ({len(chunks)} documents)")


def load_index(
    index_path: str | None = None,
) -> tuple[faiss.IndexFlatIP, list[Document]]:
    """Load FAISS index and document chunks from disk."""
    index_path = index_path or settings.FAISS_INDEX_PATH
    faiss_file = f"{index_path}.faiss"
    pkl_file = f"{index_path}.pkl"
    
    if not os.path.exists(faiss_file):
        raise FileNotFoundError(
            f"FAISS index not found at {faiss_file}. "
            "Run 'python scripts/build_index.py' first."
        )
    
    index = faiss.read_index(faiss_file)
    with open(pkl_file, "rb") as f:
        chunks = pickle.load(f)
    
    print(f"  Index loaded: {index.ntotal} vectors, {len(chunks)} documents")
    return index, chunks


def search_index(
    query: str,
    index: faiss.IndexFlatIP,
    chunks: list[Document],
    top_k: int | None = None,
) -> list[tuple[Document, float]]:
    """Search the FAISS index for documents similar to the query."""
    top_k = top_k or settings.TOP_K_RETRIEVAL
    embeddings_model = get_embeddings_model()
    
    query_vector = embeddings_model.embed_query(query)
    query_array = np.array([query_vector], dtype=np.float32)
    faiss.normalize_L2(query_array)
    
    scores, indices = index.search(query_array, top_k)
    
    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < len(chunks) and idx >= 0:
            results.append((chunks[idx], float(score)))
    
    return results
