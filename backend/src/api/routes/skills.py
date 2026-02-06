"""API routes for skill management."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.security.skill_audit import SkillAuditService
from src.security.trust_levels import SkillTrustLevel
from src.skills.autonomy import SkillAutonomyService
from src.skills.executor import SkillExecutionError, SkillExecutor
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


class StatusResponse(BaseModel):
    """Generic status response."""

    status: str


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


class TrustInfoResponse(BaseModel):
    """Trust/autonomy information for a skill."""

    skill_id: str
    successful_executions: int = 0
    failed_executions: int = 0
    session_trust_granted: bool = False
    globally_approved: bool = False
    globally_approved_at: str | None = None


# --- Request Models ---


class InstallSkillRequest(BaseModel):
    """Request to install a skill."""

    skill_id: str = Field(..., description="UUID of the skill to install")


class ExecuteSkillRequest(BaseModel):
    """Request to execute a skill."""

    skill_id: str = Field(..., description="UUID of the skill to execute")
    input_data: dict[str, Any] = Field(default_factory=dict, description="Input data for the skill")


# --- Service Getters ---


def _get_index() -> SkillIndex:
    return SkillIndex()


def _get_installer() -> SkillInstaller:
    return SkillInstaller()


def _get_audit() -> SkillAuditService:
    return SkillAuditService()


def _get_autonomy() -> SkillAutonomyService:
    return SkillAutonomyService()


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


# --- Endpoints ---


@router.get("/available")
async def list_available_skills(
    current_user: CurrentUser,
    query: str = Query(default="", description="Search query"),
    trust_level: str | None = Query(default=None, description="Filter by trust level"),
    life_sciences: bool | None = Query(default=None, description="Filter life sciences relevant"),
    limit: int = Query(default=50, ge=1, le=200, description="Max results"),
) -> list[AvailableSkillResponse]:
    """List available skills from the index with search and filtering."""
    index = _get_index()

    trust_filter = None
    if trust_level:
        try:
            trust_filter = SkillTrustLevel(trust_level)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid trust_level: {trust_level}. Must be one of: core, verified, community, user",
            ) from e

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
    """List the current user's installed skills."""
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


@router.post("/install")
async def install_skill(
    data: InstallSkillRequest,
    current_user: CurrentUser,
) -> InstalledSkillResponse:
    """Install a skill for the current user."""
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
    """Uninstall a skill for the current user."""
    installer = _get_installer()
    removed = await installer.uninstall(current_user.id, skill_id)

    if not removed:
        raise HTTPException(status_code=404, detail="Skill not installed")

    logger.info(
        "Skill uninstalled",
        extra={"user_id": current_user.id, "skill_id": skill_id},
    )

    return StatusResponse(status="uninstalled")


@router.post("/execute")
async def execute_skill(
    data: ExecuteSkillRequest,
    current_user: CurrentUser,
) -> SkillExecutionResponse:
    """Execute a skill through the security pipeline."""
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


@router.get("/audit")
async def get_audit_log(
    current_user: CurrentUser,
    skill_id: str | None = Query(default=None, description="Filter by skill ID"),
    limit: int = Query(default=50, ge=1, le=500, description="Max entries"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
) -> list[dict[str, Any]]:
    """Get the user's skill execution audit log."""
    audit = _get_audit()

    if skill_id:
        entries = await audit.get_audit_for_skill(
            current_user.id, skill_id, limit=limit, offset=offset
        )
    else:
        entries = await audit.get_audit_log(current_user.id, limit=limit, offset=offset)

    logger.info(
        "Fetched audit log",
        extra={
            "user_id": current_user.id,
            "skill_id": skill_id,
            "count": len(entries),
        },
    )

    return entries


@router.get("/autonomy/{skill_id}")
async def get_skill_trust(
    skill_id: str,
    current_user: CurrentUser,
) -> TrustInfoResponse:
    """Get trust/autonomy level for a skill."""
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
            history.globally_approved_at.isoformat() if history.globally_approved_at else None
        ),
    )


@router.post("/autonomy/{skill_id}/approve")
async def approve_skill(
    skill_id: str,
    current_user: CurrentUser,
) -> TrustInfoResponse:
    """Grant global approval for a skill."""
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
            history.globally_approved_at.isoformat() if history.globally_approved_at else None
        ),
    )
