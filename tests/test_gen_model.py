"""Test available Gemini generation models."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
import google.generativeai as genai

genai.configure(api_key=settings.GOOGLE_API_KEY)

print("Available text models:")
for m in genai.list_models():
    if "generateContent" in m.supported_generation_methods:
        print(f"  {m.name}")
