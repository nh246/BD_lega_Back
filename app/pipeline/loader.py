"""
Data Loader — Reads Bangladesh Legal Acts dataset and converts to LangChain Documents.

Handles:
- Loading individual act JSON files from the dataset/archive/acts/ folder
- Cleaning footnote markers (e.g., "1The Penal Code" → "The Penal Code")
- Parsing section numbers embedded in text (e.g., "21. The words..." → section 21)
- Extracting section titles where available
- Flagging repealed/omitted sections
- Producing LangChain Document objects with rich metadata
"""

import json
import re
from pathlib import Path
from typing import Optional

from langchain_core.documents import Document

from app.config import ACTS_DIR


# --- Text Cleaning Functions ---

def clean_act_title(title: str) -> str:
    """Remove leading footnote number markers from act titles.
    
    Examples:
        "1The Penal Code, 1860" → "The Penal Code, 1860"
        "2The Evidence Act, 1872" → "The Evidence Act, 1872"
    """
    # Remove leading digits that are footnote markers (e.g., "1The" → "The")
    cleaned = re.sub(r"^\d+(?=[A-Z\[])", "", title)
    return cleaned.strip()


def clean_section_text(text: str) -> str:
    """Clean section content while preserving legal meaning.
    
    - Removes footnote superscript markers like 2[***], 9[text]
    - Preserves the actual content inside brackets when meaningful
    - Normalizes whitespace
    """
    # Replace footnote markers with bracketed content: 9[Servant of Republic] → Servant of Republic
    # But keep markers like [Omitted] or [Repealed] as they are meaningful
    cleaned = re.sub(r"\d+\[\*\*\*\]", "", text)  # Remove 2[***] completely
    cleaned = re.sub(r"(\d+)\[([^\]]+)\]", r"\2", cleaned)  # 9[text] → text
    
    # Normalize whitespace (collapse multiple spaces, fix tab chars)
    cleaned = re.sub(r"\t", " ", cleaned)
    cleaned = re.sub(r" {2,}", " ", cleaned)
    
    return cleaned.strip()


def parse_section_number(text: str) -> Optional[str]:
    """Extract section number from the beginning of section text.
    
    Examples:
        "1. This Act shall be called..." → "1"
        "375. A man is said to commit..." → "375"
        "100A. Any worker who..." → "100A"
        "INTRODUCTION" → None (it's a title, not numbered)
    """
    match = re.match(r"^(\d+[A-Z]?)\.\s", text)
    if match:
        return match.group(1)
    return None


def is_repealed_or_omitted(text: str) -> bool:
    """Check if a section has been repealed or omitted."""
    patterns = [
        r"\[Repealed\b",
        r"\[Omitted\b",
        r"\[Omitted by\b",
        r"\[Repealed by\b",
    ]
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


# --- Main Loader ---

def load_single_act(filepath: Path) -> list[Document]:
    """Load a single act JSON file and convert sections to Documents.
    
    Args:
        filepath: Path to an act-print-*.json file
        
    Returns:
        List of LangChain Document objects, one per section
    """
    with open(filepath, "r", encoding="utf-8") as f:
        act_data = json.load(f)

    act_title = clean_act_title(act_data.get("act_title", "Unknown Act"))
    act_year = act_data.get("act_year", "Unknown")
    act_no = act_data.get("act_no", "")
    language = act_data.get("language", "english")
    is_repealed = act_data.get("csv_metadata", {}).get("is_repealed", False)
    source_url = act_data.get("source_url", "")
    
    # Extract act file ID (e.g., "act-print-11" from filename)
    act_id = filepath.stem  

    sections = act_data.get("sections", [])
    documents = []

    for idx, section in enumerate(sections):
        raw_content = section.get("section_content", "")
        if not raw_content or len(raw_content.strip()) < 10:
            continue  # Skip empty or trivially short sections

        # Clean the text
        cleaned_content = clean_section_text(raw_content)
        
        # Parse section number from text
        section_number = parse_section_number(cleaned_content)
        
        # Get section title if available
        section_title = section.get("section_title", "")
        
        # Check if this section is repealed/omitted
        repealed = is_repealed_or_omitted(cleaned_content)
        
        # Skip very short repealed sections (they add noise)
        if repealed and len(cleaned_content) < 100:
            continue

        # Build the document content with context header
        # This header helps the retriever and LLM understand what they're reading
        content_parts = [f"[{act_title}]"]
        if section_number:
            content_parts.append(f"Section {section_number}")
        if section_title:
            content_parts.append(f"({section_title})")
        content_parts.append(f"\n{cleaned_content}")
        
        page_content = " ".join(content_parts)

        # Build metadata
        metadata = {
            "act_title": act_title,
            "act_year": act_year,
            "act_no": act_no,
            "act_id": act_id,
            "section_number": section_number or f"part_{idx}",
            "section_title": section_title,
            "section_index": idx,
            "language": language,
            "is_repealed_section": repealed,
            "is_act_repealed": is_repealed,
            "source_url": source_url,
        }

        documents.append(Document(page_content=page_content, metadata=metadata))

    return documents


def load_all_acts(
    acts_dir: Path = ACTS_DIR,
    target_acts: list[str] | None = None,
    skip_repealed_acts: bool = False,
    verbose: bool = True,
) -> list[Document]:
    """Load all act JSON files from the dataset directory.
    
    Args:
        acts_dir: Path to the acts/ directory
        target_acts: If provided, only load these specific act filenames 
                      (e.g., ["act-print-11.json", "act-print-26.json"])
                      If None, loads ALL acts.
        skip_repealed_acts: If True, skip entire acts that are marked as repealed
        verbose: If True, print progress
        
    Returns:
        List of all Document objects across all acts
    """
    if target_acts:
        act_files = [acts_dir / name for name in target_acts if (acts_dir / name).exists()]
    else:
        act_files = sorted(acts_dir.glob("act-print-*.json"))

    if not act_files:
        raise FileNotFoundError(f"No act files found in {acts_dir}")

    all_documents = []
    loaded_acts = 0
    skipped_acts = 0
    total_sections = 0

    for filepath in act_files:
        try:
            docs = load_single_act(filepath)
            
            # Optionally skip repealed acts
            if skip_repealed_acts and docs and docs[0].metadata.get("is_act_repealed"):
                skipped_acts += 1
                continue
                
            all_documents.extend(docs)
            loaded_acts += 1
            total_sections += len(docs)

            if verbose and loaded_acts % 100 == 0:
                print(f"  Loaded {loaded_acts} acts, {total_sections} sections so far...")

        except Exception as e:
            if verbose:
                print(f"  Warning: Failed to load {filepath.name}: {e}")

    if verbose:
        print(f"\nLoader complete:")
        print(f"  Acts loaded: {loaded_acts}")
        print(f"  Acts skipped (repealed): {skipped_acts}")
        print(f"  Total sections: {total_sections}")
        print(f"  Avg sections/act: {total_sections / max(loaded_acts, 1):.1f}")

    return all_documents


# --- Convenience: Load only the 8 MVP focus acts ---

# Map of MVP act names to their file IDs (you may need to verify these IDs)
MVP_ACTS = {
    "Penal Code 1860": "act-print-11.json",
    "Evidence Act 1872": "act-print-24.json",
    "Contract Act 1872": "act-print-26.json",
    "Constitution 1972": None,  # Need to find the correct ID
    "Labour Act 2006": None,    # Need to find the correct ID
    "Digital Security Act 2018": None,  # Need to find the correct ID
    "Muslim Family Laws 1961": None,    # Need to find the correct ID
    "Consumer Rights 2009": None,       # Need to find the correct ID
}


def load_mvp_acts(acts_dir: Path = ACTS_DIR) -> list[Document]:
    """Load only the 8 MVP focus acts for initial development."""
    known_files = [f for f in MVP_ACTS.values() if f is not None]
    if not known_files:
        print("Warning: No MVP act file IDs configured. Loading all acts instead.")
        return load_all_acts(acts_dir)
    
    print(f"Loading {len(known_files)} MVP acts...")
    return load_all_acts(acts_dir, target_acts=known_files)
