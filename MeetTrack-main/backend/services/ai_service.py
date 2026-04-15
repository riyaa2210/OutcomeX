"""
AI Service — Gemini-powered structured extraction of tasks from meeting text.

Features:
  - Role-based system prompt ("You are a professional meeting analyst…")
  - Strict JSON output with confidence scores per action item
  - Multi-step: pre-process → LLM call → validate → fallback
  - No hallucinations: only extracts information present in the transcript
  - Graceful fallback: returns partial structured output on LLM failure
"""

import os
import json
import re
import logging
from typing import Optional

from google import genai
from google.genai import types
from dotenv import load_dotenv

from backend.services.nlp_service import run_preprocessing_pipeline

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Gemini client setup (new google-genai SDK)
# ---------------------------------------------------------------------------

_api_key = os.getenv("GEMINI_API_KEY", "")
_MODEL_NAME = "gemini-2.0-flash"


def _get_model():
    return genai.Client(api_key=_api_key)


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _build_task_extraction_prompt(
    cleaned_transcript: str,
    speakers: list[str],
    action_sentences: list[str],
) -> str:
    speaker_hint = (
        f"Known speakers in this meeting: {', '.join(speakers)}."
        if speakers
        else "No explicit speaker labels were detected."
    )

    action_hint = (
        "\n".join(f"  - {s}" for s in action_sentences[:20])
        if action_sentences
        else "  (none pre-identified)"
    )

    # Cap transcript to avoid token overflow
    transcript_excerpt = cleaned_transcript[:4000]

    return f"""You are a professional meeting analyst working for a Fortune 500 company.
Your job is to extract ONLY the action items that are explicitly stated or strongly implied in the transcript below.

{speaker_hint}

Pre-identified action-bearing sentences (use as hints, not as the only source):
{action_hint}

Rules you MUST follow:
1. Extract ONLY information present in the transcript. Do NOT invent tasks, names, or dates.
2. Each action item must have a clear, concise task description (one sentence, active voice).
3. Assign the task to the speaker or person mentioned. Use "Unassigned" only if truly unknown.
4. Deadline must be in YYYY-MM-DD format if a date is mentioned, otherwise null.
5. confidence_score: a float 0.0–1.0 reflecting how certain you are this is a real action item.
   - 1.0 = explicitly stated ("John will send the report by Friday")
   - 0.7 = strongly implied ("We need someone to review the budget")
   - 0.4 = weakly implied
6. Return ONLY a valid JSON array. No markdown, no code fences, no explanations.
7. Return [] if no action items are found.

Output schema (strict):
[
  {{
    "task": "concise action description",
    "assignee": "person name or Unassigned",
    "deadline": "YYYY-MM-DD or null",
    "confidence_score": 0.0
  }}
]

Transcript:
{transcript_excerpt}

Return ONLY the JSON array:"""


# ---------------------------------------------------------------------------
# Output validation
# ---------------------------------------------------------------------------

def _validate_task_item(item: dict) -> Optional[dict]:
    """
    Validate and normalise a single task dict.
    Returns None if the item is malformed beyond repair.
    """
    if not isinstance(item, dict):
        return None

    task = str(item.get("task") or item.get("task_description") or "").strip()
    if not task:
        return None

    assignee = str(item.get("assignee") or item.get("person_name") or "Unassigned").strip()
    deadline = item.get("deadline") or item.get("due_date") or None

    # Normalise deadline
    if deadline:
        deadline = str(deadline).strip()
        # Accept only YYYY-MM-DD or null
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", deadline):
            deadline = None

    raw_score = item.get("confidence_score", 0.8)
    try:
        score = round(float(raw_score), 2)
        score = max(0.0, min(1.0, score))
    except (TypeError, ValueError):
        score = 0.8

    return {
        "task": task,
        "assignee": assignee,
        "deadline": deadline,
        "confidence_score": score,
    }


def _parse_llm_response(raw: str) -> list[dict]:
    """
    Parse raw LLM text into a validated list of task dicts.
    Strips markdown fences if present.
    """
    cleaned = raw.strip()
    # Strip ```json ... ``` or ``` ... ```
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.warning(f"[AI] JSON decode failed: {exc}. Attempting partial extraction.")
        # Try to extract the first JSON array from the text
        array_match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if array_match:
            try:
                data = json.loads(array_match.group())
            except json.JSONDecodeError:
                return []
        else:
            return []

    if not isinstance(data, list):
        data = [data]

    validated = []
    for item in data:
        result = _validate_task_item(item)
        if result:
            validated.append(result)

    return validated


# ---------------------------------------------------------------------------
# Regex-based email extraction (fallback enrichment)
# ---------------------------------------------------------------------------

def _extract_emails(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)


def _enrich_with_emails(tasks: list[dict], transcript: str) -> list[dict]:
    """
    Attach emails found in the transcript to tasks whose assignee name
    appears near an email address.
    """
    emails = _extract_emails(transcript)
    if not emails:
        return tasks

    for task in tasks:
        assignee = task.get("assignee", "")
        if not assignee or assignee == "Unassigned":
            continue
        first_name = assignee.split()[0].lower()
        for email in emails:
            if first_name in email.lower():
                task["email"] = email
                break

    return tasks


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_tasks(meeting_text: str) -> list[dict]:
    """
    Extract structured action items from meeting text using Gemini AI.

    Pipeline:
      1. Pre-process transcript (clean, detect speakers, extract key sentences)
      2. Build role-based prompt with context hints
      3. Call Gemini API
      4. Validate and normalise output
      5. Enrich with emails from transcript
      6. Fallback to regex extraction if LLM fails

    Returns:
        List of dicts:
        [{"task": str, "assignee": str, "deadline": str|None,
          "confidence_score": float, "email": str|None}, ...]
    """
    if not meeting_text or not meeting_text.strip():
        logger.warning("[AI] Empty meeting text provided")
        return []

    logger.info(f"[AI] Starting task extraction ({len(meeting_text)} chars)")

    # Step 1 — Pre-process
    pipeline = run_preprocessing_pipeline(meeting_text)
    cleaned = pipeline["cleaned_transcript"]
    speakers = pipeline["speakers"]
    action_sentences = pipeline["action_sentences"]

    # Step 2 & 3 — LLM call
    try:
        if not _api_key:
            raise EnvironmentError("GEMINI_API_KEY not set")

        client = _get_model()
        prompt = _build_task_extraction_prompt(cleaned, speakers, action_sentences)

        logger.info("[AI] Calling Gemini API for task extraction…")
        response = client.models.generate_content(
            model=_MODEL_NAME,
            contents=prompt,
        )
        raw = response.text.strip()
        logger.info(f"[AI] Raw response preview: {raw[:200]}")

        # Step 4 — Validate
        tasks = _parse_llm_response(raw)
        logger.info(f"[AI] Validated {len(tasks)} tasks from LLM")

        # Step 5 — Enrich with emails
        tasks = _enrich_with_emails(tasks, meeting_text)

        if not tasks:
            logger.warning("[AI] LLM returned no valid tasks; falling back to regex")
            return _regex_fallback(pipeline)

        return tasks

    except Exception as exc:
        logger.error(f"[AI] LLM extraction failed: {exc}. Using regex fallback.")
        return _regex_fallback(pipeline)


def _regex_fallback(pipeline: dict) -> list[dict]:
    """
    Build a partial structured output from pre-processed NLP data
    when the LLM is unavailable or returns nothing useful.
    """
    from backend.services.nlp_service import _extract_person, _extract_deadline

    fallback_tasks = []
    for sent in pipeline.get("action_sentences", []):
        fallback_tasks.append({
            "task": sent,
            "assignee": _extract_person(sent) or "Unassigned",
            "deadline": _extract_deadline(sent),
            "confidence_score": 0.5,  # lower confidence for regex-only
        })

    logger.info(f"[AI] Regex fallback produced {len(fallback_tasks)} tasks")
    return fallback_tasks
