"""
Build FAISS Index — One-time script to process legal acts and build the search index.

Usage:
    # Build from 3 sample acts (quick test, ~2 min):
    python scripts/build_index.py --sample

    # Build from all 1,484 acts (full index, ~30-60 min via API):
    python scripts/build_index.py --full
    
    # Build from specific acts:
    python scripts/build_index.py --acts act-print-11.json act-print-24.json act-print-26.json
"""

import argparse
import sys
import time
from pathlib import Path

# Add backend dir to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import ACTS_DIR, INDEX_DIR
from app.pipeline.loader import load_all_acts, load_single_act
from app.pipeline.chunker import chunk_documents
from app.pipeline.embedder import embed_documents, build_faiss_index, save_index


# 3 sample acts for quick testing
SAMPLE_ACTS = [
    "act-print-11.json",   # Penal Code, 1860 (573 sections)
    "act-print-24.json",   # Evidence Act, 1872
    "act-print-26.json",   # Contract Act, 1872
]


def build_index(act_files: list[str] | None = None, verbose: bool = True):
    """Build the FAISS index from legal acts.
    
    Args:
        act_files: Specific act filenames to load. None = all acts.
        verbose: Print progress
    """
    start = time.time()

    # Step 1: Load
    print("=" * 50)
    print("STEP 1: Loading legal acts...")
    print("=" * 50)
    docs = load_all_acts(acts_dir=ACTS_DIR, target_acts=act_files, verbose=verbose)
    print(f"  -> {len(docs)} sections loaded")

    # Step 2: Chunk
    print("\n" + "=" * 50)
    print("STEP 2: Chunking documents...")
    print("=" * 50)
    chunks = chunk_documents(docs, verbose=verbose)
    print(f"  -> {len(chunks)} chunks created")

    # Step 3: Embed
    print("\n" + "=" * 50)
    print("STEP 3: Embedding chunks via Google API...")
    print("=" * 50)
    embeddings, chunks = embed_documents(chunks, verbose=verbose)
    print(f"  -> {embeddings.shape[0]} embeddings created (dim={embeddings.shape[1]})")

    # Step 4: Build index
    print("\n" + "=" * 50)
    print("STEP 4: Building FAISS index...")
    print("=" * 50)
    index = build_faiss_index(embeddings)
    print(f"  -> Index built with {index.ntotal} vectors")

    # Step 5: Save
    print("\n" + "=" * 50)
    print("STEP 5: Saving index to disk...")
    print("=" * 50)
    save_index(index, chunks)

    elapsed = time.time() - start
    print(f"\n{'=' * 50}")
    print(f"INDEX BUILD COMPLETE in {elapsed:.1f}s")
    print(f"  Total chunks indexed: {index.ntotal}")
    print(f"  Index location: {INDEX_DIR}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build FAISS index for BD Legal Guide AI")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--sample", action="store_true", help="Build from 3 sample acts (quick test)")
    group.add_argument("--full", action="store_true", help="Build from all 1,484 acts")
    group.add_argument("--acts", nargs="+", help="Build from specific act filenames")
    
    args = parser.parse_args()
    
    if args.sample:
        print(f"Building SAMPLE index from {len(SAMPLE_ACTS)} acts...")
        build_index(act_files=SAMPLE_ACTS)
    elif args.full:
        print("Building FULL index from ALL 1,484 acts...")
        print("This will make ~700 API calls and take 30-60 minutes.")
        build_index(act_files=None)
    elif args.acts:
        print(f"Building index from {len(args.acts)} specified acts...")
        build_index(act_files=args.acts)
