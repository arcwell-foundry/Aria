"""Tests for ErrorTracker singleton.

Tests cover:
- Singleton behavior (same instance returned)
- record_error stores errors with service, type, message
- get_error_summary returns counts by service/type for a given period
- Max 1000 errors in memory (oldest evicted)
- get_recent_errors returns latest errors
"""

import time
from unittest.mock import patch

import pytest

from src.core.error_tracker import ErrorTracker


class TestErrorTrackerSingleton:
    """ErrorTracker should always return the same instance."""

    def setup_method(self) -> None:
        ErrorTracker._instance = None

    def test_returns_same_instance(self) -> None:
        tracker1 = ErrorTracker.get_instance()
        tracker2 = ErrorTracker.get_instance()
        assert tracker1 is tracker2

    def test_instance_is_error_tracker(self) -> None:
        tracker = ErrorTracker.get_instance()
        assert isinstance(tracker, ErrorTracker)


class TestRecordError:
    """record_error should store errors with metadata."""

    def setup_method(self) -> None:
        ErrorTracker._instance = None
        self.tracker = ErrorTracker.get_instance()

    def test_records_error_with_service_and_type(self) -> None:
        self.tracker.record_error("tavus", "ConnectionError", "Connection refused")

        errors = self.tracker.get_recent_errors(limit=10)
        assert len(errors) == 1
        assert errors[0]["service"] == "tavus"
        assert errors[0]["error_type"] == "ConnectionError"
        assert errors[0]["message"] == "Connection refused"

    def test_records_timestamp(self) -> None:
        before = time.time()
        self.tracker.record_error("exa", "TimeoutError", "Request timed out")
        after = time.time()

        errors = self.tracker.get_recent_errors(limit=10)
        assert len(errors) == 1
        assert before <= errors[0]["timestamp"] <= after

    def test_records_multiple_errors(self) -> None:
        self.tracker.record_error("tavus", "ConnectionError", "Connection refused")
        self.tracker.record_error("exa", "TimeoutError", "Request timed out")
        self.tracker.record_error("supabase", "DatabaseError", "Query failed")

        errors = self.tracker.get_recent_errors(limit=10)
        assert len(errors) == 3

    def test_recent_errors_returns_newest_first(self) -> None:
        self.tracker.record_error("tavus", "ConnectionError", "first")
        self.tracker.record_error("exa", "TimeoutError", "second")

        errors = self.tracker.get_recent_errors(limit=10)
        assert errors[0]["message"] == "second"
        assert errors[1]["message"] == "first"

    def test_recent_errors_respects_limit(self) -> None:
        for i in range(5):
            self.tracker.record_error("svc", "Err", f"msg-{i}")

        errors = self.tracker.get_recent_errors(limit=2)
        assert len(errors) == 2


class TestMaxErrors:
    """ErrorTracker should evict oldest when exceeding 1000 entries."""

    def setup_method(self) -> None:
        ErrorTracker._instance = None
        self.tracker = ErrorTracker.get_instance()

    def test_evicts_oldest_beyond_max(self) -> None:
        for i in range(1005):
            self.tracker.record_error("svc", "Err", f"msg-{i}")

        errors = self.tracker.get_recent_errors(limit=1005)
        assert len(errors) == 1000
        # Oldest should be gone — msg-0 through msg-4 evicted
        messages = [e["message"] for e in errors]
        assert "msg-0" not in messages
        assert "msg-4" not in messages
        assert "msg-5" in messages
        assert "msg-1004" in messages


class TestGetErrorSummary:
    """get_error_summary returns counts grouped by service and error_type."""

    def setup_method(self) -> None:
        ErrorTracker._instance = None
        self.tracker = ErrorTracker.get_instance()

    def test_empty_summary(self) -> None:
        summary = self.tracker.get_error_summary(period_seconds=3600)
        assert summary["total"] == 0
        assert summary["by_service"] == {}
        assert summary["by_type"] == {}

    def test_counts_by_service(self) -> None:
        self.tracker.record_error("tavus", "ConnectionError", "err1")
        self.tracker.record_error("tavus", "TimeoutError", "err2")
        self.tracker.record_error("exa", "TimeoutError", "err3")

        summary = self.tracker.get_error_summary(period_seconds=3600)
        assert summary["total"] == 3
        assert summary["by_service"]["tavus"] == 2
        assert summary["by_service"]["exa"] == 1

    def test_counts_by_type(self) -> None:
        self.tracker.record_error("tavus", "ConnectionError", "err1")
        self.tracker.record_error("exa", "ConnectionError", "err2")
        self.tracker.record_error("exa", "TimeoutError", "err3")

        summary = self.tracker.get_error_summary(period_seconds=3600)
        assert summary["by_type"]["ConnectionError"] == 2
        assert summary["by_type"]["TimeoutError"] == 1

    def test_filters_by_period(self) -> None:
        # Record an old error by patching time
        old_time = time.time() - 7200  # 2 hours ago
        with patch("src.core.error_tracker.time") as mock_time:
            mock_time.time.return_value = old_time
            self.tracker.record_error("tavus", "ConnectionError", "old error")

        # Record a recent error
        self.tracker.record_error("exa", "TimeoutError", "recent error")

        summary = self.tracker.get_error_summary(period_seconds=3600)
        assert summary["total"] == 1
        assert summary["by_service"].get("tavus", 0) == 0
        assert summary["by_service"]["exa"] == 1

    def test_includes_period_in_response(self) -> None:
        summary = self.tracker.get_error_summary(period_seconds=3600)
        assert summary["period_seconds"] == 3600


class TestReset:
    """reset() should clear all tracked errors."""

    def setup_method(self) -> None:
        ErrorTracker._instance = None
        self.tracker = ErrorTracker.get_instance()

    def test_reset_clears_errors(self) -> None:
        self.tracker.record_error("tavus", "Err", "msg")
        self.tracker.reset()

        errors = self.tracker.get_recent_errors(limit=10)
        assert len(errors) == 0

        summary = self.tracker.get_error_summary(period_seconds=3600)
        assert summary["total"] == 0
