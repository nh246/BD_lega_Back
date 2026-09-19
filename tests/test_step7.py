"""
Step 7 Test — Verify the final answer generator.

Run: python tests/test_step7.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.documents import Document
from app.pipeline.generator import generate_answer


def flush_print(*args, **kwargs):
    print(*args, **kwargs, flush=True)


def test_generator():
    """Test generating answers in English and Bangla."""
    flush_print("Testing Generator (Gemini LLM)...")
    
    # Mock documents from the reranker
    docs = [
        Document(
            page_content="Whoever commits murder shall be punished with death, or imprisonment for life, and shall also be liable to fine.",
            metadata={"act_title": "The Penal Code, 1860", "section_number": "302", "act_year": "1860", "rerank_score": 10}
        ),
        Document(
            page_content="If a person commits culpable homicide not amounting to murder, they shall be punished with imprisonment for life.",
            metadata={"act_title": "The Penal Code, 1860", "section_number": "304", "act_year": "1860", "rerank_score": 8}
        )
    ]
    
    queries = [
        "What is the punishment for murder?",
        "খুনের শাস্তি কি?"  # "What is the punishment for murder?" in Bangla
    ]
    
    all_pass = True
    for query in queries:
        flush_print(f"\n========================================")
        flush_print(f"QUERY: '{query}'")
        flush_print(f"========================================")
        
        try:
            result = generate_answer(query, docs)
            answer = result["answer"]
            sources = result["sources"]
            
            flush_print(f"\n[ANSWER]\n{answer}")
            flush_print(f"\n[SOURCES EXTRACTED]")
            for s in sources:
                flush_print(f"  - {s['act_title']} Sec.{s['section_number']} (Score: {s['score']})")
                
            if len(answer) < 10:
                flush_print("\n[FAIL] Answer too short.")
                all_pass = False
            elif "302" not in answer:
                flush_print("\n[FAIL] Missing citation to Section 302.")
                all_pass = False
                
        except Exception as e:
            flush_print(f"\n[FAIL] Generator threw an error: {e}")
            all_pass = False

    return all_pass


if __name__ == "__main__":
    flush_print("=" * 50)
    flush_print("BD Legal Guide AI - Step 7 Test (Generator)")
    flush_print("=" * 50)

    success = test_generator()
    
    flush_print("\n" + "=" * 50)
    if success:
        flush_print("Step 7 PASSED - Generator working perfectly!")
    else:
        flush_print("Some checks failed - fix before proceeding.")
    flush_print("=" * 50)
