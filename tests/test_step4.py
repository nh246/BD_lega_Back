"""
Step 4 Test — Verify embedder, index build, and search work correctly.

Tests with a tiny subset first (20 chunks), then with the 3 sample acts.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings, INDEX_DIR
from app.pipeline.loader import load_single_act
from app.pipeline.chunker import chunk_documents
from app.pipeline.embedder import (
    get_embeddings_model,
    embed_documents,
    build_faiss_index,
    save_index,
    load_index,
    search_index,
)
from app.config import ACTS_DIR


def flush_print(*args, **kwargs):
    print(*args, **kwargs, flush=True)


def test_embedding_api():
    """Test that we can connect to the Google Embedding API."""
    flush_print("Testing Google Embedding API connection...")
    
    try:
        model = get_embeddings_model()
        result = model.embed_query("What is the punishment for theft in Bangladesh?")
        flush_print(f"  [PASS] API connected. Embedding dim = {len(result)}")
        return True, len(result)
    except Exception as e:
        flush_print(f"  [FAIL] API error: {e}")
        return False, 0


def test_mini_index():
    """Test building a tiny index from 20 chunks of the Penal Code."""
    flush_print("\nTesting mini index build (20 chunks)...")
    
    # Load just a few docs
    docs = load_single_act(ACTS_DIR / "act-print-11.json")[:10]
    chunks = chunk_documents(docs, verbose=False)[:20]
    flush_print(f"  Using {len(chunks)} chunks")
    
    # Embed
    flush_print("  Embedding...")
    embeddings, chunks = embed_documents(chunks, batch_size=20, verbose=False)
    flush_print(f"  [PASS] Embedded: shape={embeddings.shape}")
    
    # Build index
    index = build_faiss_index(embeddings)
    flush_print(f"  [PASS] FAISS index built: {index.ntotal} vectors")
    
    # Save
    test_path = str(INDEX_DIR / "test_mini")
    save_index(index, chunks, index_path=test_path)
    flush_print(f"  [PASS] Index saved")
    
    # Load
    loaded_index, loaded_chunks = load_index(index_path=test_path)
    flush_print(f"  [PASS] Index loaded: {loaded_index.ntotal} vectors, {len(loaded_chunks)} chunks")
    
    # Search
    flush_print("  Searching...")
    results = search_index(
        "What is the punishment for murder?",
        loaded_index, loaded_chunks, top_k=3
    )
    
    flush_print(f"  [PASS] Search returned {len(results)} results:")
    for doc, score in results:
        title = doc.metadata.get("act_title", "?")
        sec = doc.metadata.get("section_number", "?")
        flush_print(f"    Score={score:.4f} | {title} S.{sec} | {doc.page_content[:80]}...")
    
    return True


def test_sample_index():
    """Build the full sample index from 3 acts."""
    flush_print("\nTesting sample index build (3 acts)...")
    
    from app.pipeline.loader import load_all_acts
    
    sample_acts = ["act-print-11.json", "act-print-24.json", "act-print-26.json"]
    docs = load_all_acts(acts_dir=ACTS_DIR, target_acts=sample_acts, verbose=False)
    flush_print(f"  Loaded {len(docs)} sections")
    
    chunks = chunk_documents(docs, verbose=False)
    flush_print(f"  Chunked into {len(chunks)} chunks")
    
    flush_print(f"  Embedding {len(chunks)} chunks (this takes 2-3 min with rate limits)...")
    embeddings, chunks = embed_documents(chunks, batch_size=50, verbose=True)
    flush_print(f"  [PASS] Embedded: shape={embeddings.shape}")
    
    index = build_faiss_index(embeddings)
    save_index(index, chunks)
    flush_print(f"  [PASS] Sample index built and saved with {index.ntotal} vectors")
    
    # Test a few searches
    queries = [
        "What is the definition of murder under Penal Code?",
        "What is a valid contract?",
        "Rules about witness testimony and evidence",
    ]
    
    flush_print("\n  Testing searches:")
    for q in queries:
        results = search_index(q, index, chunks, top_k=3)
        flush_print(f"\n  Query: '{q}'")
        for doc, score in results:
            sec = doc.metadata.get("section_number", "?")
            title = doc.metadata.get("act_title", "?")[:30]
            flush_print(f"    {score:.4f} | {title} S.{sec} | {doc.page_content[:60]}...")
    
    return True


if __name__ == "__main__":
    flush_print("=" * 50)
    flush_print("BD Legal Guide AI - Step 4 Test (Embedder + Index)")
    flush_print("=" * 50)

    # Test 1: API connection
    api_ok, dim = test_embedding_api()
    if not api_ok:
        flush_print("\nAPI connection failed. Fix your GOOGLE_API_KEY in .env")
        sys.exit(1)

    # Wait a moment for rate limits
    flush_print("\nWaiting 5s for rate limit cooldown...")
    time.sleep(5)

    # Test 2: Mini index (quick)
    try:
        test_mini_index()
    except Exception as e:
        flush_print(f"  [FAIL] Mini index test failed: {e}")
        sys.exit(1)

    # Wait for rate limits
    flush_print("\nWaiting 60s for rate limit reset before sample build...")
    time.sleep(60)

    # Test 3: Full sample index
    try:
        test_sample_index()
    except Exception as e:
        flush_print(f"  [FAIL] Sample index build failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    flush_print("\n" + "=" * 50)
    flush_print("Step 4 PASSED - Embedder + Index working!")
    flush_print("=" * 50)
