"""API routes for the Execution Replay Viewer.

Provides two endpoints under ``/skills/audit/{execution_id}/replay``:

* **GET .../replay** -- returns the full :class:`ExecutionReplayResponse`
  JSON payload with role-based redaction applied.
* **GET .../replay/pdf** -- returns a PDF report as a streaming download.
"""

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.core.exceptions import sanitize_error
from src.skills.replay_service import ExecutionReplayData, ReplayService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audit", tags=["skills", "replay"])


# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------


class ExecutionReplayResponse(BaseModel):
    """Top-level response wrapper for the replay endpoint."""

    replay: ExecutionReplayData = Field(..., description="Complete execution replay data.")


# ---------------------------------------------------------------------------
# Service getter
# ---------------------------------------------------------------------------


def _get_replay_service() -> ReplayService:
    """Create a :class:`ReplayService` instance.

    Returns:
        A new replay service instance.
    """
    return ReplayService()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/{execution_id}/replay")
async def get_execution_replay(
    execution_id: str,
    current_user: CurrentUser,
) -> ExecutionReplayResponse:
    """Return the full execution replay for a single audit entry.

    The replay includes the audit entry, associated execution plan,
    working-memory steps, and trust impact.  Role-based redaction is
    applied automatically based on the requesting user's profile.

    Args:
        execution_id: Primary key of the ``skill_audit_log`` row.
        current_user: The authenticated user (injected by FastAPI).

    Returns:
        The replay data wrapped in :class:`ExecutionReplayResponse`.

    Raises:
        HTTPException 404: If the audit entry is not found.
        HTTPException 500: On unexpected errors.
    """
    service = _get_replay_service()
    try:
        replay = await service.get_replay(
            execution_id=execution_id,
            user_id=str(current_user.id),
        )
    except ValueError as e:
        logger.warning(
            "Replay not found",
            extra={
                "execution_id": execution_id,
                "user_id": current_user.id,
            },
        )
        raise HTTPException(status_code=404, detail=sanitize_error(e)) from e
    except Exception as e:
        logger.exception(
            "Failed to build execution replay",
            extra={
                "execution_id": execution_id,
                "user_id": current_user.id,
            },
        )
        raise HTTPException(status_code=500, detail=sanitize_error(e)) from e

    logger.info(
        "Execution replay fetched",
        extra={
            "execution_id": execution_id,
            "user_id": current_user.id,
            "redaction": replay.redaction_applied,
        },
    )

    return ExecutionReplayResponse(replay=replay)


@router.get("/{execution_id}/replay/pdf")
async def get_execution_replay_pdf(
    execution_id: str,
    current_user: CurrentUser,
) -> StreamingResponse:
    """Return the execution replay as a downloadable PDF.

    The PDF uses the same role-based redaction as the JSON endpoint.
    WeasyPrint is lazily imported; if it is not installed, a 501 error
    is returned.

    Args:
        execution_id: Primary key of the ``skill_audit_log`` row.
        current_user: The authenticated user (injected by FastAPI).

    Returns:
        A ``StreamingResponse`` with ``application/pdf`` content type.

    Raises:
        HTTPException 404: If the audit entry is not found.
        HTTPException 501: If WeasyPrint is not installed.
        HTTPException 500: On unexpected errors.
    """
    service = _get_replay_service()

    # 1. Build replay (with redaction)
    try:
        replay = await service.get_replay(
            execution_id=execution_id,
            user_id=str(current_user.id),
        )
    except ValueError as e:
        logger.warning(
            "Replay not found for PDF",
            extra={
                "execution_id": execution_id,
                "user_id": current_user.id,
            },
        )
        raise HTTPException(status_code=404, detail=sanitize_error(e)) from e
    except Exception as e:
        logger.exception(
            "Failed to build replay for PDF",
            extra={
                "execution_id": execution_id,
                "user_id": current_user.id,
            },
        )
        raise HTTPException(status_code=500, detail=sanitize_error(e)) from e

    # 2. Generate PDF
    try:
        from src.skills.replay_pdf import generate_replay_pdf

        pdf_bytes = generate_replay_pdf(replay)
    except RuntimeError as e:
        # WeasyPrint not installed
        logger.warning("PDF generation unavailable: %s", e)
        raise HTTPException(
            status_code=501,
            detail="PDF generation is not available in this environment.",
        ) from e
    except Exception as e:
        logger.exception(
            "PDF generation failed",
            extra={
                "execution_id": execution_id,
                "user_id": current_user.id,
            },
        )
        raise HTTPException(status_code=500, detail=sanitize_error(e)) from e

    logger.info(
        "Execution replay PDF generated",
        extra={
            "execution_id": execution_id,
            "user_id": current_user.id,
            "pdf_size_bytes": len(pdf_bytes),
        },
    )

    filename = f"replay_{execution_id}.pdf"
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
