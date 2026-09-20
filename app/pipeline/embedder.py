"""
Embedder — Wraps Google text-embedding-004 API and manages FAISS index.

Uses Google's free embedding API (1,500 req/min) instead of local models.
Zero local storage for the model — only the FAISS index file is stored locally.
"""

import os
import pickle
import time
from pathlib import Path

import faiss
import numpy as np
from langchain_core.documents import Document
from langchain_community.embeddings import HuggingFaceEmbeddings
from app.config import settings, INDEX_DIR

def get_embeddings_model() -> HuggingFaceEmbeddings:
    """Create the HuggingFace embeddings model instance.
    
    Uses all-MiniLM-L6-v2 which:
    - 384 dimensions
    - Runs entirely locally (no API limits)
    """
    return HuggingFaceEmbeddings(
        model_name=settings.EMBEDDING_MODEL,
        model_kwargs={'device': 'cpu'},
        encode_kwargs={'normalize_embeddings': True}
    )


def embed_documents(
    chunks: list[Document],
    batch_size: int = 256,
    verbose: bool = True,
) -> tuple[np.ndarray, list[Document]]:
    """Embed a list of document chunks using a local model.
    
    Args:
        chunks: List of Document objects to embed
        batch_size: Not strictly needed for local HF but kept for API compatibility
        verbose: Print progress
        
    Returns:
        Tuple of (embeddings_array, chunks) where embeddings_array is 
        shape (n_chunks, embedding_dim)
    """
    embeddings_model = get_embeddings_model()
    texts = [chunk.page_content for chunk in chunks]
    
    if verbose:
        print(f"  Embedding {len(texts)} chunks locally (this may take a few minutes)...")
        
    all_embeddings = embeddings_model.embed_documents(texts)
    
    if verbose:
        print(f"  Embedding complete: {len(all_embeddings)} vectors of dim {len(all_embeddings[0])}")
    
    return np.array(all_embeddings, dtype=np.float32), chunks


def build_faiss_index(embeddings: np.ndarray) -> faiss.IndexFlatIP:
    """Build a FAISS index from embedding vectors.
    
    Uses IndexFlatIP (Inner Product / cosine similarity) since
    our embeddings are normalized.
    """
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatIP(dimension)
    
    # Normalize vectors for cosine similarity
    faiss.normalize_L2(embeddings)
    index.add(embeddings)
    
    return index


def save_index(
    index: faiss.IndexFlatIP,
    chunks: list[Document],
    index_path: str | None = None,
) -> None:
    """Save FAISS index and document metadata to disk.
    
    Saves two files:
    - {index_path}.faiss — the FAISS index
    - {index_path}.pkl — the document chunks (for retrieval)
    """
    index_path = index_path or settings.FAISS_INDEX_PATH
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(index_path), exist_ok=True)
    
    # Save FAISS index
    faiss.write_index(index, f"{index_path}.faiss")
    
    # Save document chunks (metadata + content)
    with open(f"{index_path}.pkl", "wb") as f:
        pickle.dump(chunks, f)
    
    print(f"  Index saved: {index_path}.faiss ({index.ntotal} vectors)")
    print(f"  Chunks saved: {index_path}.pkl ({len(chunks)} documents)")


def load_index(
    index_path: str | None = None,
) -> tuple[faiss.IndexFlatIP, list[Document]]:
    """Load FAISS index and document chunks from disk.
    
    Returns:
        Tuple of (faiss_index, chunks)
    """
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
    """Search the FAISS index for documents similar to the query.
    
    Args:
        query: The search query text
        index: The FAISS index
        chunks: The document chunks corresponding to the index
        top_k: Number of results to return
        
    Returns:
        List of (Document, score) tuples, sorted by relevance
    """
    top_k = top_k or settings.TOP_K_RETRIEVAL
    embeddings_model = get_embeddings_model()
    
    # Embed the query
    query_vector = embeddings_model.embed_query(query)
    query_array = np.array([query_vector], dtype=np.float32)
    faiss.normalize_L2(query_array)
    
    # Search
    scores, indices = index.search(query_array, top_k)
    
    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < len(chunks) and idx >= 0:
            results.append((chunks[idx], float(score)))
    
    return results
