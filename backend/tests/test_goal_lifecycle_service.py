"""Tests for goal lifecycle service methods (US-936).

Covers: get_dashboard, create_with_aria, get_templates, add_milestone,
complete_milestone, generate_retrospective, get_goal_detail.
"""

from __future__ import annotations

import importlib
import json
import sys
import types
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _ensure_goal_service_importable() -> None:
    """Register parent packages so patch() can resolve the dotted path.

    The ``src.services`` __init__.py triggers a circular import, so we
    bypass it by loading the leaf module with importlib.util and
    registering it into sys.modules manually.
    """
    if "src.services.goal_service" in sys.modules:
        return

    from pathlib import Path

    backend_dir = Path(__file__).resolve().parent.parent
    src_dir = backend_dir / "src"

    # Ensure parent packages are registered with correct __path__
    if "src" not in sys.modules:
        pkg = types.ModuleType("src")
        pkg.__path__ = [str(src_dir)]
        pkg.__package__ = "src"
        sys.modules["src"] = pkg

    if "src.services" not in sys.modules:
        pkg = types.ModuleType("src.services")
        pkg.__path__ = [str(src_dir / "services")]
        pkg.__package__ = "src.services"
        sys.modules["src.services"] = pkg

    # Load the leaf module using importlib.util to avoid __init__.py
    goal_service_path = src_dir / "services" / "goal_service.py"
    spec = importlib.util.find_spec("src.services.goal_service")
    if spec is None:
        spec = importlib.util.spec_from_file_location(
            "src.services.goal_service",
            str(goal_service_path),
            submodule_search_locations=[],
        )
    if spec and spec.loader:
        mod = importlib.util.module_from_spec(spec)
        sys.modules["src.services.goal_service"] = mod
        spec.loader.exec_module(mod)
        # Attach as attribute so patch() traversal works
        sys.modules["src.services"].goal_service = mod  # type: ignore[attr-defined]


_ensure_goal_service_importable()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db() -> MagicMock:
    """Create mock Supabase client."""
    return MagicMock()


# ---------------------------------------------------------------------------
# get_dashboard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_dashboard_returns_goals_with_milestone_counts(
    mock_db: MagicMock,
) -> None:
    """get_dashboard computes milestone_total and milestone_complete."""
    with patch("src.services.goal_service.SupabaseClient") as mock_db_class:
        goals_data: list[dict[str, Any]] = [
            {
                "id": "g1",
                "user_id": "u1",
                "title": "Goal A",
                "goal_agents": [],
                "goal_milestones": [
                    {"id": "m1", "status": "complete"},
                    {"id": "m2", "status": "pending"},
                    {"id": "m3", "status": "complete"},
                ],
            },
            {
                "id": "g2",
                "user_id": "u1",
                "title": "Goal B",
                "goal_agents": [],
                "goal_milestones": [],
            },
        ]
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
            data=goals_data
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.goal_service import GoalService

        service = GoalService()
        result = await service.get_dashboard("u1")

        assert len(result) == 2
        assert result[0]["milestone_total"] == 3
        assert result[0]["milestone_complete"] == 2
        assert result[1]["milestone_total"] == 0
        assert result[1]["milestone_complete"] == 0


@pytest.mark.asyncio
async def test_get_dashboard_handles_no_milestones_key(
    mock_db: MagicMock,
) -> None:
    """get_dashboard tolerates goals missing goal_milestones key."""
    with patch("src.services.goal_service.SupabaseClient") as mock_db_class:
        goals_data: list[dict[str, Any]] = [
            {"id": "g1", "user_id": "u1", "title": "No MS", "goal_agents": []},
        ]
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
            data=goals_data
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.goal_service import GoalService

        service = GoalService()
        result = await service.get_dashboard("u1")

        assert result[0]["milestone_total"] == 0
        assert result[0]["milestone_complete"] == 0


# ---------------------------------------------------------------------------
# create_with_aria
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_with_aria_returns_parsed_suggestion(
    mock_db: MagicMock,
) -> None:
    """create_with_aria returns parsed LLM suggestion."""
    with patch("src.services.goal_service.SupabaseClient") as mock_db_class:
        mock_db_class.get_client.return_value = mock_db

        expected: dict[str, Any] = {
            "refined_title": "Refined Goal",
            "refined_description": "SMART description",
            "smart_score": 85,
            "sub_tasks": [{"title": "Step 1", "description": "Do thing"}],
            "agent_assignments": ["analyst", "hunter"],
            "suggested_timeline_days": 7,
            "reasoning": "This is a well-scoped goal.",
        }

        with patch("src.services.goal_service.LLMClient") as mock_llm_cls:
            mock_llm = MagicMock()
            mock_llm.generate_response = AsyncMock(return_value=json.dumps(expected))
            mock_llm_cls.return_value = mock_llm

            from src.services.goal_service import GoalService

            service = GoalService()
            result = await service.create_with_aria("u1", "My goal", "Details")

        assert result["refined_title"] == "Refined Goal"
        assert result["smart_score"] == 85
        assert result["agent_assignments"] == ["analyst", "hunter"]


@pytest.mark.asyncio
async def test_create_with_aria_returns_defaults_on_parse_failure(
    mock_db: MagicMock,
) -> None:
    """create_with_aria returns sensible defaults when LLM response is unparseable."""
    with patch("src.services.goal_service.SupabaseClient") as mock_db_class:
        mock_db_class.get_client.return_value = mock_db

        with patch("src.services.goal_service.LLMClient") as mock_llm_cls:
            mock_llm = MagicMock()
            mock_llm.generate_response = AsyncMock(return_value="not valid json")
            mock_llm_cls.return_value = mock_llm

            from src.services.goal_service import GoalService

            service = GoalService()
            result = await service.create_with_aria("u1", "Raw title", None)

        assert result["refined_title"] == "Raw title"
        assert result["smart_score"] == 50
        assert result["agent_assignments"] == ["analyst"]


# ---------------------------------------------------------------------------
# get_templates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_templates_returns_all_without_role_filter(
    mock_db: MagicMock,
) -> None:
    """get_templates returns all templates when no role is specified."""
    with patch("src.services.goal_service.SupabaseClient") as mock_db_class:
        mock_db_class.get_client.return_value = mock_db

        from src.services.goal_service import GoalService

        service = GoalService()
        result = await service.get_templates()

        assert len(result) > 0
        # All templates should be dicts with expected keys
        for t in result:
            assert "title" in t
            assert "description" in t
            assert "applicable_roles" in t


@pytest.mark.asyncio
async def test_get_templates_filters_by_role(
    mock_db: MagicMock,
) -> None:
    """get_templates filters templates by role."""
    with patch("src.services.goal_service.SupabaseClient") as mock_db_class:
        mock_db_class.get_client.return_value = mock_db

        from src.services.goal_service import GoalService

        service = GoalService()
        all_templates = await service.get_templates()
        marketing_templates = await service.get_templates(role="marketing")

        # Marketing subset should be smaller than total
        assert len(marketing_templates) < len(all_templates)
        # Each filtered template should include marketing in applicable_roles
        for t in marketing_templates:
            assert any("marketing" in r.lower() for r in t["applicable_roles"])


@pytest.mark.asyncio
async def test_get_templates_nonexistent_role_returns_empty(
    mock_db: MagicMock,
) -> None:
    """get_templates returns empty list for a role with no matching templates."""
    with patch("src.services.goal_service.SupabaseClient") as mock_db_class:
        mock_db_class.get_client.return_value = mock_db

        from src.services.goal_service import GoalService

        service = GoalService()
        result = await service.get_templates(role="nonexistent_role_xyz")

        assert result == []


# ---------------------------------------------------------------------------
# add_milestone
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_milestone_inserts_with_correct_sort_order(
    mock_db: MagicMock,
) -> None:
    """add_milestone determines sort_order from existing milestones and inserts."""
    with patch("src.services.goal_service.SupabaseClient") as mock_db_class:
        mock_db_class.get_client.return_value = mock_db

        from src.services.goal_service import GoalService

        service = GoalService()

        # Mock get_goal to return a goal
        async def _get_goal(uid: str, gid: str) -> dict[str, Any]:
            return {"id": gid, "user_id": uid, "goal_agents": []}

        service.get_goal = _get_goal  # type: ignore[method-assign]

        # Mock existing milestones query (max sort_order = 3)
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"sort_order": 3}]
        )

        # Mock insert
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": "ms-new",
                    "goal_id": "g1",
                    "title": "New Milestone",
                    "description": None,
                    "status": "pending",
                    "sort_order": 4,
                }
            ]
        )

        result = await service.add_milestone("u1", "g1", "New Milestone")

        assert result is not None
        assert result["id"] == "ms-new"
        assert result["sort_order"] == 4


@pytest.mark.asyncio
async def test_add_milestone_returns_none_when_goal_not_found(
    mock_db: MagicMock,
) -> None:
    """add_milestone returns None when goal doesn't exist."""
    with patch("src.services.goal_service.SupabaseClient") as mock_db_class:
        mock_db_class.get_client.return_value = mock_db

        from src.services.goal_service import GoalService

        service = GoalService()

        async def _get_goal(_uid: str, _gid: str) -> None:
            return None

        service.get_goal = _get_goal  # type: ignore[method-assign]

        result = await service.add_milestone("u1", "g-missing", "Milestone")

        assert result is None


@pytest.mark.asyncio
async def test_add_milestone_with_due_date(
    mock_db: MagicMock,
) -> None:
    """add_milestone includes due_date when provided."""
    with patch("src.services.goal_service.SupabaseClient") as mock_db_class:
        mock_db_class.get_client.return_value = mock_db

        from src.services.goal_service import GoalService

        service = GoalService()

        async def _get_goal(uid: str, gid: str) -> dict[str, Any]:
            return {"id": gid, "user_id": uid, "goal_agents": []}

        service.get_goal = _get_goal  # type: ignore[method-assign]

        # No existing milestones
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[]
        )

        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": "ms-1",
                    "goal_id": "g1",
                    "title": "With Due",
                    "due_date": "2026-03-01",
                    "status": "pending",
                    "sort_order": 1,
                }
            ]
        )

        result = await service.add_milestone("u1", "g1", "With Due", due_date="2026-03-01")

        assert result is not None
        assert result["due_date"] == "2026-03-01"


# ---------------------------------------------------------------------------
# complete_milestone
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_milestone_updates_status(
    mock_db: MagicMock,
) -> None:
    """complete_milestone sets status to complete and completed_at."""
    with patch("src.services.goal_service.SupabaseClient") as mock_db_class:
        mock_db_class.get_client.return_value = mock_db

        from src.services.goal_service import GoalService

        service = GoalService()

        async def _get_goal(uid: str, gid: str) -> dict[str, Any]:
            return {"id": gid, "user_id": uid, "goal_agents": []}

        service.get_goal = _get_goal  # type: ignore[method-assign]

        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": "ms-1",
                    "goal_id": "g1",
                    "status": "complete",
                    "completed_at": "2026-02-07T12:00:00Z",
                }
            ]
        )

        result = await service.complete_milestone("u1", "g1", "ms-1")

        assert result is not None
        assert result["status"] == "complete"
        assert result["completed_at"] is not None


@pytest.mark.asyncio
async def test_complete_milestone_returns_none_when_goal_not_found(
    mock_db: MagicMock,
) -> None:
    """complete_milestone returns None when goal doesn't exist."""
    with patch("src.services.goal_service.SupabaseClient") as mock_db_class:
        mock_db_class.get_client.return_value = mock_db

        from src.services.goal_service import GoalService

        service = GoalService()

        async def _get_goal(_uid: str, _gid: str) -> None:
            return None

        service.get_goal = _get_goal  # type: ignore[method-assign]

        result = await service.complete_milestone("u1", "g-missing", "ms-1")

        assert result is None


@pytest.mark.asyncio
async def test_complete_milestone_returns_none_when_milestone_not_found(
    mock_db: MagicMock,
) -> None:
    """complete_milestone returns None when milestone doesn't exist."""
    with patch("src.services.goal_service.SupabaseClient") as mock_db_class:
        mock_db_class.get_client.return_value = mock_db

        from src.services.goal_service import GoalService

        service = GoalService()

        async def _get_goal(uid: str, gid: str) -> dict[str, Any]:
            return {"id": gid, "user_id": uid, "goal_agents": []}

        service.get_goal = _get_goal  # type: ignore[method-assign]

        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )

        result = await service.complete_milestone("u1", "g1", "ms-missing")

        assert result is None


# ---------------------------------------------------------------------------
# generate_retrospective
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_retrospective_returns_parsed_retro(
    mock_db: MagicMock,
) -> None:
    """generate_retrospective parses LLM output and upserts to DB."""
    with patch("src.services.goal_service.SupabaseClient") as mock_db_class:
        mock_db_class.get_client.return_value = mock_db

        from src.services.goal_service import GoalService

        service = GoalService()

        async def _get_goal(uid: str, gid: str) -> dict[str, Any]:
            return {
                "id": gid,
                "user_id": uid,
                "title": "Test Goal",
                "goal_agents": [{"id": "a1", "agent_type": "analyst"}],
            }

        service.get_goal = _get_goal  # type: ignore[method-assign]

        # Mock milestones query
        mock_milestones = MagicMock(data=[{"id": "m1", "title": "MS1", "status": "complete"}])
        # Mock executions query
        mock_executions = MagicMock(data=[{"id": "e1", "status": "complete"}])

        # We need the table mock to handle multiple table calls
        call_count = 0

        def table_side_effect(name: str) -> MagicMock:
            nonlocal call_count
            call_count += 1
            tbl = MagicMock()
            if name == "goal_milestones":
                tbl.select.return_value.eq.return_value.order.return_value.execute.return_value = (
                    mock_milestones
                )
            elif name == "agent_executions":
                tbl.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_executions
            elif name == "goal_retrospectives":
                tbl.upsert.return_value.execute.return_value = MagicMock(
                    data=[
                        {
                            "id": "retro-1",
                            "goal_id": "g1",
                            "summary": "Good progress",
                            "what_worked": ["Communication"],
                            "what_didnt": ["Timing"],
                            "time_analysis": {"total_days": 10},
                            "agent_effectiveness": {},
                            "learnings": ["Start earlier"],
                        }
                    ]
                )
            return tbl

        mock_db.table.side_effect = table_side_effect

        retro_llm_response: dict[str, Any] = {
            "summary": "Good progress",
            "what_worked": ["Communication"],
            "what_didnt": ["Timing"],
            "time_analysis": {"total_days": 10},
            "agent_effectiveness": {},
            "learnings": ["Start earlier"],
        }

        with patch("src.services.goal_service.LLMClient") as mock_llm_cls:
            mock_llm = MagicMock()
            mock_llm.generate_response = AsyncMock(return_value=json.dumps(retro_llm_response))
            mock_llm_cls.return_value = mock_llm

            result = await service.generate_retrospective("u1", "g1")

        assert result is not None
        assert result["summary"] == "Good progress"
        assert result["what_worked"] == ["Communication"]
        assert result["learnings"] == ["Start earlier"]


@pytest.mark.asyncio
async def test_generate_retrospective_returns_none_when_goal_not_found(
    mock_db: MagicMock,
) -> None:
    """generate_retrospective returns None when goal doesn't exist."""
    with patch("src.services.goal_service.SupabaseClient") as mock_db_class:
        mock_db_class.get_client.return_value = mock_db

        from src.services.goal_service import GoalService

        service = GoalService()

        async def _get_goal(_uid: str, _gid: str) -> None:
            return None

        service.get_goal = _get_goal  # type: ignore[method-assign]

        result = await service.generate_retrospective("u1", "g-missing")

        assert result is None


@pytest.mark.asyncio
async def test_generate_retrospective_handles_llm_failure(
    mock_db: MagicMock,
) -> None:
    """generate_retrospective uses defaults when LLM response is unparseable."""
    with patch("src.services.goal_service.SupabaseClient") as mock_db_class:
        mock_db_class.get_client.return_value = mock_db

        from src.services.goal_service import GoalService

        service = GoalService()

        async def _get_goal(uid: str, gid: str) -> dict[str, Any]:
            return {
                "id": gid,
                "user_id": uid,
                "title": "Test",
                "goal_agents": [],
            }

        service.get_goal = _get_goal  # type: ignore[method-assign]

        def table_side_effect(name: str) -> MagicMock:
            tbl = MagicMock()
            if name == "goal_milestones":
                tbl.select.return_value.eq.return_value.order.return_value.execute.return_value = (
                    MagicMock(data=[])
                )
            elif name == "goal_retrospectives":
                tbl.upsert.return_value.execute.return_value = MagicMock(
                    data=[
                        {
                            "id": "retro-fallback",
                            "goal_id": "g1",
                            "summary": "Retrospective generation failed.",
                            "what_worked": [],
                            "what_didnt": [],
                            "time_analysis": {},
                            "agent_effectiveness": {},
                            "learnings": [],
                        }
                    ]
                )
            return tbl

        mock_db.table.side_effect = table_side_effect

        with patch("src.services.goal_service.LLMClient") as mock_llm_cls:
            mock_llm = MagicMock()
            mock_llm.generate_response = AsyncMock(return_value="broken json {{")
            mock_llm_cls.return_value = mock_llm

            result = await service.generate_retrospective("u1", "g1")

        assert result is not None
        assert result["summary"] == "Retrospective generation failed."


# ---------------------------------------------------------------------------
# get_goal_detail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_goal_detail_returns_goal_with_milestones_and_retro(
    mock_db: MagicMock,
) -> None:
    """get_goal_detail returns goal plus milestones and retrospective."""
    with patch("src.services.goal_service.SupabaseClient") as mock_db_class:
        mock_db_class.get_client.return_value = mock_db

        from src.services.goal_service import GoalService

        service = GoalService()

        goal_data: dict[str, Any] = {
            "id": "g1",
            "user_id": "u1",
            "title": "Detailed Goal",
            "goal_agents": [],
        }

        async def _get_goal(_uid: str, _gid: str) -> dict[str, Any]:
            return goal_data

        service.get_goal = _get_goal  # type: ignore[method-assign]

        retro_data: dict[str, Any] = {
            "id": "retro-1",
            "goal_id": "g1",
            "summary": "Done",
        }

        def table_side_effect(name: str) -> MagicMock:
            tbl = MagicMock()
            if name == "goal_milestones":
                tbl.select.return_value.eq.return_value.order.return_value.execute.return_value = (
                    MagicMock(
                        data=[
                            {"id": "m1", "title": "MS 1", "sort_order": 1},
                            {"id": "m2", "title": "MS 2", "sort_order": 2},
                        ]
                    )
                )
            elif name == "goal_retrospectives":
                tbl.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
                    data=retro_data
                )
            return tbl

        mock_db.table.side_effect = table_side_effect

        result = await service.get_goal_detail("u1", "g1")

        assert result is not None
        assert result["title"] == "Detailed Goal"
        assert len(result["milestones"]) == 2
        assert result["retrospective"]["summary"] == "Done"


@pytest.mark.asyncio
async def test_get_goal_detail_returns_none_when_goal_not_found(
    mock_db: MagicMock,
) -> None:
    """get_goal_detail returns None when goal doesn't exist."""
    with patch("src.services.goal_service.SupabaseClient") as mock_db_class:
        mock_db_class.get_client.return_value = mock_db

        from src.services.goal_service import GoalService

        service = GoalService()

        async def _get_goal(_uid: str, _gid: str) -> None:
            return None

        service.get_goal = _get_goal  # type: ignore[method-assign]

        result = await service.get_goal_detail("u1", "g-missing")

        assert result is None


@pytest.mark.asyncio
async def test_get_goal_detail_with_no_retrospective(
    mock_db: MagicMock,
) -> None:
    """get_goal_detail handles missing retrospective gracefully."""
    with patch("src.services.goal_service.SupabaseClient") as mock_db_class:
        mock_db_class.get_client.return_value = mock_db

        from src.services.goal_service import GoalService

        service = GoalService()

        async def _get_goal(uid: str, gid: str) -> dict[str, Any]:
            return {"id": gid, "user_id": uid, "title": "No Retro", "goal_agents": []}

        service.get_goal = _get_goal  # type: ignore[method-assign]

        def table_side_effect(name: str) -> MagicMock:
            tbl = MagicMock()
            if name == "goal_milestones":
                tbl.select.return_value.eq.return_value.order.return_value.execute.return_value = (
                    MagicMock(data=[])
                )
            elif name == "goal_retrospectives":
                tbl.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
                    data=None
                )
            return tbl

        mock_db.table.side_effect = table_side_effect

        result = await service.get_goal_detail("u1", "g1")

        assert result is not None
        assert result["milestones"] == []
        assert result["retrospective"] is None
