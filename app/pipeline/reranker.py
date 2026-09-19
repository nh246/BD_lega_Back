"""
LLM-based Document Reranker.

Uses Gemini 1.5 Flash to rerank documents retrieved by the hybrid search.
Instead of downloading a heavy local cross-encoder model, we pass the retrieved
chunks to the LLM and ask it to score/filter them based on the query.
"""

import json
from typing import Sequence, Any

from langchain_core.documents import Document
from langchain_core.prompts import PromptTemplate
from langchain_core.callbacks.manager import Callbacks
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.retrievers.document_compressors.base import BaseDocumentCompressor
from pydantic import ConfigDict

from app.config import settings


RERANK_PROMPT = """You are an expert legal assistant. 
Your task is to evaluate the relevance of the following legal documents to a user's query.

User Query: "{query}"

Evaluate each document and assign a relevance score from 0 to 10:
- 10: Perfect match, directly answers the query.
- 7-9: Highly relevant, contains important context.
- 4-6: Somewhat relevant, related topic but not a direct answer.
- 0-3: Not relevant or tangentially related.

Documents:
{documents}

Respond ONLY with a valid JSON array of objects, where each object has:
- "index": the document index (integer)
- "score": your relevance score (integer)

Example output:
[
  {{"index": 0, "score": 9}},
  {{"index": 1, "score": 2}},
  {{"index": 2, "score": 8}}
]
"""


class GeminiReranker(BaseDocumentCompressor):
    """Custom LangChain compressor that uses Gemini to rerank documents."""
    
    # Required for Pydantic v2 BaseDocumentCompressor
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    llm: ChatGoogleGenerativeAI
    top_n: int = 5
    
    def compress_documents(
        self,
        documents: Sequence[Document],
        query: str,
        callbacks: Callbacks = None,
    ) -> Sequence[Document]:
        """Rerank documents using Gemini."""
        if not documents:
            return []
            
        # Format documents for the prompt
        docs_text = ""
        for i, doc in enumerate(documents):
            title = doc.metadata.get("act_title", "Unknown Act")
            sec = doc.metadata.get("section_number", "?")
            # Truncate content to save tokens
            content = doc.page_content[:400] + "..." if len(doc.page_content) > 400 else doc.page_content
            docs_text += f"--- Document [{i}] ({title}, Section {sec}) ---\n{content}\n\n"
            
        prompt = PromptTemplate.from_template(RERANK_PROMPT)
        formatted_prompt = prompt.format(query=query, documents=docs_text)
        
        try:
            # Request JSON output
            response = self.llm.invoke(formatted_prompt)
            content = response.content.strip()
            
            # Clean up markdown formatting if present
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
                
            scores = json.loads(content.strip())
            
            # Sort scores descending
            sorted_scores = sorted(scores, key=lambda x: x.get("score", 0), reverse=True)
            
            # Filter and keep top_n
            reranked_docs = []
            for item in sorted_scores:
                idx = item.get("index")
                score = item.get("score", 0)
                
                # Only keep somewhat relevant documents (score >= 4)
                if isinstance(idx, int) and 0 <= idx < len(documents) and score >= 4:
                    # Update metadata with rerank score
                    doc = documents[idx]
                    doc.metadata["rerank_score"] = score
                    reranked_docs.append(doc)
                    
                    if len(reranked_docs) >= self.top_n:
                        break
                        
            return reranked_docs
            
        except Exception as e:
            print(f"Warning: Reranking failed ({e}). Falling back to original order.")
            # Fallback: just return top_n of original documents
            return documents[:self.top_n]


def get_reranker(top_n: int | None = None) -> GeminiReranker:
    """Initialize the Gemini reranker."""
    llm = ChatGoogleGenerativeAI(
        model=settings.GENERATION_MODEL,
        google_api_key=settings.GOOGLE_API_KEY,
        temperature=0.0,
        # Force JSON output if the model supports it natively (Gemini 1.5 does)
        model_kwargs={"response_mime_type": "application/json"}
    )
    
    return GeminiReranker(
        llm=llm,
        top_n=top_n or settings.TOP_N_RERANK
    )
