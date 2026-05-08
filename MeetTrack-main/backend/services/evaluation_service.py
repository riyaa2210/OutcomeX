"""
Evaluation Service
==================
Core evaluation pipeline for AI output quality.

Evaluates every meeting output on 6 dimensions:
  1. Summary quality      — coherence, length, coverage
  2. Decision accuracy    — grounded in transcript, no fabrication
  3. Action precision     — valid tasks, real assignees, real deadlines
  4. Hallucination score  — names/dates not in source
  5. Groundedness         — word overlap with transcript
  6. Completeness         — key topics covered

Also:
  - Computes precision/recall/F1 vs human corrections
  - Detects unsupported claims, fabricated deadlines, incorrect assignees
  - Applies iterative prompt refinement based on feedback patterns
  - Generates automated evaluation reports
"""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.models.evaluation import EvalResult, HumanFeedback, BenchmarkSample
from backend.models.meeting import Meeting
from backend.services.llm.quality import detect_hallucinations

logger = logging.getLogger(__name__)


# ── Scoring helpers ───────────────────────────────────────────────────────────

def _summary_quality(summary: str, transcript: str) -> float:
    """
    Score summary quality:
      - Length: 50–500 chars is ideal
      - Sentence count: 2–5 sentences
      - Groundedness: word overlap with transcript
      - No repetition
    """
    if not summary:
        return 0.0

    # Length score
    length = len(summary)
    if 80 <= length <= 600:
        length_score = 1.0
    elif length < 30:
        length_score = 0.2
    elif length < 80:
        length_score = 0.6
    else:
        length_score = 0.7  # too long

    # Sentence count
    sentences = [s.strip() for s in re.split(r'[.!?]', summary) if len(s.strip()) > 10]
    sent_score = 1.0 if 2 <= len(sentences) <= 6 else 0.6

    # Groundedness
    s_words = set(re.findall(r'\b[a-z]{4,}\b', summary.lower()))
    t_words = set(re.findall(r'\b[a-z]{4,}\b', transcript.lower()))
    ground  = len(s_words & t_words) / max(len(s_words), 1)
    ground_score = min(1.0, ground * 1.5)

    # Repetition penalty
    words = summary.lower().split()
    unique_ratio = len(set(words)) / max(len(words), 1)
    rep_score = 1.0 if unique_ratio > 0.6 else 0.5

    return round((length_score * 0.2 + sent_score * 0.2 + ground_score * 0.4 + rep_score * 0.2), 3)


def _decision_accuracy(decisions: list[str], transcript: str) -> float:
    """
    Score decision accuracy:
      - Each decision should be grounded in transcript
      - No fabricated decisions
    """
    if not decisions:
        return 0.5  # neutral — no decisions is valid

    t_lower = transcript.lower()
    grounded = 0
    for dec in decisions:
        words = re.findall(r'\b[a-z]{4,}\b', dec.lower())
        if not words:
            continue
        overlap = sum(1 for w in words if w in t_lower) / len(words)
        if overlap >= 0.4:
            grounded += 1

    return round(grounded / len(decisions), 3)


def _action_precision(action_items: list[dict], transcript: str) -> float:
    """
    Score action item precision:
      - Task description grounded in transcript
      - Assignee name appears in transcript (or is "Unassigned")
      - Deadline is plausible (not fabricated)
      - Confidence score is reasonable
    """
    if not action_items:
        return 0.5

    t_lower = transcript.lower()
    scores  = []

    for item in action_items:
        task     = str(item.get("task", "")).lower()
        assignee = str(item.get("assignee", "Unassigned"))
        deadline = item.get("deadline")
        conf     = float(item.get("confidence_score", 0.5))

        # Task groundedness
        task_words = re.findall(r'\b[a-z]{4,}\b', task)
        task_ground = (
            sum(1 for w in task_words if w in t_lower) / len(task_words)
            if task_words else 0.5
        )

        # Assignee check
        if assignee.lower() == "unassigned":
            assignee_score = 0.8  # acceptable
        else:
            assignee_score = 1.0 if assignee.lower() in t_lower else 0.3

        # Deadline check — if present, must appear in transcript
        if deadline:
            # Check if any date-like string from transcript matches
            date_in_transcript = bool(re.search(
                r'\b' + re.escape(str(deadline)) + r'\b', transcript, re.IGNORECASE
            ))
            deadline_score = 1.0 if date_in_transcript else 0.4
        else:
            deadline_score = 1.0  # null deadline is fine

        # Confidence calibration
        conf_score = 1.0 if 0.4 <= conf <= 1.0 else 0.5

        item_score = (task_ground * 0.4 + assignee_score * 0.3 + deadline_score * 0.2 + conf_score * 0.1)
        scores.append(item_score)

    return round(sum(scores) / len(scores), 3)


def _detect_unsupported_claims(summary: str, transcript: str) -> list[str]:
    """Find sentences in summary that have low overlap with transcript."""
    sentences = [s.strip() for s in re.split(r'[.!?]', summary) if len(s.strip()) > 20]
    t_words   = set(re.findall(r'\b[a-z]{4,}\b', transcript.lower()))
    unsupported = []

    for sent in sentences:
        s_words = set(re.findall(r'\b[a-z]{4,}\b', sent.lower()))
        if not s_words:
            continue
        overlap = len(s_words & t_words) / len(s_words)
        if overlap < 0.25:
            unsupported.append(sent[:200])

    return unsupported[:5]


def _detect_fabricated_deadlines(action_items: list[dict], transcript: str) -> list[str]:
    """Find deadlines in action items that don't appear in the transcript."""
    fabricated = []
    for item in action_items:
        deadline = item.get("deadline")
        if not deadline:
            continue
        # Check if the date or any part of it appears in transcript
        if not re.search(re.escape(str(deadline)), transcript, re.IGNORECASE):
            # Also check for natural language equivalents
            year = str(deadline)[:4] if len(str(deadline)) >= 4 else ""
            if year and year not in transcript:
                fabricated.append(f"{item.get('task', '?')[:60]} → deadline: {deadline}")
    return fabricated[:5]


def _detect_incorrect_assignees(action_items: list[dict], transcript: str) -> list[str]:
    """Find assignees that don't appear in the transcript."""
    incorrect = []
    for item in action_items:
        assignee = str(item.get("assignee", "Unassigned"))
        if assignee.lower() in ("unassigned", "unknown", ""):
            continue
        # Check first name at minimum
        first_name = assignee.split()[0].lower()
        if len(first_name) >= 3 and first_name not in transcript.lower():
            incorrect.append(f"{item.get('task', '?')[:60]} → assignee: {assignee}")
    return incorrect[:5]


# ── Precision / Recall ────────────────────────────────────────────────────────

def _jaccard(a: str, b: str) -> float:
    wa = set(re.findall(r'\b[a-z]{3,}\b', a.lower()))
    wb = set(re.findall(r'\b[a-z]{3,}\b', b.lower()))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def compute_precision_recall(
    predicted: list[dict],
    ground_truth: list[dict],
    threshold: float = 0.5,
) -> dict:
    """
    Compute precision, recall, F1 for action item extraction.
    Two items match if their task descriptions have Jaccard ≥ threshold.
    """
    if not predicted and not ground_truth:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    if not predicted:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    if not ground_truth:
        return {"precision": 0.0, "recall": 1.0, "f1": 0.0}

    matched_pred = set()
    matched_gt   = set()

    for i, pred in enumerate(predicted):
        for j, gt in enumerate(ground_truth):
            if j in matched_gt:
                continue
            sim = _jaccard(
                str(pred.get("task", "")),
                str(gt.get("task", "")),
            )
            if sim >= threshold:
                matched_pred.add(i)
                matched_gt.add(j)
                break

    tp        = len(matched_pred)
    precision = tp / len(predicted)
    recall    = tp / len(ground_truth)
    f1        = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    return {
        "precision": round(precision, 3),
        "recall":    round(recall, 3),
        "f1":        round(f1, 3),
        "tp":        tp,
        "fp":        len(predicted) - tp,
        "fn":        len(ground_truth) - tp,
    }


# ── Main evaluation pipeline ──────────────────────────────────────────────────

def evaluate_meeting_output(
    db: Session,
    meeting_id: int,
    transcript: str,
    summary: str,
    decisions: list[str],
    action_items: list[dict],
    provider: str = "unknown",
    model: str = "unknown",
    user_id: Optional[int] = None,
    prompt_version: str = "v1",
) -> EvalResult:
    """
    Run the full automated evaluation pipeline for a meeting's AI output.
    Creates/updates an EvalResult row.
    """
    logger.info(f"[Eval] Evaluating meeting={meeting_id} provider={provider}")

    # ── Dimension scores ──────────────────────────────────────────────────
    summary_score   = _summary_quality(summary, transcript)
    decision_score  = _decision_accuracy(decisions, transcript)
    action_score    = _action_precision(action_items, transcript)

    # Hallucination
    hall = detect_hallucinations(
        response_text=f"{summary} {' '.join(decisions)} {' '.join(str(a.get('task','')) for a in action_items)}",
        source_text=transcript,
    )
    hall_score = hall["hallucination_risk"]

    # Groundedness (summary vs transcript)
    s_words = set(re.findall(r'\b[a-z]{4,}\b', summary.lower()))
    t_words = set(re.findall(r'\b[a-z]{4,}\b', transcript.lower()))
    ground_score = round(min(1.0, len(s_words & t_words) / max(len(s_words), 1) * 1.5), 3)

    # Completeness — key NLP sentences covered
    from backend.services.nlp_service import run_preprocessing_pipeline
    pipeline = run_preprocessing_pipeline(transcript)
    key_sents = pipeline.get("action_sentences", []) + pipeline.get("decision_sentences", [])
    if key_sents:
        covered = sum(
            1 for ks in key_sents
            if any(
                _jaccard(ks, str(a.get("task", ""))) > 0.3
                or _jaccard(ks, d) > 0.3
                for a in action_items
                for d in decisions
            )
        )
        completeness_score = round(covered / len(key_sents), 3)
    else:
        completeness_score = 0.8

    # ── Weighted overall score ────────────────────────────────────────────
    overall = round(
        summary_score   * 0.25 +
        decision_score  * 0.20 +
        action_score    * 0.25 +
        (1 - hall_score) * 0.15 +
        ground_score    * 0.10 +
        completeness_score * 0.05,
        3,
    )

    # ── Hallucination detail ──────────────────────────────────────────────
    unsupported   = _detect_unsupported_claims(summary, transcript)
    fab_deadlines = _detect_fabricated_deadlines(action_items, transcript)
    bad_assignees = _detect_incorrect_assignees(action_items, transcript)

    # ── Low-confidence items ──────────────────────────────────────────────
    low_conf = sum(1 for a in action_items if float(a.get("confidence_score", 1.0)) < 0.5)

    # ── Upsert EvalResult ─────────────────────────────────────────────────
    existing = db.query(EvalResult).filter(EvalResult.meeting_id == meeting_id).first()
    if existing:
        ev = existing
    else:
        ev = EvalResult(meeting_id=meeting_id)
        db.add(ev)

    ev.user_id                  = user_id
    ev.provider                 = provider
    ev.model                    = model
    ev.summary_quality_score    = summary_score
    ev.decision_accuracy_score  = decision_score
    ev.action_precision_score   = action_score
    ev.hallucination_score      = hall_score
    ev.groundedness_score       = ground_score
    ev.completeness_score       = completeness_score
    ev.overall_score            = overall
    ev.flagged_terms            = hall.get("flagged_terms", [])
    ev.unsupported_claims       = unsupported
    ev.fabricated_deadlines     = fab_deadlines
    ev.incorrect_assignees      = bad_assignees
    ev.action_items_count       = len(action_items)
    ev.decisions_count          = len(decisions)
    ev.low_confidence_items     = low_conf
    ev.prompt_version           = prompt_version

    db.commit()
    db.refresh(ev)

    logger.info(
        f"[Eval] meeting={meeting_id} overall={overall:.3f} "
        f"summary={summary_score:.3f} actions={action_score:.3f} "
        f"hallucination={hall_score:.3f}"
    )
    return ev


# ── Human feedback processing ─────────────────────────────────────────────────

def process_human_feedback(
    db: Session,
    feedback: HumanFeedback,
) -> dict:
    """
    After human feedback is saved, compute:
      - Diff metrics (items added/removed/edited)
      - Precision/recall vs corrections
      - Update EvalResult with human-validated scores
    """
    orig_actions = feedback.original_actions or []
    corr_actions = feedback.corrected_actions or orig_actions

    # Diff
    added   = max(0, len(corr_actions) - len(orig_actions))
    removed = max(0, len(orig_actions) - len(corr_actions))
    edited  = sum(
        1 for o, c in zip(orig_actions, corr_actions)
        if str(o.get("task", "")) != str(c.get("task", ""))
    )

    feedback.actions_added   = added
    feedback.actions_removed = removed
    feedback.actions_edited  = edited
    feedback.summary_edited  = bool(
        feedback.corrected_summary and
        feedback.corrected_summary != feedback.original_summary
    )
    db.commit()

    # Precision/recall
    pr = compute_precision_recall(orig_actions, corr_actions)

    # Update EvalResult
    ev = db.query(EvalResult).filter(EvalResult.meeting_id == feedback.meeting_id).first()
    if ev:
        ev.precision = pr["precision"]
        ev.recall    = pr["recall"]
        ev.f1_score  = pr["f1"]
        db.commit()

    return {
        "diff": {"added": added, "removed": removed, "edited": edited},
        "precision_recall": pr,
    }


# ── Benchmark runner ──────────────────────────────────────────────────────────

def run_benchmark(
    db: Session,
    sample_ids: Optional[list[int]] = None,
    providers: Optional[list[str]] = None,
) -> dict:
    """
    Run AI extraction on benchmark samples and score against ground truth.
    Returns per-provider precision/recall/F1 and overall leaderboard.
    """
    from backend.services.summary_service import generate_structured_summary

    query = db.query(BenchmarkSample)
    if sample_ids:
        query = query.filter(BenchmarkSample.id.in_(sample_ids))
    samples = query.limit(50).all()

    if not samples:
        return {"error": "No benchmark samples found", "results": []}

    results = []
    provider_scores: dict[str, list] = {}

    for sample in samples:
        transcript = sample.transcript_excerpt
        expected_actions = sample.expected_actions or []

        try:
            structured = generate_structured_summary(transcript)
            predicted_actions = structured.get("action_items", [])
            meta = structured.get("_meta", {})
            used_provider = meta.get("provider", "unknown")

            pr = compute_precision_recall(predicted_actions, expected_actions)

            # Summary quality
            sq = _summary_quality(structured.get("summary", ""), transcript)

            # Decision accuracy
            da = _decision_accuracy(
                structured.get("decisions", []),
                transcript,
            )

            # Hallucination
            hall = detect_hallucinations(
                structured.get("summary", "") + " ".join(
                    a.get("task", "") for a in predicted_actions
                ),
                transcript,
            )

            sample_result = {
                "sample_id":        sample.id,
                "category":         sample.category,
                "difficulty":       sample.difficulty,
                "provider":         used_provider,
                "precision":        pr["precision"],
                "recall":           pr["recall"],
                "f1":               pr["f1"],
                "summary_quality":  sq,
                "decision_accuracy": da,
                "hallucination":    hall["hallucination_risk"],
            }
            results.append(sample_result)

            if used_provider not in provider_scores:
                provider_scores[used_provider] = []
            provider_scores[used_provider].append(pr["f1"])

            # Update sample's last run
            sample.last_run_at = datetime.now(timezone.utc)
            if not sample.last_run_scores:
                sample.last_run_scores = {}
            sample.last_run_scores[used_provider] = {
                "precision": pr["precision"],
                "recall":    pr["recall"],
                "f1":        pr["f1"],
            }

        except Exception as exc:
            logger.error(f"[Benchmark] Sample {sample.id} failed: {exc}")
            results.append({"sample_id": sample.id, "error": str(exc)})

    db.commit()

    # Leaderboard
    leaderboard = [
        {
            "provider": p,
            "avg_f1":   round(sum(scores) / len(scores), 3),
            "samples":  len(scores),
        }
        for p, scores in provider_scores.items()
    ]
    leaderboard.sort(key=lambda x: x["avg_f1"], reverse=True)

    return {
        "total_samples": len(samples),
        "results":       results,
        "leaderboard":   leaderboard,
    }


# ── Prompt refinement ─────────────────────────────────────────────────────────

def get_refinement_suggestions(db: Session, days: int = 7) -> list[dict]:
    """
    Analyse recent feedback patterns and suggest prompt improvements.
    Returns actionable suggestions based on failure modes.
    """
    from sqlalchemy import text
    from datetime import timedelta

    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Aggregate failure patterns
    rows = db.execute(text("""
        SELECT
            AVG(hallucination_score)     AS avg_hallucination,
            AVG(action_precision_score)  AS avg_action_precision,
            AVG(summary_quality_score)   AS avg_summary_quality,
            AVG(decision_accuracy_score) AS avg_decision_accuracy,
            AVG(f1_score)                AS avg_f1,
            COUNT(*)                     AS total
        FROM eval_results
        WHERE created_at >= :since
    """), {"since": since}).fetchone()

    if not rows or not rows.total:
        return []

    suggestions = []

    if rows.avg_hallucination and float(rows.avg_hallucination) > 0.2:
        suggestions.append({
            "issue":      "High hallucination rate",
            "metric":     f"avg_hallucination={float(rows.avg_hallucination):.3f}",
            "suggestion": "Add explicit grounding instruction: 'Only use information present in the transcript. Do not infer or assume.'",
            "priority":   "high",
        })

    if rows.avg_action_precision and float(rows.avg_action_precision) < 0.6:
        suggestions.append({
            "issue":      "Low action item precision",
            "metric":     f"avg_precision={float(rows.avg_action_precision):.3f}",
            "suggestion": "Increase confidence threshold to 0.6. Add: 'Only extract tasks with explicit assignment or strong implication.'",
            "priority":   "high",
        })

    if rows.avg_summary_quality and float(rows.avg_summary_quality) < 0.6:
        suggestions.append({
            "issue":      "Low summary quality",
            "metric":     f"avg_quality={float(rows.avg_summary_quality):.3f}",
            "suggestion": "Add length constraint: 'Write exactly 3 sentences. Cover: main topic, key decision, next step.'",
            "priority":   "medium",
        })

    if rows.avg_decision_accuracy and float(rows.avg_decision_accuracy) < 0.5:
        suggestions.append({
            "issue":      "Low decision accuracy",
            "metric":     f"avg_decision={float(rows.avg_decision_accuracy):.3f}",
            "suggestion": "Add decision examples to prompt. Clarify: 'A decision is a concrete agreement, not a discussion point.'",
            "priority":   "medium",
        })

    if rows.avg_f1 and float(rows.avg_f1) < 0.5:
        suggestions.append({
            "issue":      "Low overall F1 score",
            "metric":     f"avg_f1={float(rows.avg_f1):.3f}",
            "suggestion": "Consider switching to GPT-4o for extraction tasks. Enable reranking mode.",
            "priority":   "high",
        })

    return suggestions


# ── Automated report ──────────────────────────────────────────────────────────

def generate_eval_report(db: Session, days: int = 7) -> dict:
    """
    Generate a comprehensive evaluation report for the last N days.
    Includes all dimensions, trends, failure analysis, and recommendations.
    """
    from sqlalchemy import text
    from datetime import timedelta

    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Overall stats
    overall = db.execute(text("""
        SELECT
            COUNT(*)                          AS total_evals,
            AVG(overall_score)                AS avg_overall,
            AVG(summary_quality_score)        AS avg_summary,
            AVG(decision_accuracy_score)      AS avg_decision,
            AVG(action_precision_score)       AS avg_action,
            AVG(hallucination_score)          AS avg_hallucination,
            AVG(groundedness_score)           AS avg_groundedness,
            AVG(completeness_score)           AS avg_completeness,
            AVG(f1_score)                     AS avg_f1,
            AVG(precision)                    AS avg_precision,
            AVG(recall)                       AS avg_recall,
            SUM(action_items_count)           AS total_actions,
            SUM(low_confidence_items)         AS total_low_conf
        FROM eval_results
        WHERE created_at >= :since
    """), {"since": since}).fetchone()

    # Per-provider breakdown
    by_provider = db.execute(text("""
        SELECT
            provider,
            COUNT(*)                     AS evals,
            AVG(overall_score)           AS avg_overall,
            AVG(hallucination_score)     AS avg_hallucination,
            AVG(action_precision_score)  AS avg_precision,
            AVG(f1_score)                AS avg_f1
        FROM eval_results
        WHERE created_at >= :since AND provider IS NOT NULL
        GROUP BY provider
        ORDER BY avg_overall DESC
    """), {"since": since}).fetchall()

    # Daily trend
    trend = db.execute(text("""
        SELECT
            DATE_TRUNC('day', created_at) AS day,
            AVG(overall_score)            AS avg_overall,
            AVG(hallucination_score)      AS avg_hallucination,
            COUNT(*)                      AS evals
        FROM eval_results
        WHERE created_at >= :since
        GROUP BY day
        ORDER BY day ASC
    """), {"since": since}).fetchall()

    # Human feedback summary
    feedback_stats = db.execute(text("""
        SELECT
            signal,
            COUNT(*) AS cnt,
            AVG(actions_added)   AS avg_added,
            AVG(actions_removed) AS avg_removed,
            AVG(actions_edited)  AS avg_edited
        FROM human_feedback
        WHERE created_at >= :since
        GROUP BY signal
    """), {"since": since}).fetchall()

    # Refinement suggestions
    suggestions = get_refinement_suggestions(db, days=days)

    def _f(v): return round(float(v), 3) if v is not None else None

    return {
        "report_period_days": days,
        "generated_at":       datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_evaluations":    int(overall.total_evals or 0),
            "avg_overall_score":    _f(overall.avg_overall),
            "avg_summary_quality":  _f(overall.avg_summary),
            "avg_decision_accuracy": _f(overall.avg_decision),
            "avg_action_precision": _f(overall.avg_action),
            "avg_hallucination":    _f(overall.avg_hallucination),
            "avg_groundedness":     _f(overall.avg_groundedness),
            "avg_completeness":     _f(overall.avg_completeness),
            "avg_f1_score":         _f(overall.avg_f1),
            "avg_precision":        _f(overall.avg_precision),
            "avg_recall":           _f(overall.avg_recall),
            "total_actions_extracted": int(overall.total_actions or 0),
            "total_low_confidence":    int(overall.total_low_conf or 0),
        },
        "by_provider": [
            {
                "provider":          row.provider,
                "evaluations":       int(row.evals),
                "avg_overall":       _f(row.avg_overall),
                "avg_hallucination": _f(row.avg_hallucination),
                "avg_precision":     _f(row.avg_precision),
                "avg_f1":            _f(row.avg_f1),
            }
            for row in by_provider
        ],
        "daily_trend": [
            {
                "day":             row.day.strftime("%Y-%m-%d") if row.day else "",
                "avg_overall":     _f(row.avg_overall),
                "avg_hallucination": _f(row.avg_hallucination),
                "evals":           int(row.evals),
            }
            for row in trend
        ],
        "human_feedback": [
            {
                "signal":       row.signal,
                "count":        int(row.cnt),
                "avg_added":    _f(row.avg_added),
                "avg_removed":  _f(row.avg_removed),
                "avg_edited":   _f(row.avg_edited),
            }
            for row in feedback_stats
        ],
        "refinement_suggestions": suggestions,
        "grade": (
            "A" if (overall.avg_overall or 0) >= 0.8 else
            "B" if (overall.avg_overall or 0) >= 0.65 else
            "C" if (overall.avg_overall or 0) >= 0.5 else "D"
        ),
    }
