"""
Evaluation Models
=================
Three tables:

1. EvalResult      — automated evaluation of every AI output
2. HumanFeedback   — thumbs up/down, corrections, confidence votes
3. BenchmarkSample — curated ground-truth dataset built from real transcripts
"""

import enum
from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean,
    DateTime, ForeignKey, JSON, Index,
    Enum as SAEnum,
)
from sqlalchemy.sql import func
from backend.app.database import Base


# ── Enums ─────────────────────────────────────────────────────────────────────

class FeedbackSignal(str, enum.Enum):
    THUMBS_UP   = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"
    EDITED      = "edited"
    FLAGGED     = "flagged"


class EvalDimension(str, enum.Enum):
    SUMMARY_QUALITY    = "summary_quality"
    DECISION_ACCURACY  = "decision_accuracy"
    ACTION_PRECISION   = "action_precision"
    HALLUCINATION      = "hallucination"
    GROUNDEDNESS       = "groundedness"
    COMPLETENESS       = "completeness"


# ── EvalResult ────────────────────────────────────────────────────────────────

class EvalResult(Base):
    """
    Automated evaluation scores for every AI-processed meeting.
    Computed immediately after AI extraction completes.
    """
    __tablename__ = "eval_results"
    __table_args__ = (
        Index("ix_eval_meeting_id",  "meeting_id"),
        Index("ix_eval_created_at",  "created_at"),
        Index("ix_eval_provider",    "provider"),
        {"extend_existing": True},
    )

    id              = Column(Integer, primary_key=True, index=True)
    meeting_id      = Column(Integer, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False)
    user_id         = Column(Integer, nullable=True)
    provider        = Column(String(50),  nullable=True)   # gemini / openai / local
    model           = Column(String(100), nullable=True)

    # ── Automated scores (0.0–1.0) ────────────────────────────────────────
    summary_quality_score    = Column(Float, nullable=True)  # coherence + completeness
    decision_accuracy_score  = Column(Float, nullable=True)  # grounded decisions
    action_precision_score   = Column(Float, nullable=True)  # valid action items
    hallucination_score      = Column(Float, nullable=True)  # 0=clean, 1=hallucinated
    groundedness_score       = Column(Float, nullable=True)  # overlap with transcript
    completeness_score       = Column(Float, nullable=True)  # all key points covered
    overall_score            = Column(Float, nullable=True)  # weighted composite

    # ── Hallucination detail ───────────────────────────────────────────────
    flagged_terms            = Column(JSON,  nullable=True)  # list of suspicious terms
    unsupported_claims       = Column(JSON,  nullable=True)  # sentences not in transcript
    fabricated_deadlines     = Column(JSON,  nullable=True)  # dates not in transcript
    incorrect_assignees      = Column(JSON,  nullable=True)  # names not in transcript

    # ── Extraction counts ──────────────────────────────────────────────────
    action_items_count       = Column(Integer, default=0)
    decisions_count          = Column(Integer, default=0)
    low_confidence_items     = Column(Integer, default=0)   # confidence < 0.5

    # ── Precision / Recall vs human corrections ────────────────────────────
    precision                = Column(Float, nullable=True)  # set after human feedback
    recall                   = Column(Float, nullable=True)
    f1_score                 = Column(Float, nullable=True)

    # ── Prompt refinement tracking ─────────────────────────────────────────
    prompt_version           = Column(String(20), default="v1")
    refinement_applied       = Column(Boolean, default=False)

    created_at               = Column(DateTime(timezone=True), server_default=func.now())
    updated_at               = Column(DateTime(timezone=True), onupdate=func.now())


# ── HumanFeedback ─────────────────────────────────────────────────────────────

class HumanFeedback(Base):
    """
    Human-in-the-loop feedback on AI outputs.
    Drives precision/recall computation and prompt refinement.
    """
    __tablename__ = "human_feedback"
    __table_args__ = (
        Index("ix_feedback_meeting_id", "meeting_id"),
        Index("ix_feedback_user_id",    "user_id"),
        Index("ix_feedback_signal",     "signal"),
        {"extend_existing": True},
    )

    id              = Column(Integer, primary_key=True, index=True)
    meeting_id      = Column(Integer, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False)
    user_id         = Column(Integer, nullable=False)

    # ── Feedback type ──────────────────────────────────────────────────────
    signal          = Column(SAEnum(FeedbackSignal), nullable=False)
    dimension       = Column(String(50), nullable=True)   # which part was rated

    # ── Original AI output ─────────────────────────────────────────────────
    original_summary    = Column(Text, nullable=True)
    original_decisions  = Column(JSON, nullable=True)
    original_actions    = Column(JSON, nullable=True)

    # ── Human corrections ──────────────────────────────────────────────────
    corrected_summary   = Column(Text, nullable=True)
    corrected_decisions = Column(JSON, nullable=True)
    corrected_actions   = Column(JSON, nullable=True)

    # ── Confidence validation ──────────────────────────────────────────────
    # User rates each action item confidence: {item_index: true/false}
    confidence_votes    = Column(JSON, nullable=True)

    # ── Free-text comment ──────────────────────────────────────────────────
    comment             = Column(Text, nullable=True)

    # ── Computed diff metrics (filled after correction) ────────────────────
    actions_added       = Column(Integer, default=0)   # items user added
    actions_removed     = Column(Integer, default=0)   # items user deleted
    actions_edited      = Column(Integer, default=0)   # items user changed
    summary_edited      = Column(Boolean, default=False)

    created_at          = Column(DateTime(timezone=True), server_default=func.now())


# ── BenchmarkSample ───────────────────────────────────────────────────────────

class BenchmarkSample(Base):
    """
    Ground-truth benchmark dataset built from real transcripts + human corrections.
    Used for automated regression testing and prompt evaluation.
    """
    __tablename__ = "benchmark_samples"
    __table_args__ = (
        Index("ix_bench_category", "category"),
        Index("ix_bench_created",  "created_at"),
        {"extend_existing": True},
    )

    id                  = Column(Integer, primary_key=True, index=True)
    meeting_id          = Column(Integer, ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True)

    # ── Source ────────────────────────────────────────────────────────────
    transcript_excerpt  = Column(Text, nullable=False)   # ≤2000 chars
    category            = Column(String(50), default="general")  # e.g. engineering, sales
    difficulty          = Column(String(20), default="medium")   # easy / medium / hard

    # ── Ground truth ──────────────────────────────────────────────────────
    expected_summary    = Column(Text, nullable=True)
    expected_decisions  = Column(JSON, nullable=True)   # [str, ...]
    expected_actions    = Column(JSON, nullable=True)   # [{task, assignee, deadline}, ...]

    # ── Benchmark run results ──────────────────────────────────────────────
    last_run_at         = Column(DateTime(timezone=True), nullable=True)
    last_run_scores     = Column(JSON, nullable=True)   # {provider: {precision, recall, f1}}
    best_provider       = Column(String(50), nullable=True)

    # ── Metadata ──────────────────────────────────────────────────────────
    source              = Column(String(50), default="human_correction")  # or "synthetic"
    notes               = Column(Text, nullable=True)
    created_by          = Column(Integer, nullable=True)   # user_id
    created_at          = Column(DateTime(timezone=True), server_default=func.now())
    updated_at          = Column(DateTime(timezone=True), onupdate=func.now())
