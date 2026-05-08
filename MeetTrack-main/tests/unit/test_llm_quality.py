"""
Unit tests for LLM quality scoring.
"""

import pytest
from backend.services.llm.quality import (
    score_response,
    detect_hallucinations,
    _completeness_score,
    _coherence_score,
    _groundedness_score,
    _json_validity_score,
)


class TestCompletenessScore:
    def test_extraction_with_markers(self):
        text = '{"task": "Deploy", "assignee": "Alice"}'
        assert _completeness_score(text, "extraction") == 1.0

    def test_extraction_missing_markers(self):
        text = "Here is some text without the expected fields."
        assert _completeness_score(text, "extraction") < 1.0

    def test_unknown_task_type(self):
        score = _completeness_score("anything", "unknown_type")
        assert score == 0.8  # default for no markers needed


class TestCoherenceScore:
    def test_good_text(self):
        text = "The team discussed the project timeline. Alice will prepare the report. Bob will review the code."
        assert _coherence_score(text) >= 0.6

    def test_empty_text(self):
        assert _coherence_score("") == 0.0

    def test_very_short(self):
        assert _coherence_score("Hi") == 0.0


class TestGroundednessScore:
    def test_grounded_response(self):
        source   = "Alice will prepare the quarterly report by Friday."
        response = "Alice needs to prepare the quarterly report."
        score = _groundedness_score(response, source)
        assert score >= 0.5

    def test_ungrounded_response(self):
        source   = "Alice will prepare the quarterly report."
        response = "Zephyr will deploy the Kubernetes cluster."
        score = _groundedness_score(response, source)
        assert score < 0.5

    def test_empty_source(self):
        assert _groundedness_score("anything", "") == 0.5


class TestJsonValidityScore:
    def test_valid_json_object(self):
        assert _json_validity_score('{"key": "value"}') == 1.0

    def test_valid_json_array(self):
        assert _json_validity_score('[{"task": "Do something"}]') == 1.0

    def test_json_with_fences(self):
        text = '```json\n{"key": "value"}\n```'
        assert _json_validity_score(text) == 1.0

    def test_invalid_json(self):
        assert _json_validity_score("not json at all") == 0.0

    def test_partial_json(self):
        score = _json_validity_score('{"key": "value"')
        assert score == 0.3

    def test_empty_string(self):
        assert _json_validity_score("") == 0.0


class TestHallucinationDetection:
    def test_no_hallucination(self):
        source   = "Alice will prepare the report. The deadline is 2024-03-15."
        response = "Alice needs to prepare the report by 2024-03-15."
        result = detect_hallucinations(response, source)
        assert result["hallucination_risk"] < 0.3

    def test_fabricated_name(self):
        source   = "Alice will prepare the report."
        response = "Zephyr Moonbeam will prepare the report."
        result = detect_hallucinations(response, source)
        assert result["hallucination_risk"] > 0.0
        assert len(result["flagged_terms"]) > 0

    def test_empty_source(self):
        result = detect_hallucinations("anything", "")
        assert result["hallucination_risk"] == 0.0


class TestScoreResponse:
    def test_good_extraction_response(self):
        text   = '{"summary": "Meeting discussed Q3.", "decisions": [], "action_items": [{"task": "Prepare report", "assignee": "Alice"}]}'
        source = "Alice will prepare the Q3 report."
        score  = score_response(text, "extraction", source, "Extract action items")
        assert score > 0.3

    def test_empty_response(self):
        assert score_response("", "extraction") == 0.0

    def test_score_range(self):
        text  = "The team agreed to proceed with the project."
        score = score_response(text, "summarization", text, text)
        assert 0.0 <= score <= 1.0
