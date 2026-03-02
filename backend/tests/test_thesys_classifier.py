"""Tests for Thesys content routing classifier."""
import os
from unittest.mock import patch

from src.services.thesys_classifier import ThesysRoutingClassifier


class TestThesysClassifier:
    def test_short_content_returns_false(self) -> None:
        assert ThesysRoutingClassifier.should_visualize("Hi there") is False

    def test_empty_string_returns_false(self) -> None:
        assert ThesysRoutingClassifier.should_visualize("") is False

    @patch.dict(os.environ, {"THESYS_ENABLED": "false"})
    def test_disabled_feature_returns_false(self) -> None:
        content = "x" * 300 + " pipeline revenue leads forecast"
        assert ThesysRoutingClassifier.should_visualize(content) is False

    @patch.dict(os.environ, {"THESYS_ENABLED": "true"})
    def test_structured_pipeline_content(self) -> None:
        content = "x" * 300 + " Your pipeline shows strong revenue growth. Leads are progressing."
        assert ThesysRoutingClassifier.should_visualize(content) is True

    @patch.dict(os.environ, {"THESYS_ENABLED": "true"})
    def test_conversational_content_below_threshold(self) -> None:
        content = "x" * 300 + " I understand your concern. Let me explain the process."
        assert ThesysRoutingClassifier.should_visualize(content) is False

    @patch.dict(os.environ, {"THESYS_ENABLED": "true"})
    def test_rich_content_metadata_flag(self) -> None:
        content = "x" * 300 + " Some content here."
        assert ThesysRoutingClassifier.should_visualize(content, metadata={"rich_content": True}) is True

    @patch.dict(os.environ, {"THESYS_ENABLED": "true"})
    def test_email_draft_content(self) -> None:
        content = "x" * 300 + " Subject: Follow up\nDear Dr. Smith,\nI wanted to approve this draft."
        assert ThesysRoutingClassifier.should_visualize(content) is True

    @patch.dict(os.environ, {"THESYS_ENABLED": "true"})
    def test_classify_returns_content_type(self) -> None:
        content = "x" * 300 + " Your pipeline has strong revenue. Multiple leads are in close stage."
        should, ctype = ThesysRoutingClassifier.classify(content)
        assert should is True
        assert ctype is not None


class TestClassifyContentType:
    @patch.dict(os.environ, {"THESYS_ENABLED": "true"})
    def test_pipeline_type(self) -> None:
        content = "x" * 300 + " pipeline revenue forecast conversion rate"
        _, ctype = ThesysRoutingClassifier.classify(content)
        assert ctype == "pipeline_data"

    @patch.dict(os.environ, {"THESYS_ENABLED": "true"})
    def test_briefing_type(self) -> None:
        content = "x" * 300 + " **Summary** **Overview** briefing action items"
        _, ctype = ThesysRoutingClassifier.classify(content)
        assert ctype == "briefing"

    @patch.dict(os.environ, {"THESYS_ENABLED": "true"})
    def test_email_type(self) -> None:
        content = "x" * 300 + " Subject: meeting\nDear Dr. Johnson, draft approve"
        _, ctype = ThesysRoutingClassifier.classify(content)
        assert ctype == "email_draft"

    @patch.dict(os.environ, {"THESYS_ENABLED": "true"})
    def test_lead_type(self) -> None:
        content = "x" * 300 + " contacts accounts lead information recommend"
        _, ctype = ThesysRoutingClassifier.classify(content)
        assert ctype == "lead_card"
