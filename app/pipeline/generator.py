"""
Final Answer Generator using Gemini.

Takes the reranked legal documents and the user's query, and generates
a clear, professional legal answer. Automatically matches the language of the query.
"""

from typing import List, Dict, Any
from langchain_core.documents import Document
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.output_parsers import StrOutputParser

from app.config import settings

# The master prompt that tells Gemini how to behave
QA_PROMPT = """You are an expert, professional legal advisor for Bangladesh law.
Your task is to answer the user's query based strictly on the provided Legal Context.

CRITICAL INSTRUCTIONS:
1. Base your answer ONLY on the provided context. Do not make up laws or assume things outside the context.
2. If the context does not contain the answer, say clearly: "I cannot find the answer to this in the provided Bangladesh Legal Acts."
3. Always CITE the source. For example: "According to the Penal Code, Section 302..."
4. Answer in the SAME LANGUAGE as the user's query. If the query is in English, reply in English. If the query is in Bengali/Bangla, reply in beautiful, professional Bengali.
5. Format your answer clearly using bullet points and bold text where appropriate to make it easy to read.

=== LEGAL CONTEXT ===
{context}
=====================

USER QUERY: {query}
"""


def format_context(documents: List[Document]) -> str:
    """Format the retrieved documents into a clean text block for the LLM."""
    if not documents:
        return "No relevant legal acts found for this query."
        
    context_parts = []
    for i, doc in enumerate(documents):
        title = doc.metadata.get("act_title", "Unknown Act")
        sec = doc.metadata.get("section_number", "Unknown Section")
        content = doc.page_content.strip()
        
        # We append a clean, readable header for the LLM
        context_parts.append(f"[{title} - Section {sec}]\n{content}\n")
        
    return "\n".join(context_parts)


def get_generator_chain():
    """Build the LangChain generation pipeline."""
    # 1. Setup the LLM
    llm = ChatGoogleGenerativeAI(
        model=settings.GENERATION_MODEL,
        google_api_key=settings.GOOGLE_API_KEY,
        temperature=0.3, # Low temperature for factual, legal answers
    )
    
    # 2. Setup the prompt
    prompt = PromptTemplate.from_template(QA_PROMPT)
    
    # 3. Build the chain (Prompt -> LLM -> String Output)
    chain = prompt | llm | StrOutputParser()
    return chain


def generate_answer(query: str, documents: List[Document]) -> Dict[str, Any]:
    """Generate the final answer and return it along with the sources.
    
    Args:
        query: User's question
        documents: The reranked documents to use as context
        
    Returns:
        Dict containing the 'answer' text and the 'sources' metadata.
    """
    chain = get_generator_chain()
    context = format_context(documents)
    
    # Run the LLM
    answer = chain.invoke({"query": query, "context": context})
    
    # Extract source metadata to send to frontend
    sources = []
    for doc in documents:
        sources.append({
            "act_title": doc.metadata.get("act_title", ""),
            "section_number": doc.metadata.get("section_number", ""),
            "year": doc.metadata.get("act_year", ""),
            "score": doc.metadata.get("rerank_score", 0),
        })
        
    return {
        "answer": answer,
        "sources": sources
    }
