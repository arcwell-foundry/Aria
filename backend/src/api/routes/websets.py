"""Websets API routes for Exa webhook handling.

Phase 3: Websets Integration for Bulk Lead Generation.

Provides webhook endpoint for real-time Exa Webset event notifications.
"""

import hashlib
import hmac
import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from src.core.config import settings
from src.services.webset_service import WebsetService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/websets", tags=["websets"])


def verify_webhook_signature(
    payload: bytes,
    signature: str,
    secret: str,
) -> bool:
    """Verify Exa webhook signature using HMAC-SHA256.

    Args:
        payload: Raw request body bytes.
        signature: Signature from Exa-Webhook-Signature header.
        secret: Webhook secret for signature verification.

    Returns:
        True if signature is valid, False otherwise.
    """
    if not secret or not signature:
        return False

    try:
        expected_signature = hmac.new(
            secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()

        # Use constant-time comparison to prevent timing attacks
        return hmac.compare_digest(signature, expected_signature)
    except Exception as e:
        logger.warning("Webhook signature verification failed: %s", e)
        return False


@router.post(
    "/webhook",
    status_code=status.HTTP_200_OK,
)
async def exa_webhook(
    request: Request,
) -> dict[str, Any]:
    """Handle Exa Webset webhooks for real-time updates.

    This endpoint receives webhook events from Exa when:
    - webset.items.completed: An item has been processed
    - webset.completed: All items in a Webset are done

    The webhook is verified via HMAC-SHA256 signature.

    Args:
        request: FastAPI request with raw payload.

    Returns:
        Confirmation of webhook receipt.
    """
    try:
        # Get raw payload for signature verification
        payload = await request.body()

        # Get signature header
        signature = request.headers.get("Exa-Webhook-Signature", "")

        # Verify signature
        webhook_secret = settings.EXA_WEBHOOK_SECRET
        if webhook_secret and not verify_webhook_signature(payload, signature, webhook_secret):
            logger.warning(
                "Webhook signature verification failed",
                extra={"signature_present": bool(signature)},
            )
            # Still return 200 to avoid retries, but don't process
            return {"received": False, "error": "Invalid signature"}

        # Parse JSON payload
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            logger.warning("Webhook payload is not valid JSON")
            return {"received": False, "error": "Invalid JSON"}

        event_type = data.get("event_type", data.get("type", "unknown"))
        webset_id = data.get("webset_id", "")

        logger.info(
            "Received Exa webhook: event=%s webset_id=%s",
            event_type,
            webset_id,
        )

        # Handle different event types
        if event_type == "webset.items.completed":
            # Single item completed - trigger immediate import
            item_id = data.get("item_id", "")
            logger.info(
                "Webset item completed: webset=%s item=%s",
                webset_id,
                item_id,
            )

            # Trigger import for this webset
            service = WebsetService()
            result = await service.import_webset_now(webset_id)

            logger.info(
                "Webhook-triggered import: webset=%s imported=%d",
                webset_id,
                result.items_imported,
            )

        elif event_type == "webset.completed":
            # All items completed
            total_items = data.get("items_count", 0)
            logger.info(
                "Webset fully completed: webset=%s items=%d",
                webset_id,
                total_items,
            )

            # Trigger final import
            service = WebsetService()
            result = await service.import_webset_now(webset_id)

            logger.info(
                "Webhook-triggered final import: webset=%s imported=%d",
                webset_id,
                result.items_imported,
            )

        else:
            logger.info(
                "Unhandled webhook event type: %s",
                event_type,
            )

        return {"received": True}

    except Exception:
        logger.exception("Error processing webhook")
        # Always return 200 to avoid retries on known errors
        return {"received": True, "error": "Internal error"}


@router.get(
    "/jobs",
    response_model=list[dict[str, Any]],
    status_code=status.HTTP_200_OK,
)
async def list_webset_jobs(
    request: Request,
    status_filter: str | None = None,
) -> list[dict[str, Any]]:
    """List webset jobs for the current user.

    Args:
        request: FastAPI request with user info.
        status_filter: Optional status filter ('pending', 'processing', etc.).

    Returns:
        List of webset job records.
    """
    from src.api.auth import get_current_user
    from src.db.supabase import SupabaseClient

    try:
        user = await get_current_user(request)
        user_id = user["id"]

        db = SupabaseClient.get_client()
        query = db.table("webset_jobs").select("*").eq("user_id", user_id)

        if status_filter:
            query = query.eq("status", status_filter)

        query = query.order("created_at", desc=True).limit(50)
        result = query.execute()

        return result.data or []  # type: ignore[return-value]

    except Exception:
        logger.exception("Error listing webset jobs")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list webset jobs",
        ) from None


@router.get(
    "/jobs/{job_id}",
    response_model=dict[str, Any],
    status_code=status.HTTP_200_OK,
)
async def get_webset_job(
    request: Request,
    job_id: str,
) -> dict[str, Any]:
    """Get details of a specific webset job.

    Args:
        request: FastAPI request with user info.
        job_id: The webset job UUID.

    Returns:
        Webset job record.
    """
    from src.api.auth import get_current_user
    from src.db.supabase import SupabaseClient

    try:
        user = await get_current_user(request)
        user_id = user["id"]

        db = SupabaseClient.get_client()
        result = (
            db.table("webset_jobs")
            .select("*")
            .eq("id", job_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Webset job not found",
            )

        return result.data  # type: ignore[return-value]

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting webset job")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get webset job",
        ) from None
