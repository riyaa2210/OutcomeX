"""
Summary Service — Multi-LLM Structured Meeting Summary
=======================================================

Routes through LLMRouter:
  - Short transcripts  (<4800 chars) → single-pass Gemini extraction
  - Long transcripts   (≥4800 chars) → map-reduce chunked pipeline
  - Gemini unavailable               → OpenAI fallback
  - All providers fail               → local keyword extraction

Output contract:
{
  "summary": "...",
  "decisions": ["...", "..."],
  "action_items": [
    {"task": "...", "assignee": "...", "deadline": "YYYY-MM-DD or null", "confidence_score": 0.0}
  ],
  "_meta": {"provider": "gemini", "model": "...", "latency_ms": 0, "chunked": false}
}
"""

import json
import logging
import re
from typing import Optional

from backend.services.nlp_service import run_preprocessing_pipeline
from backend.services.llm.router import get_router
from backend.services.llm.providers import TaskType
from backend.services.llm.chunker import needs_chunking, map_reduce_summarize

logger = logging.getLogger(__name__)


# ── Prompt builder ────────────────────────────────────────────────────────────

def _build_summary_prompt(
    cleaned_transcript: str,
    speakers: list[str],
    action_sentences: list[str],
    decision_sentences: list[str],
) -> str:
    speaker_hint = (
        f"Known speakers: {', '.join(speakers)}."
        if speakers else "No explicit speaker labels detected."
    )
    action_hint   = "\n".join(f"  - {s}" for s in action_sentences[:15])   or "  (none)"
    decision_hint = "\n".join(f"  - {s}" for s in decision_sentences[:10]) or "  (none)"
    excerpt       = cleaned_transcript[:3500]

    return f"""You are a professional meeting analyst at a top-tier consulting firm.
Produce a concise, accurate meeting intelligence report.

{speaker_hint}

Pre-identified action-bearing sentences (hints only):
{action_hint}

Pre-identified decision-bearing sentences (hints only):
{decision_hint}

STRICT RULES:
1. Extract ONLY information explicitly stated or strongly implied in the transcript.
2. Do NOT invent, assume, or hallucinate any names, tasks, dates, or decisions.
3. summary: 2–4 sentences. Plain English. No bullet points inside the summary string.
4. decisions: List only clear decisions or agreements reached. Empty array [] if none.
5. action_items: Each item must have:
   - task: one concise sentence, active voice
   - assignee: person's name, or "Unassigned" if unknown
   - deadline: YYYY-MM-DD if a date is mentioned, otherwise null
   - confidence_score: float 0.0–1.0
6. Return ONLY valid JSON. No markdown, no code fences, no extra text.

Output schema (strict):
{{
  "summary": "string",
  "decisions": ["string", ...],
  "action_items": [
    {{"task": "string", "assignee": "string", "deadline": "YYYY-MM-DD or null", "confidence_score": 0.0}}
  ]
}}

Transcript:
{excerpt}

Return ONLY the JSON object:"""


# ── Output validation ─────────────────────────────────────────────────────────

def _validate_action_item(item: dict) -> Optional[dict]:
    if not isinstance(item, dict):
        return None
    task = str(item.get("task") or "").strip()
    if not task:
        return None
    assignee = str(item.get("assignee") or "Unassigned").strip()
    deadline = item.get("deadline") or None
    if deadline:
        deadline = str(deadline).strip()
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", deadline):
            deadline = None
    try:
        score = round(float(item.get("confidence_score", 0.8)), 2)
        score = max(0.0, min(1.0, score))
    except (TypeError, ValueError):
        score = 0.8
    return {"task": task, "assignee": assignee, "deadline": deadline, "confidence_score": score}


def _validate_structured_output(data: dict) -> dict:
    summary = str(data.get("summary") or "").strip() or "Meeting transcript processed."
    decisions = [str(d).strip() for d in (data.get("decisions") or []) if str(d).strip()]
    action_items = [v for item in (data.get("action_items") or []) if (v := _validate_action_item(item))]
    return {"summary": summary, "decisions": decisions, "action_items": action_items}


def _parse_llm_response(raw: str) -> Optional[dict]:
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return _validate_structured_output(data)
    except json.JSONDecodeError:
        pass
    obj_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if obj_match:
        try:
            data = json.loads(obj_match.group())
            if isinstance(data, dict):
                return _validate_structured_output(data)
        except json.JSONDecodeError:
            pass
    return None


# ── Fallback builder ──────────────────────────────────────────────────────────

def _build_fallback(pipeline: dict, error_note: str = "") -> dict:
    from backend.services.nlp_service import _extract_person, _extract_deadline
    if error_note:
        logger.warning(f"[Summary] Fallback reason: {error_note}")
    action_items = [
        {
            "task":             sent,
            "assignee":         _extract_person(sent) or "Unassigned",
            "deadline":         _extract_deadline(sent),
            "confidence_score": 0.5,
        }
        for sent in pipeline.get("action_sentences", [])
    ]
    decisions = list(pipeline.get("decision_sentences", []))
    parts = []
    if pipeline.get("speakers"):
        parts.append(f"Participants: {', '.join(pipeline['speakers'])}.")
    if action_items:
        parts.append(f"The meeting covered {len(action_items)} action item(s).")
    if decisions:
        parts.append(f"{len(decisions)} decision(s) were recorded.")
    return {
        "summary":      " ".join(parts) or "Meeting transcript processed.",
        "decisions":    decisions,
        "action_items": action_items,
    }


# ── Public API ────────────────────────────────────────────────────────────────

def generate_summary(transcript: str) -> str:
    """Legacy-compatible: returns JSON string."""
    result = generate_structured_summary(transcript)
    return json.dumps(result, indent=2)


def generate_structured_summary(
    transcript: str,
    meeting_id: Optional[int] = None,
    user_id: Optional[int] = None,
) -> dict:
    """
    Full pipeline: pre-process → route → LLM → validate → fallback.
    Handles long transcripts via map-reduce chunking.
    """
    if not transcript or not transcript.strip():
        return {"summary": "No transcript provided.", "decisions": [], "action_items": [], "_meta": {}}

    logger.info(f"[Summary] Starting pipeline ({len(transcript)} chars)")

    # Step 1 — Pre-process
    pipeline = run_preprocessing_pipeline(transcript)
    cleaned  = pipeline["cleaned_transcript"]

    if not cleaned:
        return {**_build_fallback(pipeline, "Empty after cleaning"), "_meta": {"provider": "local"}}

    router = get_router()

    # Step 2 — Long transcript: map-reduce
    if needs_chunking(transcript):
        logger.info(f"[Summary] Long transcript — using map-reduce chunking")
        result = map_reduce_summarize(transcript, router, task_type_str="summarization")
        result["_meta"] = {
            "provider": "multi",
            "chunked":  True,
            "chunks":   result.pop("chunk_count", 0),
        }
        result.pop("map_summaries", None)
        return result

    # Step 3 — Single-pass LLM call
    prompt = _build_summary_prompt(
        cleaned,
        pipeline["speakers"],
        pipeline["action_sentences"],
        pipeline["decision_sentences"],
    )

    response = router.complete(
        prompt=prompt,
        task_type=TaskType.EXTRACTION,
        source_text=transcript,
        meeting_id=meeting_id,
        user_id=user_id,
    )

    meta = {
        "provider":   response.provider.value,
        "model":      response.model,
        "latency_ms": response.latency_ms,
        "tokens":     response.total_tokens,
        "cost_usd":   response.cost_usd,
        "quality":    response.quality_score,
        "cache_hit":  response.cache_hit,
        "chunked":    False,
    }

    if response.success:
        result = _parse_llm_response(response.text)
        if result:
            logger.info(
                f"[Summary] ✅ {response.provider.value}/{response.model} "
                f"items={len(result['action_items'])} decisions={len(result['decisions'])}"
            )
            result["_meta"] = meta
            return result
        logger.warning("[Summary] Response failed validation — using fallback")

    return {**_build_fallback(pipeline, f"LLM failed: {response.error}"), "_meta": meta}
