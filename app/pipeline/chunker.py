"""
Text Chunker — Splits legal documents into retrieval-friendly chunks.

Legal sections can be very long (some 5000+ chars). For effective retrieval,
we split them into smaller overlapping chunks while preserving:
- Parent metadata (act title, section number, etc.)
- Enough context in each chunk to be self-contained
- Overlap so we don't lose meaning at chunk boundaries
"""

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import settings


def create_chunker(
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> RecursiveCharacterTextSplitter:
    """Create a text splitter configured for legal text.
    
    Uses RecursiveCharacterTextSplitter which tries to split on:
    1. Double newlines (paragraph breaks)
    2. Single newlines
    3. Sentences (periods)
    4. Words (spaces)
    5. Characters (last resort)
    
    This order preserves the most meaningful boundaries first.
    """
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size or settings.CHUNK_SIZE,
        chunk_overlap=chunk_overlap or settings.CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
        is_separator_regex=False,
    )


def chunk_documents(
    documents: list[Document],
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    verbose: bool = True,
) -> list[Document]:
    """Split a list of Documents into smaller chunks.
    
    Each chunk inherits all metadata from its parent document,
    plus a 'chunk_index' field indicating its position within
    the parent.
    
    Args:
        documents: List of Documents from the loader
        chunk_size: Max characters per chunk (default from config: 800)
        chunk_overlap: Overlap between consecutive chunks (default: 200)
        verbose: Print progress stats
        
    Returns:
        List of chunked Documents with preserved metadata
    """
    splitter = create_chunker(chunk_size, chunk_overlap)
    
    chunks = []
    docs_split = 0
    docs_kept_whole = 0
    
    for doc in documents:
        # Split the document
        sub_chunks = splitter.split_documents([doc])
        
        if len(sub_chunks) > 1:
            docs_split += 1
            # Add chunk index to metadata
            for i, chunk in enumerate(sub_chunks):
                chunk.metadata["chunk_index"] = i
                chunk.metadata["total_chunks"] = len(sub_chunks)
        else:
            docs_kept_whole += 1
            if sub_chunks:
                sub_chunks[0].metadata["chunk_index"] = 0
                sub_chunks[0].metadata["total_chunks"] = 1
        
        chunks.extend(sub_chunks)
    
    if verbose:
        avg_len = sum(len(c.page_content) for c in chunks) / max(len(chunks), 1)
        print(f"\nChunker complete:")
        print(f"  Input documents: {len(documents)}")
        print(f"  Output chunks: {len(chunks)}")
        print(f"  Documents split: {docs_split}")
        print(f"  Documents kept whole: {docs_kept_whole}")
        print(f"  Avg chunk length: {avg_len:.0f} chars")
        
        # Show size distribution
        sizes = [len(c.page_content) for c in chunks]
        if sizes:
            print(f"  Min chunk: {min(sizes)} chars")
            print(f"  Max chunk: {max(sizes)} chars")
    
    return chunks
