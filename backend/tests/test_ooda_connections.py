"""Tests for Phase 4C: OODA connection awareness and blocked task resumption."""

# Set required env vars BEFORE any src imports trigger config validation
import os

os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key")

import pytest
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# ConnectionRegistryService tests
# ---------------------------------------------------------------------------


class TestConnectionRegistryNewMethods:
    """Tests for get_recently_added_connections and mark_connection_expired."""

    @pytest.mark.asyncio
    async def test_get_recently_added_connections_returns_recent(self):
        """Should return connections updated within the time window."""
        from src.integrations.connection_registry import ConnectionRegistryService

        mock_data = [
            {
                "id": "conn-1",
                "user_id": "user-1",
                "toolkit_slug": "SALESFORCE",
                "status": "active",
                "updated_at": datetime.now(UTC).isoformat(),
            }
        ]

        registry = ConnectionRegistryService()
        with patch("src.integrations.connection_registry.SupabaseClient") as mock_sb:
            mock_client = MagicMock()
            mock_sb.get_client.return_value = mock_client
            mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.gte.return_value.execute.return_value = MagicMock(
                data=mock_data
            )

            result = await registry.get_recently_added_connections("user-1", hours=24)
            assert len(result) == 1
            assert result[0]["toolkit_slug"] == "SALESFORCE"

    @pytest.mark.asyncio
    async def test_get_recently_added_connections_empty(self):
        """Should return empty list when no recent connections."""
        from src.integrations.connection_registry import ConnectionRegistryService

        registry = ConnectionRegistryService()
        with patch("src.integrations.connection_registry.SupabaseClient") as mock_sb:
            mock_client = MagicMock()
            mock_sb.get_client.return_value = mock_client
            mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.gte.return_value.execute.return_value = MagicMock(
                data=[]
            )

            result = await registry.get_recently_added_connections("user-1", hours=1)
            assert result == []

    @pytest.mark.asyncio
    async def test_mark_connection_expired_updates_status(self):
        """Should set status to 'expired' and audit the change."""
        from src.integrations.connection_registry import ConnectionRegistryService

        registry = ConnectionRegistryService()
        registry._audit = AsyncMock()

        with patch("src.integrations.connection_registry.SupabaseClient") as mock_sb:
            mock_client = MagicMock()
            mock_sb.get_client.return_value = mock_client
            mock_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock()

            await registry.mark_connection_expired("user-1", "GMAIL")

            # Verify update was called with status=expired
            mock_client.table.assert_called_with("user_connections")
            update_call = mock_client.table.return_value.update.call_args
            assert update_call[0][0]["status"] == "expired"

            # Verify audit was called
            registry._audit.assert_awaited_once()
            audit_call = registry._audit.call_args
            assert audit_call.kwargs["action"] == "mark_expired"


# ---------------------------------------------------------------------------
# OODA Orient connection awareness tests
# ---------------------------------------------------------------------------


class TestOODAOrientConnectionAwareness:
    """Tests for _orient_with_connections method."""

    @pytest.mark.asyncio
    async def test_orient_no_gaps_returns_unchanged(self):
        """When goal has no capability gaps, orientation should pass through."""
        from src.core.ooda import OODALoop

        ooda = OODALoop(
            llm_client=MagicMock(),
            episodic_memory=MagicMock(),
            semantic_memory=MagicMock(),
            working_memory=MagicMock(user_id="test-user"),
            user_id="test-user",
        )

        with patch("src.db.supabase.SupabaseClient") as mock_sb:
            mock_client = MagicMock()
            mock_sb.get_client.return_value = mock_client
            # Goal has no capability_gaps
            mock_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
                data={"config": {}, "status": "active"}
            )

            result = await ooda._orient_with_connections(
                goal_id="test-goal",
                user_id="test-user",
                existing_orientation={"patterns": [], "opportunities": []},
            )

            assert result["patterns"] == []
            assert not result["connection_changes"]["new_connections_detected"]

    @pytest.mark.asyncio
    async def test_orient_detects_resolved_gaps(self):
        """Orient should detect when new connections resolve capability gaps."""
        from src.core.ooda import OODALoop

        ooda = OODALoop(
            llm_client=MagicMock(),
            episodic_memory=MagicMock(),
            semantic_memory=MagicMock(),
            working_memory=MagicMock(user_id="test-user"),
            user_id="test-user",
        )

        mock_provider = MagicMock()
        mock_provider.quality_score = 0.9

        with patch("src.db.supabase.SupabaseClient") as mock_sb, \
             patch("src.integrations.connection_registry.get_connection_registry") as mock_reg, \
             patch("src.services.capability_provisioning.CapabilityGraphService") as mock_graph_cls:

            mock_client = MagicMock()
            mock_sb.get_client.return_value = mock_client

            # Goal has blocking capability_gaps
            mock_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
                data={
                    "config": {
                        "capability_gaps": [
                            {"capability": "read_crm_pipeline", "severity": "blocking"}
                        ],
                        "capability_assessed_at": (
                            datetime.now(UTC) - timedelta(hours=2)
                        ).isoformat(),
                    },
                    "status": "active",
                }
            )

            # User recently connected SALESFORCE
            mock_registry = MagicMock()
            mock_registry.get_recently_added_connections = AsyncMock(
                return_value=[
                    {"toolkit_slug": "SALESFORCE", "updated_at": datetime.now(UTC).isoformat()}
                ]
            )
            mock_reg.return_value = mock_registry

            # CapabilityGraphService says read_crm_pipeline now has a provider
            mock_graph = MagicMock()
            mock_graph.get_best_available = AsyncMock(return_value=mock_provider)
            mock_graph_cls.return_value = mock_graph

            result = await ooda._orient_with_connections(
                goal_id="test-goal",
                user_id="test-user",
                existing_orientation={"patterns": [], "opportunities": []},
            )

            assert result["connection_changes"]["new_connections_detected"]
            assert "read_crm_pipeline" in result["connection_changes"]["resolved_gaps"]
            assert result["connection_changes"]["recommendation"] == "resume_blocked_tasks"

    @pytest.mark.asyncio
    async def test_orient_no_recent_connections(self):
        """When no recent connections, gaps remain blocked."""
        from src.core.ooda import OODALoop

        ooda = OODALoop(
            llm_client=MagicMock(),
            episodic_memory=MagicMock(),
            semantic_memory=MagicMock(),
            working_memory=MagicMock(user_id="test-user"),
            user_id="test-user",
        )

        with patch("src.db.supabase.SupabaseClient") as mock_sb, \
             patch("src.integrations.connection_registry.get_connection_registry") as mock_reg:

            mock_client = MagicMock()
            mock_sb.get_client.return_value = mock_client

            mock_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
                data={
                    "config": {
                        "capability_gaps": [
                            {"capability": "read_email", "severity": "blocking"}
                        ],
                    },
                    "status": "active",
                }
            )

            mock_registry = MagicMock()
            mock_registry.get_recently_added_connections = AsyncMock(return_value=[])
            mock_reg.return_value = mock_registry

            result = await ooda._orient_with_connections(
                goal_id="test-goal",
                user_id="test-user",
                existing_orientation={"patterns": []},
            )

            assert not result["connection_changes"]["new_connections_detected"]
            assert "read_email" in result["connection_changes"]["still_blocked"]
            assert result["connection_changes"]["recommendation"] is None


# ---------------------------------------------------------------------------
# OODA Decide tests
# ---------------------------------------------------------------------------


class TestOODADecideResumeBlocked:
    """Tests for resume_blocked_tasks decision in Decide phase."""

    @pytest.mark.asyncio
    async def test_decide_auto_selects_resume_when_gaps_resolved(self):
        """Decide should auto-select resume_blocked_tasks when Orient recommends it."""
        from src.core.ooda import OODAConfig, OODALoop, OODAPhase, OODAState

        ooda = OODALoop(
            llm_client=MagicMock(),
            episodic_memory=MagicMock(),
            semantic_memory=MagicMock(),
            working_memory=MagicMock(user_id="test-user"),
            user_id="test-user",
        )

        state = OODAState(goal_id="test-goal")
        state.orientation = {
            "patterns": [],
            "connection_changes": {
                "new_connections_detected": True,
                "resolved_gaps": ["read_crm_pipeline"],
                "still_blocked": [],
                "recommendation": "resume_blocked_tasks",
            },
        }

        goal = {"id": "test-goal", "title": "Test Goal", "description": "Test"}

        state = await ooda.decide(state, goal)

        assert state.decision is not None
        assert state.decision["action"] == "resume_blocked_tasks"
        assert "read_crm_pipeline" in state.decision["resolved_capabilities"]
        assert state.current_phase == OODAPhase.ACT

    @pytest.mark.asyncio
    async def test_decide_falls_through_when_no_recommendation(self):
        """Decide should proceed with LLM when no resume recommendation."""
        from src.core.ooda import OODAConfig, OODALoop, OODAState

        mock_llm = MagicMock()
        mock_llm.generate_response = AsyncMock(return_value='{"action": "research", "agent": "analyst", "parameters": {}, "reasoning": "test"}')

        ooda = OODALoop(
            llm_client=mock_llm,
            episodic_memory=MagicMock(),
            semantic_memory=MagicMock(),
            working_memory=MagicMock(user_id="test-user"),
            user_id=None,  # Disable extended thinking
        )

        state = OODAState(goal_id="test-goal")
        state.orientation = {
            "patterns": [],
            "connection_changes": {
                "new_connections_detected": False,
                "resolved_gaps": [],
                "still_blocked": ["read_email"],
                "recommendation": None,
            },
        }

        goal = {"id": "test-goal", "title": "Test Goal", "description": "Test"}

        state = await ooda.decide(state, goal)

        assert state.decision is not None
        assert state.decision["action"] == "research"
        mock_llm.generate_response.assert_awaited_once()


# ---------------------------------------------------------------------------
# OODA Act resume handler tests
# ---------------------------------------------------------------------------


class TestOODAActResume:
    """Tests for _resume_blocked_tasks Act handler."""

    @pytest.mark.asyncio
    async def test_resume_no_blocked_tasks(self):
        """When no blocked tasks exist, should return no_blocked_tasks."""
        from src.core.ooda import OODALoop

        ooda = OODALoop(
            llm_client=MagicMock(),
            episodic_memory=MagicMock(),
            semantic_memory=MagicMock(),
            working_memory=MagicMock(user_id="test-user"),
            user_id="test-user",
        )

        with patch("src.db.supabase.SupabaseClient") as mock_sb:
            mock_client = MagicMock()
            mock_sb.get_client.return_value = mock_client
            mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[]
            )

            result = await ooda._resume_blocked_tasks(
                goal_id="test-goal",
                user_id="test-user",
                resolved_capabilities=["read_crm_pipeline"],
            )

            assert result["status"] == "no_blocked_tasks"
            assert result["resumed_count"] == 0

    @pytest.mark.asyncio
    async def test_resume_updates_blocked_agents(self):
        """Should update blocked agents to running and call GoalExecutionService."""
        from src.core.ooda import OODALoop

        ooda = OODALoop(
            llm_client=MagicMock(),
            episodic_memory=MagicMock(),
            semantic_memory=MagicMock(),
            working_memory=MagicMock(user_id="test-user"),
            user_id="test-user",
        )

        with patch("src.db.supabase.SupabaseClient") as mock_sb, \
             patch("src.services.goal_execution.GoalExecutionService") as mock_exec_cls, \
             patch("src.core.ws.ws_manager") as mock_ws:

            mock_client = MagicMock()
            mock_sb.get_client.return_value = mock_client

            # Blocked agents
            mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[
                    {
                        "id": "agent-1",
                        "agent_type": "hunter",
                        "agent_config": {"blocked_by": "read_crm_pipeline"},
                    }
                ]
            )

            # Goal config for gap update
            mock_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
                data={
                    "config": {
                        "capability_gaps": [
                            {"capability": "read_crm_pipeline", "severity": "blocking"}
                        ]
                    }
                }
            )

            mock_exec = MagicMock()
            mock_exec.resume_blocked_tasks = AsyncMock()
            mock_exec_cls.return_value = mock_exec

            mock_ws.send_to_user = AsyncMock()

            result = await ooda._resume_blocked_tasks(
                goal_id="test-goal",
                user_id="test-user",
                resolved_capabilities=["read_crm_pipeline"],
            )

            assert result["status"] == "tasks_resumed"
            assert result["resumed_count"] == 1
            mock_exec.resume_blocked_tasks.assert_awaited_once()


# ---------------------------------------------------------------------------
# Connection health monitor tests
# ---------------------------------------------------------------------------


class TestConnectionHealthCheck:
    """Tests for the connection health check scheduler job."""

    @pytest.mark.asyncio
    async def test_get_health_check_action_mapping(self):
        """Health check action should map known toolkits correctly."""
        from src.services.scheduler import _get_health_check_action

        assert _get_health_check_action("GMAIL") == "GMAIL_LIST_MESSAGES"
        assert _get_health_check_action("SALESFORCE") == "SALESFORCE_GET_USER_INFO"
        assert _get_health_check_action("SLACK") == "SLACK_AUTH_TEST"
        assert _get_health_check_action("UNKNOWN_TOOL") is None
        assert _get_health_check_action("gmail") == "GMAIL_LIST_MESSAGES"

    @pytest.mark.asyncio
    async def test_health_check_marks_expired_on_auth_failure(self):
        """Health check should mark connection as expired on 401 error."""
        from src.services.scheduler import _run_connection_health_check

        with patch("src.db.supabase.SupabaseClient") as mock_sb, \
             patch("src.integrations.connection_registry.get_connection_registry") as mock_reg, \
             patch("src.integrations.composio_sessions.get_session_manager") as mock_session:

            mock_client = MagicMock()
            mock_sb.get_client.return_value = mock_client

            mock_client.table.return_value.select.return_value.eq.return_value.or_.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[
                    {
                        "id": "conn-1",
                        "user_id": "user-1",
                        "toolkit_slug": "GMAIL",
                        "composio_connection_id": "comp-1",
                        "last_health_check_at": None,
                        "failure_count": 0,
                    }
                ]
            )

            # Simulate 401 auth error
            mock_mgr = MagicMock()
            mock_mgr.execute_action = AsyncMock(side_effect=Exception("401 Unauthorized"))
            mock_session.return_value = mock_mgr

            mock_registry = MagicMock()
            mock_registry.mark_connection_expired = AsyncMock()
            mock_reg.return_value = mock_registry

            await _run_connection_health_check()

            mock_registry.mark_connection_expired.assert_awaited_once_with("user-1", "GMAIL")

    @pytest.mark.asyncio
    async def test_health_check_updates_timestamp_on_success(self):
        """Health check should update last_health_check_at and reset failure_count on success."""
        from src.services.scheduler import _run_connection_health_check

        with patch("src.db.supabase.SupabaseClient") as mock_sb, \
             patch("src.integrations.connection_registry.get_connection_registry") as mock_reg, \
             patch("src.integrations.composio_sessions.get_session_manager") as mock_session:

            mock_client = MagicMock()
            mock_sb.get_client.return_value = mock_client

            # Connection with previous failures
            mock_client.table.return_value.select.return_value.eq.return_value.or_.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[
                    {
                        "id": "conn-1",
                        "user_id": "user-1",
                        "toolkit_slug": "GMAIL",
                        "composio_connection_id": "comp-1",
                        "last_health_check_at": None,
                        "failure_count": 2,  # Had previous transient errors
                    }
                ]
            )

            # Successful API call
            mock_mgr = MagicMock()
            mock_mgr.execute_action = AsyncMock(return_value={"messages": []})
            mock_session.return_value = mock_mgr

            mock_registry = MagicMock()
            mock_registry.mark_connection_expired = AsyncMock()
            mock_reg.return_value = mock_registry

            await _run_connection_health_check()

            # Should NOT mark as expired
            mock_registry.mark_connection_expired.assert_not_awaited()

            # Should update last_health_check_at and reset failure_count
            update_call = mock_client.table.return_value.update.call_args
            assert update_call is not None
            update_data = update_call[0][0]
            assert "last_health_check_at" in update_data
            assert update_data["failure_count"] == 0

    @pytest.mark.asyncio
    async def test_health_check_increments_failure_count_on_transient_error(self):
        """Health check should increment failure_count but NOT expire on transient errors."""
        from src.services.scheduler import _run_connection_health_check

        with patch("src.db.supabase.SupabaseClient") as mock_sb, \
             patch("src.integrations.connection_registry.get_connection_registry") as mock_reg, \
             patch("src.integrations.composio_sessions.get_session_manager") as mock_session:

            mock_client = MagicMock()
            mock_sb.get_client.return_value = mock_client

            mock_client.table.return_value.select.return_value.eq.return_value.or_.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[
                    {
                        "id": "conn-1",
                        "user_id": "user-1",
                        "toolkit_slug": "GMAIL",
                        "composio_connection_id": "comp-1",
                        "last_health_check_at": None,
                        "failure_count": 1,
                    }
                ]
            )

            # Transient error (not auth-related)
            mock_mgr = MagicMock()
            mock_mgr.execute_action = AsyncMock(side_effect=Exception("Network timeout"))
            mock_session.return_value = mock_mgr

            mock_registry = MagicMock()
            mock_registry.mark_connection_expired = AsyncMock()
            mock_reg.return_value = mock_registry

            await _run_connection_health_check()

            # Should NOT mark as expired for transient errors
            mock_registry.mark_connection_expired.assert_not_awaited()

            # Should increment failure_count
            update_call = mock_client.table.return_value.update.call_args
            assert update_call is not None
            update_data = update_call[0][0]
            assert "last_health_check_at" in update_data
            assert update_data["failure_count"] == 2  # 1 + 1


# ---------------------------------------------------------------------------
# Composio webhook handler tests
# ---------------------------------------------------------------------------


class TestComposioWebhookHandler:
    """Tests for the Composio connection webhook endpoint."""

    @pytest.mark.asyncio
    async def test_resolve_entity_to_user(self):
        """Should resolve aria_user_ entity to user UUID."""
        from src.api.routes.integrations import _resolve_entity_to_user

        with patch("src.db.supabase.SupabaseClient") as mock_sb:
            mock_client = MagicMock()
            mock_sb.get_client.return_value = mock_client
            mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value.maybe_single.return_value.execute.return_value = MagicMock(
                data={"user_id": "abc-123-full-uuid"}
            )

            user_id = await _resolve_entity_to_user("aria_user_abc123def456")
            assert user_id == "abc-123-full-uuid"

    @pytest.mark.asyncio
    async def test_resolve_unknown_entity_returns_none(self):
        """Should return None for non-aria entities."""
        from src.api.routes.integrations import _resolve_entity_to_user

        result = await _resolve_entity_to_user("unknown_entity_123")
        assert result is None

        result = await _resolve_entity_to_user("")
        assert result is None


# ---------------------------------------------------------------------------
# GoalExecutionService.resume_blocked_tasks tests
# ---------------------------------------------------------------------------


class TestGoalExecutionServiceResume:
    """Tests for GoalExecutionService.resume_blocked_tasks."""

    @pytest.mark.asyncio
    async def test_resume_no_blocked_agents(self):
        """Should return early when no blocked agents exist."""
        from src.services.goal_execution import GoalExecutionService

        service = GoalExecutionService()

        with patch.object(service, "_db") as mock_db:
            mock_db.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
                data=[]
            )

            # Should not raise
            await service.resume_blocked_tasks(
                goal_id="test-goal",
                user_id="test-user",
                resolved_capabilities=["read_crm_pipeline"],
            )

    @pytest.mark.asyncio
    async def test_resume_executes_unblocked_agents(self):
        """Should execute agents whose blocking capability is now resolved."""
        from src.services.goal_execution import GoalExecutionService

        service = GoalExecutionService()

        with patch.object(service, "_db") as mock_db, \
             patch.object(service, "_execute_agent", new_callable=AsyncMock) as mock_exec, \
             patch.object(service, "_gather_execution_context", new_callable=AsyncMock) as mock_ctx:

            # Blocked agents
            mock_db.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
                data=[
                    {
                        "id": "agent-1",
                        "agent_type": "hunter",
                        "agent_config": {"blocked_by": "read_crm_pipeline"},
                    }
                ]
            )

            # Goal data
            mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
                data={"id": "test-goal", "title": "Test", "config": {}}
            )

            # Context
            mock_ctx.return_value = {"profile": {}}

            # Progress recalculation
            mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"status": "complete"}]
            )

            mock_exec.return_value = {"success": True}

            await service.resume_blocked_tasks(
                goal_id="test-goal",
                user_id="test-user",
                resolved_capabilities=["read_crm_pipeline"],
            )

            mock_exec.assert_awaited_once()
