"""Tests for perception API endpoints: topic-stats, session events, engagement-history."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


# ---------------------------------------------------------------------------
# Load the perception route module directly from file to avoid pulling in
# every sibling route via __init__.py
# ---------------------------------------------------------------------------
def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_perception_mod = _load_module(
    "src.api.routes.perception",
    Path(__file__).resolve().parent.parent.parent.parent
    / "src"
    / "api"
    / "routes"
    / "perception.py",
)


# ---------------------------------------------------------------------------
# Tests: Verify endpoint functions exist and are callable
# ---------------------------------------------------------------------------


class TestPerceptionAPIEndpoints:
    """Tests verifying the three new perception API endpoint functions exist."""

    def test_topic_stats_endpoint_exists(self) -> None:
        """Verify get_topic_stats endpoint function exists and is callable."""
        fn = getattr(_perception_mod, "get_topic_stats", None)
        assert fn is not None, "get_topic_stats not defined in perception module"
        assert callable(fn), "get_topic_stats is not callable"

    def test_session_events_endpoint_exists(self) -> None:
        """Verify get_session_events endpoint function exists and is callable."""
        fn = getattr(_perception_mod, "get_session_events", None)
        assert fn is not None, "get_session_events not defined in perception module"
        assert callable(fn), "get_session_events is not callable"

    def test_engagement_history_endpoint_exists(self) -> None:
        """Verify get_engagement_history endpoint function exists and is callable."""
        fn = getattr(_perception_mod, "get_engagement_history", None)
        assert fn is not None, "get_engagement_history not defined in perception module"
        assert callable(fn), "get_engagement_history is not callable"
