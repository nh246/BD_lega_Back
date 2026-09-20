import sys
import os
import asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pipeline.embedder import load_index
from app.pipeline.retriever import build_hybrid_retriever
from app.config import settings

def test():
    faiss_index, chunks = load_index(settings.FAISS_INDEX_PATH)
    retriever = build_hybrid_retriever(faiss_index, chunks, top_k=5)
    
    query = "What is the punishment for murder?"
    docs = retriever.invoke(query)
    
    print(f"Found {len(docs)} documents for query: {query}")
    for i, doc in enumerate(docs):
        print(f"\n--- Result {i+1} ---")
        print(f"Title: {doc.metadata.get('act_title')}")
        print(f"Section: {doc.metadata.get('section_number')}")
        print(f"Content: {doc.page_content[:200]}...")

if __name__ == "__main__":
    test()
