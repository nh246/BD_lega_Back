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
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from app.config import settings, INDEX_DIR


def get_embeddings_model() -> GoogleGenerativeAIEmbeddings:
    """Create the Google embeddings model instance.
    
    Uses text-embedding-004 which:
    - Supports 100+ languages including Bangla
    - 768 dimensions
    - Free tier: 1,500 requests/minute
    - No local model download needed
    """
    if not settings.GOOGLE_API_KEY or settings.GOOGLE_API_KEY == "your-api-key-here":
        raise ValueError(
            "GOOGLE_API_KEY not set! Add it to backend/.env file.\n"
            "Get your key from: https://ai.google.dev/"
        )
    
    return GoogleGenerativeAIEmbeddings(
        model=settings.EMBEDDING_MODEL,
        google_api_key=settings.GOOGLE_API_KEY,
    )


def embed_documents(
    chunks: list[Document],
    batch_size: int = 50,
    verbose: bool = True,
) -> tuple[np.ndarray, list[Document]]:
    """Embed a list of document chunks using Google API.
    
    Includes rate limiting and retry logic for free tier (100 req/min).
    
    Args:
        chunks: List of Document objects to embed
        batch_size: Number of texts per API call (50 to stay under limits)
        verbose: Print progress
        
    Returns:
        Tuple of (embeddings_array, chunks) where embeddings_array is 
        shape (n_chunks, embedding_dim)
    """
    embeddings_model = get_embeddings_model()
    
    all_embeddings = []
    texts = [chunk.page_content for chunk in chunks]
    total_batches = (len(texts) + batch_size - 1) // batch_size
    
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        batch_num = i // batch_size + 1
        
        # Retry with exponential backoff on rate limit errors
        max_retries = 5
        for attempt in range(max_retries):
            try:
                batch_embeddings = embeddings_model.embed_documents(batch)
                all_embeddings.extend(batch_embeddings)
                break
            except Exception as e:
                error_msg = str(e).lower()
                if "429" in str(e) or "resource_exhausted" in error_msg or "quota" in error_msg:
                    wait_time = 45 * (attempt + 1)  # 45s, 90s, 135s...
                    if verbose:
                        print(f"  Rate limited at batch {batch_num}. Waiting {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    raise
        else:
            raise RuntimeError(f"Failed after {max_retries} retries at batch {batch_num}")
        
        if verbose:
            print(f"  Batch {batch_num}/{total_batches}: embedded {min(i + batch_size, len(texts))}/{len(texts)} chunks")
        
        # Rate limit: sleep between batches to avoid hitting 100 req/min
        if i + batch_size < len(texts):
            time.sleep(2)
    
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
