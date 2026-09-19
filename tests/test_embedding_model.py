"""Test the correct embedding model."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from langchain_google_genai import GoogleGenerativeAIEmbeddings

for model_name in ["models/gemini-embedding-001", "models/gemini-embedding-2"]:
    try:
        e = GoogleGenerativeAIEmbeddings(
            model=model_name,
            google_api_key=settings.GOOGLE_API_KEY,
        )
        r = e.embed_query("What are the working hours under Bangladesh Labour Act?")
        print(f"SUCCESS with '{model_name}' -> dim={len(r)}")
    except Exception as ex:
        print(f"FAILED with '{model_name}': {str(ex)[:120]}")
