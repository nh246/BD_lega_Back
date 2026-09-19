# BD Legal Guide AI — Backend Configuration
# Loads settings from environment variables / .env file

import os
from pathlib import Path
from pydantic_settings import BaseSettings


# Project paths
BACKEND_DIR = Path(__file__).resolve().parent.parent  # backend/
PROJECT_ROOT = BACKEND_DIR.parent                     # Law_Project/
DATASET_DIR = PROJECT_ROOT / "dataset" / "archive"
ACTS_DIR = DATASET_DIR / "acts"
DATA_DIR = BACKEND_DIR / "data"
INDEX_DIR = BACKEND_DIR / "indexes"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # --- Required ---
    GOOGLE_API_KEY: str = ""

    # --- Embedding ---
    EMBEDDING_MODEL: str = "models/gemini-embedding-001"

    # --- Generation ---
    GENERATION_MODEL: str = "gemini-3.6-flash"

    # --- Index paths ---
    FAISS_INDEX_PATH: str = str(INDEX_DIR / "faiss_index")

    # --- Retrieval ---
    TOP_K_RETRIEVAL: int = 20    # candidates from hybrid search
    TOP_N_RERANK: int = 5        # final docs after reranking
    BM25_WEIGHT: float = 0.4
    FAISS_WEIGHT: float = 0.6

    # --- Chunking ---
    CHUNK_SIZE: int = 800
    CHUNK_OVERLAP: int = 200

    # --- Server ---
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    model_config = {
        "env_file": str(BACKEND_DIR / ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# Singleton instance
settings = Settings()
