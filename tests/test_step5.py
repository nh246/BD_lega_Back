"""
Step 5 Test — Verify hybrid retrieval (FAISS + BM25).

Run: python tests/test_step5.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import INDEX_DIR
from app.pipeline.embedder import load_index
from app.pipeline.retriever import build_hybrid_retriever


def flush_print(*args, **kwargs):
    print(*args, **kwargs, flush=True)


def test_hybrid_retriever():
    """Test building and querying the ensemble retriever."""
    flush_print("Testing Hybrid Retriever (FAISS + BM25)...")
    
    test_path = str(INDEX_DIR / "test_mini")
    
    try:
        faiss_index, chunks = load_index(index_path=test_path)
    except FileNotFoundError:
        flush_print("  [FAIL] Mini index not found. Run test_step4.py first.")
        return False
        
    flush_print(f"  [PASS] Loaded mini index ({faiss_index.ntotal} vectors)")
    
    flush_print("  Building BM25 and Ensemble retriever...")
    retriever = build_hybrid_retriever(faiss_index, chunks, top_k=5)
    flush_print("  [PASS] Retriever built successfully")
    
    # Test queries
    queries = [
        "punishment for murder",
        "Section 4",
    ]
    
    all_pass = True
    for query in queries:
        flush_print(f"\n  Query: '{query}'")
        results = retriever.invoke(query)
        
        passed = len(results) > 0
        icon = "[PASS]" if passed else "[FAIL]"
        flush_print(f"  {icon} Found {len(results)} results")
        
        if not passed:
            all_pass = False
        else:
            for i, doc in enumerate(results[:3]):
                title = doc.metadata.get("act_title", "?")[:30]
                sec = doc.metadata.get("section_number", "?")
                flush_print(f"    {i+1}. {title} S.{sec} | {doc.page_content[:60]}...")
                
    return all_pass


if __name__ == "__main__":
    flush_print("=" * 50)
    flush_print("BD Legal Guide AI - Step 5 Test (Retriever)")
    flush_print("=" * 50)

    success = test_hybrid_retriever()
    
    flush_print("\n" + "=" * 50)
    if success:
        flush_print("Step 5 PASSED - Hybrid Retriever working!")
    else:
        flush_print("Some checks failed - fix before proceeding.")
    flush_print("=" * 50)
