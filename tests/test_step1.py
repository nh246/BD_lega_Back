"""
Step 1 Test — Verify backend setup and config loading.

Run: python tests/test_step1.py
Expected: All checks pass with green checkmarks.
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_imports():
    """Test that all core dependencies import successfully."""
    print("Testing imports...")

    checks = []

    try:
        import fastapi
        checks.append(("FastAPI", True, fastapi.__version__))
    except ImportError as e:
        checks.append(("FastAPI", False, str(e)))

    try:
        import langchain
        checks.append(("LangChain", True, langchain.__version__))
    except ImportError as e:
        checks.append(("LangChain", False, str(e)))

    try:
        import langchain_google_genai
        checks.append(("LangChain Google GenAI", True, "OK"))
    except ImportError as e:
        checks.append(("LangChain Google GenAI", False, str(e)))

    try:
        import faiss
        checks.append(("FAISS", True, "OK"))
    except ImportError as e:
        checks.append(("FAISS", False, str(e)))

    try:
        from rank_bm25 import BM25Okapi
        checks.append(("rank_bm25", True, "OK"))
    except ImportError as e:
        checks.append(("rank_bm25", False, str(e)))

    try:
        from pydantic_settings import BaseSettings
        checks.append(("pydantic-settings", True, "OK"))
    except ImportError as e:
        checks.append(("pydantic-settings", False, str(e)))

    try:
        import pypdf
        checks.append(("PyPDF", True, pypdf.__version__))
    except ImportError as e:
        checks.append(("PyPDF", False, str(e)))

    for name, passed, info in checks:
        icon = "✅" if passed else "❌"
        print(f"  {icon} {name}: {info}")

    return all(passed for _, passed, _ in checks)


def test_config():
    """Test that config loads and paths are correct."""
    print("\nTesting config...")

    from app.config import settings, DATASET_DIR, ACTS_DIR, INDEX_DIR

    checks = []

    # Check paths exist
    checks.append(("DATASET_DIR exists", DATASET_DIR.exists(), str(DATASET_DIR)))
    checks.append(("ACTS_DIR exists", ACTS_DIR.exists(), str(ACTS_DIR)))

    # Check dataset has files
    act_files = list(ACTS_DIR.glob("act-print-*.json"))
    checks.append(("Act files found", len(act_files) > 0, f"{len(act_files)} files"))

    # Check config defaults
    checks.append(("Embedding model set", settings.EMBEDDING_MODEL == "models/text-embedding-004", settings.EMBEDDING_MODEL))
    checks.append(("Generation model set", settings.GENERATION_MODEL == "gemini-1.5-flash", settings.GENERATION_MODEL))
    checks.append(("Chunk size", settings.CHUNK_SIZE == 800, str(settings.CHUNK_SIZE)))
    checks.append(("Chunk overlap", settings.CHUNK_OVERLAP == 200, str(settings.CHUNK_OVERLAP)))

    # Check API key status (don't print the key!)
    has_key = bool(settings.GOOGLE_API_KEY and settings.GOOGLE_API_KEY != "your-api-key-here")
    checks.append(("API key configured", has_key, "Set" if has_key else "NOT SET — add to .env"))

    for name, passed, info in checks:
        icon = "✅" if passed else "⚠️" if "NOT SET" in str(info) else "❌"
        print(f"  {icon} {name}: {info}")

    return all(passed for _, passed, _ in checks if "API key" not in name)


def test_dataset_structure():
    """Quick check on dataset file structure."""
    print("\nTesting dataset structure...")

    import json
    from app.config import ACTS_DIR

    # Load one act and check schema
    test_file = ACTS_DIR / "act-print-11.json"  # Penal Code
    if not test_file.exists():
        print("  ❌ Penal Code file not found!")
        return False

    with open(test_file, "r", encoding="utf-8") as f:
        act = json.load(f)

    checks = []
    checks.append(("Has act_title", "act_title" in act, act.get("act_title", "MISSING")[:50]))
    checks.append(("Has act_year", "act_year" in act, act.get("act_year", "MISSING")))
    checks.append(("Has sections", "sections" in act, f"{len(act.get('sections', []))} sections"))
    checks.append(("Has language", "language" in act, act.get("language", "MISSING")))
    checks.append(("Sections have content", all("section_content" in s for s in act.get("sections", [])), "All have section_content"))

    for name, passed, info in checks:
        icon = "✅" if passed else "❌"
        print(f"  {icon} {name}: {info}")

    return all(passed for _, passed, _ in checks)


if __name__ == "__main__":
    print("=" * 50)
    print("BD Legal Guide AI — Step 1 Test")
    print("=" * 50)

    results = []
    results.append(("Imports", test_imports()))
    results.append(("Config", test_config()))
    results.append(("Dataset", test_dataset_structure()))

    print("\n" + "=" * 50)
    print("RESULTS:")
    all_pass = True
    for name, passed in results:
        icon = "✅" if passed else "❌"
        print(f"  {icon} {name}")
        if not passed:
            all_pass = False

    if all_pass:
        print("\n🎉 Step 1 PASSED — Ready for Step 2!")
    else:
        print("\n⚠️ Some checks failed — fix before proceeding.")
