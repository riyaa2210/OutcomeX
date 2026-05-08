"""
Embedding Service
=================
Generates vector embeddings for transcript chunks using Google Gemini.

Model: text-embedding-004 (768 dimensions)
Fallback: simple TF-IDF-style keyword vector if API unavailable

Chunking strategy:
  - Split by speaker turns first
  - Then by sentence boundaries
  - Target chunk size: 200-400 tokens (~150-300 words)
  - Overlap: 50 words between chunks for context continuity
"""

import os
import re
import logging
import hashlib
from typing import Optional

logger = logging.getLogger(__name__)

CHUNK_SIZE   = 250   # target words per chunk
CHUNK_OVERLAP = 50   # words overlap between chunks
EMBEDDING_DIM = 768  # Gemini text-embedding-004 dimensions


# ── Gemini embedding client ───────────────────────────────────────────────────

def _get_embedding_client():
    try:
        from google import genai
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            return None
        return genai.Client(api_key=api_key)
    except Exception:
        return None


def embed_text(text: str) -> Optional[list[float]]:
    """
    Generate a 768-dim embedding for a text string.
    Returns None if embedding fails (caller handles fallback).
    """
    if not text or not text.strip():
        return None

    client = _get_embedding_client()
    if not client:
        logger.warning("[Embed] GEMINI_API_KEY not set — using keyword fallback")
        return _keyword_fallback(text)

    try:
        result = client.models.embed_content(
            model="models/text-embedding-004",
            contents=text[:8000],   # API limit
        )
        embedding = result.embeddings[0].values
        logger.debug(f"[Embed] Generated {len(embedding)}-dim embedding")
        return list(embedding)
    except Exception as exc:
        logger.error(f"[Embed] Gemini embedding failed: {exc}")
        return _keyword_fallback(text)


def _keyword_fallback(text: str) -> list[float]:
    """
    Simple deterministic fallback embedding using character hashing.
    Not semantically meaningful but allows the system to function
    without the Gemini API.
    """
    import math
    words = re.findall(r'\w+', text.lower())[:500]
    vec = [0.0] * EMBEDDING_DIM
    for i, word in enumerate(words):
        h = int(hashlib.md5(word.encode()).hexdigest(), 16)
        idx = h % EMBEDDING_DIM
        vec[idx] += 1.0 / (i + 1)
    # L2 normalize
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


# ── Semantic chunking ─────────────────────────────────────────────────────────

def chunk_transcript(transcript: str, meeting_title: str = "") -> list[dict]:
    """
    Split a transcript into semantic chunks.

    Strategy:
      1. Split by speaker turns (Alice:, [Bob], etc.)
      2. If no speakers detected, split by paragraph/sentence
      3. Merge small chunks, split large ones
      4. Add overlap between adjacent chunks

    Returns list of:
      {
        "text": str,
        "chunk_index": int,
        "speaker": str | None,
        "chunk_type": "transcript"
      }
    """
    if not transcript or not transcript.strip():
        return []

    # Try speaker-based splitting first
    speaker_pattern = re.compile(
        r'^(?:([A-Z][a-zA-Z\s]{1,25}):|(?:\[([^\]]+)\])\s*:?)\s*',
        re.MULTILINE
    )

    chunks = []
    lines  = transcript.strip().split('\n')
    current_speaker = None
    current_text    = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        match = speaker_pattern.match(line)
        if match:
            # Flush previous speaker block
            if current_text:
                chunks.append({
                    "speaker": current_speaker,
                    "text":    " ".join(current_text).strip(),
                })
                current_text = []
            current_speaker = (match.group(1) or match.group(2) or "").strip()
            remainder = line[match.end():].strip()
            if remainder:
                current_text.append(remainder)
        else:
            current_text.append(line)

    if current_text:
        chunks.append({
            "speaker": current_speaker,
            "text":    " ".join(current_text).strip(),
        })

    # If no speakers found, fall back to paragraph splitting
    if not any(c.get("speaker") for c in chunks):
        chunks = _paragraph_chunks(transcript)

    # Merge tiny chunks and split huge ones
    chunks = _normalize_chunks(chunks)

    # Add index and type
    result = []
    for i, c in enumerate(chunks):
        if c["text"].strip():
            result.append({
                "text":        c["text"].strip(),
                "chunk_index": i,
                "speaker":     c.get("speaker"),
                "chunk_type":  "transcript",
            })

    logger.info(f"[Chunk] Split transcript into {len(result)} chunks")
    return result


def _paragraph_chunks(text: str) -> list[dict]:
    """Split by double newline or sentence boundaries."""
    paragraphs = re.split(r'\n{2,}|(?<=[.!?])\s{2,}', text)
    return [{"speaker": None, "text": p.strip()} for p in paragraphs if p.strip()]


def _normalize_chunks(chunks: list[dict]) -> list[dict]:
    """Merge chunks under 30 words; split chunks over 400 words."""
    result = []
    buffer_text    = ""
    buffer_speaker = None

    for chunk in chunks:
        words = chunk["text"].split()
        if len(words) < 30:
            # Too small — merge into buffer
            buffer_text    += " " + chunk["text"]
            buffer_speaker = buffer_speaker or chunk.get("speaker")
        elif len(words) > 400:
            # Too large — split into sub-chunks with overlap
            if buffer_text.strip():
                result.append({"speaker": buffer_speaker, "text": buffer_text.strip()})
                buffer_text = ""
                buffer_speaker = None
            sub = _split_large_chunk(chunk["text"], chunk.get("speaker"))
            result.extend(sub)
        else:
            if buffer_text.strip():
                result.append({"speaker": buffer_speaker, "text": buffer_text.strip()})
                buffer_text = ""
                buffer_speaker = None
            result.append(chunk)

    if buffer_text.strip():
        result.append({"speaker": buffer_speaker, "text": buffer_text.strip()})

    return result


def _split_large_chunk(text: str, speaker: Optional[str]) -> list[dict]:
    """Split a large chunk into CHUNK_SIZE-word pieces with CHUNK_OVERLAP overlap."""
    words  = text.split()
    chunks = []
    start  = 0
    while start < len(words):
        end   = min(start + CHUNK_SIZE, len(words))
        piece = " ".join(words[start:end])
        chunks.append({"speaker": speaker, "text": piece})
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks
