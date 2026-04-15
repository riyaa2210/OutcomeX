"""
Document Processor
==================
Handles ingestion of PDF, DOCX, and TXT files.
Extracts raw text, cleans it, and returns it ready for chunking.

Supported formats:
  - .pdf  → PyMuPDF (fitz)
  - .docx → python-docx
  - .txt  → plain read
"""

import re
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


# ── PDF extraction ────────────────────────────────────────────────────────────

def _extract_pdf(path: str) -> list[dict]:
    """
    Extract text page-by-page from a PDF.
    Returns list of {"page": int, "text": str}
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise ImportError("Install PyMuPDF: pip install pymupdf")

    pages = []
    doc = fitz.open(path)
    for i, page in enumerate(doc):
        text = page.get_text("text")
        if text.strip():
            pages.append({"page": i + 1, "text": text})
    doc.close()
    return pages


# ── DOCX extraction ───────────────────────────────────────────────────────────

def _extract_docx(path: str) -> list[dict]:
    """
    Extract text from a DOCX file.
    Returns list of {"page": 1, "text": str} (DOCX has no page concept).
    """
    try:
        from docx import Document
    except ImportError:
        raise ImportError("Install python-docx: pip install python-docx")

    doc = Document(path)
    full_text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    return [{"page": 1, "text": full_text}]


# ── TXT extraction ────────────────────────────────────────────────────────────

def _extract_txt(path: str) -> list[dict]:
    """Read a plain text file."""
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()
    return [{"page": 1, "text": text}]


# ── Text cleaning ─────────────────────────────────────────────────────────────

def _clean_text(text: str) -> str:
    """
    Remove noise from extracted text:
      - Collapse multiple blank lines
      - Remove non-printable characters
      - Normalise whitespace
    """
    # Remove non-printable chars (keep newlines and tabs)
    text = re.sub(r"[^\x09\x0A\x0D\x20-\x7E\u00A0-\uFFFF]", " ", text)
    # Collapse 3+ newlines → 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Collapse multiple spaces
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


# ── Public API ────────────────────────────────────────────────────────────────

def extract_text(file_path: str) -> list[dict]:
    """
    Extract and clean text from a document.

    Args:
        file_path: Absolute or relative path to the file.

    Returns:
        List of page dicts: [{"page": int, "text": str}, ...]

    Raises:
        ValueError: Unsupported file type.
        FileNotFoundError: File does not exist.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    suffix = path.suffix.lower()
    logger.info(f"[DocProcessor] Extracting {suffix} file: {path.name}")

    if suffix == ".pdf":
        pages = _extract_pdf(str(path))
    elif suffix == ".docx":
        pages = _extract_docx(str(path))
    elif suffix == ".txt":
        pages = _extract_txt(str(path))
    else:
        raise ValueError(f"Unsupported file type: {suffix}. Use PDF, DOCX, or TXT.")

    # Clean each page
    cleaned = []
    for p in pages:
        text = _clean_text(p["text"])
        if text:  # skip empty pages
            cleaned.append({"page": p["page"], "text": text})

    logger.info(f"[DocProcessor] Extracted {len(cleaned)} pages from {path.name}")
    return cleaned
