"""Social media API routes for ARIA.

This module provides endpoints for:
- Querying LinkedIn post drafts
- Approving, rejecting, scheduling, and publishing drafts
- Viewing published posts
- Approving reply drafts
- Viewing social media stats
"""

import contextlib
import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from src.agents.capabilities.base import UserContext
from src.agents.capabilities.linkedin import LinkedInIntelligenceCapability
from src.api.deps import CurrentUser
from src.db.supabase import SupabaseClient
from src.models.social import (
    DraftApproveRequest,
    DraftRejectRequest,
    DraftScheduleRequest,
    ReplyApproveRequest,
    SocialStatsResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/social", tags=["social"])


def _get_supabase() -> Any:
    """Get Supabase client instance."""
    return SupabaseClient.get_client()


def _get_capability(user_id: str) -> LinkedInIntelligenceCapability:
    """Create a LinkedInIntelligenceCapability for the given user."""
    return LinkedInIntelligenceCapability(
        supabase_client=_get_supabase(),
        memory_service=None,
        knowledge_graph=None,
        user_context=UserContext(user_id=user_id),
    )


@router.get("/drafts")
async def list_drafts(
    current_user: CurrentUser,
    channel: str = Query("linkedin", description="Social channel to filter by"),
) -> list[dict[str, Any]]:
    """List pending social media post drafts.

    Returns a list of draft actions for the current user, filtered by channel.
    """
    db = _get_supabase()

    action_type = f"{channel}_post"
    try:
        resp = (
            db.table("aria_actions")
            .select("*")
            .eq("user_id", current_user.id)
            .eq("action_type", action_type)
            .eq("status", "pending")
            .order("created_at", desc=True)
            .execute()
        )
    except Exception as e:
        logger.exception("Failed to list drafts")
        raise HTTPException(status_code=500, detail="Failed to list drafts. Please try again.") from e

    drafts = resp.data or []

    # Parse payload JSON strings
    for draft in drafts:
        payload = draft.get("payload")
        if isinstance(payload, str):
            with contextlib.suppress(json.JSONDecodeError):
                draft["payload"] = json.loads(payload)
        metadata = draft.get("metadata")
        if isinstance(metadata, str):
            with contextlib.suppress(json.JSONDecodeError):
                draft["metadata"] = json.loads(metadata)

    logger.info(
        "Social drafts listed",
        extra={"user_id": current_user.id, "channel": channel, "count": len(drafts)},
    )

    return drafts


@router.put("/drafts/{draft_id}/approve")
async def approve_draft(
    draft_id: str,
    data: DraftApproveRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Approve a social media post draft.

    Marks the draft as approved with the selected variation and any edits.
    """
    db = _get_supabase()

    try:
        action_resp = (
            db.table("aria_actions")
            .select("*")
            .eq("id", draft_id)
            .eq("user_id", current_user.id)
            .eq("status", "pending")
            .single()
            .execute()
        )
        action = action_resp.data
    except Exception as e:
        logger.warning("Draft not found for approval: %s", e)
        raise HTTPException(status_code=404, detail="Draft not found or not pending") from e

    if not action:
        raise HTTPException(status_code=404, detail="Draft not found or not pending")

    # Update payload with selection and edits
    payload = action.get("payload", {})
    if isinstance(payload, str):
        payload = json.loads(payload)
    payload["selected_variation_index"] = data.selected_variation_index
    if data.edited_text is not None:
        payload["edited_text"] = data.edited_text
    if data.edited_hashtags is not None:
        payload["edited_hashtags"] = data.edited_hashtags

    try:
        db.table("aria_actions").update(
            {
                "status": "approved",
                "payload": json.dumps(payload),
            }
        ).eq("id", draft_id).execute()
    except Exception as e:
        logger.exception("Failed to approve draft")
        raise HTTPException(status_code=500, detail="Failed to approve draft. Please try again.") from e

    logger.info(
        "Draft approved",
        extra={"draft_id": draft_id, "user_id": current_user.id},
    )

    return {"id": draft_id, "status": "approved"}


@router.put("/drafts/{draft_id}/reject")
async def reject_draft(
    draft_id: str,
    data: DraftRejectRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Reject a social media post draft and store feedback.

    Updates the draft status to rejected and stores the rejection reason
    in procedural_memories for ARIA to learn from.
    """
    db = _get_supabase()

    try:
        action_resp = (
            db.table("aria_actions")
            .select("*")
            .eq("id", draft_id)
            .eq("user_id", current_user.id)
            .eq("status", "pending")
            .single()
            .execute()
        )
        action = action_resp.data
    except Exception as e:
        logger.warning("Draft not found for rejection: %s", e)
        raise HTTPException(status_code=404, detail="Draft not found or not pending") from e

    if not action:
        raise HTTPException(status_code=404, detail="Draft not found or not pending")

    try:
        db.table("aria_actions").update(
            {
                "status": "rejected",
                "metadata": json.dumps(
                    {
                        **(
                            json.loads(action.get("metadata", "{}"))
                            if isinstance(action.get("metadata"), str)
                            else (action.get("metadata") or {})
                        ),
                        "rejection_reason": data.reason,
                    }
                ),
            }
        ).eq("id", draft_id).execute()
    except Exception as e:
        logger.exception("Failed to reject draft")
        raise HTTPException(status_code=500, detail="Failed to reject draft. Please try again.") from e

    # Store feedback in procedural_memories for learning
    try:
        import uuid
        from datetime import UTC, datetime

        db.table("procedural_memories").insert(
            {
                "id": str(uuid.uuid4()),
                "user_id": current_user.id,
                "memory_type": "linkedin_post_feedback",
                "title": "LinkedIn post draft rejected",
                "content": data.reason,
                "metadata": json.dumps({"draft_id": draft_id}),
                "created_at": datetime.now(UTC).isoformat(),
            }
        ).execute()
    except Exception as e:
        logger.debug("Failed to store rejection feedback: %s", e)

    logger.info(
        "Draft rejected",
        extra={"draft_id": draft_id, "user_id": current_user.id},
    )

    return {"id": draft_id, "status": "rejected"}


@router.post("/drafts/{draft_id}/publish")
async def publish_draft(
    draft_id: str,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Publish an approved social media post draft to LinkedIn.

    Uses the LinkedInIntelligenceCapability to post via the LinkedIn API.
    """
    cap = _get_capability(current_user.id)
    result = await cap.publish_post(draft_id)

    if not result.success:
        raise HTTPException(status_code=400, detail=result.error or "Publish failed")

    logger.info(
        "Draft published",
        extra={
            "draft_id": draft_id,
            "user_id": current_user.id,
            "post_urn": result.post_urn,
        },
    )

    return {
        "id": draft_id,
        "status": "published",
        "post_urn": result.post_urn,
    }


@router.post("/drafts/{draft_id}/schedule")
async def schedule_draft(
    draft_id: str,
    data: DraftScheduleRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Schedule a social media post draft for future publication."""
    db = _get_supabase()

    try:
        action_resp = (
            db.table("aria_actions")
            .select("*")
            .eq("id", draft_id)
            .eq("user_id", current_user.id)
            .eq("status", "pending")
            .single()
            .execute()
        )
        action = action_resp.data
    except Exception as e:
        logger.warning("Draft not found for scheduling: %s", e)
        raise HTTPException(status_code=404, detail="Draft not found or not pending") from e

    if not action:
        raise HTTPException(status_code=404, detail="Draft not found or not pending")

    # Update payload with selection and edits
    payload = action.get("payload", {})
    if isinstance(payload, str):
        payload = json.loads(payload)
    payload["selected_variation_index"] = data.selected_variation_index
    payload["scheduled_time"] = data.scheduled_time
    if data.edited_text is not None:
        payload["edited_text"] = data.edited_text
    if data.edited_hashtags is not None:
        payload["edited_hashtags"] = data.edited_hashtags

    try:
        db.table("aria_actions").update(
            {
                "status": "scheduled",
                "payload": json.dumps(payload),
            }
        ).eq("id", draft_id).execute()
    except Exception as e:
        logger.exception("Failed to schedule draft")
        raise HTTPException(status_code=500, detail="Failed to schedule draft. Please try again.") from e

    # Create a prospective memory to trigger publish at scheduled time
    try:
        import uuid

        db.table("prospective_memories").insert(
            {
                "id": str(uuid.uuid4()),
                "user_id": current_user.id,
                "memory_type": "scheduled_post",
                "title": "Publish scheduled LinkedIn post",
                "description": f"Publish draft {draft_id}",
                "trigger_time": data.scheduled_time,
                "metadata": json.dumps({"draft_id": draft_id}),
                "status": "pending",
            }
        ).execute()
    except Exception as e:
        logger.debug("Failed to create schedule trigger: %s", e)

    logger.info(
        "Draft scheduled",
        extra={
            "draft_id": draft_id,
            "user_id": current_user.id,
            "scheduled_time": data.scheduled_time,
        },
    )

    return {
        "id": draft_id,
        "status": "scheduled",
        "scheduled_time": data.scheduled_time,
    }


@router.get("/published")
async def list_published(
    current_user: CurrentUser,
    channel: str = Query("linkedin", description="Social channel to filter by"),
) -> list[dict[str, Any]]:
    """List published social media posts.

    Returns published posts for the current user, filtered by channel.
    """
    db = _get_supabase()

    action_type = f"{channel}_post"
    try:
        resp = (
            db.table("aria_actions")
            .select("*")
            .eq("user_id", current_user.id)
            .eq("action_type", action_type)
            .eq("status", "user_approved")
            .order("created_at", desc=True)
            .execute()
        )
    except Exception as e:
        logger.exception("Failed to list published posts")
        raise HTTPException(status_code=500, detail="Failed to list published posts. Please try again.") from e

    posts = resp.data or []

    # Parse payload and metadata JSON strings
    for post in posts:
        payload = post.get("payload")
        if isinstance(payload, str):
            with contextlib.suppress(json.JSONDecodeError):
                post["payload"] = json.loads(payload)
        metadata = post.get("metadata")
        if isinstance(metadata, str):
            with contextlib.suppress(json.JSONDecodeError):
                post["metadata"] = json.loads(metadata)

    logger.info(
        "Published posts listed",
        extra={"user_id": current_user.id, "channel": channel, "count": len(posts)},
    )

    return posts


@router.put("/replies/{reply_id}/approve")
async def approve_reply(
    reply_id: str,
    data: ReplyApproveRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Approve a draft reply to a LinkedIn post comment.

    Optionally accepts edited text for the reply.
    """
    db = _get_supabase()

    try:
        reply_resp = (
            db.table("aria_actions")
            .select("*")
            .eq("id", reply_id)
            .eq("user_id", current_user.id)
            .eq("action_type", "linkedin_reply")
            .eq("status", "pending")
            .single()
            .execute()
        )
        reply = reply_resp.data
    except Exception as e:
        logger.warning("Reply not found for approval: %s", e)
        raise HTTPException(status_code=404, detail="Reply not found or not pending") from e

    if not reply:
        raise HTTPException(status_code=404, detail="Reply not found or not pending")

    # Apply edits if provided
    payload = reply.get("payload", {})
    if isinstance(payload, str):
        payload = json.loads(payload)
    if data.edited_text is not None:
        payload["edited_text"] = data.edited_text

    try:
        db.table("aria_actions").update(
            {
                "status": "approved",
                "payload": json.dumps(payload),
            }
        ).eq("id", reply_id).execute()
    except Exception as e:
        logger.exception("Failed to approve reply")
        raise HTTPException(status_code=500, detail="Failed to approve reply. Please try again.") from e

    logger.info(
        "Reply approved",
        extra={"reply_id": reply_id, "user_id": current_user.id},
    )

    return {"id": reply_id, "status": "approved"}


@router.get("/stats")
async def get_social_stats(
    current_user: CurrentUser,
) -> SocialStatsResponse:
    """Get social media posting statistics for the current user."""
    db = _get_supabase()

    try:
        resp = (
            db.table("aria_actions")
            .select("*")
            .eq("user_id", current_user.id)
            .eq("action_type", "linkedin_post")
            .eq("status", "user_approved")
            .execute()
        )
    except Exception as e:
        logger.exception("Failed to fetch social stats")
        raise HTTPException(status_code=500, detail="Failed to fetch stats. Please try again.") from e

    posts = resp.data or []
    total = len(posts)

    if total == 0:
        return SocialStatsResponse()

    # Calculate averages from engagement metrics
    total_likes = 0
    total_comments = 0
    total_shares = 0
    total_impressions = 0
    best_post_id = None
    best_impressions = 0
    posts_this_week = 0

    from datetime import UTC, datetime, timedelta

    week_ago = (datetime.now(UTC) - timedelta(days=7)).isoformat()

    for post in posts:
        metadata = post.get("metadata", {})
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError:
                metadata = {}

        metrics = metadata.get("engagement_metrics", {})
        total_likes += metrics.get("likes", 0)
        total_comments += metrics.get("comments", 0)
        total_shares += metrics.get("shares", 0)
        impressions = metrics.get("impressions", 0)
        total_impressions += impressions

        if impressions > best_impressions:
            best_impressions = impressions
            best_post_id = post.get("id")

        created = post.get("created_at", "")
        if created > week_ago:
            posts_this_week += 1

    posting_goal = 2

    return SocialStatsResponse(
        total_posts=total,
        posts_this_week=posts_this_week,
        avg_likes=round(total_likes / total, 1) if total else 0.0,
        avg_comments=round(total_comments / total, 1) if total else 0.0,
        avg_shares=round(total_shares / total, 1) if total else 0.0,
        avg_impressions=round(total_impressions / total, 1) if total else 0.0,
        best_post_id=best_post_id,
        best_post_impressions=best_impressions,
        posting_goal=posting_goal,
        posting_goal_met=posts_this_week >= posting_goal,
    )
