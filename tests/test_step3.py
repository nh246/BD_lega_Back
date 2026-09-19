"""
Step 3 Test — Verify chunker splits documents correctly.

Run: python tests/test_step3.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pipeline.loader import load_single_act, load_all_acts
from app.pipeline.chunker import chunk_documents
from app.config import ACTS_DIR


def test_single_act_chunking():
    """Test chunking the Penal Code (large act with 573 sections)."""
    print("Testing chunking on Penal Code (act-print-11)...")

    docs = load_single_act(ACTS_DIR / "act-print-11.json")
    chunks = chunk_documents(docs, verbose=True)

    checks = []
    checks.append(("More chunks than docs", len(chunks) >= len(docs), f"{len(docs)} docs -> {len(chunks)} chunks"))

    # Check metadata preserved
    sample = chunks[0]
    checks.append(("Has act_title", "act_title" in sample.metadata, sample.metadata.get("act_title", "MISSING")))
    checks.append(("Has section_number", "section_number" in sample.metadata, sample.metadata.get("section_number", "MISSING")))
    checks.append(("Has chunk_index", "chunk_index" in sample.metadata, str(sample.metadata.get("chunk_index", "MISSING"))))
    checks.append(("Has total_chunks", "total_chunks" in sample.metadata, str(sample.metadata.get("total_chunks", "MISSING"))))

    # Check chunk sizes are within bounds
    sizes = [len(c.page_content) for c in chunks]
    max_size = max(sizes)
    checks.append(("Max chunk <= 900", max_size <= 900, f"max={max_size} chars"))
    checks.append(("No empty chunks", min(sizes) > 0, f"min={min(sizes)} chars"))

    all_pass = True
    for name, passed, info in checks:
        icon = "[PASS]" if passed else "[FAIL]"
        print(f"  {icon} {name}: {info}")
        if not passed:
            all_pass = False
    return all_pass


def test_short_section_preserved():
    """Test that short sections are NOT split."""
    print("\nTesting short section preservation...")
    from langchain_core.documents import Document

    short_doc = Document(
        page_content="[The Penal Code, 1860] Section 8\n8. The pronoun 'he' and its derivatives are used of any person.",
        metadata={"act_title": "Test", "section_number": "8"}
    )

    chunks = chunk_documents([short_doc], verbose=False)

    checks = []
    checks.append(("Short doc not split", len(chunks) == 1, f"{len(chunks)} chunk(s)"))
    checks.append(("Content preserved", chunks[0].page_content == short_doc.page_content, "Content matches"))

    all_pass = True
    for name, passed, info in checks:
        icon = "[PASS]" if passed else "[FAIL]"
        print(f"  {icon} {name}: {info}")
        if not passed:
            all_pass = False
    return all_pass


def test_full_dataset_chunking():
    """Test chunking the entire dataset."""
    print("\nTesting full dataset chunking (35,420 sections)...")
    print("  Loading all acts first...")

    docs = load_all_acts(verbose=False)
    print(f"  Loaded {len(docs)} documents. Chunking...")

    chunks = chunk_documents(docs, verbose=True)

    checks = []
    checks.append(("Has chunks", len(chunks) > 0, f"{len(chunks)} total chunks"))
    checks.append(("More chunks than docs", len(chunks) >= len(docs), f"{len(docs)} -> {len(chunks)}"))

    # Verify all chunks have required metadata
    required_keys = ["act_title", "act_year", "section_number", "language", "chunk_index"]
    sample_check = all(key in chunks[0].metadata for key in required_keys)
    checks.append(("All metadata keys present", sample_check, str(required_keys)))

    all_pass = True
    for name, passed, info in checks:
        icon = "[PASS]" if passed else "[FAIL]"
        print(f"\n  {icon} {name}: {info}")
        if not passed:
            all_pass = False
    return all_pass


if __name__ == "__main__":
    print("=" * 50)
    print("BD Legal Guide AI - Step 3 Test (Chunker)")
    print("=" * 50)

    results = []
    results.append(("Single Act Chunking", test_single_act_chunking()))
    results.append(("Short Section Preservation", test_short_section_preserved()))
    results.append(("Full Dataset Chunking", test_full_dataset_chunking()))

    print("\n" + "=" * 50)
    print("RESULTS:")
    all_pass = True
    for name, passed in results:
        icon = "[PASS]" if passed else "[FAIL]"
        print(f"  {icon} {name}")
        if not passed:
            all_pass = False

    if all_pass:
        print("\nStep 3 PASSED - Ready for Step 4 (Embedder + Index)!")
    else:
        print("\nSome checks failed - fix before proceeding.")
