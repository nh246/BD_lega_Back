import os
import sys
import numpy as np
from pathlib import Path
from langchain_core.documents import Document

# Add backend dir to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pipeline.embedder import load_index, get_embeddings_model
from app.config import settings

def test_faiss():
    """Simple test to verify FAISS index loading and searching directly."""
    # Hardcode index path to avoid config dependency
    INDEX_PATH = r"E:\Law_Project\backend\indexes\faiss_index"
    print(f"Loading FAISS index from {INDEX_PATH}...")
    
    index, metadata_list = load_index(INDEX_PATH)
    embeddings_model = get_embeddings_model()
    
    query = "What is the punishment for murder?"
    print(f"\nSearching for: '{query}'")
    
    # 1. Embed query
    query_embedding = embeddings_model.embed_query(query)
    
    # 2. Search FAISS index
    k = 5
    scores, indices = index.search(np.array([query_embedding], dtype=np.float32), k)
    
    # 3. Format results
    for i, (score, idx) in enumerate(zip(scores[0], indices[0])):
        if idx == -1:
            continue
            
        doc_meta = metadata_list[idx]
        print(f"\n--- Result {i+1} (Score: {score:.4f}) ---")
        doc_metadata = doc_meta.metadata
        print(f"Act: {doc_metadata.get('act_title', 'Unknown')}")
        print(f"Chapter: {doc_metadata.get('chapter', 'Unknown')}")
        print(f"Section: {doc_metadata.get('section_id', 'Unknown')}")
        print(f"Text: {doc_meta.page_content[:200]}...")

if __name__ == "__main__":
    test_faiss()
