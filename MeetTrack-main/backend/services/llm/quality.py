"""
Response Quality Scorer & Reranker
====================================
Scores LLM responses on multiple dimensions:
  - Completeness  : does the response contain expected fields?
  - Coherence     : is the text grammatically sensible?
  - Groundedness  : does the response reference content from the source?
  - JSON validity : for structured tasks, is the JSON parseable?
  - Length ratio  : is the response proportional to the input?

Reranker: given N candidate responses (from different providers),
returns the best one based on composite quality score.

Hallucination detection: flags responses that introduce names/dates
not present in the source transcript.
"""

import json
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


# ── Scoring weights per task type ─────────────────────────────────────────────

WEIGHTS = {
    "summarization":  {"completeness": 0.3, "coherence": 0.3, "groundedness": 0.3, "json": 0.0, "length": 0.1},
    "extraction":     {"completeness": 0.2, "coherence": 0.1, "groundedness": 0.2, "json": 0.4, "length": 0.1},
    "reasoning":      {"completeness": 0.3, "coherence": 0.4, "groundedness": 0.2, "json": 0.0, "length": 0.1},
    "sentiment":      {"completeness": 0.2, "coherence": 0.1, "groundedness": 0.1, "json": 0.5, "length": 0.1},
    "classification": {"completeness": 0.3, "coherence": 0.1, "groundedness": 0.1, "json": 0.4, "length": 0.1},
    "chat":           {"completeness": 0.2, "coherence": 0.5, "groundedness": 0.2, "json": 0.0, "length": 0.1},
    "fallback":       {"completeness": 0.3, "coherence": 0.2, "groundedness": 0.2, "json": 0.2, "length": 0.1},
}

DEFAULT_WEIGHTS = {"completeness": 0.25, "coherence": 0.25, "groundedness": 0.25, "json": 0.15, "length": 0.1}


def _completeness_score(text: str, task_type: str) -> float:
    """Check if expected content markers are present."""
    if not text:
        return 0.0

    markers = {
        "summarization":  ["summary", "decision", "action"],
        "extraction":     ["task", "assignee"],
        "reasoning":      ["because", "therefore", "conclusion", "result"],
        "sentiment":      ["positive", "negative", "neutral"],
        "classification": [],
        "chat":           [],
        "fallback":       [],
    }
    expected = markers.get(task_type, [])
    if not expected:
        return 0.8  # no specific markers needed

    lower = text.lower()
    found = sum(1 for m in expected if m in lower)
    return round(found / len(expected), 2)


def _coherence_score(text: str) -> float:
    """Heuristic coherence: sentence structure, no repeated phrases."""
    if not text or len(text) < 10:
        return 0.0

    sentences = re.split(r'[.!?]', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 5]
    if not sentences:
        return 0.3

    # Penalise very short or very long responses
    avg_len = sum(len(s) for s in sentences) / len(sentences)
    length_ok = 0.8 if 20 <= avg_len <= 200 else 0.4

    # Penalise repetition
    unique_ratio = len(set(sentences)) / len(sentences)

    return round((length_ok + unique_ratio) / 2, 2)


def _groundedness_score(text: str, source: str) -> float:
    """
    Check how many words in the response appear in the source.
    High groundedness = low hallucination risk.
    """
    if not text or not source:
        return 0.5

    response_words = set(re.findall(r'\b[a-z]{4,}\b', text.lower()))
    source_words   = set(re.findall(r'\b[a-z]{4,}\b', source.lower()))

    if not response_words:
        return 0.5

    overlap = len(response_words & source_words) / len(response_words)
    return round(min(1.0, overlap * 1.5), 2)  # scale up slightly


def _json_validity_score(text: str) -> float:
    """For structured tasks: is the JSON valid and non-empty?"""
    if not text:
        return 0.0

    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()

    try:
        data = json.loads(cleaned)
        if isinstance(data, (dict, list)) and data:
            return 1.0
        return 0.5
    except json.JSONDecodeError:
        # Partial JSON
        if "{" in cleaned or "[" in cleaned:
            return 0.3
        return 0.0


def _length_ratio_score(response: str, prompt: str) -> float:
    """Response should be 10–50% of prompt length for most tasks."""
    if not prompt:
        return 0.5
    ratio = len(response) / max(len(prompt), 1)
    if 0.05 <= ratio <= 0.6:
        return 1.0
    elif ratio < 0.05:
        return 0.3  # too short
    else:
        return 0.6  # too long but not terrible


def score_response(
    text: str,
    task_type: str,
    source_text: str = "",
    prompt: str = "",
) -> float:
    """
    Compute composite quality score 0.0–1.0 for an LLM response.
    """
    if not text:
        return 0.0

    weights = WEIGHTS.get(task_type, DEFAULT_WEIGHTS)

    scores = {
        "completeness": _completeness_score(text, task_type),
        "coherence":    _coherence_score(text),
        "groundedness": _groundedness_score(text, source_text),
        "json":         _json_validity_score(text) if weights["json"] > 0 else 0.0,
        "length":       _length_ratio_score(text, prompt),
    }

    composite = sum(scores[k] * weights[k] for k in scores)
    return round(min(1.0, composite), 3)


# ── Hallucination detection ───────────────────────────────────────────────────

def detect_hallucinations(response_text: str, source_text: str) -> dict:
    """
    Flag proper nouns (names, dates) in the response that don't appear in source.
    Returns {"hallucination_risk": float, "flagged_terms": [str]}
    """
    if not source_text:
        return {"hallucination_risk": 0.0, "flagged_terms": []}

    # Extract capitalised words (likely names) from response
    response_names = set(re.findall(r'\b[A-Z][a-z]{2,}\b', response_text))
    source_names   = set(re.findall(r'\b[A-Z][a-z]{2,}\b', source_text))

    # Extract dates from response
    response_dates = set(re.findall(r'\b\d{4}-\d{2}-\d{2}\b|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2}\b', response_text))
    source_dates   = set(re.findall(r'\b\d{4}-\d{2}-\d{2}\b|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2}\b', source_text))

    # Common English words that look like names — exclude them
    COMMON = {"The", "This", "That", "These", "Those", "When", "Where", "What",
              "How", "Why", "Who", "Which", "With", "From", "Into", "Upon",
              "Meeting", "Team", "Project", "Action", "Item", "Task", "Note"}

    flagged_names = (response_names - source_names - COMMON)
    flagged_dates = response_dates - source_dates
    flagged = list(flagged_names | flagged_dates)

    total_response_terms = len(response_names) + len(response_dates) + 1
    risk = min(1.0, len(flagged) / total_response_terms)

    return {
        "hallucination_risk": round(risk, 3),
        "flagged_terms":      flagged[:10],
    }


# ── Reranker ──────────────────────────────────────────────────────────────────

def rerank_responses(
    responses: list,  # list of LLMResponse
    task_type: str,
    source_text: str = "",
    prompt: str = "",
) -> list:
    """
    Score and sort a list of LLMResponse objects.
    Returns sorted list (best first).
    """
    from backend.services.llm.providers import LLMResponse

    scored = []
    for r in responses:
        if not r.success:
            r.quality_score = 0.0
            scored.append((0.0, r))
            continue

        q = score_response(r.text, task_type, source_text, prompt)
        r.quality_score = q
        scored.append((q, r))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored]
