"""
Hybrid Retriever — Combines FAISS (Semantic) and BM25 (Keyword) search.

Semantic search understands the meaning (e.g., "killing" -> "murder"),
while BM25 excels at exact matches (e.g., "Section 302", "Penal Code").
Using an EnsembleRetriever gives the best of both worlds.
"""

from typing import List, Any
import faiss

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain.retrievers import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever

from app.config import settings
from app.pipeline.embedder import get_embeddings_model


class FAISSRetriever(BaseRetriever):
    """Custom LangChain retriever wrapper for our local FAISS index."""
    
    index: Any
    chunks: List[Document]
    k: int = 10
    
    def _get_relevant_documents(
        self, query: str, *, run_manager: Any = None
    ) -> List[Document]:
        """Search FAISS and return top_k documents."""
        embeddings_model = get_embeddings_model()
        
        # Embed query
        query_vector = embeddings_model.embed_query(query)
        import numpy as np
        query_array = np.array([query_vector], dtype=np.float32)
        faiss.normalize_L2(query_array)
        
        # Search index
        scores, indices = self.index.search(query_array, self.k)
        
        results = []
        for idx in indices[0]:
            if idx < len(self.chunks) and idx >= 0:
                results.append(self.chunks[idx])
                
        return results


def build_hybrid_retriever(
    faiss_index: faiss.IndexFlatIP,
    chunks: list[Document],
    top_k: int | None = None,
) -> EnsembleRetriever:
    """Build a hybrid retriever combining FAISS and BM25.
    
    Args:
        faiss_index: Loaded FAISS index
        chunks: All document chunks
        top_k: Number of total candidates to retrieve (before reranking)
        
    Returns:
        EnsembleRetriever ready to be queried
    """
    k = top_k or settings.TOP_K_RETRIEVAL
    
    # 1. FAISS Retriever (Semantic)
    semantic_retriever = FAISSRetriever(
        index=faiss_index,
        chunks=chunks,
        k=k
    )
    
    # 2. BM25 Retriever (Keyword)
    # This tokenizes the documents and builds the BM25 index in memory
    keyword_retriever = BM25Retriever.from_documents(chunks)
    keyword_retriever.k = k
    
    # 3. Combine them
    ensemble_retriever = EnsembleRetriever(
        retrievers=[semantic_retriever, keyword_retriever],
        weights=[settings.FAISS_WEIGHT, settings.BM25_WEIGHT]
    )
    
    return ensemble_retriever
