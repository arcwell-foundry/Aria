"""Tests for workflow API routes."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from src.api.deps import get_current_user
from src.main import app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_current_user() -> MagicMock:
    """Create mock current user."""
    user = MagicMock()
    user.id = "test-user-123"
    user.email = "test@example.com"
    return user


@pytest.fixture
def test_client(mock_current_user: MagicMock) -> TestClient:
    """Create test client with mocked authentication."""

    async def override_get_current_user() -> MagicMock:
        return mock_current_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    client = TestClient(app)
    yield client  # type: ignore[misc]
    app.dependency_overrides.clear()


@pytest.fixture
def sample_workflow_row() -> dict:
    """Sample procedural_memories row as returned by Supabase."""
    now = datetime.now(UTC).isoformat()
    return {
        "id": str(uuid.uuid4()),
        "user_id": "test-user-123",
        "workflow_name": "Morning Prep",
        "description": "Daily briefing workflow",
        "trigger_conditions": {
            "type": "time",
            "cron_expression": "0 6 * * 1-5",
            "metadata": {
                "category": "productivity",
                "icon": "sun",
                "color": "#F59E0B",
                "enabled": True,
                "run_count": 0,
            },
        },
        "steps": [
            {
                "step_id": "briefing",
                "action_type": "run_skill",
                "config": {"skill_id": "morning-briefing"},
                "requires_approval": False,
                "timeout_seconds": 60,
                "on_failure": "stop",
            }
        ],
        "success_count": 5,
        "failure_count": 1,
        "is_shared": False,
        "version": 1,
        "created_at": now,
        "updated_at": now,
    }


# ---------------------------------------------------------------------------
# Pydantic model validation tests
# ---------------------------------------------------------------------------


class TestRequestResponseModels:
    """Test that request/response Pydantic models are valid."""

    def test_create_workflow_request_model(self) -> None:
        """Test CreateWorkflowRequest validates correctly."""
        from src.api.routes.workflows import CreateWorkflowRequest

        req = CreateWorkflowRequest(
            name="Test Workflow",
            description="A test",
            trigger={"type": "time", "cron_expression": "0 9 * * 1-5"},
            actions=[
                {
                    "step_id": "s1",
                    "action_type": "run_skill",
                    "config": {"skill_id": "test"},
                }
            ],
            metadata={"category": "productivity"},
        )
        assert req.name == "Test Workflow"
        assert req.trigger["type"] == "time"
        assert len(req.actions) == 1

    def test_update_workflow_request_model_partial(self) -> None:
        """Test UpdateWorkflowRequest accepts partial updates."""
        from src.api.routes.workflows import UpdateWorkflowRequest

        req = UpdateWorkflowRequest(name="Updated Name")
        assert req.name == "Updated Name"
        assert req.description is None
        assert req.trigger is None
        assert req.actions is None
        assert req.metadata is None

    def test_workflow_response_model(self) -> None:
        """Test WorkflowResponse model validates correctly."""
        from src.api.routes.workflows import WorkflowResponse

        resp = WorkflowResponse(
            id="wf-123",
            name="My Workflow",
            description="Does things",
            trigger={"type": "event", "event_type": "meeting_completed"},
            actions=[],
            metadata={"category": "follow_up"},
            is_shared=False,
            enabled=True,
            success_count=10,
            failure_count=2,
            version=3,
        )
        assert resp.id == "wf-123"
        assert resp.version == 3
        assert resp.success_count == 10

    def test_execute_workflow_request_model(self) -> None:
        """Test ExecuteWorkflowRequest validates correctly."""
        from src.api.routes.workflows import ExecuteWorkflowRequest

        req = ExecuteWorkflowRequest(trigger_context={"event_type": "meeting_completed"})
        assert req.trigger_context["event_type"] == "meeting_completed"

    def test_execute_workflow_request_default_context(self) -> None:
        """Test ExecuteWorkflowRequest defaults to empty context."""
        from src.api.routes.workflows import ExecuteWorkflowRequest

        req = ExecuteWorkflowRequest()
        assert req.trigger_context == {}


# ---------------------------------------------------------------------------
# Endpoint existence tests
# ---------------------------------------------------------------------------


class TestEndpointFunctions:
    """Test that all endpoint functions exist and are callable."""

    def test_list_prebuilt_workflows_exists(self) -> None:
        """Test list_prebuilt_workflows endpoint function exists."""
        from src.api.routes.workflows import list_prebuilt_workflows

        assert callable(list_prebuilt_workflows)

    def test_list_workflows_exists(self) -> None:
        """Test list_workflows endpoint function exists."""
        from src.api.routes.workflows import list_workflows

        assert callable(list_workflows)

    def test_create_workflow_exists(self) -> None:
        """Test create_workflow endpoint function exists."""
        from src.api.routes.workflows import create_workflow

        assert callable(create_workflow)

    def test_get_workflow_exists(self) -> None:
        """Test get_workflow endpoint function exists."""
        from src.api.routes.workflows import get_workflow

        assert callable(get_workflow)

    def test_update_workflow_exists(self) -> None:
        """Test update_workflow endpoint function exists."""
        from src.api.routes.workflows import update_workflow

        assert callable(update_workflow)

    def test_delete_workflow_exists(self) -> None:
        """Test delete_workflow endpoint function exists."""
        from src.api.routes.workflows import delete_workflow

        assert callable(delete_workflow)

    def test_execute_workflow_exists(self) -> None:
        """Test execute_workflow endpoint function exists."""
        from src.api.routes.workflows import execute_workflow

        assert callable(execute_workflow)


# ---------------------------------------------------------------------------
# Route prefix tests
# ---------------------------------------------------------------------------


class TestRoutePrefix:
    """Test that the router uses the /workflows prefix."""

    def test_router_prefix_is_workflows(self) -> None:
        """Test the router prefix is /workflows."""
        from src.api.routes.workflows import router

        assert router.prefix == "/workflows"

    def test_router_tags_include_workflows(self) -> None:
        """Test the router tags include 'workflows'."""
        from src.api.routes.workflows import router

        assert "workflows" in router.tags


# ---------------------------------------------------------------------------
# GET /workflows/prebuilt tests
# ---------------------------------------------------------------------------


class TestListPrebuiltWorkflows:
    """Test the prebuilt workflows endpoint."""

    def test_get_prebuilt_returns_200(self, test_client: TestClient) -> None:
        """Test GET /workflows/prebuilt returns 200 with prebuilt workflows."""
        response = test_client.get("/api/v1/workflows/prebuilt")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1  # At least one prebuilt workflow

    def test_prebuilt_workflows_have_required_fields(self, test_client: TestClient) -> None:
        """Test that prebuilt workflows contain required response fields."""
        response = test_client.get("/api/v1/workflows/prebuilt")
        data = response.json()
        for wf in data:
            assert "id" in wf
            assert "name" in wf
            assert "trigger" in wf
            assert "actions" in wf
            assert "is_shared" in wf
            assert wf["is_shared"] is True


# ---------------------------------------------------------------------------
# GET /workflows tests
# ---------------------------------------------------------------------------


class TestListWorkflows:
    """Test the list workflows endpoint."""

    def test_list_workflows_returns_200(self, test_client: TestClient) -> None:
        """Test GET /workflows returns 200 with user workflows."""
        with patch("src.api.routes.workflows.ProceduralMemory") as mock_memory_cls:
            mock_memory = MagicMock()
            mock_memory.list_workflows = AsyncMock(return_value=[])
            mock_memory_cls.return_value = mock_memory

            response = test_client.get("/api/v1/workflows/")
            assert response.status_code == status.HTTP_200_OK
            assert isinstance(response.json(), list)

    def test_list_workflows_include_shared_param(self, test_client: TestClient) -> None:
        """Test GET /workflows respects include_shared query param."""
        with patch("src.api.routes.workflows.ProceduralMemory") as mock_memory_cls:
            mock_memory = MagicMock()
            mock_memory.list_workflows = AsyncMock(return_value=[])
            mock_memory_cls.return_value = mock_memory

            response = test_client.get("/api/v1/workflows/?include_shared=false")
            assert response.status_code == status.HTTP_200_OK
            mock_memory.list_workflows.assert_called_once_with(
                "test-user-123", include_shared=False
            )


# ---------------------------------------------------------------------------
# POST /workflows tests
# ---------------------------------------------------------------------------


class TestCreateWorkflow:
    """Test the create workflow endpoint."""

    def test_create_workflow_returns_201(self, test_client: TestClient) -> None:
        """Test POST /workflows returns 201 on success."""
        with patch("src.api.routes.workflows.ProceduralMemory") as mock_memory_cls:
            mock_memory = MagicMock()
            workflow_id = str(uuid.uuid4())
            mock_memory.create_workflow = AsyncMock(return_value=workflow_id)
            mock_memory_cls.return_value = mock_memory

            response = test_client.post(
                "/api/v1/workflows/",
                json={
                    "name": "New Workflow",
                    "description": "A new workflow",
                    "trigger": {
                        "type": "event",
                        "event_type": "meeting_completed",
                    },
                    "actions": [
                        {
                            "step_id": "s1",
                            "action_type": "run_skill",
                            "config": {"skill_id": "test"},
                        }
                    ],
                    "metadata": {"category": "follow_up"},
                },
            )
            assert response.status_code == status.HTTP_201_CREATED
            data = response.json()
            assert data["id"] == workflow_id
            assert data["name"] == "New Workflow"

    def test_create_workflow_validates_trigger(self, test_client: TestClient) -> None:
        """Test POST /workflows returns 422 for invalid trigger."""
        response = test_client.post(
            "/api/v1/workflows/",
            json={
                "name": "Bad Trigger",
                "trigger": "not-a-dict",
                "actions": [],
                "metadata": {"category": "productivity"},
            },
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# ---------------------------------------------------------------------------
# GET /workflows/{workflow_id} tests
# ---------------------------------------------------------------------------


class TestGetWorkflow:
    """Test the get workflow endpoint."""

    def test_get_workflow_returns_200(
        self, test_client: TestClient, sample_workflow_row: dict
    ) -> None:
        """Test GET /workflows/{id} returns 200 for existing workflow."""
        from src.memory.procedural import Workflow

        wf = Workflow.from_dict(sample_workflow_row)
        with patch("src.api.routes.workflows.ProceduralMemory") as mock_memory_cls:
            mock_memory = MagicMock()
            mock_memory.get_workflow = AsyncMock(return_value=wf)
            mock_memory_cls.return_value = mock_memory

            response = test_client.get(f"/api/v1/workflows/{sample_workflow_row['id']}")
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["name"] == "Morning Prep"

    def test_get_workflow_returns_404(self, test_client: TestClient) -> None:
        """Test GET /workflows/{id} returns 404 for missing workflow."""
        from src.core.exceptions import WorkflowNotFoundError

        with patch("src.api.routes.workflows.ProceduralMemory") as mock_memory_cls:
            mock_memory = MagicMock()
            mock_memory.get_workflow = AsyncMock(side_effect=WorkflowNotFoundError("nonexistent"))
            mock_memory_cls.return_value = mock_memory

            response = test_client.get("/api/v1/workflows/nonexistent")
            assert response.status_code == status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# PUT /workflows/{workflow_id} tests
# ---------------------------------------------------------------------------


class TestUpdateWorkflow:
    """Test the update workflow endpoint."""

    def test_update_workflow_returns_200(
        self, test_client: TestClient, sample_workflow_row: dict
    ) -> None:
        """Test PUT /workflows/{id} returns 200 on success."""
        from src.memory.procedural import Workflow

        wf = Workflow.from_dict(sample_workflow_row)
        with patch("src.api.routes.workflows.ProceduralMemory") as mock_memory_cls:
            mock_memory = MagicMock()
            mock_memory.get_workflow = AsyncMock(return_value=wf)
            mock_memory.update_workflow = AsyncMock(return_value=None)
            mock_memory_cls.return_value = mock_memory

            response = test_client.put(
                f"/api/v1/workflows/{sample_workflow_row['id']}",
                json={"name": "Updated Name"},
            )
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["name"] == "Updated Name"


# ---------------------------------------------------------------------------
# DELETE /workflows/{workflow_id} tests
# ---------------------------------------------------------------------------


class TestDeleteWorkflow:
    """Test the delete workflow endpoint."""

    def test_delete_workflow_returns_200(
        self, test_client: TestClient, sample_workflow_row: dict
    ) -> None:
        """Test DELETE /workflows/{id} returns 200 on success."""
        with patch("src.api.routes.workflows.ProceduralMemory") as mock_memory_cls:
            mock_memory = MagicMock()
            mock_memory.delete_workflow = AsyncMock(return_value=None)
            mock_memory_cls.return_value = mock_memory

            response = test_client.delete(f"/api/v1/workflows/{sample_workflow_row['id']}")
            assert response.status_code == status.HTTP_200_OK

    def test_delete_workflow_returns_404(self, test_client: TestClient) -> None:
        """Test DELETE /workflows/{id} returns 404 for missing workflow."""
        from src.core.exceptions import WorkflowNotFoundError

        with patch("src.api.routes.workflows.ProceduralMemory") as mock_memory_cls:
            mock_memory = MagicMock()
            mock_memory.delete_workflow = AsyncMock(
                side_effect=WorkflowNotFoundError("nonexistent")
            )
            mock_memory_cls.return_value = mock_memory

            response = test_client.delete("/api/v1/workflows/nonexistent")
            assert response.status_code == status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# POST /workflows/{workflow_id}/execute tests
# ---------------------------------------------------------------------------


class TestExecuteWorkflow:
    """Test the execute workflow endpoint."""

    def test_execute_workflow_returns_200(
        self, test_client: TestClient, sample_workflow_row: dict
    ) -> None:
        """Test POST /workflows/{id}/execute returns 200 on success."""
        from src.memory.procedural import Workflow
        from src.skills.workflows.models import WorkflowRunStatus

        wf = Workflow.from_dict(sample_workflow_row)
        run_status = WorkflowRunStatus(
            workflow_id=wf.id,
            status="completed",
            steps_completed=1,
            steps_total=1,
            step_outputs={},
        )

        with (
            patch("src.api.routes.workflows.ProceduralMemory") as mock_memory_cls,
            patch("src.api.routes.workflows.WorkflowEngine") as mock_engine_cls,
        ):
            mock_memory = MagicMock()
            mock_memory.get_workflow = AsyncMock(return_value=wf)
            mock_memory.record_outcome = AsyncMock(return_value=None)
            mock_memory_cls.return_value = mock_memory

            mock_engine = MagicMock()
            mock_engine.execute = AsyncMock(return_value=run_status)
            mock_engine_cls.return_value = mock_engine

            response = test_client.post(
                f"/api/v1/workflows/{wf.id}/execute",
                json={"trigger_context": {"event_type": "manual"}},
            )
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["status"] == "completed"
            assert data["steps_completed"] == 1


# ---------------------------------------------------------------------------
# Authentication tests
# ---------------------------------------------------------------------------


class TestAuthenticationRequired:
    """Test that workflow endpoints require authentication."""

    def test_endpoints_require_authentication(self) -> None:
        """Test all workflow endpoints require authentication."""
        client = TestClient(app)

        endpoints = [
            ("GET", "/api/v1/workflows/prebuilt"),
            ("GET", "/api/v1/workflows/"),
            ("POST", "/api/v1/workflows/"),
            ("GET", "/api/v1/workflows/some-id"),
            ("PUT", "/api/v1/workflows/some-id"),
            ("DELETE", "/api/v1/workflows/some-id"),
            ("POST", "/api/v1/workflows/some-id/execute"),
        ]

        for method, url in endpoints:
            if method == "GET":
                response = client.get(url)
            elif method == "POST":
                response = client.post(url, json={})
            elif method == "PUT":
                response = client.put(url, json={})
            elif method == "DELETE":
                response = client.delete(url)
            else:
                continue

            assert response.status_code == status.HTTP_401_UNAUTHORIZED, (
                f"{method} {url} should require authentication, got {response.status_code}"
            )
