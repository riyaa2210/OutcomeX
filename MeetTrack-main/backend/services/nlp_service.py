"""
NLP Service — Multi-step meeting transcript processing pipeline.

Pipeline:
  Step 1: Clean transcript (normalize whitespace, remove filler words)
  Step 2: Detect speakers and segment by speaker turns
  Step 3: Extract key sentences (action-bearing, decision-bearing)
  Step 4: Return cleaned + structured data for downstream LLM calls
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Keyword banks
# ---------------------------------------------------------------------------

ACTION_KEYWORDS = [
    "will", "need to", "needs to", "must", "should",
    "assign", "schedule", "complete", "follow up", "follow-up",
    "prepare", "send", "review", "update", "notify", "confirm",
    "check", "submit", "approve", "create", "fix", "implement",
    "coordinate", "reach out", "set up", "look into", "take care of",
    "handle", "ensure", "make sure", "responsible for",
]

DECISION_KEYWORDS = [
    "decided", "agreed", "approved", "confirmed", "resolved",
    "concluded", "finalized", "chosen", "selected", "voted",
    "consensus", "going with", "we will", "team will", "plan is",
    "moving forward", "going ahead", "signed off",
]

FILLER_WORDS = re.compile(
    r"\b(um+|uh+|hmm+|like|you know|i mean|basically|literally|actually|"
    r"sort of|kind of|right\?|okay\?|so yeah|yeah so)\b",
    re.IGNORECASE,
)

# Speaker turn patterns: "John:", "JOHN:", "[John]", "(John)"
SPEAKER_PATTERN = re.compile(
    r"^(?:\[([^\]]+)\]|\(([^)]+)\)|([A-Z][a-zA-Z\s]{1,30}):)\s*",
)


# ---------------------------------------------------------------------------
# Step 1 — Clean transcript
# ---------------------------------------------------------------------------

def clean_transcript(text: str) -> str:
    """
    Normalize whitespace, strip filler words, and standardise punctuation.
    Returns a cleaner version of the transcript suitable for LLM input.
    """
    if not text or not text.strip():
        return ""

    # Collapse multiple spaces / newlines
    text = re.sub(r"\r\n|\r", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Remove filler words
    text = FILLER_WORDS.sub("", text)

    # Fix spacing around punctuation
    text = re.sub(r"\s+([.,!?;:])", r"\1", text)
    text = re.sub(r"([.,!?;:])(?=[^\s])", r"\1 ", text)

    # Collapse any double-spaces introduced above
    text = re.sub(r"  +", " ", text)

    return text.strip()


# ---------------------------------------------------------------------------
# Step 2 — Speaker detection
# ---------------------------------------------------------------------------

def detect_speakers(text: str) -> dict:
    """
    Detect speaker names from transcript.

    Returns:
        {
          "speakers": ["Alice", "Bob"],
          "segments": [{"speaker": "Alice", "text": "..."}, ...]
        }
    """
    lines = text.split("\n")
    segments = []
    current_speaker: Optional[str] = None
    current_lines: list[str] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        match = SPEAKER_PATTERN.match(line)
        if match:
            # Flush previous speaker block
            if current_lines:
                segments.append({
                    "speaker": current_speaker or "Unknown",
                    "text": " ".join(current_lines).strip(),
                })
                current_lines = []

            # Extract speaker name from whichever group matched
            current_speaker = (match.group(1) or match.group(2) or match.group(3) or "").strip()
            remainder = line[match.end():].strip()
            if remainder:
                current_lines.append(remainder)
        else:
            current_lines.append(line)

    # Flush last block
    if current_lines:
        segments.append({
            "speaker": current_speaker or "Unknown",
            "text": " ".join(current_lines).strip(),
        })

    speakers = list(dict.fromkeys(
        s["speaker"] for s in segments if s["speaker"] != "Unknown"
    ))

    return {"speakers": speakers, "segments": segments}


# ---------------------------------------------------------------------------
# Step 3 — Extract key sentences
# ---------------------------------------------------------------------------

def _split_sentences(text: str) -> list[str]:
    """Split text into sentences."""
    raw = re.split(r"(?<=[.!?])\s+(?=[A-Z\[(\"])|(?<=\n)", text)
    return [s.strip() for s in raw if s.strip()]


def extract_key_sentences(text: str) -> dict:
    """
    Identify action-bearing and decision-bearing sentences.

    Returns:
        {
          "action_sentences": [...],
          "decision_sentences": [...],
          "all_sentences": [...]
        }
    """
    sentences = _split_sentences(text)
    action_sentences = []
    decision_sentences = []

    for sent in sentences:
        lower = sent.lower()
        if any(kw in lower for kw in ACTION_KEYWORDS):
            action_sentences.append(sent)
        if any(kw in lower for kw in DECISION_KEYWORDS):
            decision_sentences.append(sent)

    return {
        "action_sentences": action_sentences,
        "decision_sentences": decision_sentences,
        "all_sentences": sentences,
    }


# ---------------------------------------------------------------------------
# Step 4 — Assign tasks to speakers (regex fallback)
# ---------------------------------------------------------------------------

PERSON_PATTERNS = [
    r"(?:assigned to|assign to|given to|contact|reach out to|tell|ask|notify)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:will|should|needs?\s+to|must)",
]

DATE_PATTERNS = [
    r"\b(?:by|on|before|after|until)\s+((?:today|tomorrow|next\s+(?:week|month|monday|tuesday|wednesday|thursday|friday)|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)))\b",
    r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b",
    r"\b(today|tomorrow|next\s+(?:week|monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b",
]


def _extract_person(text: str) -> Optional[str]:
    for pattern in PERSON_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _extract_deadline(text: str) -> Optional[str]:
    for pattern in DATE_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


# ---------------------------------------------------------------------------
# Public entry point — used by upload_routes.py as a lightweight fallback
# ---------------------------------------------------------------------------

def extract_action_items(transcript: str) -> list[dict]:
    """
    Regex-based action item extraction.
    Used as a fallback when the LLM pipeline is unavailable.
    """
    try:
        logger.info(f"[NLP] Extracting action items from {len(transcript)} chars")
        cleaned = clean_transcript(transcript)
        key = extract_key_sentences(cleaned)
        action_items = []

        for sent in key["action_sentences"]:
            action_items.append({
                "description": sent,
                "assigned_to": _extract_person(sent),
                "deadline": _extract_deadline(sent),
                "status": "Pending",
            })

        logger.info(f"[NLP] Extracted {len(action_items)} action items (regex fallback)")
        return action_items

    except Exception as exc:
        logger.error(f"[NLP] extract_action_items failed: {exc}")
        return []


# ---------------------------------------------------------------------------
# Full pipeline — returns enriched context dict for the LLM
# ---------------------------------------------------------------------------

def run_preprocessing_pipeline(transcript: str) -> dict:
    """
    Run the full pre-processing pipeline on a raw transcript.

    Returns a dict consumed by ai_service / summary_service:
        {
          "cleaned_transcript": str,
          "speakers": [...],
          "segments": [...],
          "action_sentences": [...],
          "decision_sentences": [...],
          "char_count": int,
        }
    """
    if not transcript or not transcript.strip():
        return {
            "cleaned_transcript": "",
            "speakers": [],
            "segments": [],
            "action_sentences": [],
            "decision_sentences": [],
            "char_count": 0,
        }

    cleaned = clean_transcript(transcript)
    speaker_data = detect_speakers(cleaned)
    key_sentences = extract_key_sentences(cleaned)

    return {
        "cleaned_transcript": cleaned,
        "speakers": speaker_data["speakers"],
        "segments": speaker_data["segments"],
        "action_sentences": key_sentences["action_sentences"],
        "decision_sentences": key_sentences["decision_sentences"],
        "char_count": len(cleaned),
    }
