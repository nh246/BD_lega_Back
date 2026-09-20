# BD Legal Guide AI - Backend

This directory contains the Python-based backend for the BD Legal Guide AI platform. It powers the Hybrid Retrieval-Augmented Generation (RAG) pipeline designed specifically for the Bangladesh legal ecosystem.

## 🛠 Tech Stack

- **Framework:** FastAPI (Python 3.10+)
- **LLM Orchestration:** LangChain
- **AI Models:** Google Gemini API
- **Vector Store:** FAISS (Facebook AI Similarity Search)
- **Sparse Retrieval:** BM25 (`rank_bm25`)
- **Reranking:** Cross-Encoder
- **Embeddings:** BAAI/bge-m3 / Bengali SBERT

## ✨ Key Features (Backend)

- **Hybrid RAG Pipeline:** Combines dense retrieval (FAISS) for semantic understanding with sparse retrieval (BM25) for exact keyword matching (crucial for legal jargon and Act sections).
- **Cross-Encoder Reranking:** Re-evaluates retrieved chunks to ensure the most highly relevant legal sections are passed to the LLM.
- **Bilingual Grounding:** Processes and answers legal queries in both Bangla and English based on a dataset of 35,633 sections across 1,484 Bangladesh legal acts.
- **Multi-Agent Architecture (Enterprise):** Uses a Manager agent to route queries to specialized Worker agents (e.g., Document Analysis, Citation Extraction).
- **RESTful API:** Exposes endpoints for the React frontend, handling chat streaming, document uploads, and analytics.

## 🚀 Quick Start

### 1. Create a Virtual Environment
Navigate to the `backend` directory and create a virtual environment:
```bash
python -m venv venv
```

### 2. Activate the Environment
- **Windows:**
  ```bash
  venv\Scripts\activate
  ```
- **macOS/Linux:**
  ```bash
  source venv/bin/activate
  ```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Environment Variables
Create a `.env` file in the `backend` root:
```env
GEMINI_API_KEY=your_gemini_api_key
# Add other necessary database/API keys here
```

### 5. Run the Server
Start the FastAPI server using Uvicorn:
```bash
uvicorn api.main:app --reload --port 8000
```

The API will be accessible at `http://localhost:8000`. You can view the interactive API documentation (Swagger UI) at `http://localhost:8000/docs`.

## 📂 Project Structure

- `/api` - FastAPI routes, controllers, and dependency injections.
- `/public/pipeline` - The core RAG pipeline (Retrievers, Rerankers, Prompts).
- `/enterprise` - Multi-agent swarm logic and firm-specific isolated knowledge bases.
- `/data` - (Git-ignored) FAISS indexes and raw data required for the pipeline.
