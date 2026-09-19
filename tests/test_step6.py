"""
Step 6 Test — Verify Gemini reranker works.

Run: python tests/test_step6.py
"""

import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.documents import Document
from app.pipeline.reranker import get_reranker


def flush_print(*args, **kwargs):
    print(*args, **kwargs, flush=True)


def test_reranker():
    """Test that the Gemini reranker correctly identifies the relevant document."""
    flush_print("Testing Gemini Reranker...")
    
    # Create dummy documents (one highly relevant, others irrelevant)
    query = "What is the punishment for murder?"
    
    docs = [
        Document(
            page_content="Any person who commits theft shall be punished with imprisonment of either description for a term which may extend to three years, or with fine, or with both.",
            metadata={"act_title": "Penal Code", "section_number": "379"}
        ),
        Document(
            page_content="Whoever commits murder shall be punished with death, or imprisonment for life, and shall also be liable to fine.",
            metadata={"act_title": "Penal Code", "section_number": "302"}
        ),
        Document(
            page_content="The word 'document' denotes any matter expressed or described upon any substance by means of letters, figures or marks.",
            metadata={"act_title": "Penal Code", "section_number": "29"}
        ),
        Document(
            page_content="This Act may be called the Contract Act, 1872.",
            metadata={"act_title": "Contract Act", "section_number": "1"}
        )
    ]
    
    flush_print(f"  Input query: '{query}'")
    flush_print(f"  Input documents: {len(docs)}")
    
    try:
        # We want top 2 results
        reranker = get_reranker(top_n=2)
        reranked_docs = reranker.compress_documents(docs, query)
        
        checks = []
        checks.append(("Returned documents", len(reranked_docs) > 0, f"{len(reranked_docs)} docs returned"))
        
        if reranked_docs:
            first_doc = reranked_docs[0]
            checks.append(("Best match selected", first_doc.metadata.get("section_number") == "302", f"Section {first_doc.metadata.get('section_number')}"))
            checks.append(("Score added to metadata", "rerank_score" in first_doc.metadata, f"Score: {first_doc.metadata.get('rerank_score')}"))
            checks.append(("Max docs respected", len(reranked_docs) <= 2, f"Got {len(reranked_docs)} docs"))
            
        all_pass = True
        for name, passed, info in checks:
            icon = "[PASS]" if passed else "[FAIL]"
            flush_print(f"  {icon} {name}: {info}")
            if not passed:
                all_pass = False
        return all_pass
        
    except Exception as e:
        flush_print(f"  [FAIL] Reranker threw an error: {e}")
        return False


if __name__ == "__main__":
    flush_print("=" * 50)
    flush_print("BD Legal Guide AI - Step 6 Test (Reranker)")
    flush_print("=" * 50)

    success = test_reranker()
    
    flush_print("\n" + "=" * 50)
    if success:
        flush_print("Step 6 PASSED - Gemini Reranker working!")
    else:
        flush_print("Some checks failed - fix before proceeding.")
    flush_print("=" * 50)
