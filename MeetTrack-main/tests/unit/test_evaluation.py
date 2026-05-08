"""
Unit tests for the evaluation service.
No DB or external API calls needed.
"""

import pytest
from backend.services.evaluation_service import (
    _summary_quality,
    _decision_accuracy,
    _action_precision,
    _detect_unsupported_claims,
    _detect_fabricated_deadlines,
    _detect_incorrect_assignees,
    compute_precision_recall,
)


TRANSCRIPT = """
Alice will prepare the Q3 report by Friday.
Bob needs to review the authentication module before the sprint ends.
The team agreed to use PostgreSQL for the database.
We decided to launch the beta on 2024-03-15.
Carol mentioned she is blocked on the API integration.
"""


class TestSummaryQuality:
    def test_good_summary(self):
        summary = "The team discussed Q3 planning and agreed on PostgreSQL. Alice will prepare the report by Friday."
        score = _summary_quality(summary, TRANSCRIPT)
        assert score >= 0.6

    def test_empty_summary(self):
        assert _summary_quality("", TRANSCRIPT) == 0.0

    def test_too_short_summary(self):
        score = _summary_quality("Short.", TRANSCRIPT)
        assert score < 0.5

    def test_ungrounded_summary(self):
        score = _summary_quality(
            "The team discussed quantum computing and blockchain technology.",
            TRANSCRIPT,
        )
        assert score < 0.7


class TestDecisionAccuracy:
    def test_grounded_decision(self):
        decisions = ["The team agreed to use PostgreSQL for the database."]
        score = _decision_accuracy(decisions, TRANSCRIPT)
        assert score >= 0.5

    def test_fabricated_decision(self):
        decisions = ["The team decided to use MongoDB and GraphQL exclusively."]
        score = _decision_accuracy(decisions, TRANSCRIPT)
        assert score < 0.5

    def test_empty_decisions(self):
        score = _decision_accuracy([], TRANSCRIPT)
        assert score == 0.5  # neutral


class TestActionPrecision:
    def test_valid_action_items(self):
        items = [
            {"task": "Prepare Q3 report", "assignee": "Alice", "deadline": "2024-03-15", "confidence_score": 0.9},
            {"task": "Review authentication module", "assignee": "Bob", "deadline": None, "confidence_score": 0.8},
        ]
        score = _action_precision(items, TRANSCRIPT)
        assert score >= 0.5

    def test_fabricated_assignee(self):
        items = [
            {"task": "Deploy to production", "assignee": "Zephyr", "deadline": None, "confidence_score": 0.9},
        ]
        score = _action_precision(items, TRANSCRIPT)
        assert score < 0.8

    def test_empty_items(self):
        assert _action_precision([], TRANSCRIPT) == 0.5


class TestHallucinationDetection:
    def test_unsupported_claims(self):
        summary = "The team decided to migrate to Kubernetes and adopt microservices architecture."
        claims = _detect_unsupported_claims(summary, TRANSCRIPT)
        assert isinstance(claims, list)

    def test_fabricated_deadlines(self):
        items = [
            {"task": "Deploy", "assignee": "Alice", "deadline": "2025-12-31", "confidence_score": 0.9},
        ]
        fab = _detect_fabricated_deadlines(items, TRANSCRIPT)
        assert len(fab) > 0

    def test_real_deadline_not_flagged(self):
        items = [
            {"task": "Launch beta", "assignee": "Alice", "deadline": "2024-03-15", "confidence_score": 0.9},
        ]
        fab = _detect_fabricated_deadlines(items, TRANSCRIPT)
        assert len(fab) == 0

    def test_incorrect_assignees(self):
        items = [
            {"task": "Do something", "assignee": "Zephyr Moonbeam", "deadline": None, "confidence_score": 0.9},
        ]
        bad = _detect_incorrect_assignees(items, TRANSCRIPT)
        assert len(bad) > 0

    def test_correct_assignee_not_flagged(self):
        items = [
            {"task": "Prepare report", "assignee": "Alice", "deadline": None, "confidence_score": 0.9},
        ]
        bad = _detect_incorrect_assignees(items, TRANSCRIPT)
        assert len(bad) == 0


class TestPrecisionRecall:
    def test_perfect_match(self):
        items = [{"task": "Prepare Q3 report"}]
        result = compute_precision_recall(items, items)
        assert result["precision"] == 1.0
        assert result["recall"] == 1.0
        assert result["f1"] == 1.0

    def test_no_match(self):
        pred = [{"task": "Deploy to Kubernetes"}]
        gt   = [{"task": "Prepare Q3 report"}]
        result = compute_precision_recall(pred, gt)
        assert result["precision"] == 0.0
        assert result["recall"] == 0.0

    def test_partial_match(self):
        pred = [
            {"task": "Prepare Q3 report"},
            {"task": "Deploy to production"},
        ]
        gt = [
            {"task": "Prepare Q3 report"},
            {"task": "Review authentication"},
        ]
        result = compute_precision_recall(pred, gt)
        assert 0 < result["f1"] < 1.0

    def test_empty_both(self):
        result = compute_precision_recall([], [])
        assert result["f1"] == 1.0

    def test_empty_predicted(self):
        result = compute_precision_recall([], [{"task": "Something"}])
        assert result["precision"] == 0.0
        assert result["recall"] == 0.0
