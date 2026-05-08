"""
Long Transcript Chunker & Map-Reduce Summarizer
================================================
Handles transcripts that exceed a single LLM context window.

Strategy:
  1. Chunk transcript into overlapping segments (~800 tokens each)
  2. Map: summarize each chunk independently (parallel-friendly)
  3. Reduce: combine chunk summaries into a final hierarchical summary
  4. Extract action items from each chunk, deduplicate globally

Chunking modes:
  - sentence  : split on sentence boundaries (default)
  - paragraph : split on blank lines
  - fixed     : fixed character count with overlap
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

CHUNK_TOKENS    = 800    # target tokens per chunk
OVERLAP_TOKENS  = 80     # overlap between chunks (context continuity)
CHARS_PER_TOKEN = 4      # rough estimate

CHUNK_CHARS   = CHUNK_TOKENS  * CHARS_PER_TOKEN   # 3200
OVERLAP_CHARS = OVERLAP_TOKENS * CHARS_PER_TOKEN  # 320

# Transcripts shorter than this don't need chunking
CHUNKING_THRESHOLD = CHUNK_CHARS * 1.5  # ~4800 chars


# ── Chunker ───────────────────────────────────────────────────────────────────

def needs_chunking(transcript: str) -> bool:
    return len(transcript) > CHUNKING_THRESHOLD


def chunk_transcript(
    transcript: str,
    mode: str = "sentence",
    chunk_chars: int = CHUNK_CHARS,
    overlap_chars: int = OVERLAP_CHARS,
) -> list[dict]:
    """
    Split transcript into overlapping chunks.

    Returns:
        [{"index": int, "text": str, "start": int, "end": int}, ...]
    """
    if mode == "paragraph":
        segments = _split_paragraphs(transcript)
    elif mode == "fixed":
        segments = _split_fixed(transcript, chunk_chars)
    else:
        segments = _split_sentences(transcript)

    # Merge small segments into chunks of ~chunk_chars
    chunks = []
    current = ""
    current_start = 0
    pos = 0

    for seg in segments:
        if len(current) + len(seg) > chunk_chars and current:
            chunks.append({
                "index": len(chunks),
                "text":  current.strip(),
                "start": current_start,
                "end":   current_start + len(current),
            })
            # Overlap: keep last overlap_chars of current chunk
            overlap = current[-overlap_chars:] if len(current) > overlap_chars else current
            current_start = current_start + len(current) - len(overlap)
            current = overlap + seg
        else:
            if not current:
                current_start = pos
            current += seg
        pos += len(seg)

    if current.strip():
        chunks.append({
            "index": len(chunks),
            "text":  current.strip(),
            "start": current_start,
            "end":   current_start + len(current),
        })

    logger.info(f"[Chunker] Split {len(transcript)} chars → {len(chunks)} chunks")
    return chunks


def _split_sentences(text: str) -> list[str]:
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s + " " for s in sentences if s.strip()]


def _split_paragraphs(text: str) -> list[str]:
    paras = re.split(r'\n\s*\n', text)
    return [p.strip() + "\n\n" for p in paras if p.strip()]


def _split_fixed(text: str, size: int) -> list[str]:
    return [text[i:i+size] for i in range(0, len(text), size)]


# ── Map-Reduce Summarizer ─────────────────────────────────────────────────────

def map_reduce_summarize(
    transcript: str,
    router,  # LLMRouter instance
    task_type_str: str = "summarization",
) -> dict:
    """
    Full map-reduce pipeline for long transcripts.

    Returns:
        {
          "summary": str,
          "decisions": [str],
          "action_items": [dict],
          "chunk_count": int,
          "map_summaries": [str],
        }
    """
    from backend.services.llm.providers import TaskType

    chunks = chunk_transcript(transcript)
    logger.info(f"[MapReduce] Processing {len(chunks)} chunks")

    # ── Map phase: summarize each chunk ──────────────────────────────────────
    map_summaries = []
    all_action_items = []
    all_decisions = []

    for chunk in chunks:
        chunk_text = chunk["text"]
        chunk_idx  = chunk["index"] + 1
        total      = len(chunks)

        map_prompt = f"""You are summarizing chunk {chunk_idx} of {total} from a meeting transcript.
Extract from this chunk ONLY:
1. Key points (2-3 sentences)
2. Any decisions made
3. Any action items assigned

Return ONLY valid JSON:
{{
  "key_points": "2-3 sentence summary",
  "decisions": ["decision 1", ...],
  "action_items": [{{"task": "...", "assignee": "...", "deadline": null, "confidence_score": 0.8}}]
}}

Chunk {chunk_idx}/{total}:
{chunk_text}

Return ONLY the JSON:"""

        response = router.complete(
            prompt=map_prompt,
            task_type=TaskType.EXTRACTION,
            source_text=chunk_text,
        )

        if response.success:
            import json, re as _re
            try:
                cleaned = _re.sub(r"^```(?:json)?\s*", "", response.text.strip(), flags=_re.IGNORECASE)
                cleaned = _re.sub(r"\s*```$", "", cleaned).strip()
                data = json.loads(cleaned)
                map_summaries.append(data.get("key_points", ""))
                all_decisions.extend(data.get("decisions", []))
                all_action_items.extend(data.get("action_items", []))
            except Exception:
                map_summaries.append(response.text[:300])
        else:
            # Fallback: use first 200 chars of chunk as summary
            map_summaries.append(chunk_text[:200] + "…")

    # ── Reduce phase: combine chunk summaries ─────────────────────────────────
    combined = "\n\n".join(
        f"[Chunk {i+1}]: {s}" for i, s in enumerate(map_summaries) if s
    )

    reduce_prompt = f"""You are combining summaries from {len(chunks)} chunks of a meeting transcript.
Produce a final coherent meeting summary.

Chunk summaries:
{combined[:3000]}

Return ONLY valid JSON:
{{
  "summary": "3-5 sentence overall meeting summary",
  "decisions": ["final deduplicated decision list"],
  "action_items": [{{"task": "...", "assignee": "...", "deadline": null, "confidence_score": 0.8}}]
}}

Return ONLY the JSON:"""

    reduce_response = router.complete(
        prompt=reduce_prompt,
        task_type=TaskType.SUMMARIZATION,
        source_text=combined,
    )

    import json as _json, re as _re

    final = {"summary": "", "decisions": [], "action_items": []}
    if reduce_response.success:
        try:
            cleaned = _re.sub(r"^```(?:json)?\s*", "", reduce_response.text.strip(), flags=_re.IGNORECASE)
            cleaned = _re.sub(r"\s*```$", "", cleaned).strip()
            final = _json.loads(cleaned)
        except Exception:
            final["summary"] = reduce_response.text[:500]

    # Merge decisions and action items from map phase
    final["decisions"]    = _deduplicate_strings(final.get("decisions", []) + all_decisions)
    final["action_items"] = _deduplicate_actions(final.get("action_items", []) + all_action_items)
    final["chunk_count"]  = len(chunks)
    final["map_summaries"] = map_summaries

    return final


def _deduplicate_strings(items: list[str], threshold: float = 0.7) -> list[str]:
    """Remove near-duplicate strings using Jaccard similarity."""
    unique = []
    for item in items:
        item = item.strip()
        if not item:
            continue
        words_a = set(item.lower().split())
        is_dup = False
        for existing in unique:
            words_b = set(existing.lower().split())
            if words_a and words_b:
                jaccard = len(words_a & words_b) / len(words_a | words_b)
                if jaccard >= threshold:
                    is_dup = True
                    break
        if not is_dup:
            unique.append(item)
    return unique[:20]


def _deduplicate_actions(items: list[dict], threshold: float = 0.7) -> list[dict]:
    """Remove near-duplicate action items."""
    unique = []
    for item in items:
        task = str(item.get("task", "")).strip()
        if not task:
            continue
        words_a = set(task.lower().split())
        is_dup = False
        for existing in unique:
            words_b = set(str(existing.get("task", "")).lower().split())
            if words_a and words_b:
                jaccard = len(words_a & words_b) / len(words_a | words_b)
                if jaccard >= threshold:
                    is_dup = True
                    break
        if not is_dup:
            unique.append(item)
    return unique[:30]
