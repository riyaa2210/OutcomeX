"""
Analytics Service — AI-Powered Insights
=========================================
Computes:
  - Meeting efficiency score (0-100)
  - Participation imbalance detection
  - Sentiment analysis (positive/neutral/negative)
  - Blocker frequency
  - Repeated discussion topics

Uses Gemini for sentiment + topic analysis.
Falls back to keyword-based analysis if API unavailable.
"""

import json
import logging
import re
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

# ── Sentiment keywords ────────────────────────────────────────────────────────

POSITIVE_WORDS = [
    "great", "excellent", "good", "agree", "approved", "done", "completed",
    "success", "achieved", "resolved", "finalized", "confirmed", "perfect",
    "happy", "excited", "progress", "milestone", "shipped", "launched",
]
NEGATIVE_WORDS = [
    "blocked", "issue", "problem", "failed", "delay", "stuck", "concern",
    "risk", "blocker", "overdue", "missed", "behind", "unclear", "confused",
    "difficult", "challenge", "obstacle", "error", "bug", "broken",
]
BLOCKER_WORDS = [
    "blocked", "blocker", "waiting on", "depends on", "can't proceed",
    "stuck", "need approval", "pending review", "not started yet",
]


# ── Efficiency score ──────────────────────────────────────────────────────────

def compute_efficiency_score(
    total_actions: int,
    completed_actions: int,
    decisions_count: int,
    meeting_count: int,
    overdue_count: int,
) -> dict:
    """
    Efficiency score 0-100 based on:
      - Action completion rate (40%)
      - Decision-to-action ratio (20%)
      - Overdue penalty (20%)
      - Meeting frequency (20%)
    """
    if meeting_count == 0:
        return {"score": 0, "grade": "N/A", "breakdown": {}}

    # Completion rate component (0-40)
    completion_rate = completed_actions / total_actions if total_actions else 0
    completion_score = completion_rate * 40

    # Decision ratio component (0-20)
    d2a = decisions_count / total_actions if total_actions else 0
    d2a_score = min(d2a * 20, 20)

    # Overdue penalty (0-20, inverted)
    overdue_rate = overdue_count / total_actions if total_actions else 0
    overdue_score = max(0, 20 - overdue_rate * 40)

    # Meeting productivity (0-20) — 3-5 meetings/week is optimal
    meetings_per_week = meeting_count / 4  # assume 4-week period
    if 3 <= meetings_per_week <= 5:
        freq_score = 20
    elif meetings_per_week < 1:
        freq_score = 5
    else:
        freq_score = min(20, meetings_per_week * 4)

    total = completion_score + d2a_score + overdue_score + freq_score
    score = round(total, 1)

    grade = "A" if score >= 80 else "B" if score >= 65 else "C" if score >= 50 else "D"

    return {
        "score": score,
        "grade": grade,
        "breakdown": {
            "completion":  round(completion_score, 1),
            "decisions":   round(d2a_score, 1),
            "timeliness":  round(overdue_score, 1),
            "frequency":   round(freq_score, 1),
        },
    }


# ── Sentiment analysis ────────────────────────────────────────────────────────

def _keyword_sentiment(text: str) -> dict:
    """Fast keyword-based sentiment scoring."""
    words = re.findall(r'\w+', text.lower())
    pos = sum(1 for w in words if w in POSITIVE_WORDS)
    neg = sum(1 for w in words if w in NEGATIVE_WORDS)
    total = pos + neg or 1

    pos_pct = round(pos / total * 100)
    neg_pct = round(neg / total * 100)
    neu_pct = 100 - pos_pct - neg_pct

    if pos_pct > neg_pct + 20:
        label = "positive"
    elif neg_pct > pos_pct + 20:
        label = "negative"
    else:
        label = "neutral"

    return {
        "label":    label,
        "positive": pos_pct,
        "neutral":  max(0, neu_pct),
        "negative": neg_pct,
    }


async def _gemini_sentiment(transcripts: list[str]) -> dict:
    """Use Gemini for more accurate sentiment analysis."""
    import os
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key or not transcripts:
        return None

    combined = " ".join(transcripts[:5])[:3000]

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        prompt = f"""Analyze the sentiment of these meeting transcripts.
Return ONLY valid JSON: {{"label": "positive|neutral|negative", "positive": 0-100, "neutral": 0-100, "negative": 0-100, "summary": "one sentence"}}

Transcripts: {combined}"""

        response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
        raw = response.text.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as exc:
        logger.warning(f"[Analytics] Gemini sentiment failed: {exc}")
        return None


# ── Blocker detection ─────────────────────────────────────────────────────────

def _detect_blockers(transcripts: list[str]) -> list[dict]:
    """Find blocker mentions across transcripts."""
    blockers = []
    for transcript in transcripts:
        sentences = re.split(r'[.!?\n]', transcript)
        for sent in sentences:
            lower = sent.lower()
            if any(kw in lower for kw in BLOCKER_WORDS):
                blockers.append(sent.strip()[:200])
    return blockers[:10]  # top 10


# ── Participation imbalance ───────────────────────────────────────────────────

def _detect_imbalance(action_items_by_person: dict) -> dict:
    """
    Detect if one person has disproportionate task load.
    Returns imbalance score 0-100 (100 = perfectly balanced).
    """
    if not action_items_by_person or len(action_items_by_person) < 2:
        return {"score": 100, "alert": None, "distribution": {}}

    values = list(action_items_by_person.values())
    total  = sum(values) or 1
    avg    = total / len(values)
    max_v  = max(values)
    max_person = max(action_items_by_person, key=action_items_by_person.get)

    # Coefficient of variation (lower = more balanced)
    variance = sum((v - avg) ** 2 for v in values) / len(values)
    std_dev  = variance ** 0.5
    cv       = std_dev / avg if avg else 0

    balance_score = max(0, round(100 - cv * 50))

    alert = None
    if max_v / total > 0.5:
        alert = f"{max_person} has {round(max_v/total*100)}% of all tasks — consider redistributing."

    return {
        "score":        balance_score,
        "alert":        alert,
        "distribution": {k: round(v / total * 100, 1) for k, v in action_items_by_person.items()},
    }


# ── Main compute function ─────────────────────────────────────────────────────

async def compute_ai_insights(db: Session, user_id: int, since: datetime) -> dict:
    """
    Compute all AI-powered insights for the analytics dashboard.
    """
    # Fetch raw data
    meetings = db.execute(text("""
        SELECT m.id, m.transcript, m.created_at,
               COUNT(ai.id) AS action_count,
               COUNT(CASE WHEN LOWER(ai.status) IN ('completed','done') THEN 1 END) AS done_count,
               COUNT(CASE WHEN ai.deadline IS NOT NULL
                          AND LOWER(ai.status) NOT IN ('completed','done') THEN 1 END) AS overdue_count
        FROM meetings m
        LEFT JOIN action_items ai ON ai.meeting_id = m.id
        WHERE m.user_id = :uid AND m.created_at >= :since
        GROUP BY m.id
        ORDER BY m.created_at DESC
    """), {"uid": user_id, "since": since}).fetchall()

    if not meetings:
        return {
            "efficiency":   {"score": 0, "grade": "N/A", "breakdown": {}},
            "sentiment":    {"label": "neutral", "positive": 33, "neutral": 34, "negative": 33},
            "blockers":     [],
            "imbalance":    {"score": 100, "alert": None, "distribution": {}},
            "top_topics":   [],
            "total_analyzed": 0,
        }

    # Aggregate counts
    total_actions    = sum(int(m.action_count) for m in meetings)
    completed        = sum(int(m.done_count) for m in meetings)
    overdue          = sum(int(m.overdue_count) for m in meetings)
    meeting_count    = len(meetings)

    # Decisions from results
    from backend.routes.analytics_routes import _count_decisions
    decisions = _count_decisions(db, user_id, since)

    # Efficiency score
    efficiency = compute_efficiency_score(
        total_actions, completed, decisions, meeting_count, overdue
    )

    # Transcripts for NLP
    transcripts = [m.transcript or "" for m in meetings if m.transcript]

    # Sentiment — try Gemini first, fall back to keywords
    combined_text = " ".join(transcripts[:10])
    sentiment = await _gemini_sentiment(transcripts) or _keyword_sentiment(combined_text)

    # Blockers
    blockers = _detect_blockers(transcripts)

    # Action items by person for imbalance
    person_rows = db.execute(text("""
        SELECT ai.assigned_to, COUNT(*) AS cnt
        FROM action_items ai
        JOIN meetings m ON ai.meeting_id = m.id
        WHERE m.user_id = :uid AND m.created_at >= :since
          AND ai.assigned_to IS NOT NULL
        GROUP BY ai.assigned_to
    """), {"uid": user_id, "since": since}).fetchall()

    by_person = {row.assigned_to: int(row.cnt) for row in person_rows if row.assigned_to}
    imbalance = _detect_imbalance(by_person)

    # Top topics (most common nouns/phrases from transcripts)
    top_topics = _extract_top_topics(combined_text)

    return {
        "efficiency":     efficiency,
        "sentiment":      sentiment,
        "blockers":       blockers,
        "imbalance":      imbalance,
        "top_topics":     top_topics,
        "total_analyzed": meeting_count,
    }


def _extract_top_topics(text: str) -> list[dict]:
    """Extract most frequent meaningful words as topics."""
    STOP = {
        "the","a","an","and","or","but","in","on","at","to","for","of","with",
        "is","was","are","were","be","been","have","has","had","will","would",
        "can","could","should","may","might","do","did","does","this","that",
        "we","i","you","he","she","they","it","our","your","their","my",
        "meeting","team","going","think","know","just","also","need","want",
    }
    words = re.findall(r'\b[a-z]{4,}\b', text.lower())
    freq: dict = {}
    for w in words:
        if w not in STOP:
            freq[w] = freq.get(w, 0) + 1

    top = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:10]
    return [{"topic": w, "count": c} for w, c in top]
