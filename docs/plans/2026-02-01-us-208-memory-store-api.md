# US-208: Memory Store API Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement REST endpoints to store memories (episodes, facts, tasks, workflows) so learning persists across sessions.

**Architecture:** Extend the existing `memory.py` routes file with four POST endpoints that accept validated Pydantic request models and delegate to the corresponding memory service classes (EpisodicMemory, SemanticMemory, ProspectiveMemory, ProceduralMemory). Each endpoint returns the created memory with its ID. Follow the existing auth pattern (CurrentUser dependency) and error handling.

**Tech Stack:** FastAPI, Pydantic, existing memory service classes, existing auth dependencies

---

## Prerequisites

- US-207 Memory Query API implemented ✓
- All four memory modules implemented: `episodic.py`, `semantic.py`, `procedural.py`, `prospective.py` ✓
- Authentication dependencies in `deps.py` ✓
- Exception hierarchy in `exceptions.py` ✓

---

## Task 1: Create Episode Request Model and Store Endpoint

**Files:**
- Modify: `backend/src/api/routes/memory.py`
- Modify: `backend/tests/api/routes/test_memory.py`

**Step 1: Write the failing test for CreateEpisodeRequest model**

Add to `backend/tests/api/routes/test_memory.py`:

```python
class TestCreateEpisodeRequestModel:
    """Tests for CreateEpisodeRequest Pydantic model."""

    def test_create_episode_request_valid(self) -> None:
        """Test creating a valid episode request."""
        from src.api.routes.memory import CreateEpisodeRequest

        request = CreateEpisodeRequest(
            event_type="meeting",
            content="Discussed Q3 budget with finance team",
            participants=["John Smith", "Jane Doe"],
            occurred_at=datetime(2024, 6, 15, 14, 0, 0, tzinfo=UTC),
            context={"location": "Conference Room A"},
        )

        assert request.event_type == "meeting"
        assert request.content == "Discussed Q3 budget with finance team"
        assert len(request.participants) == 2
        assert request.context["location"] == "Conference Room A"

    def test_create_episode_request_minimal(self) -> None:
        """Test creating episode with only required fields."""
        from src.api.routes.memory import CreateEpisodeRequest

        request = CreateEpisodeRequest(
            event_type="note",
            content="Quick note about project status",
        )

        assert request.event_type == "note"
        assert request.content == "Quick note about project status"
        assert request.participants == []
        assert request.occurred_at is None
        assert request.context == {}

    def test_create_episode_request_empty_content_fails(self) -> None:
        """Test that empty content raises validation error."""
        from pydantic import ValidationError

        from src.api.routes.memory import CreateEpisodeRequest

        with pytest.raises(ValidationError):
            CreateEpisodeRequest(
                event_type="meeting",
                content="",
            )
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/api/routes/test_memory.py::TestCreateEpisodeRequestModel -v`
Expected: FAIL with ImportError (CreateEpisodeRequest doesn't exist)

**Step 3: Add CreateEpisodeRequest model to memory.py**

Add after the existing models in `backend/src/api/routes/memory.py`:

```python
# Request Models for Store Endpoints
class CreateEpisodeRequest(BaseModel):
    """Request body for creating a new episodic memory."""

    event_type: str = Field(..., min_length=1, description="Type of event (meeting, call, email, etc.)")
    content: str = Field(..., min_length=1, description="Event content/description")
    participants: list[str] = Field(default_factory=list, description="People involved in the event")
    occurred_at: datetime | None = Field(None, description="When the event occurred (defaults to now)")
    context: dict[str, Any] = Field(default_factory=dict, description="Additional context metadata")


class CreateEpisodeResponse(BaseModel):
    """Response body for episode creation."""

    id: str
    message: str = "Episode created successfully"
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/api/routes/test_memory.py::TestCreateEpisodeRequestModel -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/api/routes/memory.py backend/tests/api/routes/test_memory.py
git commit -m "$(cat <<'EOF'
feat(api): add CreateEpisodeRequest model for memory store API

Add Pydantic request model for POST /api/v1/memory/episode endpoint
with validation for event_type, content, participants, occurred_at,
and context fields.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Implement POST /api/v1/memory/episode Endpoint

**Files:**
- Modify: `backend/src/api/routes/memory.py`
- Modify: `backend/tests/api/routes/test_memory.py`

**Step 1: Write the failing test for the endpoint**

Add to `backend/tests/api/routes/test_memory.py`:

```python
class TestStoreEpisodeEndpoint:
    """Tests for POST /api/v1/memory/episode endpoint."""

    def test_store_episode_requires_authentication(self) -> None:
        """Test that endpoint requires authentication."""
        from src.main import app

        client = TestClient(app)
        response = client.post(
            "/api/v1/memory/episode",
            json={
                "event_type": "meeting",
                "content": "Test meeting content",
            },
        )

        assert response.status_code == 401

    @pytest.fixture
    def mock_auth(self) -> Any:
        """Fixture to mock authentication."""
        with patch("src.api.deps.get_current_user", new_callable=AsyncMock) as mock:
            user = MagicMock()
            user.id = "test-user-123"
            mock.return_value = user
            yield mock

    @pytest.fixture
    def mock_graphiti(self) -> Any:
        """Fixture to mock Graphiti client."""
        with patch("src.db.graphiti.GraphitiClient.get_instance", new_callable=AsyncMock) as mock:
            client = MagicMock()
            client.add_episode = AsyncMock(return_value=None)
            mock.return_value = client
            yield mock

    def test_store_episode_success(self, mock_auth: Any, mock_graphiti: Any) -> None:
        """Test successful episode creation."""
        from src.main import app

        client = TestClient(app)

        response = client.post(
            "/api/v1/memory/episode",
            json={
                "event_type": "meeting",
                "content": "Discussed Q3 budget with finance team",
                "participants": ["John Smith"],
            },
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["message"] == "Episode created successfully"

    def test_store_episode_validation_error(self, mock_auth: Any) -> None:
        """Test that invalid request returns 422."""
        from src.main import app

        client = TestClient(app)

        response = client.post(
            "/api/v1/memory/episode",
            json={
                "event_type": "",  # Empty string should fail
                "content": "Some content",
            },
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 422
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/api/routes/test_memory.py::TestStoreEpisodeEndpoint -v`
Expected: FAIL with 404 (endpoint doesn't exist)

**Step 3: Implement the endpoint**

Add to `backend/src/api/routes/memory.py`:

```python
@router.post("/episode", response_model=CreateEpisodeResponse, status_code=201)
async def store_episode(
    current_user: CurrentUser,
    request: CreateEpisodeRequest,
) -> CreateEpisodeResponse:
    """Store a new episodic memory.

    Creates an episode representing a past event or interaction.
    Episodes are stored in Graphiti for temporal querying.

    Args:
        current_user: Authenticated user.
        request: Episode creation request body.

    Returns:
        Created episode with ID.
    """
    from src.memory.episodic import Episode, EpisodicMemory

    # Build episode from request
    now = datetime.now(UTC)
    episode = Episode(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        event_type=request.event_type,
        content=request.content,
        participants=request.participants,
        occurred_at=request.occurred_at or now,
        recorded_at=now,
        context=request.context,
    )

    # Store episode
    memory = EpisodicMemory()
    episode_id = await memory.store_episode(episode)

    logger.info(
        "Stored episode via API",
        extra={
            "episode_id": episode_id,
            "user_id": current_user.id,
            "event_type": request.event_type,
        },
    )

    return CreateEpisodeResponse(id=episode_id)
```

**Step 4: Add uuid import at top of file**

```python
import uuid
from datetime import UTC, datetime
```

**Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/api/routes/test_memory.py::TestStoreEpisodeEndpoint -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/src/api/routes/memory.py backend/tests/api/routes/test_memory.py
git commit -m "$(cat <<'EOF'
feat(api): add POST /api/v1/memory/episode endpoint

Implement episode storage endpoint that:
- Validates request with Pydantic
- Creates Episode dataclass from request
- Delegates to EpisodicMemory.store_episode()
- Returns created episode ID with 201 status

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Create Fact Request Model and Store Endpoint

**Files:**
- Modify: `backend/src/api/routes/memory.py`
- Modify: `backend/tests/api/routes/test_memory.py`

**Step 1: Write the failing test for CreateFactRequest model**

Add to `backend/tests/api/routes/test_memory.py`:

```python
class TestCreateFactRequestModel:
    """Tests for CreateFactRequest Pydantic model."""

    def test_create_fact_request_valid(self) -> None:
        """Test creating a valid fact request."""
        from src.api.routes.memory import CreateFactRequest

        request = CreateFactRequest(
            subject="Acme Corp",
            predicate="has_budget_cycle",
            object="Q3",
            source="user_stated",
            confidence=0.95,
        )

        assert request.subject == "Acme Corp"
        assert request.predicate == "has_budget_cycle"
        assert request.object == "Q3"
        assert request.source == "user_stated"
        assert request.confidence == 0.95

    def test_create_fact_request_minimal(self) -> None:
        """Test creating fact with only required fields."""
        from src.api.routes.memory import CreateFactRequest

        request = CreateFactRequest(
            subject="John",
            predicate="works_at",
            object="TechCorp",
        )

        assert request.subject == "John"
        assert request.source is None
        assert request.confidence is None

    def test_create_fact_request_invalid_source(self) -> None:
        """Test that invalid source raises validation error."""
        from pydantic import ValidationError

        from src.api.routes.memory import CreateFactRequest

        with pytest.raises(ValidationError):
            CreateFactRequest(
                subject="John",
                predicate="works_at",
                object="TechCorp",
                source="invalid_source",
            )

    def test_create_fact_request_confidence_bounds(self) -> None:
        """Test that confidence must be between 0 and 1."""
        from pydantic import ValidationError

        from src.api.routes.memory import CreateFactRequest

        with pytest.raises(ValidationError):
            CreateFactRequest(
                subject="John",
                predicate="works_at",
                object="TechCorp",
                confidence=1.5,
            )
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/api/routes/test_memory.py::TestCreateFactRequestModel -v`
Expected: FAIL with ImportError (CreateFactRequest doesn't exist)

**Step 3: Add CreateFactRequest model to memory.py**

Add after CreateEpisodeResponse in `backend/src/api/routes/memory.py`:

```python
class CreateFactRequest(BaseModel):
    """Request body for creating a new semantic fact."""

    subject: str = Field(..., min_length=1, description="Entity the fact is about")
    predicate: str = Field(..., min_length=1, description="Relationship type")
    object: str = Field(..., min_length=1, description="Value or related entity")
    source: Literal["user_stated", "extracted", "inferred", "crm_import", "web_research"] | None = Field(
        None, description="Source of the fact"
    )
    confidence: float | None = Field(None, ge=0.0, le=1.0, description="Confidence score")
    valid_from: datetime | None = Field(None, description="When the fact became valid")
    valid_to: datetime | None = Field(None, description="When the fact expires")


class CreateFactResponse(BaseModel):
    """Response body for fact creation."""

    id: str
    message: str = "Fact created successfully"
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/api/routes/test_memory.py::TestCreateFactRequestModel -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/api/routes/memory.py backend/tests/api/routes/test_memory.py
git commit -m "$(cat <<'EOF'
feat(api): add CreateFactRequest model for semantic memory

Add Pydantic request model for POST /api/v1/memory/fact endpoint
with validation for subject, predicate, object, source, confidence,
and temporal validity fields.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Implement POST /api/v1/memory/fact Endpoint

**Files:**
- Modify: `backend/src/api/routes/memory.py`
- Modify: `backend/tests/api/routes/test_memory.py`

**Step 1: Write the failing test for the endpoint**

Add to `backend/tests/api/routes/test_memory.py`:

```python
class TestStoreFactEndpoint:
    """Tests for POST /api/v1/memory/fact endpoint."""

    def test_store_fact_requires_authentication(self) -> None:
        """Test that endpoint requires authentication."""
        from src.main import app

        client = TestClient(app)
        response = client.post(
            "/api/v1/memory/fact",
            json={
                "subject": "Acme Corp",
                "predicate": "has_budget_cycle",
                "object": "Q3",
            },
        )

        assert response.status_code == 401

    @pytest.fixture
    def mock_auth(self) -> Any:
        """Fixture to mock authentication."""
        with patch("src.api.deps.get_current_user", new_callable=AsyncMock) as mock:
            user = MagicMock()
            user.id = "test-user-123"
            mock.return_value = user
            yield mock

    @pytest.fixture
    def mock_graphiti(self) -> Any:
        """Fixture to mock Graphiti client."""
        with patch("src.db.graphiti.GraphitiClient.get_instance", new_callable=AsyncMock) as mock:
            client = MagicMock()
            client.add_episode = AsyncMock(return_value=None)
            client.search = AsyncMock(return_value=[])
            mock.return_value = client
            yield mock

    def test_store_fact_success(self, mock_auth: Any, mock_graphiti: Any) -> None:
        """Test successful fact creation."""
        from src.main import app

        client = TestClient(app)

        response = client.post(
            "/api/v1/memory/fact",
            json={
                "subject": "Acme Corp",
                "predicate": "has_budget_cycle",
                "object": "Q3",
                "source": "user_stated",
                "confidence": 0.95,
            },
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["message"] == "Fact created successfully"

    def test_store_fact_with_defaults(self, mock_auth: Any, mock_graphiti: Any) -> None:
        """Test fact creation with default confidence."""
        from src.main import app

        client = TestClient(app)

        response = client.post(
            "/api/v1/memory/fact",
            json={
                "subject": "John",
                "predicate": "works_at",
                "object": "TechCorp",
            },
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 201
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/api/routes/test_memory.py::TestStoreFactEndpoint -v`
Expected: FAIL with 404 (endpoint doesn't exist)

**Step 3: Implement the endpoint**

Add to `backend/src/api/routes/memory.py`:

```python
@router.post("/fact", response_model=CreateFactResponse, status_code=201)
async def store_fact(
    current_user: CurrentUser,
    request: CreateFactRequest,
) -> CreateFactResponse:
    """Store a new semantic fact.

    Creates a fact representing knowledge about an entity.
    Facts are stored in Graphiti with confidence scores and
    automatic contradiction detection.

    Args:
        current_user: Authenticated user.
        request: Fact creation request body.

    Returns:
        Created fact with ID.
    """
    from src.memory.semantic import FactSource, SemanticFact, SemanticMemory, SOURCE_CONFIDENCE

    # Determine source and confidence
    source = FactSource(request.source) if request.source else FactSource.USER_STATED
    confidence = request.confidence if request.confidence is not None else SOURCE_CONFIDENCE[source]

    # Build fact from request
    now = datetime.now(UTC)
    fact = SemanticFact(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        subject=request.subject,
        predicate=request.predicate,
        object=request.object,
        confidence=confidence,
        source=source,
        valid_from=request.valid_from or now,
        valid_to=request.valid_to,
    )

    # Store fact
    memory = SemanticMemory()
    fact_id = await memory.add_fact(fact)

    logger.info(
        "Stored fact via API",
        extra={
            "fact_id": fact_id,
            "user_id": current_user.id,
            "subject": request.subject,
            "predicate": request.predicate,
        },
    )

    return CreateFactResponse(id=fact_id)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/api/routes/test_memory.py::TestStoreFactEndpoint -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/api/routes/memory.py backend/tests/api/routes/test_memory.py
git commit -m "$(cat <<'EOF'
feat(api): add POST /api/v1/memory/fact endpoint

Implement semantic fact storage endpoint that:
- Validates request with Pydantic
- Applies default confidence based on source type
- Delegates to SemanticMemory.add_fact() with contradiction detection
- Returns created fact ID with 201 status

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Create Task Request Model and Store Endpoint

**Files:**
- Modify: `backend/src/api/routes/memory.py`
- Modify: `backend/tests/api/routes/test_memory.py`

**Step 1: Write the failing test for CreateTaskRequest model**

Add to `backend/tests/api/routes/test_memory.py`:

```python
class TestCreateTaskRequestModel:
    """Tests for CreateTaskRequest Pydantic model."""

    def test_create_task_request_valid(self) -> None:
        """Test creating a valid task request."""
        from src.api.routes.memory import CreateTaskRequest

        request = CreateTaskRequest(
            task="Follow up with client",
            description="Send proposal review request",
            trigger_type="time",
            trigger_config={"due_at": "2024-07-01T10:00:00Z"},
            priority="high",
        )

        assert request.task == "Follow up with client"
        assert request.description == "Send proposal review request"
        assert request.trigger_type == "time"
        assert request.priority == "high"

    def test_create_task_request_minimal(self) -> None:
        """Test creating task with only required fields."""
        from src.api.routes.memory import CreateTaskRequest

        request = CreateTaskRequest(
            task="Call John",
            trigger_type="time",
            trigger_config={"due_at": "2024-07-01T10:00:00Z"},
        )

        assert request.task == "Call John"
        assert request.description is None
        assert request.priority == "medium"  # default

    def test_create_task_request_invalid_trigger_type(self) -> None:
        """Test that invalid trigger_type raises validation error."""
        from pydantic import ValidationError

        from src.api.routes.memory import CreateTaskRequest

        with pytest.raises(ValidationError):
            CreateTaskRequest(
                task="Call John",
                trigger_type="invalid",
                trigger_config={},
            )

    def test_create_task_request_invalid_priority(self) -> None:
        """Test that invalid priority raises validation error."""
        from pydantic import ValidationError

        from src.api.routes.memory import CreateTaskRequest

        with pytest.raises(ValidationError):
            CreateTaskRequest(
                task="Call John",
                trigger_type="time",
                trigger_config={"due_at": "2024-07-01T10:00:00Z"},
                priority="invalid",
            )
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/api/routes/test_memory.py::TestCreateTaskRequestModel -v`
Expected: FAIL with ImportError (CreateTaskRequest doesn't exist)

**Step 3: Add CreateTaskRequest model to memory.py**

Add after CreateFactResponse in `backend/src/api/routes/memory.py`:

```python
class CreateTaskRequest(BaseModel):
    """Request body for creating a new prospective task."""

    task: str = Field(..., min_length=1, description="Short task description")
    description: str | None = Field(None, description="Detailed description")
    trigger_type: Literal["time", "event", "condition"] = Field(..., description="Type of trigger")
    trigger_config: dict[str, Any] = Field(..., description="Trigger-specific configuration")
    priority: Literal["low", "medium", "high", "urgent"] = Field("medium", description="Task priority")
    related_goal_id: str | None = Field(None, description="Optional linked goal ID")
    related_lead_id: str | None = Field(None, description="Optional linked lead ID")


class CreateTaskResponse(BaseModel):
    """Response body for task creation."""

    id: str
    message: str = "Task created successfully"
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/api/routes/test_memory.py::TestCreateTaskRequestModel -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/api/routes/memory.py backend/tests/api/routes/test_memory.py
git commit -m "$(cat <<'EOF'
feat(api): add CreateTaskRequest model for prospective memory

Add Pydantic request model for POST /api/v1/memory/task endpoint
with validation for task, description, trigger_type, trigger_config,
priority, and related entity IDs.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Implement POST /api/v1/memory/task Endpoint

**Files:**
- Modify: `backend/src/api/routes/memory.py`
- Modify: `backend/tests/api/routes/test_memory.py`

**Step 1: Write the failing test for the endpoint**

Add to `backend/tests/api/routes/test_memory.py`:

```python
class TestStoreTaskEndpoint:
    """Tests for POST /api/v1/memory/task endpoint."""

    def test_store_task_requires_authentication(self) -> None:
        """Test that endpoint requires authentication."""
        from src.main import app

        client = TestClient(app)
        response = client.post(
            "/api/v1/memory/task",
            json={
                "task": "Follow up with client",
                "trigger_type": "time",
                "trigger_config": {"due_at": "2024-07-01T10:00:00Z"},
            },
        )

        assert response.status_code == 401

    @pytest.fixture
    def mock_auth(self) -> Any:
        """Fixture to mock authentication."""
        with patch("src.api.deps.get_current_user", new_callable=AsyncMock) as mock:
            user = MagicMock()
            user.id = "test-user-123"
            mock.return_value = user
            yield mock

    @pytest.fixture
    def mock_supabase(self) -> Any:
        """Fixture to mock Supabase client."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock:
            client = MagicMock()
            table_mock = MagicMock()
            table_mock.insert.return_value = table_mock
            table_mock.execute.return_value = MagicMock(data=[{"id": "task-123"}])
            client.table.return_value = table_mock
            mock.return_value = client
            yield mock

    def test_store_task_success(self, mock_auth: Any, mock_supabase: Any) -> None:
        """Test successful task creation."""
        from src.main import app

        client = TestClient(app)

        response = client.post(
            "/api/v1/memory/task",
            json={
                "task": "Follow up with client",
                "description": "Send proposal review request",
                "trigger_type": "time",
                "trigger_config": {"due_at": "2024-07-01T10:00:00Z"},
                "priority": "high",
            },
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["message"] == "Task created successfully"

    def test_store_task_with_related_ids(self, mock_auth: Any, mock_supabase: Any) -> None:
        """Test task creation with related goal/lead IDs."""
        from src.main import app

        client = TestClient(app)

        response = client.post(
            "/api/v1/memory/task",
            json={
                "task": "Review lead status",
                "trigger_type": "event",
                "trigger_config": {"event": "email_received"},
                "related_goal_id": "goal-123",
                "related_lead_id": "lead-456",
            },
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 201
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/api/routes/test_memory.py::TestStoreTaskEndpoint -v`
Expected: FAIL with 404 (endpoint doesn't exist)

**Step 3: Implement the endpoint**

Add to `backend/src/api/routes/memory.py`:

```python
@router.post("/task", response_model=CreateTaskResponse, status_code=201)
async def store_task(
    current_user: CurrentUser,
    request: CreateTaskRequest,
) -> CreateTaskResponse:
    """Store a new prospective task.

    Creates a task for future execution with time, event, or
    condition-based triggers. Tasks are stored in Supabase.

    Args:
        current_user: Authenticated user.
        request: Task creation request body.

    Returns:
        Created task with ID.
    """
    from src.memory.prospective import (
        ProspectiveMemory,
        ProspectiveTask,
        TaskPriority,
        TaskStatus,
        TriggerType,
    )

    # Build task from request
    now = datetime.now(UTC)
    task = ProspectiveTask(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        task=request.task,
        description=request.description,
        trigger_type=TriggerType(request.trigger_type),
        trigger_config=request.trigger_config,
        status=TaskStatus.PENDING,
        priority=TaskPriority(request.priority),
        related_goal_id=request.related_goal_id,
        related_lead_id=request.related_lead_id,
        completed_at=None,
        created_at=now,
    )

    # Store task
    memory = ProspectiveMemory()
    task_id = await memory.create_task(task)

    logger.info(
        "Stored task via API",
        extra={
            "task_id": task_id,
            "user_id": current_user.id,
            "task": request.task,
            "trigger_type": request.trigger_type,
        },
    )

    return CreateTaskResponse(id=task_id)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/api/routes/test_memory.py::TestStoreTaskEndpoint -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/api/routes/memory.py backend/tests/api/routes/test_memory.py
git commit -m "$(cat <<'EOF'
feat(api): add POST /api/v1/memory/task endpoint

Implement prospective task storage endpoint that:
- Validates request with Pydantic
- Creates ProspectiveTask with PENDING status
- Supports time/event/condition triggers
- Delegates to ProspectiveMemory.create_task()
- Returns created task ID with 201 status

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Create Workflow Request Model and Store Endpoint

**Files:**
- Modify: `backend/src/api/routes/memory.py`
- Modify: `backend/tests/api/routes/test_memory.py`

**Step 1: Write the failing test for CreateWorkflowRequest model**

Add to `backend/tests/api/routes/test_memory.py`:

```python
class TestCreateWorkflowRequestModel:
    """Tests for CreateWorkflowRequest Pydantic model."""

    def test_create_workflow_request_valid(self) -> None:
        """Test creating a valid workflow request."""
        from src.api.routes.memory import CreateWorkflowRequest

        request = CreateWorkflowRequest(
            workflow_name="follow_up_sequence",
            description="Standard follow-up after initial contact",
            trigger_conditions={"event_type": "initial_contact"},
            steps=[
                {"action": "send_email", "template": "follow_up_1", "delay_days": 1},
                {"action": "send_email", "template": "follow_up_2", "delay_days": 3},
            ],
            is_shared=True,
        )

        assert request.workflow_name == "follow_up_sequence"
        assert len(request.steps) == 2
        assert request.is_shared is True

    def test_create_workflow_request_minimal(self) -> None:
        """Test creating workflow with only required fields."""
        from src.api.routes.memory import CreateWorkflowRequest

        request = CreateWorkflowRequest(
            workflow_name="simple_workflow",
            description="A simple workflow",
            steps=[{"action": "log", "message": "Workflow executed"}],
        )

        assert request.workflow_name == "simple_workflow"
        assert request.trigger_conditions == {}
        assert request.is_shared is False

    def test_create_workflow_request_empty_steps_fails(self) -> None:
        """Test that empty steps list raises validation error."""
        from pydantic import ValidationError

        from src.api.routes.memory import CreateWorkflowRequest

        with pytest.raises(ValidationError):
            CreateWorkflowRequest(
                workflow_name="empty_workflow",
                description="No steps",
                steps=[],
            )
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/api/routes/test_memory.py::TestCreateWorkflowRequestModel -v`
Expected: FAIL with ImportError (CreateWorkflowRequest doesn't exist)

**Step 3: Add CreateWorkflowRequest model to memory.py**

Add after CreateTaskResponse in `backend/src/api/routes/memory.py`:

```python
class CreateWorkflowRequest(BaseModel):
    """Request body for creating a new procedural workflow."""

    workflow_name: str = Field(..., min_length=1, description="Name of the workflow")
    description: str = Field(..., min_length=1, description="Description of what the workflow does")
    trigger_conditions: dict[str, Any] = Field(
        default_factory=dict, description="Conditions that trigger this workflow"
    )
    steps: list[dict[str, Any]] = Field(..., min_length=1, description="Ordered list of workflow steps")
    is_shared: bool = Field(False, description="Whether workflow is available to other users")


class CreateWorkflowResponse(BaseModel):
    """Response body for workflow creation."""

    id: str
    message: str = "Workflow created successfully"
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/api/routes/test_memory.py::TestCreateWorkflowRequestModel -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/api/routes/memory.py backend/tests/api/routes/test_memory.py
git commit -m "$(cat <<'EOF'
feat(api): add CreateWorkflowRequest model for procedural memory

Add Pydantic request model for POST /api/v1/memory/workflow endpoint
with validation for workflow_name, description, trigger_conditions,
steps (min 1 required), and is_shared flag.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Implement POST /api/v1/memory/workflow Endpoint

**Files:**
- Modify: `backend/src/api/routes/memory.py`
- Modify: `backend/tests/api/routes/test_memory.py`

**Step 1: Write the failing test for the endpoint**

Add to `backend/tests/api/routes/test_memory.py`:

```python
class TestStoreWorkflowEndpoint:
    """Tests for POST /api/v1/memory/workflow endpoint."""

    def test_store_workflow_requires_authentication(self) -> None:
        """Test that endpoint requires authentication."""
        from src.main import app

        client = TestClient(app)
        response = client.post(
            "/api/v1/memory/workflow",
            json={
                "workflow_name": "test_workflow",
                "description": "A test workflow",
                "steps": [{"action": "log"}],
            },
        )

        assert response.status_code == 401

    @pytest.fixture
    def mock_auth(self) -> Any:
        """Fixture to mock authentication."""
        with patch("src.api.deps.get_current_user", new_callable=AsyncMock) as mock:
            user = MagicMock()
            user.id = "test-user-123"
            mock.return_value = user
            yield mock

    @pytest.fixture
    def mock_supabase(self) -> Any:
        """Fixture to mock Supabase client."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock:
            client = MagicMock()
            table_mock = MagicMock()
            table_mock.insert.return_value = table_mock
            table_mock.execute.return_value = MagicMock(data=[{"id": "workflow-123"}])
            client.table.return_value = table_mock
            mock.return_value = client
            yield mock

    def test_store_workflow_success(self, mock_auth: Any, mock_supabase: Any) -> None:
        """Test successful workflow creation."""
        from src.main import app

        client = TestClient(app)

        response = client.post(
            "/api/v1/memory/workflow",
            json={
                "workflow_name": "follow_up_sequence",
                "description": "Standard follow-up after initial contact",
                "trigger_conditions": {"event_type": "initial_contact"},
                "steps": [
                    {"action": "send_email", "template": "follow_up_1"},
                    {"action": "wait", "days": 3},
                ],
                "is_shared": True,
            },
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["message"] == "Workflow created successfully"

    def test_store_workflow_minimal(self, mock_auth: Any, mock_supabase: Any) -> None:
        """Test workflow creation with minimal fields."""
        from src.main import app

        client = TestClient(app)

        response = client.post(
            "/api/v1/memory/workflow",
            json={
                "workflow_name": "simple",
                "description": "Simple workflow",
                "steps": [{"action": "log"}],
            },
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 201
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/api/routes/test_memory.py::TestStoreWorkflowEndpoint -v`
Expected: FAIL with 404 (endpoint doesn't exist)

**Step 3: Implement the endpoint**

Add to `backend/src/api/routes/memory.py`:

```python
@router.post("/workflow", response_model=CreateWorkflowResponse, status_code=201)
async def store_workflow(
    current_user: CurrentUser,
    request: CreateWorkflowRequest,
) -> CreateWorkflowResponse:
    """Store a new procedural workflow.

    Creates a workflow representing a learned pattern of actions.
    Workflows are stored in Supabase with success/failure tracking.

    Args:
        current_user: Authenticated user.
        request: Workflow creation request body.

    Returns:
        Created workflow with ID.
    """
    from src.memory.procedural import ProceduralMemory, Workflow

    # Build workflow from request
    now = datetime.now(UTC)
    workflow = Workflow(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        workflow_name=request.workflow_name,
        description=request.description,
        trigger_conditions=request.trigger_conditions,
        steps=request.steps,
        success_count=0,
        failure_count=0,
        is_shared=request.is_shared,
        version=1,
        created_at=now,
        updated_at=now,
    )

    # Store workflow
    memory = ProceduralMemory()
    workflow_id = await memory.create_workflow(workflow)

    logger.info(
        "Stored workflow via API",
        extra={
            "workflow_id": workflow_id,
            "user_id": current_user.id,
            "workflow_name": request.workflow_name,
            "is_shared": request.is_shared,
        },
    )

    return CreateWorkflowResponse(id=workflow_id)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/api/routes/test_memory.py::TestStoreWorkflowEndpoint -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/api/routes/memory.py backend/tests/api/routes/test_memory.py
git commit -m "$(cat <<'EOF'
feat(api): add POST /api/v1/memory/workflow endpoint

Implement procedural workflow storage endpoint that:
- Validates request with Pydantic
- Creates Workflow with initial version 1
- Initializes success/failure counts to 0
- Delegates to ProceduralMemory.create_workflow()
- Returns created workflow ID with 201 status

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Run Type Checking and Linting

**Files:**
- Modify: `backend/src/api/routes/memory.py`

**Step 1: Run mypy to check for type errors**

Run: `cd backend && mypy src/api/routes/memory.py --strict`

**Step 2: Fix any type issues identified**

Common fixes may include:
- Add explicit return types
- Fix Any type usage where possible
- Add proper type annotations

**Step 3: Run ruff check and format**

Run: `cd backend && ruff check src/api/routes/memory.py --fix && ruff format src/api/routes/memory.py`

**Step 4: Run all quality gates**

Run: `cd backend && pytest tests/api/routes/test_memory.py -v && mypy src/api/routes/memory.py --strict && ruff check src/api/routes/memory.py`
Expected: All pass

**Step 5: Commit**

```bash
git add backend/src/api/routes/memory.py
git commit -m "$(cat <<'EOF'
style(api): fix type annotations and linting in memory routes

Ensure mypy --strict and ruff checks pass for all new store endpoints.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Run Full Quality Gates and Final Verification

**Step 1: Run all backend tests**

Run: `cd backend && pytest tests/ -v`
Expected: All tests pass

**Step 2: Run type checking**

Run: `cd backend && mypy src/ --strict`
Expected: No errors

**Step 3: Run linting**

Run: `cd backend && ruff check src/`
Expected: No errors

**Step 4: Run formatting check**

Run: `cd backend && ruff format src/ --check`
Expected: No changes needed

**Step 5: Final commit if any cleanup needed**

```bash
git add -A
git commit -m "$(cat <<'EOF'
feat(api): complete US-208 Memory Store API implementation

Implements memory store endpoints per docs/PHASE_2_MEMORY.md:
- POST /api/v1/memory/episode - Store new episodic memory
- POST /api/v1/memory/fact - Store new semantic fact
- POST /api/v1/memory/task - Store new prospective task
- POST /api/v1/memory/workflow - Store new procedural workflow

All endpoints:
- Require authentication via CurrentUser
- Validate input with Pydantic models
- Return created memory with ID (201 status)
- Have comprehensive unit and integration tests

Acceptance criteria met:
- ✅ POST /api/v1/memory/episode
- ✅ POST /api/v1/memory/fact
- ✅ POST /api/v1/memory/task
- ✅ POST /api/v1/memory/workflow
- ✅ Input validation with Pydantic models
- ✅ Returns created memory with ID
- ✅ Integration tests for all endpoints

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Summary

This plan implements US-208 Memory Store API with:

1. **Request Models** - Pydantic models with validation for each memory type
2. **Response Models** - Consistent response format with ID and message
3. **Four POST endpoints** - One for each memory type (episode, fact, task, workflow)
4. **Comprehensive tests** - Unit tests for models, integration tests for endpoints
5. **Type safety** - mypy strict mode compliance
6. **Code quality** - ruff linting/formatting compliance

**Files created/modified:**
- `backend/src/api/routes/memory.py` (modified - add 4 endpoints + 8 models)
- `backend/tests/api/routes/test_memory.py` (modified - add 8 test classes)

**Endpoints added:**
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/memory/episode` | Store new episodic memory |
| POST | `/api/v1/memory/fact` | Store new semantic fact |
| POST | `/api/v1/memory/task` | Store new prospective task |
| POST | `/api/v1/memory/workflow` | Store new procedural workflow |
