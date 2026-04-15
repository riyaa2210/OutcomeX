"""
Text Chunker
============
Splits document pages into overlapping chunks suitable for embedding.

Strategy:
  - Target chunk size: ~400 tokens  (≈ 1600 characters at ~4 chars/token)
  - Overlap:           ~75 tokens   (≈ 300 characters)
  - Split on sentence boundaries first, then hard-cut if needed

Each chunk carries metadata:
  {
    "chunk_id":   str,   # "{filename}_{page}_{index}"
    "file_name":  str,
    "page":       int,
    "chunk_index":int,
    "text":       str,
    "char_count": int,
  }
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Approximate characters per token (conservative estimate)
CHARS_PER_TOKEN = 4

# Default settings
DEFAULT_CHUNK_TOKENS   = 400   # target chunk size in tokens
DEFAULT_OVERLAP_TOKENS = 75    # overlap between consecutive chunks


def _estimate_tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences using punctuation boundaries."""
    # Split on . ! ? followed by whitespace or end of string
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def chunk_pages(
    pages: list[dict],
    file_name: str,
    chunk_tokens: int = DEFAULT_CHUNK_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[dict]:
    """
    Convert a list of page dicts into overlapping text chunks.

    Args:
        pages:          Output of document_processor.extract_text()
        file_name:      Original file name (stored in metadata)
        chunk_tokens:   Target chunk size in tokens
        overlap_tokens: Overlap size in tokens

    Returns:
        List of chunk dicts with text + metadata.
    """
    chunk_chars   = chunk_tokens   * CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * CHARS_PER_TOKEN

    all_chunks: list[dict] = []
    chunk_index = 0

    for page_data in pages:
        page_num = page_data["page"]
        text     = page_data["text"]

        sentences = _split_sentences(text)
        buffer    = ""

        for sentence in sentences:
            # If adding this sentence keeps us under the limit, add it
            if len(buffer) + len(sentence) + 1 <= chunk_chars:
                buffer = (buffer + " " + sentence).strip()
            else:
                # Flush current buffer as a chunk
                if buffer:
                    all_chunks.append(_make_chunk(
                        buffer, file_name, page_num, chunk_index
                    ))
                    chunk_index += 1

                    # Start new buffer with overlap from end of previous chunk
                    overlap_text = buffer[-overlap_chars:] if len(buffer) > overlap_chars else buffer
                    buffer = (overlap_text + " " + sentence).strip()
                else:
                    # Single sentence longer than chunk_chars — hard split
                    for i in range(0, len(sentence), chunk_chars - overlap_chars):
                        piece = sentence[i : i + chunk_chars]
                        if piece.strip():
                            all_chunks.append(_make_chunk(
                                piece, file_name, page_num, chunk_index
                            ))
                            chunk_index += 1
                    buffer = ""

        # Flush remaining buffer
        if buffer.strip():
            all_chunks.append(_make_chunk(buffer, file_name, page_num, chunk_index))
            chunk_index += 1

    logger.info(
        f"[Chunker] {file_name}: {len(pages)} pages → {len(all_chunks)} chunks "
        f"(~{chunk_tokens} tokens each, {overlap_tokens} overlap)"
    )
    return all_chunks


def _make_chunk(text: str, file_name: str, page: int, index: int) -> dict:
    """Build a single chunk dict."""
    safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", file_name)
    return {
        "chunk_id":    f"{safe_name}_{page}_{index}",
        "file_name":   file_name,
        "page":        page,
        "chunk_index": index,
        "text":        text.strip(),
        "char_count":  len(text.strip()),
        "token_est":   _estimate_tokens(text),
    }
