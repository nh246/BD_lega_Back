"""Test the chunker works correctly."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.documents import Document
from app.pipeline.chunker import chunk_documents

# Create test documents of varying sizes
test_docs = [
    Document(
        page_content="Short section. This is under 800 chars so should stay whole.",
        metadata={"act_title": "Test Act", "section_number": "1", "act_year": "2020"}
    ),
    Document(
        page_content=("Long section. " * 100),  # ~1400 chars, should be split
        metadata={"act_title": "Test Act", "section_number": "2", "act_year": "2020"}
    ),
    Document(
        page_content="",  # Empty doc
        metadata={"act_title": "Test Act", "section_number": "3", "act_year": "2020"}
    ),
]

print("=== Chunker Test ===")
chunks = chunk_documents(test_docs, verbose=True)

# Assertions
assert len(chunks) >= 3, f"Expected at least 3 chunks, got {len(chunks)}"

# Check metadata preserved
for c in chunks:
    assert "act_title" in c.metadata, "Missing act_title metadata"
    assert "chunk_index" in c.metadata, "Missing chunk_index metadata"

# Check that short doc stayed whole
short_chunks = [c for c in chunks if c.metadata["section_number"] == "1"]
assert len(short_chunks) == 1, f"Short doc should be 1 chunk, got {len(short_chunks)}"

# Check that long doc was split
long_chunks = [c for c in chunks if c.metadata["section_number"] == "2"]
assert len(long_chunks) > 1, f"Long doc should be split, got {len(long_chunks)}"

# Check max chunk size
for c in chunks:
    assert len(c.page_content) <= 850, f"Chunk too large: {len(c.page_content)} chars"

print("\n=== ALL CHUNKER TESTS PASSED ===")
