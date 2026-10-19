import os
from pathlib import Path
from dotenv import load_dotenv

# Locate backend root and load .env
BASE_DIR = Path(__file__).resolve().parent.parent.parent
env_path = BASE_DIR / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

# Database
raw_db_url = os.getenv("DATABASE_URL", "").strip()
if not raw_db_url:
    DATABASE_URL = "sqlite:///./app.db"
else:
    # Standardize postgres protocol for SQLAlchemy
    if raw_db_url.startswith("postgres://"):
        DATABASE_URL = raw_db_url.replace("postgres://", "postgresql://", 1)
    else:
        DATABASE_URL = raw_db_url

# Security & Auth
JWT_SECRET = os.getenv("JWT_SECRET", "bdlegal-production-jwt-secret-key-2026")

# LLM Providers
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# Payments
PAYMENT_PROVIDER = os.getenv("PAYMENT_PROVIDER", "stripe")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
