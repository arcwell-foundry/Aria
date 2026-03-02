"""Tests for goal execution pipeline field name normalization.

Verifies that task dicts produced by plan_goal() (which use "agent" and
"dependencies") are correctly consumed by _run_goal_background(),
_execute_task_with_events(), and _build_dependency_layers() (which expect
"agent_type" and "depends_on").
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_service():
    """Create a GoalExecutionService with mocked dependencies."""
    with patch("src.services.goal_execution.SupabaseClient") as mock_supa:
        mock_client = MagicMock()
        mock_supa.get_client.return_value = mock_client
        from src.services.goal_execution import GoalExecutionService

        service = GoalExecutionService()
        service._db = mock_client
        return service, mock_client


class TestBuildDependencyLayers:
    """Tests for _build_dependency_layers static method."""

    def test_tasks_with_depends_on_key(self):
        """Tasks using 'depends_on' are grouped into correct layers."""
        from src.services.goal_execution import GoalExecutionService

        tasks = [
            {"title": "Research", "agent_type": "analyst", "depends_on": []},
            {"title": "Find leads", "agent_type": "hunter", "depends_on": ["Research"]},
            {"title": "Draft email", "agent_type": "scribe", "depends_on": ["Find leads"]},
        ]
        layers = GoalExecutionService._build_dependency_layers(tasks)
        assert len(layers) == 3
        assert layers[0][0]["title"] == "Research"
        assert layers[1][0]["title"] == "Find leads"
        assert layers[2][0]["title"] == "Draft email"

    def test_tasks_with_no_depends_on_all_in_layer_zero(self):
        """Tasks without depends_on all go into layer 0."""
        from src.services.goal_execution import GoalExecutionService

        tasks = [
            {"title": "A", "agent_type": "analyst"},
            {"title": "B", "agent_type": "hunter"},
            {"title": "C", "agent_type": "scout"},
        ]
        layers = GoalExecutionService._build_dependency_layers(tasks)
        assert len(layers) == 1
        assert len(layers[0]) == 3

    def test_tasks_with_dependencies_key_are_not_recognized(self):
        """Tasks using only 'dependencies' are NOT recognized by
        _build_dependency_layers — this is the old bug. Normalization must
        happen before calling this method."""
        from src.services.goal_execution import GoalExecutionService

        tasks = [
            {"title": "Research", "agent": "analyst", "dependencies": []},
            {"title": "Find leads", "agent": "hunter", "dependencies": ["Research"]},
        ]
        # Without normalization, "dependencies" key is ignored and both tasks
        # land in layer 0 (no depends_on found).
        layers = GoalExecutionService._build_dependency_layers(tasks)
        assert len(layers) == 1  # Both in layer 0 — incorrect ordering


class TestTaskFieldNormalization:
    """Verify that plan_goal normalizes LLM-returned keys."""

    @pytest.mark.asyncio
    async def test_plan_goal_normalizes_agent_key(self):
        """plan_goal() should add 'agent_type' when LLM returns 'agent'."""
        service, mock_db = _make_service()

        # Mock goal fetch
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
            "id": "goal-1",
            "title": "Test Goal",
            "description": "Desc",
            "goal_type": "research",
            "config": {},
        }

        service._gather_execution_context = AsyncMock(
            return_value={
                "company_name": "Acme",
                "facts": [],
                "gaps": [],
                "readiness": {},
                "profile": {},
                "user_profile": {},
            }
        )

        # LLM returns "agent" (the key used in the prompt template)
        service._llm = MagicMock()
        service._llm.generate_response = AsyncMock(
            return_value=json.dumps({
                "tasks": [
                    {
                        "title": "Research competitors",
                        "agent": "analyst",
                        "dependencies": [],
                        "tools_needed": ["exa_search"],
                        "auth_required": [],
                        "risk_level": "LOW",
                        "estimated_minutes": 15,
                        "auto_executable": True,
                    },
                    {
                        "title": "Find target accounts",
                        "agent": "hunter",
                        "dependencies": ["Research competitors"],
                        "tools_needed": ["exa_search"],
                        "auth_required": [],
                        "risk_level": "LOW",
                        "estimated_minutes": 20,
                        "auto_executable": True,
                    },
                ],
                "execution_mode": "parallel",
                "missing_integrations": [],
                "approval_points": [],
                "estimated_total_minutes": 35,
            })
        )

        # Mock DB operations
        mock_db.table.return_value.insert.return_value.execute.return_value.data = [
            {"id": "plan-1"}
        ]

        result = await service.plan_goal("goal-1", "user-1")

        tasks = result["tasks"]
        assert len(tasks) == 2

        # Verify both keys exist
        assert tasks[0]["agent"] == "analyst"
        assert tasks[0]["agent_type"] == "analyst"
        assert tasks[1]["agent"] == "hunter"
        assert tasks[1]["agent_type"] == "hunter"

        # Verify dependency normalization
        assert tasks[1]["dependencies"] == ["Research competitors"]
        assert tasks[1]["depends_on"] == ["Research competitors"]

    @pytest.mark.asyncio
    async def test_plan_goal_fallback_also_normalized(self):
        """When JSON parsing fails, fallback plan also has canonical keys."""
        service, mock_db = _make_service()

        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
            "id": "goal-1",
            "title": "Test Goal",
            "description": "Desc",
            "goal_type": "research",
            "config": {"agent_type": "hunter"},
        }

        service._gather_execution_context = AsyncMock(
            return_value={
                "company_name": "Acme",
                "facts": [],
                "gaps": [],
                "readiness": {},
                "profile": {},
                "user_profile": {},
            }
        )

        # LLM returns invalid JSON → triggers fallback
        service._llm = MagicMock()
        service._llm.generate_response = AsyncMock(return_value="NOT VALID JSON {{{}}")

        mock_db.table.return_value.insert.return_value.execute.return_value.data = [
            {"id": "plan-1"}
        ]

        result = await service.plan_goal("goal-1", "user-1")

        tasks = result["tasks"]
        assert len(tasks) == 1
        assert tasks[0]["agent"] == "hunter"
        assert tasks[0]["agent_type"] == "hunter"
        assert tasks[0]["depends_on"] == []
        assert tasks[0]["dependencies"] == []


class TestRunGoalBackgroundNormalization:
    """Verify that _run_goal_background normalizes task keys when loading
    plans from the database."""

    @pytest.mark.asyncio
    async def test_loaded_plan_tasks_get_agent_type_key(self):
        """Tasks loaded from DB with only 'agent' key get 'agent_type' added."""
        service, mock_db = _make_service()

        # Simulate stored plan with LLM-style keys ("agent", "dependencies")
        stored_tasks = [
            {
                "title": "Research",
                "agent": "analyst",
                "dependencies": [],
                "tools_needed": [],
            },
            {
                "title": "Prospect",
                "agent": "hunter",
                "dependencies": ["Research"],
                "tools_needed": [],
            },
        ]

        # Mock goal status check
        goal_status_mock = MagicMock()
        goal_status_mock.data = {"status": "active"}

        # Mock plan fetch
        plan_mock = MagicMock()
        plan_mock.data = {
            "tasks": json.dumps(stored_tasks),
            "execution_mode": "sequential",
            "plan": None,
            "conversation_id": None,
        }

        # Mock goal fetch
        goal_data_mock = MagicMock()
        goal_data_mock.data = {
            "id": "goal-1",
            "title": "Test Goal",
            "config": {},
            "user_id": "user-1",
        }

        # Set up mock chain for different table calls
        call_count = {"n": 0}
        original_table = mock_db.table

        def table_side_effect(name):
            call_count["n"] += 1
            mock_t = MagicMock()
            if name == "goals":
                if call_count["n"] <= 2:
                    # First call: status check
                    mock_t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = goal_status_mock
                else:
                    # Later: full goal fetch
                    mock_t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = goal_data_mock
                mock_t.update.return_value.eq.return_value.execute.return_value = MagicMock()
                mock_t.update.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock()
            elif name == "goal_execution_plans":
                mock_t.select.return_value.eq.return_value.order.return_value.limit.return_value.maybe_single.return_value.execute.return_value = plan_mock
            elif name == "goal_agents":
                mock_t.update.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock()
            return mock_t

        mock_db.table = MagicMock(side_effect=table_side_effect)

        # Capture what _execute_task_with_events receives
        captured_tasks = []

        async def capture_task(task, **kwargs):
            captured_tasks.append(task)
            return {"task_title": task.get("title"), "agent_type": task.get("agent_type", "analyst"), "success": True}

        service._execute_task_with_events = AsyncMock(side_effect=capture_task)
        service._gather_execution_context = AsyncMock(return_value={"profile": {}, "company_name": "Acme"})
        service.complete_goal_with_retro = AsyncMock()
        service._activity = MagicMock()
        service._activity.record = AsyncMock()

        await service._run_goal_background("goal-1", "user-1")

        # Verify normalization happened
        assert len(captured_tasks) == 2
        assert captured_tasks[0]["agent_type"] == "analyst"
        assert captured_tasks[1]["agent_type"] == "hunter"
        assert captured_tasks[1]["depends_on"] == ["Research"]


class TestExecuteTaskWithEventsUsesAgentType:
    """Verify _execute_task_with_events reads agent_type correctly."""

    @pytest.mark.asyncio
    async def test_agent_type_key_used_for_agent_dispatch(self):
        """_execute_task_with_events should use agent_type, not default to analyst."""
        service, mock_db = _make_service()

        task = {
            "title": "Find leads",
            "agent_type": "hunter",
            "depends_on": [],
        }

        # Track which agent_type is passed to _execute_agent
        captured_agent_types = []
        original_execute = service._execute_agent

        async def mock_execute_agent(user_id, goal, agent_type, context, **kwargs):
            captured_agent_types.append(agent_type)
            return {"agent_type": agent_type, "success": True, "content": {}}

        service._execute_agent = AsyncMock(side_effect=mock_execute_agent)
        service._handle_agent_result = AsyncMock()

        result = await service._execute_task_with_events(
            task=task,
            goal_id="goal-1",
            user_id="user-1",
            goal={"id": "goal-1", "title": "Test", "config": {}},
            context={},
        )

        assert len(captured_agent_types) == 1
        assert captured_agent_types[0] == "hunter"
        assert result["agent_type"] == "hunter"

    @pytest.mark.asyncio
    async def test_task_with_only_agent_key_defaults_to_analyst(self):
        """Without normalization, task with only 'agent' key defaults to analyst."""
        service, mock_db = _make_service()

        # Task with only "agent" key (not normalized)
        task = {
            "title": "Find leads",
            "agent": "hunter",  # Only 'agent', no 'agent_type'
        }

        captured_agent_types = []

        async def mock_execute_agent(user_id, goal, agent_type, context, **kwargs):
            captured_agent_types.append(agent_type)
            return {"agent_type": agent_type, "success": True, "content": {}}

        service._execute_agent = AsyncMock(side_effect=mock_execute_agent)
        service._handle_agent_result = AsyncMock()

        result = await service._execute_task_with_events(
            task=task,
            goal_id="goal-1",
            user_id="user-1",
            goal={"id": "goal-1", "title": "Test", "config": {}},
            context={},
        )

        # Without normalization this would be "analyst" — the bug.
        # This test documents the current behavior: if normalization
        # didn't happen upstream, agent defaults to "analyst".
        assert captured_agent_types[0] == "analyst"
