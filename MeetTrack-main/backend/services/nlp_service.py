"""
Advanced NLP + AI Hybrid Pipeline
===================================
Multi-pass extraction replacing the old regex-only approach.

Pipeline:
  Pass 1 — Transcript cleaning + speaker segmentation
  Pass 2 — spaCy NER + dependency parsing (candidate extraction)
  Pass 3 — Rule-based implicit task detection
  Pass 4 — Gemini validation + structured JSON generation
  Pass 5 — Semantic deduplication + confidence scoring
  Pass 6 — Evaluation logging

spaCy model: en_core_web_sm (lightweight, no GPU needed)
Falls back gracefully if spaCy not installed.

Detects:
  - Assignees (PERSON entities + subject-verb patterns)
  - Deadlines (DATE/TIME entities + temporal expressions)
  - Priorities (HIGH/MEDIUM/LOW from urgency keywords)
  - Blockers ("blocked by", "waiting on", "depends on")
  - Project names (ORG entities + capitalized noun phrases)
  - Implicit tasks ("we should", "someone needs to", "let's")
"""

import re
import logging
import hashlib
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# ── spaCy lazy loader ─────────────────────────────────────────────────────────

_nlp = None

def _get_nlp():
    """Lazy-load spaCy model. Falls back to None if not installed."""
    global _nlp
    if _nlp is not None:
        return _nlp
    try:
        import spacy
        try:
            _nlp = spacy.load("en_core_web_sm")
            logger.info("[NLP] spaCy en_core_web_sm loaded")
        except OSError:
            # Model not downloaded — try downloading
            try:
                from spacy.cli import download
                download("en_core_web_sm")
                _nlp = spacy.load("en_core_web_sm")
                logger.info("[NLP] spaCy model downloaded and loaded")
            except Exception as e:
                logger.warning(f"[NLP] Could not load spaCy model: {e} — using regex fallback")
                _nlp = False   # sentinel: tried but failed
    except ImportError:
        logger.warning("[NLP] spaCy not installed — using regex fallback")
        _nlp = False
    return _nlp


# ── Keyword banks ─────────────────────────────────────────────────────────────

ACTION_KEYWORDS = [
    "will", "need to", "needs to", "must", "should",
    "assign", "schedule", "complete", "follow up", "follow-up",
    "prepare", "send", "review", "update", "notify", "confirm",
    "check", "submit", "approve", "create", "fix", "implement",
    "coordinate", "reach out", "set up", "look into", "take care of",
    "handle", "ensure", "make sure", "responsible for", "going to",
    "planning to", "intend to", "committed to",
]

IMPLICIT_TASK_PATTERNS = [
    r"\bwe should\b",
    r"\bsomeone (?:needs?|should|must|has) to\b",
    r"\blet'?s\b.{3,50}\b(?:by|before|until)\b",
    r"\bwe need to\b",
    r"\bit would be good to\b",
    r"\bwe(?:'re| are) going to\b",
    r"\bteam (?:should|needs? to|will)\b",
    r"\bdon'?t forget to\b",
    r"\bmake sure (?:to|that)\b",
    r"\bremember to\b",
    r"\baction item[:\s]",
    r"\btodo[:\s]",
    r"\bfollow.?up[:\s]",
]

DECISION_KEYWORDS = [
    "decided", "agreed", "approved", "confirmed", "resolved",
    "concluded", "finalized", "chosen", "selected", "voted",
    "consensus", "going with", "we will", "team will", "plan is",
    "moving forward", "going ahead", "signed off",
]

PRIORITY_HIGH   = ["urgent", "asap", "immediately", "critical", "blocker", "p0", "p1", "high priority"]
PRIORITY_MEDIUM = ["soon", "this week", "next sprint", "medium priority", "p2"]
PRIORITY_LOW    = ["eventually", "nice to have", "low priority", "backlog", "p3", "p4"]

BLOCKER_PATTERNS = [
    r"blocked by\s+(.+?)(?:\.|$)",
    r"waiting (?:on|for)\s+(.+?)(?:\.|$)",
    r"depends? on\s+(.+?)(?:\.|$)",
    r"can'?t proceed (?:until|without)\s+(.+?)(?:\.|$)",
]

FILLER_WORDS = re.compile(
    r"\b(um+|uh+|hmm+|like|you know|i mean|basically|literally|actually|"
    r"sort of|kind of|right\?|okay\?|so yeah|yeah so)\b",
    re.IGNORECASE,
)

SPEAKER_PATTERN = re.compile(
    r"^(?:\[([^\]]+)\]|\(([^)]+)\)|([A-Z][a-zA-Z\s]{1,30}):)\s*",
)

PERSON_PATTERNS = [
    r"(?:assigned to|assign to|given to|contact|reach out to|tell|ask|notify)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:will|should|needs?\s+to|must|is going to)",
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:to|can)\s+(?:handle|take care of|own|lead)",
]

DATE_PATTERNS = [
    r"\b(?:by|on|before|after|until|due)\s+((?:today|tomorrow|next\s+(?:week|month|monday|tuesday|wednesday|thursday|friday)|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|end of (?:day|week|month|sprint)))\b",
    r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b",
    r"\b(today|tomorrow|next\s+(?:week|monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b",
    r"\b(end of (?:day|week|month|sprint|quarter))\b",
    r"\b(this (?:friday|monday|tuesday|wednesday|thursday))\b",
]


# ═══════════════════════════════════════════════════════════════════════════════
# PASS 1 — Transcript cleaning
# ═══════════════════════════════════════════════════════════════════════════════

def clean_transcript(text: str) -> str:
    if not text or not text.strip():
        return ""
    text = re.sub(r"\r\n|\r", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = FILLER_WORDS.sub("", text)
    text = re.sub(r"\s+([.,!?;:])", r"\1", text)
    text = re.sub(r"([.,!?;:])(?=[^\s])", r"\1 ", text)
    text = re.sub(r"  +", " ", text)
    return text.strip()


# ═══════════════════════════════════════════════════════════════════════════════
# PASS 2 — Speaker detection + segmentation
# ═══════════════════════════════════════════════════════════════════════════════

def detect_speakers(text: str) -> dict:
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
            if current_lines:
                segments.append({
                    "speaker": current_speaker or "Unknown",
                    "text": " ".join(current_lines).strip(),
                })
                current_lines = []
            current_speaker = (match.group(1) or match.group(2) or match.group(3) or "").strip()
            remainder = line[match.end():].strip()
            if remainder:
                current_lines.append(remainder)
        else:
            current_lines.append(line)

    if current_lines:
        segments.append({
            "speaker": current_speaker or "Unknown",
            "text": " ".join(current_lines).strip(),
        })

    speakers = list(dict.fromkeys(
        s["speaker"] for s in segments if s["speaker"] != "Unknown"
    ))
    return {"speakers": speakers, "segments": segments}


# ═══════════════════════════════════════════════════════════════════════════════
# PASS 3 — spaCy NER + dependency parsing
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_with_spacy(sentence: str, speaker: Optional[str] = None) -> dict:
    """
    Use spaCy to extract:
      - PERSON entities (assignees)
      - DATE/TIME entities (deadlines)
      - ORG entities (project names)
      - Subject of action verbs (implicit assignee)
    Returns enriched candidate dict.
    """
    nlp = _get_nlp()
    result = {
        "persons":      [],
        "dates":        [],
        "orgs":         [],
        "dep_assignee": None,
        "spacy_used":   False,
    }

    if not nlp:
        return result

    try:
        doc = nlp(sentence[:500])   # cap for performance
        result["spacy_used"] = True

        for ent in doc.ents:
            if ent.label_ == "PERSON":
                result["persons"].append(ent.text)
            elif ent.label_ in ("DATE", "TIME"):
                result["dates"].append(ent.text)
            elif ent.label_ == "ORG":
                result["orgs"].append(ent.text)

        # Dependency parsing: find subject of action verbs
        for token in doc:
            if token.dep_ in ("nsubj", "nsubjpass") and token.head.pos_ == "VERB":
                if token.ent_type_ == "PERSON" or token.text[0].isupper():
                    result["dep_assignee"] = token.text
                    break

    except Exception as exc:
        logger.debug(f"[NLP] spaCy parse error: {exc}")

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# PASS 4 — Implicit task detection
# ═══════════════════════════════════════════════════════════════════════════════

def _is_implicit_task(sentence: str) -> tuple[bool, float]:
    """
    Detect implicit tasks like "We should finish auth by Friday".
    Returns (is_task, confidence_boost).
    """
    lower = sentence.lower()
    for pattern in IMPLICIT_TASK_PATTERNS:
        if re.search(pattern, lower):
            return True, 0.15
    return False, 0.0


def _detect_priority(sentence: str) -> str:
    lower = sentence.lower()
    if any(kw in lower for kw in PRIORITY_HIGH):
        return "HIGH"
    if any(kw in lower for kw in PRIORITY_MEDIUM):
        return "MEDIUM"
    if any(kw in lower for kw in PRIORITY_LOW):
        return "LOW"
    return "MEDIUM"


def _detect_blocker(sentence: str) -> Optional[str]:
    for pattern in BLOCKER_PATTERNS:
        match = re.search(pattern, sentence, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# PASS 5 — Confidence scoring
# ═══════════════════════════════════════════════════════════════════════════════

def _score_candidate(
    sentence: str,
    has_assignee: bool,
    has_deadline: bool,
    has_action_verb: bool,
    is_implicit: bool,
    spacy_person: bool,
    speaker: Optional[str],
) -> float:
    """
    Multi-factor confidence score (0.0 – 1.0).

    Factors:
      - Has explicit action verb:    +0.25
      - Has assignee (regex):        +0.20
      - Has assignee (spaCy NER):    +0.10 bonus
      - Has deadline:                +0.20
      - Is implicit task:            +0.15
      - Has speaker context:         +0.10
      - Sentence length (5-30 words): +0.05
    """
    score = 0.0
    if has_action_verb:  score += 0.25
    if has_assignee:     score += 0.20
    if spacy_person:     score += 0.10
    if has_deadline:     score += 0.20
    if is_implicit:      score += 0.15
    if speaker:          score += 0.10
    words = len(sentence.split())
    if 5 <= words <= 30: score += 0.05
    return round(min(score, 1.0), 3)


# ═══════════════════════════════════════════════════════════════════════════════
# PASS 6 — Semantic deduplication
# ═══════════════════════════════════════════════════════════════════════════════

def _deduplicate(candidates: list[dict]) -> list[dict]:
    """
    Remove near-duplicate action items using:
      1. Exact text hash
      2. Normalized text similarity (Jaccard on word sets)
    """
    seen_hashes: set[str] = set()
    seen_word_sets: list[set] = []
    unique = []

    for c in candidates:
        text = c.get("description", "").strip().lower()
        if not text:
            continue

        # Exact hash
        h = hashlib.md5(text.encode()).hexdigest()
        if h in seen_hashes:
            continue
        seen_hashes.add(h)

        # Jaccard similarity
        words = set(re.findall(r'\w+', text))
        is_dup = False
        for existing_words in seen_word_sets:
            if not words or not existing_words:
                continue
            jaccard = len(words & existing_words) / len(words | existing_words)
            if jaccard > 0.75:   # 75% word overlap = duplicate
                is_dup = True
                break

        if not is_dup:
            seen_word_sets.append(words)
            unique.append(c)

    return unique


# ═══════════════════════════════════════════════════════════════════════════════
# PASS 7 — Evaluation logging
# ═══════════════════════════════════════════════════════════════════════════════

def _log_extraction_eval(candidates: list[dict], transcript_len: int) -> None:
    """Log extraction metrics for monitoring false positive/negative rates."""
    high_conf   = sum(1 for c in candidates if c.get("confidence", 0) >= 0.7)
    medium_conf = sum(1 for c in candidates if 0.4 <= c.get("confidence", 0) < 0.7)
    low_conf    = sum(1 for c in candidates if c.get("confidence", 0) < 0.4)
    spacy_used  = sum(1 for c in candidates if c.get("spacy_used", False))

    logger.info(
        f"[NLP] Extraction eval — total={len(candidates)} "
        f"high={high_conf} medium={medium_conf} low={low_conf} "
        f"spacy_enhanced={spacy_used} "
        f"transcript_chars={transcript_len}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS (used by ai_service fallback)
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_person(text: str) -> Optional[str]:
    # Try spaCy first
    spacy_data = _extract_with_spacy(text)
    if spacy_data["persons"]:
        return spacy_data["persons"][0]
    if spacy_data["dep_assignee"]:
        return spacy_data["dep_assignee"]
    # Regex fallback
    for pattern in PERSON_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _extract_deadline(text: str) -> Optional[str]:
    # Try spaCy first
    spacy_data = _extract_with_spacy(text)
    if spacy_data["dates"]:
        return spacy_data["dates"][0]
    # Regex fallback
    for pattern in DATE_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API — extract_action_items (multi-pass hybrid)
# ═══════════════════════════════════════════════════════════════════════════════

def extract_action_items(transcript: str) -> list[dict]:
    """
    Advanced multi-pass action item extraction.

    Pass 1: Clean transcript
    Pass 2: Detect speakers + segment
    Pass 3: spaCy NER + dependency parsing per sentence
    Pass 4: Implicit task detection
    Pass 5: Confidence scoring
    Pass 6: Semantic deduplication
    Pass 7: Evaluation logging

    Returns list of enriched action item dicts.
    """
    try:
        logger.info(f"[NLP] Starting multi-pass extraction ({len(transcript)} chars)")

        # Pass 1 — Clean
        cleaned = clean_transcript(transcript)
        if not cleaned:
            return []

        # Pass 2 — Speaker segments
        speaker_data = detect_speakers(cleaned)
        segments     = speaker_data["segments"]

        # Build sentence list with speaker context
        sentences_with_context = []
        for seg in segments:
            for sent in _split_sentences(seg["text"]):
                sentences_with_context.append({
                    "text":    sent,
                    "speaker": seg.get("speaker"),
                })

        # If no segments, fall back to plain sentences
        if not sentences_with_context:
            for sent in _split_sentences(cleaned):
                sentences_with_context.append({"text": sent, "speaker": None})

        candidates = []

        for item in sentences_with_context:
            sent    = item["text"]
            speaker = item["speaker"]
            lower   = sent.lower()

            # Check action keywords
            has_action_verb = any(kw in lower for kw in ACTION_KEYWORDS)

            # Pass 4 — Implicit task detection
            is_implicit, implicit_boost = _is_implicit_task(sent)

            if not has_action_verb and not is_implicit:
                continue

            # Pass 3 — spaCy enrichment
            spacy_data = _extract_with_spacy(sent, speaker)

            # Assignee resolution: spaCy > regex > speaker
            assignee = None
            if spacy_data["persons"]:
                assignee = spacy_data["persons"][0]
            elif spacy_data["dep_assignee"]:
                assignee = spacy_data["dep_assignee"]
            else:
                assignee = _extract_person(sent)
            if not assignee and speaker and speaker != "Unknown":
                assignee = speaker

            # Deadline resolution: spaCy > regex
            deadline = None
            if spacy_data["dates"]:
                deadline = spacy_data["dates"][0]
            else:
                deadline = _extract_deadline(sent)

            # Pass 5 — Confidence scoring
            confidence = _score_candidate(
                sentence       = sent,
                has_assignee   = bool(assignee),
                has_deadline   = bool(deadline),
                has_action_verb= has_action_verb,
                is_implicit    = is_implicit,
                spacy_person   = bool(spacy_data["persons"] or spacy_data["dep_assignee"]),
                speaker        = speaker,
            )

            # Skip very low confidence items
            if confidence < 0.25:
                continue

            candidates.append({
                "description":  sent,
                "assigned_to":  assignee or "Unassigned",
                "deadline":     deadline,
                "status":       "Pending",
                "priority":     _detect_priority(sent),
                "blocker":      _detect_blocker(sent),
                "project":      spacy_data["orgs"][0] if spacy_data["orgs"] else None,
                "confidence":   confidence,
                "is_implicit":  is_implicit,
                "speaker":      speaker,
                "spacy_used":   spacy_data["spacy_used"],
                "extraction_method": "spacy+hybrid" if spacy_data["spacy_used"] else "regex",
            })

        # Pass 6 — Deduplicate
        unique = _deduplicate(candidates)

        # Sort by confidence descending
        unique.sort(key=lambda x: x["confidence"], reverse=True)

        # Pass 7 — Evaluation log
        _log_extraction_eval(unique, len(transcript))

        logger.info(f"[NLP] Extracted {len(unique)} unique action items")
        return unique

    except Exception as exc:
        logger.error(f"[NLP] extract_action_items failed: {exc}")
        return []


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API — run_preprocessing_pipeline (unchanged interface)
# ═══════════════════════════════════════════════════════════════════════════════

def _split_sentences(text: str) -> list[str]:
    """Split text into sentences using spaCy if available, else regex."""
    nlp = _get_nlp()
    if nlp:
        try:
            doc = nlp(text[:5000])
            return [s.text.strip() for s in doc.sents if s.text.strip()]
        except Exception:
            pass
    raw = re.split(r"(?<=[.!?])\s+(?=[A-Z\[(\"])|(?<=\n)", text)
    return [s.strip() for s in raw if s.strip()]


def extract_key_sentences(text: str) -> dict:
    sentences = _split_sentences(text)
    action_sentences   = []
    decision_sentences = []

    for sent in sentences:
        lower = sent.lower()
        is_implicit, _ = _is_implicit_task(sent)
        if any(kw in lower for kw in ACTION_KEYWORDS) or is_implicit:
            action_sentences.append(sent)
        if any(kw in lower for kw in DECISION_KEYWORDS):
            decision_sentences.append(sent)

    return {
        "action_sentences":   action_sentences,
        "decision_sentences": decision_sentences,
        "all_sentences":      sentences,
    }


def run_preprocessing_pipeline(transcript: str) -> dict:
    """
    Full pre-processing pipeline — unchanged interface for ai_service/summary_service.
    Now enhanced with spaCy NER and implicit task detection.
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

    cleaned      = clean_transcript(transcript)
    speaker_data = detect_speakers(cleaned)
    key_sentences = extract_key_sentences(cleaned)

    return {
        "cleaned_transcript": cleaned,
        "speakers":           speaker_data["speakers"],
        "segments":           speaker_data["segments"],
        "action_sentences":   key_sentences["action_sentences"],
        "decision_sentences": key_sentences["decision_sentences"],
        "char_count":         len(cleaned),
    }
