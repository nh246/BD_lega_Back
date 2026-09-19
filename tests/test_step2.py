"""
Step 2 Test — Verify data loader works correctly.

Run: python tests/test_step2.py
Tests:
- Title cleaning (footnote markers removed)
- Section number parsing
- Section text cleaning
- Single act loading
- Full dataset loading (all 1,484 acts)
- Document structure and metadata
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pipeline.loader import (
    clean_act_title,
    clean_section_text,
    parse_section_number,
    is_repealed_or_omitted,
    load_single_act,
    load_all_acts,
)
from app.config import ACTS_DIR


def test_title_cleaning():
    """Test footnote marker removal from titles."""
    print("Testing title cleaning...")
    tests = [
        ("1The Penal Code, 1860", "The Penal Code, 1860"),
        ("2The Evidence Act, 1872", "The Evidence Act, 1872"),
        ("The Contract Act, 1872", "The Contract Act, 1872"),  # no marker
        ("1The Districts Act, 1836", "The Districts Act, 1836"),
    ]
    
    all_pass = True
    for raw, expected in tests:
        result = clean_act_title(raw)
        passed = result == expected
        icon = "[PASS]" if passed else "[FAIL]"
        print(f"  {icon} '{raw}' -> '{result}'")
        if not passed:
            print(f"         Expected: '{expected}'")
            all_pass = False
    return all_pass


def test_section_number_parsing():
    """Test extracting section numbers from text."""
    print("\nTesting section number parsing...")
    tests = [
        ("1. This Act shall be called the Penal Code", "1"),
        ("375. A man is said to commit rape", "375"),
        ("100A. Any worker who contravenes", "100A"),
        ("INTRODUCTION", None),
        ("GENERAL EXPLANATIONS", None),
        ("21. The words \"public servant\" denote", "21"),
    ]
    
    all_pass = True
    for text, expected in tests:
        result = parse_section_number(text)
        passed = result == expected
        icon = "[PASS]" if passed else "[FAIL]"
        print(f"  {icon} '{text[:40]}...' -> {result}")
        if not passed:
            print(f"         Expected: {expected}")
            all_pass = False
    return all_pass


def test_text_cleaning():
    """Test footnote marker and whitespace cleaning."""
    print("\nTesting text cleaning...")
    tests = [
        ("2[***] Government", "Government"),
        ("9[Servant of the Republic]", "Servant of the Republic"),
        ("hello   world\ttab", "hello world tab"),
    ]
    
    all_pass = True
    for raw, expected in tests:
        result = clean_section_text(raw)
        passed = result == expected
        icon = "[PASS]" if passed else "[FAIL]"
        print(f"  {icon} '{raw}' -> '{result}'")
        if not passed:
            print(f"         Expected: '{expected}'")
            all_pass = False
    return all_pass


def test_repealed_detection():
    """Test repealed/omitted section detection."""
    print("\nTesting repealed detection...")
    tests = [
        ("[Repealed by the Government of India Act]", True),
        ("[Omitted by Article 2]", True),
        ("This section defines murder", False),
    ]
    
    all_pass = True
    for text, expected in tests:
        result = is_repealed_or_omitted(text)
        passed = result == expected
        icon = "[PASS]" if passed else "[FAIL]"
        print(f"  {icon} '{text[:40]}...' -> {result}")
        if not passed:
            all_pass = False
    return all_pass


def test_single_act():
    """Test loading a single act (Penal Code)."""
    print("\nTesting single act loading (Penal Code)...")
    
    filepath = ACTS_DIR / "act-print-11.json"
    if not filepath.exists():
        print("  [FAIL] act-print-11.json not found")
        return False
    
    docs = load_single_act(filepath)
    
    checks = []
    checks.append(("Documents returned", len(docs) > 0, f"{len(docs)} documents"))
    
    if docs:
        first = docs[0]
        checks.append(("Has page_content", bool(first.page_content), f"{len(first.page_content)} chars"))
        checks.append(("Has metadata", bool(first.metadata), str(list(first.metadata.keys())[:5])))
        checks.append(("Title is clean", "1The" not in first.metadata["act_title"], first.metadata["act_title"]))
        checks.append(("Has act_year", first.metadata["act_year"] == "1860", first.metadata["act_year"]))
        checks.append(("Has language", first.metadata["language"] == "english", first.metadata["language"]))
        
        # Check content has the header format
        checks.append(("Content has header", "[The Penal Code, 1860]" in first.page_content, first.page_content[:60]))
        
        # Check we have section numbers
        numbered = [d for d in docs if d.metadata["section_number"] != d.metadata["section_number"].startswith("part_")]
        checks.append(("Most sections numbered", len(numbered) > len(docs) * 0.5, f"{len(numbered)} numbered"))
    
    all_pass = True
    for name, passed, info in checks:
        icon = "[PASS]" if passed else "[FAIL]"
        print(f"  {icon} {name}: {info}")
        if not passed:
            all_pass = False
    return all_pass


def test_full_dataset():
    """Test loading ALL acts — the big test."""
    print("\nTesting full dataset loading (all 1,484 acts)...")
    print("  This may take 10-20 seconds...\n")
    
    docs = load_all_acts(verbose=True)
    
    checks = []
    checks.append(("Total documents > 10000", len(docs) > 10000, f"{len(docs)} total documents"))
    
    # Check language distribution
    english = sum(1 for d in docs if d.metadata["language"] == "english")
    bengali = sum(1 for d in docs if d.metadata["language"] in ("bengali", "bangla"))
    mixed = sum(1 for d in docs if d.metadata["language"] == "mixed")
    checks.append(("Has English docs", english > 0, f"{english} English"))
    checks.append(("Has Bengali docs", bengali > 0, f"{bengali} Bengali"))
    
    # Check year range
    years = [d.metadata["act_year"] for d in docs if d.metadata["act_year"].isdigit()]
    if years:
        min_year = min(int(y) for y in years)
        max_year = max(int(y) for y in years)
        checks.append(("Year range", min_year < 1900 and max_year > 2000, f"{min_year}-{max_year}"))
    
    # Sample a document to check quality
    sample = docs[len(docs) // 2]  # middle document
    checks.append(("Sample has content", len(sample.page_content) > 50, f"{len(sample.page_content)} chars"))
    checks.append(("Sample has clean title", not sample.metadata["act_title"].startswith(("1", "2", "3")), sample.metadata["act_title"][:40]))
    
    all_pass = True
    for name, passed, info in checks:
        icon = "[PASS]" if passed else "[FAIL]"
        print(f"\n  {icon} {name}: {info}")
        if not passed:
            all_pass = False
    return all_pass


if __name__ == "__main__":
    print("=" * 50)
    print("BD Legal Guide AI - Step 2 Test (Loader)")
    print("=" * 50)

    results = []
    results.append(("Title Cleaning", test_title_cleaning()))
    results.append(("Section Number Parsing", test_section_number_parsing()))
    results.append(("Text Cleaning", test_text_cleaning()))
    results.append(("Repealed Detection", test_repealed_detection()))
    results.append(("Single Act Loading", test_single_act()))
    results.append(("Full Dataset Loading", test_full_dataset()))

    print("\n" + "=" * 50)
    print("RESULTS:")
    all_pass = True
    for name, passed in results:
        icon = "[PASS]" if passed else "[FAIL]"
        print(f"  {icon} {name}")
        if not passed:
            all_pass = False

    if all_pass:
        print("\nStep 2 PASSED - Ready for Step 3 (Chunker)!")
    else:
        print("\nSome checks failed - fix before proceeding.")
