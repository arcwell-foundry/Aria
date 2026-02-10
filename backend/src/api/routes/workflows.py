"""API routes for workflow CRUD and execution."""

import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.core.exceptions import (
    ProceduralMemoryError,
    WorkflowNotFoundError,
    sanitize_error,
)
from src.memory.procedural import ProceduralMemory, Workflow
from src.skills.workflows.engine import WorkflowEngine
from src.skills.workflows.models import (
    UserWorkflowDefinition,
    WorkflowAction,
    WorkflowMetadata,
    WorkflowTrigger,
)
from src.skills.workflows.prebuilt import get_prebuilt_workflows

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workflows", tags=["workflows"])


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------


class CreateWorkflowRequest(BaseModel):
    """Request body for creating a new workflow."""

    name: str = Field(..., min_length=1, max_length=200, description="Workflow display name.")
    description: str = Field(default="", description="Human-readable description.")
    trigger: dict[str, Any] = Field(..., description="Trigger configuration dict.")
    actions: list[dict[str, Any]] = Field(..., description="Ordered list of action dicts.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Display metadata.")


class UpdateWorkflowRequest(BaseModel):
    """Request body for updating an existing workflow (all fields optional)."""

    name: str | None = Field(default=None, max_length=200, description="Workflow display name.")
    description: str | None = Field(default=None, description="Human-readable description.")
    trigger: dict[str, Any] | None = Field(default=None, description="Trigger configuration dict.")
    actions: list[dict[str, Any]] | None = Field(
        default=None, description="Ordered list of action dicts."
    )
    metadata: dict[str, Any] | None = Field(default=None, description="Display metadata.")


class ExecuteWorkflowRequest(BaseModel):
    """Request body for manually executing a workflow."""

    trigger_context: dict[str, Any] = Field(
        default_factory=dict, description="Context passed to the trigger evaluation."
    )


# ---------------------------------------------------------------------------
# Response Models
# ---------------------------------------------------------------------------


class WorkflowResponse(BaseModel):
    """Serialised workflow returned by the API."""

    id: str
    name: str
    description: str = ""
    trigger: dict[str, Any] = Field(default_factory=dict)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    is_shared: bool = False
    enabled: bool = True
    success_count: int = 0
    failure_count: int = 0
    version: int = 1


class StatusResponse(BaseModel):
    """Generic status response."""

    status: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _workflow_to_response(workflow: Workflow) -> WorkflowResponse:
    """Convert a ProceduralMemory Workflow dataclass to an API response.

    The procedural_memories table stores trigger + metadata together in
    ``trigger_conditions`` and actions in ``steps``.  This helper
    unpacks them into the flat response shape the frontend expects.

    Args:
        workflow: A Workflow dataclass from procedural memory.

    Returns:
        A WorkflowResponse with all fields populated.
    """
    trigger_conditions = dict(workflow.trigger_conditions)
    metadata = trigger_conditions.pop("metadata", {})

    return WorkflowResponse(
        id=workflow.id,
        name=workflow.workflow_name,
        description=workflow.description,
        trigger=trigger_conditions,
        actions=workflow.steps,
        metadata=metadata,
        is_shared=workflow.is_shared,
        enabled=metadata.get("enabled", True) if isinstance(metadata, dict) else True,
        success_count=workflow.success_count,
        failure_count=workflow.failure_count,
        version=workflow.version,
    )


def _prebuilt_to_response(definition: UserWorkflowDefinition) -> WorkflowResponse:
    """Convert a pre-built UserWorkflowDefinition to an API response.

    Args:
        definition: A pre-built workflow definition.

    Returns:
        A WorkflowResponse with all fields populated.
    """
    return WorkflowResponse(
        id=definition.id or str(uuid.uuid4()),
        name=definition.name,
        description=definition.description,
        trigger=definition.trigger.model_dump(exclude_none=True),
        actions=[action.model_dump() for action in definition.actions],
        metadata=definition.metadata.model_dump(exclude_none=True),
        is_shared=True,
        enabled=definition.metadata.enabled,
        success_count=0,
        failure_count=0,
        version=1,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/prebuilt")
async def list_prebuilt_workflows(
    current_user: CurrentUser,
) -> list[WorkflowResponse]:
    """List pre-built workflow templates available to all users.

    Args:
        current_user: The authenticated user.

    Returns:
        List of pre-built workflow responses.
    """
    prebuilt = get_prebuilt_workflows()

    logger.info(
        "Listed prebuilt workflows",
        extra={
            "user_id": current_user.id,
            "count": len(prebuilt),
        },
    )

    return [_prebuilt_to_response(wf) for wf in prebuilt]


@router.get("/")
async def list_workflows(
    current_user: CurrentUser,
    include_shared: bool = Query(default=True, description="Include shared workflows"),
) -> list[WorkflowResponse]:
    """List the current user's workflows (optionally including shared ones).

    Args:
        current_user: The authenticated user.
        include_shared: Whether to include shared workflows from other users.

    Returns:
        List of workflow responses.
    """
    memory = ProceduralMemory()
    try:
        workflows = await memory.list_workflows(str(current_user.id), include_shared=include_shared)
    except ProceduralMemoryError as e:
        logger.exception("Failed to list workflows")
        raise HTTPException(status_code=500, detail=sanitize_error(e)) from e

    logger.info(
        "Listed workflows",
        extra={
            "user_id": current_user.id,
            "include_shared": include_shared,
            "count": len(workflows),
        },
    )

    return [_workflow_to_response(wf) for wf in workflows]


@router.post("/", status_code=201)
async def create_workflow(
    data: CreateWorkflowRequest,
    current_user: CurrentUser,
) -> WorkflowResponse:
    """Create a new workflow for the current user.

    Validates trigger, actions, and metadata by parsing into typed models
    before persisting.

    Args:
        data: The workflow creation payload.
        current_user: The authenticated user.

    Returns:
        The created workflow response.
    """
    # Validate trigger, actions, and metadata via typed models
    try:
        trigger = WorkflowTrigger(**data.trigger)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid trigger: {sanitize_error(e)}") from e

    try:
        actions = [WorkflowAction(**a) for a in data.actions]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid actions: {sanitize_error(e)}") from e

    try:
        metadata = (
            WorkflowMetadata(**data.metadata)
            if data.metadata
            else WorkflowMetadata(category="productivity")
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid metadata: {sanitize_error(e)}") from e

    # Build the definition to serialise trigger_conditions and steps
    definition = UserWorkflowDefinition(
        name=data.name,
        description=data.description,
        trigger=trigger,
        actions=actions,
        metadata=metadata,
    )

    workflow_id = str(uuid.uuid4())
    workflow = Workflow(
        id=workflow_id,
        user_id=str(current_user.id),
        workflow_name=data.name,
        description=data.description,
        trigger_conditions=definition.to_trigger_conditions(),
        steps=definition.to_steps(),
        success_count=0,
        failure_count=0,
        is_shared=False,
        version=1,
        created_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        updated_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
    )

    memory = ProceduralMemory()
    try:
        created_id = await memory.create_workflow(workflow)
    except ProceduralMemoryError as e:
        logger.exception("Failed to create workflow")
        raise HTTPException(status_code=500, detail=sanitize_error(e)) from e

    logger.info(
        "Workflow created",
        extra={
            "user_id": current_user.id,
            "workflow_id": created_id,
            "workflow_name": data.name,
        },
    )

    return WorkflowResponse(
        id=created_id,
        name=data.name,
        description=data.description,
        trigger=data.trigger,
        actions=data.actions,
        metadata=data.metadata,
        is_shared=False,
        enabled=metadata.enabled,
        success_count=0,
        failure_count=0,
        version=1,
    )


@router.get("/{workflow_id}")
async def get_workflow(
    workflow_id: str,
    current_user: CurrentUser,
) -> WorkflowResponse:
    """Get a specific workflow by ID.

    Args:
        workflow_id: The workflow ID.
        current_user: The authenticated user.

    Returns:
        The workflow response.
    """
    memory = ProceduralMemory()
    try:
        workflow = await memory.get_workflow(str(current_user.id), workflow_id)
    except WorkflowNotFoundError as e:
        raise HTTPException(status_code=404, detail=sanitize_error(e)) from e
    except ProceduralMemoryError as e:
        logger.exception("Failed to get workflow")
        raise HTTPException(status_code=500, detail=sanitize_error(e)) from e

    logger.info(
        "Fetched workflow",
        extra={
            "user_id": current_user.id,
            "workflow_id": workflow_id,
        },
    )

    return _workflow_to_response(workflow)


@router.put("/{workflow_id}")
async def update_workflow(
    workflow_id: str,
    data: UpdateWorkflowRequest,
    current_user: CurrentUser,
) -> WorkflowResponse:
    """Update an existing workflow.

    Only supplied fields are changed; the rest remain as-is.

    Args:
        workflow_id: The workflow ID to update.
        data: The partial update payload.
        current_user: The authenticated user.

    Returns:
        The updated workflow response.
    """
    memory = ProceduralMemory()

    # Fetch existing workflow
    try:
        existing = await memory.get_workflow(str(current_user.id), workflow_id)
    except WorkflowNotFoundError as e:
        raise HTTPException(status_code=404, detail=sanitize_error(e)) from e
    except ProceduralMemoryError as e:
        logger.exception("Failed to get workflow for update")
        raise HTTPException(status_code=500, detail=sanitize_error(e)) from e

    # Apply updates
    if data.name is not None:
        existing.workflow_name = data.name
    if data.description is not None:
        existing.description = data.description

    if data.trigger is not None or data.metadata is not None or data.actions is not None:
        # Rebuild trigger_conditions if trigger or metadata changed
        current_trigger_conditions = dict(existing.trigger_conditions)
        current_metadata = current_trigger_conditions.pop("metadata", {})

        if data.trigger is not None:
            try:
                trigger = WorkflowTrigger(**data.trigger)
                current_trigger_conditions = trigger.model_dump(exclude_none=True)
            except Exception as e:
                raise HTTPException(
                    status_code=400, detail=f"Invalid trigger: {sanitize_error(e)}"
                ) from e

        if data.metadata is not None:
            try:
                metadata = WorkflowMetadata(**data.metadata)
                current_metadata = metadata.model_dump(exclude_none=True)
            except Exception as e:
                raise HTTPException(
                    status_code=400, detail=f"Invalid metadata: {sanitize_error(e)}"
                ) from e

        current_trigger_conditions["metadata"] = current_metadata
        existing.trigger_conditions = current_trigger_conditions

        if data.actions is not None:
            try:
                actions = [WorkflowAction(**a) for a in data.actions]
                existing.steps = [a.model_dump() for a in actions]
            except Exception as e:
                raise HTTPException(
                    status_code=400, detail=f"Invalid actions: {sanitize_error(e)}"
                ) from e

    try:
        await memory.update_workflow(existing)
    except ProceduralMemoryError as e:
        logger.exception("Failed to update workflow")
        raise HTTPException(status_code=500, detail=sanitize_error(e)) from e

    logger.info(
        "Workflow updated",
        extra={
            "user_id": current_user.id,
            "workflow_id": workflow_id,
        },
    )

    return _workflow_to_response(existing)


@router.delete("/{workflow_id}")
async def delete_workflow(
    workflow_id: str,
    current_user: CurrentUser,
) -> StatusResponse:
    """Delete a workflow.

    Args:
        workflow_id: The workflow ID to delete.
        current_user: The authenticated user.

    Returns:
        Status confirmation.
    """
    memory = ProceduralMemory()
    try:
        await memory.delete_workflow(str(current_user.id), workflow_id)
    except WorkflowNotFoundError as e:
        raise HTTPException(status_code=404, detail=sanitize_error(e)) from e
    except ProceduralMemoryError as e:
        logger.exception("Failed to delete workflow")
        raise HTTPException(status_code=500, detail=sanitize_error(e)) from e

    logger.info(
        "Workflow deleted",
        extra={
            "user_id": current_user.id,
            "workflow_id": workflow_id,
        },
    )

    return StatusResponse(status="deleted")


@router.post("/{workflow_id}/execute")
async def execute_workflow(
    workflow_id: str,
    data: ExecuteWorkflowRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Manually execute a workflow.

    Fetches the workflow, converts it to a UserWorkflowDefinition,
    runs it through the WorkflowEngine, and records the outcome.

    Args:
        workflow_id: The workflow ID to execute.
        data: Trigger context for the execution.
        current_user: The authenticated user.

    Returns:
        The WorkflowRunStatus as a dict.
    """
    memory = ProceduralMemory()

    # Fetch the workflow
    try:
        workflow = await memory.get_workflow(str(current_user.id), workflow_id)
    except WorkflowNotFoundError as e:
        raise HTTPException(status_code=404, detail=sanitize_error(e)) from e
    except ProceduralMemoryError as e:
        logger.exception("Failed to get workflow for execution")
        raise HTTPException(status_code=500, detail=sanitize_error(e)) from e

    # Convert procedural_memories row to UserWorkflowDefinition
    trigger_conditions = dict(workflow.trigger_conditions)
    metadata_dict = trigger_conditions.pop("metadata", {"category": "productivity"})

    try:
        trigger = WorkflowTrigger(**trigger_conditions)
        actions = [WorkflowAction(**step) for step in workflow.steps]
        metadata = WorkflowMetadata(**metadata_dict)
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid workflow definition: {sanitize_error(e)}"
        ) from e

    definition = UserWorkflowDefinition(
        id=workflow.id,
        user_id=workflow.user_id,
        name=workflow.workflow_name,
        description=workflow.description,
        trigger=trigger,
        actions=actions,
        metadata=metadata,
        is_shared=workflow.is_shared,
    )

    # Execute
    engine = WorkflowEngine()
    try:
        run_status = await engine.execute(
            user_id=str(current_user.id),
            workflow=definition,
            trigger_context=data.trigger_context,
        )
    except Exception as e:
        logger.exception("Workflow execution failed")
        # Record failure
        try:
            await memory.record_outcome(workflow_id, success=False)
        except Exception:
            logger.exception("Failed to record workflow failure outcome")
        raise HTTPException(status_code=500, detail=sanitize_error(e)) from e

    # Record outcome
    success = run_status.status == "completed"
    try:
        await memory.record_outcome(workflow_id, success=success)
    except Exception:
        logger.exception("Failed to record workflow outcome")

    logger.info(
        "Workflow executed",
        extra={
            "user_id": current_user.id,
            "workflow_id": workflow_id,
            "status": run_status.status,
            "steps_completed": run_status.steps_completed,
            "steps_total": run_status.steps_total,
        },
    )

    return run_status.model_dump()
