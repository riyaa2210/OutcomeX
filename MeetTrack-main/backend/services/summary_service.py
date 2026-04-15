"""
Summary Service — Generates a strict structured JSON meeting summary via Gemini.

Output contract:
{
  "summary": "...",
  "decisions": ["...", "..."],
  "action_items": [
    {"task": "...", "assignee": "...", "deadline": "YYYY-MM-DD or null", "confidence_score": 0.0}
  ]
}

Features:
  - Role-based prompt ("You are a professional meeting analyst…")
  - Multi-step pipeline: pre-process → LLM → validate → fallback
  - No hallucinations: only information present in the transcript
  - Graceful fallback: returns partial structured output on failure
"""

import os
import json
import re
import logging
from typing import Optional

from google import genai
from dotenv import load_dotenv

from backend.services.nlp_service import run_preprocessing_pipeline

load_dotenv()

logger = logging.getLogger(__name__)

_api_key = os.getenv("GEMINI_API_KEY", "")
_MODEL_NAME = "gemini-1.5-flash"

# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_summary_prompt(
    cleaned_transcript: str,
    speakers: list[str],
    action_sentences: list[str],
    decision_sentences: list[str],
) -> str:
    speaker_hint = (
        f"Known speakers: {', '.join(speakers)}."
        if speakers
        else "No explicit speaker labels detected."
    )

    action_hint = "\n".join(f"  - {s}" for s in action_sentences[:15]) or "  (none)"
    decision_hint = "\n".join(f"  - {s}" for s in decision_sentences[:10]) or "  (none)"

    # Cap to avoid token overflow (~3500 chars leaves room for prompt overhead)
    excerpt = cleaned_transcript[:3500]

    return f"""You are a professional meeting analyst at a top-tier consulting firm.
Your task is to produce a concise, accurate meeting intelligence report.

{speaker_hint}

Pre-identified action-bearing sentences (hints only):
{action_hint}

Pre-identified decision-bearing sentences (hints only):
{decision_hint}

STRICT RULES:
1. Extract ONLY information explicitly stated or strongly implied in the transcript.
2. Do NOT invent, assume, or hallucinate any names, tasks, dates, or decisions.
3. summary: 2–4 sentences. Plain English. No bullet points inside the summary string.
4. decisions: List only clear decisions or agreements reached. Include implicit decisions
   (e.g., "The team agreed to proceed with Option A" counts even if not stated verbatim).
   Empty array [] if none.
5. action_items: Each item must have:
   - task: one concise sentence, active voice
   - assignee: person's name, or "Unassigned" if unknown
   - deadline: YYYY-MM-DD if a date is mentioned, otherwise null
   - confidence_score: float 0.0–1.0
     (1.0 = explicitly stated, 0.7 = strongly implied, 0.4 = weakly implied)
6. Avoid repetition across summary, decisions, and action_items.
7. Return ONLY valid JSON. No markdown, no code fences, no extra text.

Output schema (strict):
{{
  "summary": "string",
  "decisions": ["string", ...],
  "action_items": [
    {{
      "task": "string",
      "assignee": "string",
      "deadline": "YYYY-MM-DD or null",
      "confidence_score": 0.0
    }}
  ]
}}

Transcript:
{excerpt}

Return ONLY the JSON object:"""


# ---------------------------------------------------------------------------
# Output validation
# ---------------------------------------------------------------------------

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

    return {
        "task": task,
        "assignee": assignee,
        "deadline": deadline,
        "confidence_score": score,
    }


def _validate_structured_output(data: dict) -> dict:
    """
    Validate and normalise the full structured output dict.
    Fills in defaults for missing/malformed fields.
    """
    summary = str(data.get("summary") or "").strip()
    if not summary:
        summary = "Meeting transcript processed. Review the action items below."

    raw_decisions = data.get("decisions") or []
    if not isinstance(raw_decisions, list):
        raw_decisions = []
    decisions = [str(d).strip() for d in raw_decisions if str(d).strip()]

    raw_items = data.get("action_items") or []
    if not isinstance(raw_items, list):
        raw_items = []
    action_items = [v for item in raw_items if (v := _validate_action_item(item))]

    return {
        "summary": summary,
        "decisions": decisions,
        "action_items": action_items,
    }


def _parse_llm_response(raw: str) -> Optional[dict]:
    """
    Parse raw LLM text into a validated structured dict.
    Returns None if parsing fails completely.
    """
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return _validate_structured_output(data)
    except json.JSONDecodeError:
        pass

    # Try to find a JSON object anywhere in the response
    obj_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if obj_match:
        try:
            data = json.loads(obj_match.group())
            if isinstance(data, dict):
                return _validate_structured_output(data)
        except json.JSONDecodeError:
            pass

    return None


# ---------------------------------------------------------------------------
# Fallback builder
# ---------------------------------------------------------------------------

def _build_fallback(pipeline: dict, error_note: str = "") -> dict:
    """
    Build a partial structured output from NLP pre-processing data
    when the LLM is unavailable or returns unparseable output.
    """
    from backend.services.nlp_service import _extract_person, _extract_deadline

    action_items = []
    for sent in pipeline.get("action_sentences", []):
        action_items.append({
            "task": sent,
            "assignee": _extract_person(sent) or "Unassigned",
            "deadline": _extract_deadline(sent),
            "confidence_score": 0.5,
        })

    decisions = list(pipeline.get("decision_sentences", []))

    summary_parts = []
    if pipeline.get("speakers"):
        summary_parts.append(f"Participants: {', '.join(pipeline['speakers'])}.")
    if action_items:
        summary_parts.append(
            f"The meeting covered {len(action_items)} action item(s)."
        )
    if decisions:
        summary_parts.append(f"{len(decisions)} decision(s) were recorded.")

    # Log the error internally but never expose it to the user
    if error_note:
        logger.warning(f"[Summary] Fallback reason: {error_note}")

    summary = (
        " ".join(summary_parts)
        or "Meeting transcript processed. Review the action items below."
    )

    return {
        "summary": summary,
        "decisions": decisions,
        "action_items": action_items,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_summary(transcript: str) -> str:
    """
    Legacy-compatible entry point.
    Returns the structured output as a JSON string so existing callers
    that store `summary` as Text still work — they now store richer data.
    """
    result = generate_structured_summary(transcript)
    return json.dumps(result, indent=2)


def generate_structured_summary(transcript: str) -> dict:
    """
    Full pipeline: pre-process → LLM → validate → fallback.

    Returns:
        {
          "summary": str,
          "decisions": [str, ...],
          "action_items": [
            {"task": str, "assignee": str, "deadline": str|None, "confidence_score": float}
          ]
        }
    """
    if not transcript or not transcript.strip():
        return {
            "summary": "No transcript provided.",
            "decisions": [],
            "action_items": [],
        }

    logger.info(f"[Summary] Starting pipeline ({len(transcript)} chars)")

    # Step 1 — Pre-process
    pipeline = run_preprocessing_pipeline(transcript)
    cleaned = pipeline["cleaned_transcript"]

    if not cleaned:
        return _build_fallback(pipeline, "Transcript was empty after cleaning.")

    # Step 2 — LLM call
    try:
        if not _api_key:
            raise EnvironmentError("GEMINI_API_KEY not set")

        client = genai.Client(api_key=_api_key)
        prompt = _build_summary_prompt(
            cleaned,
            pipeline["speakers"],
            pipeline["action_sentences"],
            pipeline["decision_sentences"],
        )

        logger.info("[Summary] Calling Gemini API…")
        response = client.models.generate_content(
            model=_MODEL_NAME,
            contents=prompt,
        )
        raw = response.text.strip()
        logger.info(f"[Summary] Raw response preview: {raw[:300]}")

        # Step 3 — Validate
        result = _parse_llm_response(raw)
        if result:
            logger.info(
                f"[Summary] Success — {len(result['action_items'])} action items, "
                f"{len(result['decisions'])} decisions"
            )
            return result

        logger.warning("[Summary] LLM response failed validation; using fallback")
        return _build_fallback(pipeline, "AI response could not be parsed.")

    except Exception as exc:
        logger.error(f"[Summary] LLM call failed: {exc}. Using fallback.")
        return _build_fallback(pipeline, f"AI unavailable: {type(exc).__name__}")
