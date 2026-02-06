# US-532: Skills API Endpoints Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create REST API endpoints for skill discovery, installation, execution, audit, and autonomy management.

**Architecture:** Thin route layer in `src/api/routes/skills.py` that delegates to existing services (`SkillIndex`, `SkillInstaller`, `SkillExecutor`, `SkillAuditService`, `SkillAutonomyService`). Follows the same patterns as other routes: Pydantic request/response models, `CurrentUser` auth dependency, service getters, structured logging.

**Tech Stack:** FastAPI, Pydantic, pytest, unittest.mock

---

### Task 1: Add `list_user_skills` method to SkillInstaller

The existing `SkillInstaller` has `get_installed(user_id, skill_id)` but no method to list ALL installed skills for a user. The API needs this.

**Files:**
- Modify: `backend/src/skills/installer.py:236` (add method before `get_installed`)
- Test: `backend/tests/test_skills_api.py`

**Step 1: Write the failing test**

Create `backend/tests/test_skills_api.py` with:

```python
"""Tests for skills API routes."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from src.api.deps import get_current_user
from src.main import app


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
    yield client
    app.dependency_overrides.clear()


class TestListUserSkills:
    def test_list_user_skills_returns_installed_skills(
        self, test_client: TestClient
    ) -> None:
        """Test that list_user_skills returns all installed skills for user."""
        with patch("src.api.routes.skills.SkillInstaller") as mock_installer_class:
            mock_installer = MagicMock()
            mock_installer.list_user_skills = AsyncMock(
                return_value=[
                    {
                        "id": "install-1",
                        "user_id": "test-user-123",
                        "skill_id": "skill-uuid-1",
                        "skill_path": "anthropics/skills/pdf",
                        "trust_level": "verified",
                        "execution_count": 5,
                        "success_count": 5,
                        "installed_at": "2026-02-01T10:00:00+00:00",
                    }
                ]
            )
            mock_installer_class.return_value = mock_installer

            response = test_client.get("/api/v1/skills/installed")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 1
        assert data[0]["skill_path"] == "anthropics/skills/pdf"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_skills_api.py::TestListUserSkills::test_list_user_skills_returns_installed_skills -v`
Expected: FAIL (module `src.api.routes.skills` not found)

**Step 3: Add `list_user_skills` method to SkillInstaller**

In `backend/src/skills/installer.py`, add this method after the `get_installed` method (after line 246):

```python
    async def list_user_skills(self, user_id: str) -> list[dict[str, Any]]:
        """List all installed skills for a user.

        Args:
            user_id: The user's UUID.

        Returns:
            List of installed skill dictionaries.
        """
        try:
            response = (
                self._client.table("user_skills")
                .select("*")
                .eq("user_id", user_id)
                .order("installed_at", desc=True)
                .execute()
            )
            return response.data or []
        except Exception as e:
            logger.error(f"Error listing installed skills for user {user_id}: {e}")
            return []
```

**Step 4: Commit**

```bash
git add backend/src/skills/installer.py backend/tests/test_skills_api.py
git commit -m "feat(skills): add list_user_skills method to SkillInstaller"
```

---

### Task 2: Create skills route file with available and installed endpoints

**Files:**
- Create: `backend/src/api/routes/skills.py`
- Modify: `backend/src/main.py:13-31` (add skills import)
- Modify: `backend/src/api/routes/__init__.py` (add skills export)
- Test: `backend/tests/test_skills_api.py`

**Step 1: Write the failing tests**

Append to `backend/tests/test_skills_api.py`:

```python
class TestAvailableSkills:
    def test_search_available_skills(self, test_client: TestClient) -> None:
        """Test GET /skills/available returns skills from index."""
        with patch("src.api.routes.skills.SkillIndex") as mock_index_class:
            mock_index = MagicMock()
            mock_index.search = AsyncMock(
                return_value=[
                    MagicMock(
                        id="skill-uuid-1",
                        skill_path="anthropics/skills/pdf",
                        skill_name="PDF Generator",
                        description="Generate PDF documents",
                        author="anthropic",
                        version="1.0.0",
                        tags=["document", "pdf"],
                        trust_level=MagicMock(value="verified"),
                        life_sciences_relevant=False,
                    )
                ]
            )
            mock_index_class.return_value = mock_index

            response = test_client.get(
                "/api/v1/skills/available?query=pdf"
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 1
        assert data[0]["skill_name"] == "PDF Generator"

    def test_search_available_skills_with_trust_filter(
        self, test_client: TestClient
    ) -> None:
        """Test GET /skills/available filters by trust level."""
        with patch("src.api.routes.skills.SkillIndex") as mock_index_class:
            mock_index = MagicMock()
            mock_index.search = AsyncMock(return_value=[])
            mock_index_class.return_value = mock_index

            response = test_client.get(
                "/api/v1/skills/available?query=test&trust_level=core"
            )

        assert response.status_code == status.HTTP_200_OK
        mock_index.search.assert_called_once()
        call_kwargs = mock_index.search.call_args
        assert call_kwargs.kwargs.get("trust_level") is not None


class TestSkillsRequireAuth:
    def test_all_endpoints_require_authentication(self) -> None:
        """Test all skill endpoints require authentication."""
        client = TestClient(app)

        endpoints = [
            ("GET", "/api/v1/skills/available"),
            ("GET", "/api/v1/skills/installed"),
            ("POST", "/api/v1/skills/install"),
            ("DELETE", "/api/v1/skills/some-skill-id"),
            ("POST", "/api/v1/skills/execute"),
            ("GET", "/api/v1/skills/audit"),
            ("GET", "/api/v1/skills/autonomy/some-skill-id"),
            ("POST", "/api/v1/skills/autonomy/some-skill-id/approve"),
        ]

        for method, path in endpoints:
            response = getattr(client, method.lower())(path)
            assert response.status_code == status.HTTP_401_UNAUTHORIZED, (
                f"{method} {path} should require auth"
            )
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_skills_api.py -v`
Expected: FAIL (route module not found)

**Step 3: Create the route file**

Create `backend/src/api/routes/skills.py`:

```python
"""API routes for skill management."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.security.skill_audit import SkillAuditService
from src.security.trust_levels import SkillTrustLevel
from src.skills.autonomy import SkillAutonomyService
from src.skills.index import SkillIndex
from src.skills.installer import SkillInstaller

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/skills", tags=["skills"])


# --- Response Models ---


class AvailableSkillResponse(BaseModel):
    """A skill available in the skills index."""

    id: str
    skill_path: str
    skill_name: str
    description: str | None = None
    author: str | None = None
    version: str | None = None
    tags: list[str] = Field(default_factory=list)
    trust_level: str
    life_sciences_relevant: bool = False


class InstalledSkillResponse(BaseModel):
    """A skill installed by the user."""

    id: str
    skill_id: str
    skill_path: str
    trust_level: str
    execution_count: int = 0
    success_count: int = 0
    installed_at: str
    last_used_at: str | None = None


# --- Service Getters ---


def _get_index() -> SkillIndex:
    return SkillIndex()


def _get_installer() -> SkillInstaller:
    return SkillInstaller()


def _get_audit() -> SkillAuditService:
    return SkillAuditService()


def _get_autonomy() -> SkillAutonomyService:
    return SkillAutonomyService()


# --- Endpoints ---


@router.get("/available")
async def list_available_skills(
    current_user: CurrentUser,
    query: str = Query(default="", description="Search query"),
    trust_level: str | None = Query(default=None, description="Filter by trust level"),
    life_sciences: bool | None = Query(default=None, description="Filter life sciences relevant"),
    limit: int = Query(default=50, ge=1, le=200, description="Max results"),
) -> list[AvailableSkillResponse]:
    """List available skills from the index with search and filtering.

    Args:
        current_user: Authenticated user.
        query: Search query for skill name/description.
        trust_level: Optional trust level filter (core, verified, community, user).
        life_sciences: Optional life sciences relevance filter.
        limit: Maximum results to return.

    Returns:
        List of available skills matching the criteria.
    """
    index = _get_index()

    trust_filter = None
    if trust_level:
        try:
            trust_filter = SkillTrustLevel(trust_level)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid trust_level: {trust_level}. Must be one of: core, verified, community, user",
            )

    results = await index.search(
        query,
        trust_level=trust_filter,
        life_sciences_relevant=life_sciences,
        limit=limit,
    )

    logger.info(
        "Listed available skills",
        extra={
            "user_id": current_user.id,
            "query": query,
            "result_count": len(results),
        },
    )

    return [
        AvailableSkillResponse(
            id=entry.id,
            skill_path=entry.skill_path,
            skill_name=entry.skill_name,
            description=entry.description,
            author=entry.author,
            version=entry.version,
            tags=entry.tags,
            trust_level=entry.trust_level.value,
            life_sciences_relevant=entry.life_sciences_relevant,
        )
        for entry in results
    ]


@router.get("/installed")
async def list_installed_skills(
    current_user: CurrentUser,
) -> list[InstalledSkillResponse]:
    """List the current user's installed skills.

    Args:
        current_user: Authenticated user.

    Returns:
        List of installed skills.
    """
    installer = _get_installer()
    rows = await installer.list_user_skills(current_user.id)

    logger.info(
        "Listed installed skills",
        extra={"user_id": current_user.id, "count": len(rows)},
    )

    return [
        InstalledSkillResponse(
            id=str(row["id"]),
            skill_id=str(row["skill_id"]),
            skill_path=str(row["skill_path"]),
            trust_level=str(row.get("trust_level", "community")),
            execution_count=int(row.get("execution_count", 0)),
            success_count=int(row.get("success_count", 0)),
            installed_at=str(row["installed_at"]),
            last_used_at=row.get("last_used_at"),
        )
        for row in rows
    ]
```

**Step 4: Register the router in main.py**

In `backend/src/main.py`, add `skills` to the import block (line 13-31):

```python
from src.api.routes import (
    auth,
    battle_cards,
    briefings,
    chat,
    cognitive_load,
    debriefs,
    drafts,
    goals,
    insights,
    integrations,
    leads,
    meetings,
    memory,
    notifications,
    predictions,
    preferences,
    signals,
    skills,
)
```

And add the router registration after the existing ones (around line 109):

```python
app.include_router(skills.router, prefix="/api/v1")
```

**Step 5: Add skills export to routes `__init__.py`**

In `backend/src/api/routes/__init__.py`, add:

```python
from src.api.routes import skills as skills
```

**Step 6: Run tests to verify they pass**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_skills_api.py -v`
Expected: TestAvailableSkills and TestListUserSkills PASS, TestSkillsRequireAuth PASS

**Step 7: Commit**

```bash
git add backend/src/api/routes/skills.py backend/src/api/routes/__init__.py backend/src/main.py backend/tests/test_skills_api.py
git commit -m "feat(api): add GET /skills/available and GET /skills/installed endpoints"
```

---

### Task 3: Add install and uninstall endpoints

**Files:**
- Modify: `backend/src/api/routes/skills.py`
- Test: `backend/tests/test_skills_api.py`

**Step 1: Write the failing tests**

Append to `backend/tests/test_skills_api.py`:

```python
class TestInstallSkill:
    def test_install_skill_succeeds(self, test_client: TestClient) -> None:
        """Test POST /skills/install installs a skill."""
        with patch("src.api.routes.skills.SkillInstaller") as mock_installer_class:
            mock_installer = MagicMock()
            mock_installer.install = AsyncMock(
                return_value=MagicMock(
                    id="install-1",
                    user_id="test-user-123",
                    skill_id="skill-uuid-1",
                    skill_path="anthropics/skills/pdf",
                    trust_level=MagicMock(value="verified"),
                    permissions_granted=["read"],
                    installed_at=MagicMock(isoformat=MagicMock(return_value="2026-02-01T10:00:00+00:00")),
                    auto_installed=False,
                    execution_count=0,
                    success_count=0,
                )
            )
            mock_installer_class.return_value = mock_installer

            response = test_client.post(
                "/api/v1/skills/install",
                json={"skill_id": "skill-uuid-1"},
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["skill_path"] == "anthropics/skills/pdf"

    def test_install_skill_not_found(self, test_client: TestClient) -> None:
        """Test POST /skills/install returns 404 for unknown skill."""
        with patch("src.api.routes.skills.SkillInstaller") as mock_installer_class:
            from src.skills.installer import SkillNotFoundError

            mock_installer = MagicMock()
            mock_installer.install = AsyncMock(
                side_effect=SkillNotFoundError("Skill not found")
            )
            mock_installer_class.return_value = mock_installer

            response = test_client.post(
                "/api/v1/skills/install",
                json={"skill_id": "nonexistent"},
            )

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestUninstallSkill:
    def test_uninstall_skill_succeeds(self, test_client: TestClient) -> None:
        """Test DELETE /skills/{skill_id} uninstalls a skill."""
        with patch("src.api.routes.skills.SkillInstaller") as mock_installer_class:
            mock_installer = MagicMock()
            mock_installer.uninstall = AsyncMock(return_value=True)
            mock_installer_class.return_value = mock_installer

            response = test_client.delete("/api/v1/skills/skill-uuid-1")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "uninstalled"

    def test_uninstall_skill_not_installed(self, test_client: TestClient) -> None:
        """Test DELETE /skills/{skill_id} returns 404 if not installed."""
        with patch("src.api.routes.skills.SkillInstaller") as mock_installer_class:
            mock_installer = MagicMock()
            mock_installer.uninstall = AsyncMock(return_value=False)
            mock_installer_class.return_value = mock_installer

            response = test_client.delete("/api/v1/skills/nonexistent")

        assert response.status_code == status.HTTP_404_NOT_FOUND
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_skills_api.py::TestInstallSkill -v`
Expected: FAIL (no route for POST /skills/install)

**Step 3: Add install and uninstall endpoints to skills.py**

Add these request models and endpoints to `backend/src/api/routes/skills.py`:

```python
# --- Request Models (add after response models) ---


class InstallSkillRequest(BaseModel):
    """Request to install a skill."""

    skill_id: str = Field(..., description="UUID of the skill to install")


class StatusResponse(BaseModel):
    """Generic status response."""

    status: str


# --- Install/Uninstall Endpoints (add after list_installed_skills) ---


@router.post("/install")
async def install_skill(
    data: InstallSkillRequest,
    current_user: CurrentUser,
) -> InstalledSkillResponse:
    """Install a skill for the current user.

    Args:
        data: Install request with skill_id.
        current_user: Authenticated user.

    Returns:
        The installed skill details.

    Raises:
        HTTPException: 404 if skill not found in index.
    """
    from src.skills.installer import SkillNotFoundError

    installer = _get_installer()
    try:
        installed = await installer.install(current_user.id, data.skill_id)
    except SkillNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    logger.info(
        "Skill installed",
        extra={
            "user_id": current_user.id,
            "skill_id": data.skill_id,
            "skill_path": installed.skill_path,
        },
    )

    return InstalledSkillResponse(
        id=installed.id,
        skill_id=installed.skill_id,
        skill_path=installed.skill_path,
        trust_level=installed.trust_level.value,
        execution_count=installed.execution_count,
        success_count=installed.success_count,
        installed_at=installed.installed_at.isoformat(),
        last_used_at=installed.last_used_at.isoformat() if installed.last_used_at else None,
    )


@router.delete("/{skill_id}")
async def uninstall_skill(
    skill_id: str,
    current_user: CurrentUser,
) -> StatusResponse:
    """Uninstall a skill for the current user.

    Args:
        skill_id: UUID of the skill to uninstall.
        current_user: Authenticated user.

    Returns:
        Status confirmation.

    Raises:
        HTTPException: 404 if skill was not installed.
    """
    installer = _get_installer()
    removed = await installer.uninstall(current_user.id, skill_id)

    if not removed:
        raise HTTPException(status_code=404, detail="Skill not installed")

    logger.info(
        "Skill uninstalled",
        extra={"user_id": current_user.id, "skill_id": skill_id},
    )

    return StatusResponse(status="uninstalled")
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_skills_api.py::TestInstallSkill tests/test_skills_api.py::TestUninstallSkill -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/api/routes/skills.py backend/tests/test_skills_api.py
git commit -m "feat(api): add POST /skills/install and DELETE /skills/{skill_id} endpoints"
```

---

### Task 4: Add execute endpoint

**Files:**
- Modify: `backend/src/api/routes/skills.py`
- Test: `backend/tests/test_skills_api.py`

**Step 1: Write the failing tests**

Append to `backend/tests/test_skills_api.py`:

```python
class TestExecuteSkill:
    def test_execute_skill_succeeds(self, test_client: TestClient) -> None:
        """Test POST /skills/execute runs a skill through security pipeline."""
        with patch("src.api.routes.skills._get_executor") as mock_get_executor:
            mock_executor = MagicMock()
            mock_executor.execute = AsyncMock(
                return_value=MagicMock(
                    skill_id="skill-uuid-1",
                    skill_path="anthropics/skills/pdf",
                    trust_level=MagicMock(value="verified"),
                    success=True,
                    result={"document_url": "https://example.com/doc.pdf"},
                    error=None,
                    execution_time_ms=150,
                    sanitized=True,
                )
            )
            mock_get_executor.return_value = mock_executor

            response = test_client.post(
                "/api/v1/skills/execute",
                json={
                    "skill_id": "skill-uuid-1",
                    "input_data": {"title": "Q1 Report"},
                },
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["result"]["document_url"] == "https://example.com/doc.pdf"

    def test_execute_skill_failure(self, test_client: TestClient) -> None:
        """Test POST /skills/execute returns error on execution failure."""
        with patch("src.api.routes.skills._get_executor") as mock_get_executor:
            from src.skills.executor import SkillExecutionError

            mock_executor = MagicMock()
            mock_executor.execute = AsyncMock(
                side_effect=SkillExecutionError(
                    "Skill not installed", skill_id="skill-uuid-1", stage="lookup"
                )
            )
            mock_get_executor.return_value = mock_executor

            response = test_client.post(
                "/api/v1/skills/execute",
                json={
                    "skill_id": "skill-uuid-1",
                    "input_data": {"title": "Test"},
                },
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_skills_api.py::TestExecuteSkill -v`
Expected: FAIL

**Step 3: Add execute endpoint and executor service getter**

Add to `backend/src/api/routes/skills.py`:

```python
# Add import at top of file
from src.skills.executor import SkillExecutionError, SkillExecutor

# Add request/response models

class ExecuteSkillRequest(BaseModel):
    """Request to execute a skill."""

    skill_id: str = Field(..., description="UUID of the skill to execute")
    input_data: dict[str, Any] = Field(default_factory=dict, description="Input data for the skill")


class SkillExecutionResponse(BaseModel):
    """Response from skill execution."""

    skill_id: str
    skill_path: str
    trust_level: str
    success: bool
    result: Any = None
    error: str | None = None
    execution_time_ms: int
    sanitized: bool


# Add service getter (requires building the executor with its dependencies)

def _get_executor() -> SkillExecutor:
    from src.security.data_classification import DataClassifier
    from src.security.sandbox import SkillSandbox
    from src.security.sanitization import DataSanitizer

    return SkillExecutor(
        classifier=DataClassifier(),
        sanitizer=DataSanitizer(),
        sandbox=SkillSandbox(),
        index=_get_index(),
        installer=_get_installer(),
        audit_service=_get_audit(),
    )


# Add endpoint

@router.post("/execute")
async def execute_skill(
    data: ExecuteSkillRequest,
    current_user: CurrentUser,
) -> SkillExecutionResponse:
    """Execute a skill through the security pipeline.

    Runs: classify -> sanitize -> sandbox execute -> validate -> detokenize -> audit.

    Args:
        data: Execution request with skill_id and input_data.
        current_user: Authenticated user.

    Returns:
        Execution result with metadata.

    Raises:
        HTTPException: 400 if execution fails.
    """
    executor = _get_executor()
    try:
        execution = await executor.execute(
            user_id=current_user.id,
            skill_id=data.skill_id,
            input_data=data.input_data,
        )
    except SkillExecutionError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    logger.info(
        "Skill executed",
        extra={
            "user_id": current_user.id,
            "skill_id": data.skill_id,
            "success": execution.success,
            "execution_time_ms": execution.execution_time_ms,
        },
    )

    return SkillExecutionResponse(
        skill_id=execution.skill_id,
        skill_path=execution.skill_path,
        trust_level=execution.trust_level.value,
        success=execution.success,
        result=execution.result,
        error=execution.error,
        execution_time_ms=execution.execution_time_ms,
        sanitized=execution.sanitized,
    )
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_skills_api.py::TestExecuteSkill -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/api/routes/skills.py backend/tests/test_skills_api.py
git commit -m "feat(api): add POST /skills/execute endpoint with security pipeline"
```

---

### Task 5: Add audit log endpoint

**Files:**
- Modify: `backend/src/api/routes/skills.py`
- Test: `backend/tests/test_skills_api.py`

**Step 1: Write the failing tests**

Append to `backend/tests/test_skills_api.py`:

```python
class TestAuditLog:
    def test_get_audit_log(self, test_client: TestClient) -> None:
        """Test GET /skills/audit returns paginated audit entries."""
        with patch("src.api.routes.skills.SkillAuditService") as mock_audit_class:
            mock_audit = MagicMock()
            mock_audit.get_audit_log = AsyncMock(
                return_value=[
                    {
                        "id": "audit-1",
                        "user_id": "test-user-123",
                        "skill_id": "skill-uuid-1",
                        "skill_path": "anthropics/skills/pdf",
                        "skill_trust_level": "verified",
                        "trigger_reason": "user_request",
                        "success": True,
                        "execution_time_ms": 150,
                        "timestamp": "2026-02-01T10:00:00Z",
                    }
                ]
            )
            mock_audit_class.return_value = mock_audit

            response = test_client.get("/api/v1/skills/audit?limit=10&offset=0")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 1
        assert data[0]["skill_path"] == "anthropics/skills/pdf"

    def test_get_audit_log_with_skill_filter(self, test_client: TestClient) -> None:
        """Test GET /skills/audit?skill_id= filters by skill."""
        with patch("src.api.routes.skills.SkillAuditService") as mock_audit_class:
            mock_audit = MagicMock()
            mock_audit.get_audit_for_skill = AsyncMock(return_value=[])
            mock_audit_class.return_value = mock_audit

            response = test_client.get(
                "/api/v1/skills/audit?skill_id=skill-uuid-1"
            )

        assert response.status_code == status.HTTP_200_OK
        mock_audit.get_audit_for_skill.assert_called_once()
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_skills_api.py::TestAuditLog -v`
Expected: FAIL

**Step 3: Add audit endpoint**

Add to `backend/src/api/routes/skills.py`:

```python
@router.get("/audit")
async def get_audit_log(
    current_user: CurrentUser,
    skill_id: str | None = Query(default=None, description="Filter by skill ID"),
    limit: int = Query(default=50, ge=1, le=500, description="Max entries"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
) -> list[dict[str, Any]]:
    """Get the user's skill execution audit log.

    Args:
        current_user: Authenticated user.
        skill_id: Optional filter by specific skill.
        limit: Maximum entries to return.
        offset: Pagination offset.

    Returns:
        List of audit log entries.
    """
    audit = _get_audit()

    if skill_id:
        entries = await audit.get_audit_for_skill(
            current_user.id, skill_id, limit=limit, offset=offset
        )
    else:
        entries = await audit.get_audit_log(
            current_user.id, limit=limit, offset=offset
        )

    logger.info(
        "Fetched audit log",
        extra={
            "user_id": current_user.id,
            "skill_id": skill_id,
            "count": len(entries),
        },
    )

    return entries
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_skills_api.py::TestAuditLog -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/api/routes/skills.py backend/tests/test_skills_api.py
git commit -m "feat(api): add GET /skills/audit endpoint with pagination"
```

---

### Task 6: Add autonomy endpoints (get trust level + grant approval)

**Files:**
- Modify: `backend/src/api/routes/skills.py`
- Test: `backend/tests/test_skills_api.py`

**Step 1: Write the failing tests**

Append to `backend/tests/test_skills_api.py`:

```python
class TestAutonomy:
    def test_get_trust_level(self, test_client: TestClient) -> None:
        """Test GET /skills/autonomy/{skill_id} returns trust info."""
        with patch("src.api.routes.skills.SkillAutonomyService") as mock_autonomy_class:
            mock_autonomy = MagicMock()
            mock_autonomy.get_trust_history = AsyncMock(
                return_value=MagicMock(
                    id="trust-1",
                    user_id="test-user-123",
                    skill_id="skill-uuid-1",
                    successful_executions=5,
                    failed_executions=0,
                    session_trust_granted=False,
                    globally_approved=False,
                    globally_approved_at=None,
                    created_at=MagicMock(isoformat=MagicMock(return_value="2026-02-01T10:00:00+00:00")),
                    updated_at=MagicMock(isoformat=MagicMock(return_value="2026-02-01T12:00:00+00:00")),
                )
            )
            mock_autonomy_class.return_value = mock_autonomy

            response = test_client.get("/api/v1/skills/autonomy/skill-uuid-1")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["successful_executions"] == 5
        assert data["globally_approved"] is False

    def test_get_trust_level_no_history(self, test_client: TestClient) -> None:
        """Test GET /skills/autonomy/{skill_id} returns defaults when no history."""
        with patch("src.api.routes.skills.SkillAutonomyService") as mock_autonomy_class:
            mock_autonomy = MagicMock()
            mock_autonomy.get_trust_history = AsyncMock(return_value=None)
            mock_autonomy_class.return_value = mock_autonomy

            response = test_client.get("/api/v1/skills/autonomy/skill-uuid-1")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["successful_executions"] == 0
        assert data["globally_approved"] is False

    def test_grant_global_approval(self, test_client: TestClient) -> None:
        """Test POST /skills/autonomy/{skill_id}/approve grants global approval."""
        with patch("src.api.routes.skills.SkillAutonomyService") as mock_autonomy_class:
            mock_autonomy = MagicMock()
            mock_autonomy.grant_global_approval = AsyncMock(
                return_value=MagicMock(
                    id="trust-1",
                    user_id="test-user-123",
                    skill_id="skill-uuid-1",
                    successful_executions=5,
                    failed_executions=0,
                    session_trust_granted=False,
                    globally_approved=True,
                    globally_approved_at=MagicMock(isoformat=MagicMock(return_value="2026-02-05T10:00:00+00:00")),
                    created_at=MagicMock(isoformat=MagicMock(return_value="2026-02-01T10:00:00+00:00")),
                    updated_at=MagicMock(isoformat=MagicMock(return_value="2026-02-05T10:00:00+00:00")),
                )
            )
            mock_autonomy_class.return_value = mock_autonomy

            response = test_client.post(
                "/api/v1/skills/autonomy/skill-uuid-1/approve"
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["globally_approved"] is True

    def test_grant_approval_fails(self, test_client: TestClient) -> None:
        """Test POST /skills/autonomy/{skill_id}/approve handles failure."""
        with patch("src.api.routes.skills.SkillAutonomyService") as mock_autonomy_class:
            mock_autonomy = MagicMock()
            mock_autonomy.grant_global_approval = AsyncMock(return_value=None)
            mock_autonomy_class.return_value = mock_autonomy

            response = test_client.post(
                "/api/v1/skills/autonomy/nonexistent/approve"
            )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_skills_api.py::TestAutonomy -v`
Expected: FAIL

**Step 3: Add autonomy endpoints**

Add response model and endpoints to `backend/src/api/routes/skills.py`:

```python
class TrustInfoResponse(BaseModel):
    """Trust/autonomy information for a skill."""

    skill_id: str
    successful_executions: int = 0
    failed_executions: int = 0
    session_trust_granted: bool = False
    globally_approved: bool = False
    globally_approved_at: str | None = None


@router.get("/autonomy/{skill_id}")
async def get_skill_trust(
    skill_id: str,
    current_user: CurrentUser,
) -> TrustInfoResponse:
    """Get trust/autonomy level for a skill.

    Args:
        skill_id: UUID of the skill.
        current_user: Authenticated user.

    Returns:
        Trust information including approval status and execution stats.
    """
    autonomy = _get_autonomy()
    history = await autonomy.get_trust_history(current_user.id, skill_id)

    if history is None:
        return TrustInfoResponse(skill_id=skill_id)

    return TrustInfoResponse(
        skill_id=skill_id,
        successful_executions=history.successful_executions,
        failed_executions=history.failed_executions,
        session_trust_granted=history.session_trust_granted,
        globally_approved=history.globally_approved,
        globally_approved_at=(
            history.globally_approved_at.isoformat()
            if history.globally_approved_at
            else None
        ),
    )


@router.post("/autonomy/{skill_id}/approve")
async def approve_skill(
    skill_id: str,
    current_user: CurrentUser,
) -> TrustInfoResponse:
    """Grant global approval for a skill.

    The skill will no longer require approval prompts for this user.

    Args:
        skill_id: UUID of the skill.
        current_user: Authenticated user.

    Returns:
        Updated trust information.

    Raises:
        HTTPException: 500 if approval fails.
    """
    autonomy = _get_autonomy()
    history = await autonomy.grant_global_approval(current_user.id, skill_id)

    if history is None:
        raise HTTPException(
            status_code=500,
            detail="Failed to grant approval",
        )

    logger.info(
        "Global approval granted",
        extra={"user_id": current_user.id, "skill_id": skill_id},
    )

    return TrustInfoResponse(
        skill_id=skill_id,
        successful_executions=history.successful_executions,
        failed_executions=history.failed_executions,
        session_trust_granted=history.session_trust_granted,
        globally_approved=history.globally_approved,
        globally_approved_at=(
            history.globally_approved_at.isoformat()
            if history.globally_approved_at
            else None
        ),
    )
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_skills_api.py::TestAutonomy -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/api/routes/skills.py backend/tests/test_skills_api.py
git commit -m "feat(api): add GET/POST /skills/autonomy/{skill_id} endpoints"
```

---

### Task 7: Run full test suite and verify

**Files:**
- None (verification only)

**Step 1: Run all skills API tests**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_skills_api.py -v`
Expected: All tests PASS

**Step 2: Run existing tests to ensure no regressions**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/ -v --timeout=30`
Expected: No new failures

**Step 3: Run type checking**

Run: `cd /Users/dhruv/aria/backend && python -m mypy src/api/routes/skills.py --strict`
Expected: No errors

**Step 4: Run linting**

Run: `cd /Users/dhruv/aria/backend && ruff check src/api/routes/skills.py && ruff format --check src/api/routes/skills.py`
Expected: No errors

**Step 5: Final commit (if any lint/type fixes needed)**

```bash
git add -u
git commit -m "fix(api): address lint and type issues in skills routes"
```

---

## File Summary

| Action | File |
|--------|------|
| Create | `backend/src/api/routes/skills.py` |
| Create | `backend/tests/test_skills_api.py` |
| Modify | `backend/src/skills/installer.py` (add `list_user_skills`) |
| Modify | `backend/src/main.py` (add skills router import + registration) |
| Modify | `backend/src/api/routes/__init__.py` (add skills export) |

## Endpoint Summary

| Method | Path | Handler | Service |
|--------|------|---------|---------|
| GET | `/api/v1/skills/available` | `list_available_skills` | `SkillIndex.search()` |
| GET | `/api/v1/skills/installed` | `list_installed_skills` | `SkillInstaller.list_user_skills()` |
| POST | `/api/v1/skills/install` | `install_skill` | `SkillInstaller.install()` |
| DELETE | `/api/v1/skills/{skill_id}` | `uninstall_skill` | `SkillInstaller.uninstall()` |
| POST | `/api/v1/skills/execute` | `execute_skill` | `SkillExecutor.execute()` |
| GET | `/api/v1/skills/audit` | `get_audit_log` | `SkillAuditService.get_audit_log()` |
| GET | `/api/v1/skills/autonomy/{skill_id}` | `get_skill_trust` | `SkillAutonomyService.get_trust_history()` |
| POST | `/api/v1/skills/autonomy/{skill_id}/approve` | `approve_skill` | `SkillAutonomyService.grant_global_approval()` |
