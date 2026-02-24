"""Tests for DelegationTraceService — immutable delegation audit trail."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from src.core.delegation_trace import DelegationTrace, DelegationTraceService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_execute(data: list | dict | None = None) -> MagicMock:
    """Mock Supabase .execute() return."""
    result = MagicMock()
    result.data = data
    return result


def _build_chain(execute_return: list | dict | None = None) -> MagicMock:
    """Build a fluent Supabase query chain mock."""
    chain = MagicMock()
    for method in (
        "select",
        "insert",
        "update",
        "eq",
        "order",
        "limit",
        "single",
        "maybe_single",
        "is_",
    ):
        getattr(chain, method).return_value = chain
    chain.execute.return_value = _mock_execute(execute_return)
    return chain


TRACE_ROW = {
    "trace_id": str(uuid.uuid4()),
    "goal_id": str(uuid.uuid4()),
    "parent_trace_id": None,
    "user_id": str(uuid.uuid4()),
    "delegator": "orchestrator",
    "delegatee": "analyst",
    "task_description": "Research BioGenix pipeline",
    "task_characteristics": {"risk_score": 0.35, "complexity": 0.4},
    "capability_token": {"allowed": ["read_pubmed"]},
    "inputs": {"query": "BioGenix clinical trials"},
    "outputs": None,
    "thinking_trace": None,
    "verification_result": None,
    "approval_record": None,
    "cost_usd": 0,
    "status": "dispatched",
    "started_at": datetime.now(UTC).isoformat(),
    "completed_at": None,
    "duration_ms": None,
    "created_at": datetime.now(UTC).isoformat(),
}


# ---------------------------------------------------------------------------
# DelegationTrace dataclass
# ---------------------------------------------------------------------------


class TestDelegationTrace:
    """Tests for the DelegationTrace dataclass."""

    def test_from_dict_creates_instance(self) -> None:
        trace = DelegationTrace.from_dict(TRACE_ROW)
        assert trace.trace_id == TRACE_ROW["trace_id"]
        assert trace.delegator == "orchestrator"
        assert trace.delegatee == "analyst"
        assert trace.status == "dispatched"

    def test_to_dict_round_trips(self) -> None:
        trace = DelegationTrace.from_dict(TRACE_ROW)
        d = trace.to_dict()
        assert d["delegator"] == "orchestrator"
        assert d["delegatee"] == "analyst"
        assert d["trace_id"] == TRACE_ROW["trace_id"]

    def test_is_terminal_for_completed(self) -> None:
        row = {**TRACE_ROW, "status": "completed"}
        trace = DelegationTrace.from_dict(row)
        assert trace.is_terminal is True

    def test_is_terminal_for_dispatched(self) -> None:
        trace = DelegationTrace.from_dict(TRACE_ROW)
        assert trace.is_terminal is False


# ---------------------------------------------------------------------------
# DelegationTraceService
# ---------------------------------------------------------------------------


class TestDelegationTraceService:
    """Tests for DelegationTraceService CRUD operations."""

    @pytest.fixture()
    def mock_db(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture()
    def service(self, mock_db: MagicMock) -> DelegationTraceService:
        svc = DelegationTraceService.__new__(DelegationTraceService)
        svc._client = mock_db
        return svc

    @pytest.mark.asyncio
    async def test_start_trace_returns_trace_id(
        self, service: DelegationTraceService, mock_db: MagicMock
    ) -> None:
        inserted = {**TRACE_ROW}
        mock_db.table.return_value = _build_chain([inserted])

        trace_id = await service.start_trace(
            user_id=TRACE_ROW["user_id"],
            goal_id=TRACE_ROW["goal_id"],
            delegator="orchestrator",
            delegatee="analyst",
            task_description="Research BioGenix pipeline",
            task_characteristics={"risk_score": 0.35},
            capability_token={"allowed": ["read_pubmed"]},
            inputs={"query": "BioGenix clinical trials"},
        )

        assert isinstance(trace_id, str)
        mock_db.table.assert_called_with("delegation_traces")

    @pytest.mark.asyncio
    async def test_complete_trace_sets_status_and_outputs(
        self, service: DelegationTraceService, mock_db: MagicMock
    ) -> None:
        completed_row = {
            **TRACE_ROW,
            "status": "completed",
            "outputs": {"summary": "Found 3 trials"},
            "cost_usd": 0.0042,
        }
        mock_db.table.return_value = _build_chain([completed_row])

        await service.complete_trace(
            trace_id=TRACE_ROW["trace_id"],
            outputs={"summary": "Found 3 trials"},
            verification_result={"passed": True},
            cost_usd=0.0042,
            status="completed",
        )

        mock_db.table.assert_called_with("delegation_traces")

    @pytest.mark.asyncio
    async def test_fail_trace_records_error(
        self, service: DelegationTraceService, mock_db: MagicMock
    ) -> None:
        failed_row = {**TRACE_ROW, "status": "failed"}
        mock_db.table.return_value = _build_chain([failed_row])

        await service.fail_trace(
            trace_id=TRACE_ROW["trace_id"],
            error_message="PubMed API timeout",
        )

        mock_db.table.assert_called_with("delegation_traces")

    @pytest.mark.asyncio
    async def test_get_trace_tree_returns_ordered_list(
        self, service: DelegationTraceService, mock_db: MagicMock
    ) -> None:
        parent_id = str(uuid.uuid4())
        child_id = str(uuid.uuid4())
        goal = str(uuid.uuid4())
        rows = [
            {**TRACE_ROW, "trace_id": parent_id, "goal_id": goal, "parent_trace_id": None},
            {
                **TRACE_ROW,
                "trace_id": child_id,
                "goal_id": goal,
                "parent_trace_id": parent_id,
            },
        ]
        mock_db.table.return_value = _build_chain(rows)

        tree = await service.get_trace_tree(goal_id=goal)

        assert len(tree) == 2
        assert tree[0].trace_id == parent_id
        assert tree[1].parent_trace_id == parent_id

    @pytest.mark.asyncio
    async def test_get_user_traces_respects_limit(
        self, service: DelegationTraceService, mock_db: MagicMock
    ) -> None:
        rows = [TRACE_ROW]
        mock_db.table.return_value = _build_chain(rows)

        traces = await service.get_user_traces(
            user_id=TRACE_ROW["user_id"],
            limit=5,
        )

        assert len(traces) == 1
        assert traces[0].delegator == "orchestrator"

    @pytest.mark.asyncio
    async def test_cost_tracking_per_trace(
        self, service: DelegationTraceService, mock_db: MagicMock
    ) -> None:
        """Verify cost_usd is stored on complete_trace."""
        row = {**TRACE_ROW, "cost_usd": 0.1234, "status": "completed"}
        mock_db.table.return_value = _build_chain([row])

        await service.complete_trace(
            trace_id=TRACE_ROW["trace_id"],
            outputs={"data": "result"},
            verification_result=None,
            cost_usd=0.1234,
            status="completed",
        )

        # Verify the update call included cost_cents (cost_usd * 100, truncated to int)
        update_call = mock_db.table.return_value.update
        update_call.assert_called_once()
        update_data = update_call.call_args[0][0]
        assert update_data["cost_cents"] == 12
