# LinkedIn Posting & Social Media Drafts Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add LinkedIn post drafting, publishing, and engagement tracking to ARIA's capabilities, with a full Social Media Drafts UI page.

**Architecture:** Extend existing `linkedin.py` capability with 4 new methods (draft_post, publish_post, check_engagement, auto_post_check). New `social.py` API routes following the action_queue pattern. New `SocialPage.tsx` frontend page following ActionQueue page patterns. Trigger integrations in signal_radar.py and meeting_intel.py. User preferences extended with linkedin settings.

**Tech Stack:** Python/FastAPI (backend), React/TypeScript/Tailwind (frontend), Supabase (storage via aria_actions + aria_activity tables), LinkedIn API v2, LLM for draft generation.

---

### Task 1: Backend Pydantic Models for Social/LinkedIn

**Files:**
- Create: `backend/src/models/social.py`

**Step 1: Write the models file**

```python
"""Pydantic models for LinkedIn posting and social media features."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TriggerType(str, Enum):
    """What triggered the post draft."""

    SIGNAL = "signal"
    MEETING = "meeting"
    CURATION = "curation"
    MILESTONE = "milestone"
    CADENCE = "cadence"


class PostVariationType(str, Enum):
    """Type of post variation."""

    INSIGHT = "insight"
    EDUCATIONAL = "educational"
    ENGAGEMENT = "engagement"


class PostVariation(BaseModel):
    """A single post draft variation."""

    variation_type: PostVariationType
    text: str
    hashtags: list[str] = Field(default_factory=list)
    voice_match_confidence: float = Field(0.0, ge=0.0, le=1.0)


class PostDraft(BaseModel):
    """A complete post draft with variations."""

    action_id: str
    trigger_type: TriggerType
    trigger_source: str = ""
    variations: list[PostVariation] = Field(default_factory=list)
    suggested_time: str | None = None
    suggested_time_reasoning: str = ""
    created_at: str = ""


class DraftApproveRequest(BaseModel):
    """Request to approve a draft, optionally with edits."""

    selected_variation_index: int = Field(0, ge=0, description="Which variation to publish")
    edited_text: str | None = Field(None, description="Override text if user edited")
    edited_hashtags: list[str] | None = Field(None, description="Override hashtags if user edited")


class DraftRejectRequest(BaseModel):
    """Request to reject a draft with feedback."""

    reason: str = Field(..., min_length=1, description="Rejection reason for learning")


class DraftScheduleRequest(BaseModel):
    """Request to schedule a draft for a specific time."""

    selected_variation_index: int = Field(0, ge=0)
    edited_text: str | None = None
    edited_hashtags: list[str] | None = None
    scheduled_time: str = Field(..., description="ISO datetime for publishing")


class ReplyApproveRequest(BaseModel):
    """Request to approve a reply draft."""

    edited_text: str | None = Field(None, description="Override reply text if edited")


class PublishResult(BaseModel):
    """Result of publishing a post."""

    success: bool
    post_urn: str | None = None
    error: str | None = None


class EngagementStats(BaseModel):
    """Engagement statistics for a published post."""

    likes: int = 0
    comments: int = 0
    shares: int = 0
    impressions: int = 0


class EngagerInfo(BaseModel):
    """Info about a notable engager."""

    name: str
    linkedin_url: str | None = None
    relationship: str = ""  # "prospect", "customer", "unknown"
    lead_id: str | None = None


class EngagementReport(BaseModel):
    """Full engagement report for a post."""

    stats: EngagementStats
    notable_engagers: list[EngagerInfo] = Field(default_factory=list)
    reply_drafts: list[dict[str, Any]] = Field(default_factory=list)


class SocialStatsResponse(BaseModel):
    """Aggregated social media statistics."""

    total_posts: int = 0
    posts_this_week: int = 0
    avg_likes: float = 0.0
    avg_comments: float = 0.0
    avg_shares: float = 0.0
    avg_impressions: float = 0.0
    best_post_id: str | None = None
    best_post_impressions: int = 0
    posting_goal: int = 2
    posting_goal_met: bool = False
```

**Step 2: Verify lint passes**

Run: `cd /Users/dhruv/aria && python -m ruff check backend/src/models/social.py`
Expected: No errors

**Step 3: Commit**

```bash
git add backend/src/models/social.py
git commit -m "feat: add Pydantic models for LinkedIn posting and social media"
```

---

### Task 2: Extend LinkedIn Capability with draft_post

**Files:**
- Modify: `backend/src/agents/capabilities/linkedin.py` (append new methods)

**Step 1: Add imports and PostDraft/PublishResult types at top of linkedin.py**

Add these imports after existing imports:

```python
import uuid
from datetime import datetime, timezone

from src.models.social import (
    EngagementReport,
    EngagementStats,
    EngagerInfo,
    PostDraft,
    PostVariation,
    PostVariationType,
    PublishResult,
    TriggerType,
)
```

**Step 2: Add draft_post method to LinkedInCapability class**

Append after the existing `draft_connection_request` method:

```python
    async def draft_post(
        self,
        user_id: str,
        trigger_context: dict[str, Any],
    ) -> list[PostDraft]:
        """Generate 2-3 LinkedIn post variations based on trigger context.

        Args:
            user_id: The user to draft for.
            trigger_context: Contains trigger_type and source_data.

        Returns:
            List of PostDraft objects stored in aria_actions.
        """
        from src.core.llm import get_llm_client

        trigger_type = trigger_context.get("trigger_type", "curation")
        source_data = trigger_context.get("source_data", {})

        # Load user's Digital Twin profile for voice matching
        digital_twin = {}
        try:
            sb = self.get_supabase()
            if sb:
                twin_resp = (
                    sb.table("digital_twin_profiles")
                    .select("*")
                    .eq("user_id", user_id)
                    .maybe_single()
                    .execute()
                )
                if twin_resp.data:
                    digital_twin = twin_resp.data
        except Exception:
            logger.warning("Could not load digital twin for %s", user_id)

        # Load user preferences for therapeutic area / hashtag context
        user_prefs: dict[str, Any] = {}
        try:
            sb = self.get_supabase()
            if sb:
                prefs_resp = (
                    sb.table("user_preferences")
                    .select("*")
                    .eq("user_id", user_id)
                    .maybe_single()
                    .execute()
                )
                if prefs_resp.data:
                    user_prefs = prefs_resp.data
        except Exception:
            logger.warning("Could not load preferences for %s", user_id)

        # Build voice guidance from digital twin
        voice_guidance = ""
        if digital_twin:
            tone = digital_twin.get("communication_style", {})
            voice_guidance = (
                f"Match this writing style — "
                f"directness: {tone.get('directness', 'moderate')}, "
                f"formality: {tone.get('formality', 'professional')}, "
                f"warmth: {tone.get('warmth', 'moderate')}. "
                f"Industry vocabulary the user typically uses: "
                f"{', '.join(digital_twin.get('vocabulary', [])[:10])}."
            )

        therapeutic_areas = user_prefs.get("tracked_competitors", [])
        hashtag_context = (
            f"Suggest hashtags relevant to: {', '.join(therapeutic_areas)}"
            if therapeutic_areas
            else "Suggest relevant life sciences industry hashtags"
        )

        source_summary = ""
        if isinstance(source_data, dict):
            source_summary = source_data.get("summary", source_data.get("title", str(source_data)[:500]))
        else:
            source_summary = str(source_data)[:500]

        prompt = (
            "Generate 3 LinkedIn post variations for a life sciences commercial professional.\n\n"
            f"Trigger: {trigger_type}\n"
            f"Source context: {source_summary}\n\n"
            f"{voice_guidance}\n\n"
            "Create exactly 3 variations:\n"
            "1. INSIGHT - A hot take or unique perspective on this topic\n"
            "2. EDUCATIONAL - Share knowledge or teach something from this\n"
            "3. ENGAGEMENT - Ask a thought-provoking question to drive discussion\n\n"
            f"{hashtag_context}\n\n"
            "For each variation, suggest an optimal posting time "
            "(Tuesday/Wednesday 9am EST tends to perform best for B2B life sciences).\n\n"
            "Return valid JSON:\n"
            "{\n"
            '  "variations": [\n'
            "    {\n"
            '      "type": "insight",\n'
            '      "text": "Post text here",\n'
            '      "hashtags": ["#tag1", "#tag2"],\n'
            '      "voice_match_confidence": 0.85\n'
            "    },\n"
            "    {\n"
            '      "type": "educational",\n'
            '      "text": "Post text here",\n'
            '      "hashtags": ["#tag1", "#tag2"],\n'
            '      "voice_match_confidence": 0.80\n'
            "    },\n"
            "    {\n"
            '      "type": "engagement",\n'
            '      "text": "Post text here",\n'
            '      "hashtags": ["#tag1", "#tag2"],\n'
            '      "voice_match_confidence": 0.75\n'
            "    }\n"
            "  ],\n"
            '  "suggested_time": "2026-02-11T14:00:00Z",\n'
            '  "suggested_time_reasoning": "Why this time is optimal"\n'
            "}"
        )

        try:
            llm = get_llm_client()
            raw_response = await llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=(
                    "You are an expert social media strategist for life sciences "
                    "executives. Output ONLY valid JSON."
                ),
                temperature=0.7,
                max_tokens=1500,
            )

            import json

            text = raw_response.strip()
            if text.startswith("```"):
                text = text[text.index("\n") + 1 :]
            if text.endswith("```"):
                text = text[:-3].rstrip()

            draft_data = json.loads(text)
        except Exception as e:
            logger.warning("Failed to generate post drafts: %s", e)
            return []

        # Build PostVariation objects
        variations: list[PostVariation] = []
        for v in draft_data.get("variations", []):
            vtype_str = v.get("type", "insight").upper()
            try:
                vtype = PostVariationType(v.get("type", "insight"))
            except ValueError:
                vtype = PostVariationType.INSIGHT
            variations.append(
                PostVariation(
                    variation_type=vtype,
                    text=v.get("text", ""),
                    hashtags=v.get("hashtags", []),
                    voice_match_confidence=v.get("voice_match_confidence", 0.5),
                )
            )

        # Store in aria_actions
        action_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        try:
            sb = self.get_supabase()
            if sb:
                sb.table("aria_actions").insert(
                    {
                        "id": action_id,
                        "user_id": user_id,
                        "action_type": "linkedin_post",
                        "status": "pending",
                        "estimated_minutes_saved": 15,
                        "metadata": {
                            "trigger_type": trigger_type,
                            "trigger_source": source_summary[:200],
                            "variations": [v.model_dump() for v in variations],
                            "suggested_time": draft_data.get("suggested_time"),
                            "suggested_time_reasoning": draft_data.get(
                                "suggested_time_reasoning", ""
                            ),
                        },
                        "created_at": now,
                    }
                ).execute()
        except Exception as e:
            logger.warning("Failed to store post draft in aria_actions: %s", e)
            return []

        # Log activity
        await self.log_activity(
            activity_type="linkedin_draft_ready",
            title="LinkedIn post drafts ready for review",
            description=(
                f"Generated {len(variations)} LinkedIn post variations "
                f"triggered by {trigger_type}: {source_summary[:100]}"
            ),
            confidence=0.85,
            metadata={
                "action_id": action_id,
                "trigger_type": trigger_type,
                "variation_count": len(variations),
            },
        )

        return [
            PostDraft(
                action_id=action_id,
                trigger_type=TriggerType(trigger_type) if trigger_type in TriggerType.__members__.values() else TriggerType.CURATION,
                trigger_source=source_summary[:200],
                variations=variations,
                suggested_time=draft_data.get("suggested_time"),
                suggested_time_reasoning=draft_data.get("suggested_time_reasoning", ""),
                created_at=now,
            )
        ]
```

**Step 3: Verify lint passes**

Run: `cd /Users/dhruv/aria && python -m ruff check backend/src/agents/capabilities/linkedin.py`

**Step 4: Commit**

```bash
git add backend/src/agents/capabilities/linkedin.py
git commit -m "feat: add draft_post method to LinkedIn capability"
```

---

### Task 3: Add publish_post and check_engagement to LinkedIn Capability

**Files:**
- Modify: `backend/src/agents/capabilities/linkedin.py` (append after draft_post)

**Step 1: Add publish_post method**

```python
    async def publish_post(self, action_id: str) -> PublishResult:
        """Publish an approved LinkedIn post draft.

        Args:
            action_id: The aria_actions row ID containing the approved draft.

        Returns:
            PublishResult with success status and post URN.
        """
        sb = self.get_supabase()
        if not sb:
            return PublishResult(success=False, error="No database connection")

        # Load the approved draft
        try:
            action_resp = (
                sb.table("aria_actions")
                .select("*")
                .eq("id", action_id)
                .eq("user_id", self._user_context.user_id)
                .maybe_single()
                .execute()
            )
            if not action_resp.data:
                return PublishResult(success=False, error="Draft not found")

            action = action_resp.data
            metadata = action.get("metadata", {})
        except Exception as e:
            return PublishResult(success=False, error=f"Failed to load draft: {e}")

        # Get the selected variation text
        variations = metadata.get("variations", [])
        selected_idx = metadata.get("selected_variation_index", 0)
        published_text = metadata.get("edited_text")
        if not published_text and variations:
            idx = min(selected_idx, len(variations) - 1)
            published_text = variations[idx].get("text", "")

        published_hashtags = metadata.get("edited_hashtags")
        if not published_hashtags and variations:
            idx = min(selected_idx, len(variations) - 1)
            published_hashtags = variations[idx].get("hashtags", [])

        if published_hashtags:
            published_text = published_text + "\n\n" + " ".join(published_hashtags)

        if not published_text:
            return PublishResult(success=False, error="No post text to publish")

        # Get user's LinkedIn OAuth token
        try:
            token_resp = (
                sb.table("user_integrations")
                .select("access_token")
                .eq("user_id", self._user_context.user_id)
                .eq("provider", "linkedin")
                .eq("status", "active")
                .maybe_single()
                .execute()
            )
            if not token_resp.data:
                return PublishResult(
                    success=False, error="No active LinkedIn integration found"
                )
            access_token = token_resp.data["access_token"]
        except Exception as e:
            return PublishResult(
                success=False, error=f"Failed to get LinkedIn token: {e}"
            )

        # Get LinkedIn profile URN
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                me_resp = await client.get(
                    "https://api.linkedin.com/v2/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                me_resp.raise_for_status()
                profile_sub = me_resp.json().get("sub", "")
                author_urn = f"urn:li:person:{profile_sub}"
        except Exception as e:
            return PublishResult(
                success=False, error=f"Failed to get LinkedIn profile: {e}"
            )

        # Publish via LinkedIn UGC API
        post_urn = ""
        try:
            ugc_payload = {
                "author": author_urn,
                "lifecycleState": "PUBLISHED",
                "specificContent": {
                    "com.linkedin.ugc.ShareContent": {
                        "shareCommentary": {"text": published_text},
                        "shareMediaCategory": "NONE",
                    }
                },
                "visibility": {
                    "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
                },
            }

            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                pub_resp = await client.post(
                    "https://api.linkedin.com/v2/ugcPosts",
                    json=ugc_payload,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                        "X-Restli-Protocol-Version": "2.0.0",
                    },
                )
                pub_resp.raise_for_status()
                post_urn = pub_resp.headers.get(
                    "X-RestLi-Id", pub_resp.json().get("id", "")
                )
        except Exception as e:
            # Update action as failed
            try:
                sb.table("aria_actions").update(
                    {"status": "rejected", "metadata": {**metadata, "publish_error": str(e)}}
                ).eq("id", action_id).execute()
            except Exception:
                pass
            return PublishResult(success=False, error=f"LinkedIn API error: {e}")

        # Update aria_actions
        now = datetime.now(timezone.utc).isoformat()
        try:
            sb.table("aria_actions").update(
                {
                    "status": "user_approved",
                    "completed_at": now,
                    "metadata": {
                        **metadata,
                        "post_urn": post_urn,
                        "published_text": published_text,
                        "published_at": now,
                    },
                }
            ).eq("id", action_id).execute()
        except Exception as e:
            logger.warning("Failed to update action after publish: %s", e)

        # Schedule engagement checks at 1h, 4h, 24h, 48h via prospective_memories
        check_hours = [1, 4, 24, 48]
        for hours in check_hours:
            try:
                check_time = datetime.now(timezone.utc)
                from datetime import timedelta

                check_time = check_time + timedelta(hours=hours)
                sb.table("prospective_memories").insert(
                    {
                        "id": str(uuid.uuid4()),
                        "user_id": self._user_context.user_id,
                        "memory_type": "scheduled_task",
                        "title": f"Check LinkedIn post engagement ({hours}h)",
                        "description": f"Check engagement metrics for post {post_urn}",
                        "trigger_time": check_time.isoformat(),
                        "status": "pending",
                        "metadata": {
                            "task_type": "linkedin_engagement_check",
                            "post_urn": post_urn,
                            "action_id": action_id,
                            "check_hour": hours,
                        },
                    }
                ).execute()
            except Exception as e:
                logger.warning("Failed to schedule engagement check at %dh: %s", hours, e)

        # Log activity
        await self.log_activity(
            activity_type="linkedin_post_published",
            title="LinkedIn post published",
            description=f"Published LinkedIn post: {published_text[:100]}...",
            confidence=0.95,
            metadata={"action_id": action_id, "post_urn": post_urn},
        )

        return PublishResult(success=True, post_urn=post_urn)
```

**Step 2: Add check_engagement method**

```python
    async def check_engagement(
        self, post_urn: str, user_id: str
    ) -> EngagementReport:
        """Check engagement metrics for a published LinkedIn post.

        Args:
            post_urn: The LinkedIn post URN.
            user_id: The post author's user ID.

        Returns:
            EngagementReport with stats and notable engagers.
        """
        sb = self.get_supabase()
        if not sb:
            return EngagementReport(stats=EngagementStats())

        # Get access token
        try:
            token_resp = (
                sb.table("user_integrations")
                .select("access_token")
                .eq("user_id", user_id)
                .eq("provider", "linkedin")
                .eq("status", "active")
                .maybe_single()
                .execute()
            )
            if not token_resp.data:
                return EngagementReport(stats=EngagementStats())
            access_token = token_resp.data["access_token"]
        except Exception:
            return EngagementReport(stats=EngagementStats())

        # Fetch social actions from LinkedIn
        stats = EngagementStats()
        try:
            encoded_urn = post_urn.replace(":", "%3A")
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(
                    f"https://api.linkedin.com/v2/socialActions/{encoded_urn}",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                resp.raise_for_status()
                data = resp.json()

                stats = EngagementStats(
                    likes=data.get("likesSummary", {}).get("totalLikes", 0),
                    comments=data.get("commentsSummary", {}).get("totalFirstLevelComments", 0),
                    shares=data.get("sharesSummary", {}).get("totalShares", 0),
                    impressions=data.get("impressionsSummary", {}).get("totalImpressions", 0),
                )
        except Exception as e:
            logger.warning("Failed to fetch LinkedIn engagement: %s", e)

        # Cross-reference engagers with lead_memories
        notable_engagers: list[EngagerInfo] = []
        # Note: LinkedIn API limits who you can see engaged — this is best-effort
        try:
            likes_resp_data: list[dict[str, Any]] = []
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                likes_resp = await client.get(
                    f"https://api.linkedin.com/v2/socialActions/{encoded_urn}/likes",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={"count": 50},
                )
                if likes_resp.status_code == 200:
                    likes_resp_data = likes_resp.json().get("elements", [])

            for like in likes_resp_data:
                actor_urn = like.get("actor", "")
                # Check if this person is in our lead_memories
                lead_match = (
                    sb.table("lead_memory_stakeholders")
                    .select("id, name, lead_id, role")
                    .ilike("linkedin_url", f"%{actor_urn.split(':')[-1]}%")
                    .eq("user_id", user_id)
                    .limit(1)
                    .execute()
                )
                if lead_match.data:
                    match = lead_match.data[0]
                    # Check if prospect or customer
                    lead_resp = (
                        sb.table("lead_memories")
                        .select("lifecycle_stage")
                        .eq("id", match["lead_id"])
                        .maybe_single()
                        .execute()
                    )
                    relationship = "unknown"
                    if lead_resp.data:
                        stage = lead_resp.data.get("lifecycle_stage", "")
                        if stage in ("PROSPECT", "QUALIFIED", "PROPOSAL"):
                            relationship = "prospect"
                        elif stage in ("CUSTOMER", "ACCOUNT"):
                            relationship = "customer"

                    notable_engagers.append(
                        EngagerInfo(
                            name=match.get("name", "Unknown"),
                            linkedin_url=f"https://linkedin.com/in/{actor_urn.split(':')[-1]}",
                            relationship=relationship,
                            lead_id=match.get("lead_id"),
                        )
                    )
        except Exception as e:
            logger.warning("Failed to cross-reference engagers: %s", e)

        # Store engagement data on the aria_actions row
        try:
            action_resp = (
                sb.table("aria_actions")
                .select("id, metadata")
                .eq("user_id", user_id)
                .filter("metadata->>post_urn", "eq", post_urn)
                .limit(1)
                .execute()
            )
            if action_resp.data:
                action = action_resp.data[0]
                existing_meta = action.get("metadata", {})
                existing_meta["engagement_metrics"] = stats.model_dump()
                existing_meta["notable_engagers"] = [e.model_dump() for e in notable_engagers]
                sb.table("aria_actions").update(
                    {"metadata": existing_meta}
                ).eq("id", action["id"]).execute()
        except Exception as e:
            logger.warning("Failed to store engagement metrics: %s", e)

        # Create notification if a notable prospect engaged
        for engager in notable_engagers:
            if engager.relationship == "prospect":
                try:
                    sb.table("notifications").insert(
                        {
                            "id": str(uuid.uuid4()),
                            "user_id": user_id,
                            "type": "linkedin_prospect_engaged",
                            "title": f"Prospect {engager.name} engaged with your post",
                            "message": (
                                f"{engager.name} liked your LinkedIn post. "
                                "This could be a good opportunity to follow up."
                            ),
                            "metadata": {
                                "post_urn": post_urn,
                                "engager_name": engager.name,
                                "lead_id": engager.lead_id,
                            },
                            "read": False,
                        }
                    ).execute()
                except Exception:
                    pass

        # Log activity
        await self.log_activity(
            activity_type="linkedin_engagement_checked",
            title=f"LinkedIn engagement: {stats.likes} likes, {stats.comments} comments",
            description=(
                f"Post {post_urn}: {stats.likes} likes, {stats.comments} comments, "
                f"{stats.shares} shares, {stats.impressions} impressions. "
                f"{len(notable_engagers)} notable engagers found."
            ),
            confidence=0.9,
            metadata={
                "post_urn": post_urn,
                "stats": stats.model_dump(),
                "notable_count": len(notable_engagers),
            },
        )

        return EngagementReport(
            stats=stats,
            notable_engagers=notable_engagers,
        )
```

**Step 3: Add auto_post_check method**

```python
    async def auto_post_check(self, user_id: str) -> None:
        """Check for auto-publishable drafts (called by scheduler).

        Auto-approves and publishes drafts where voice_match_confidence > 0.8
        and the user has enabled auto-posting.

        Args:
            user_id: User to check drafts for.
        """
        sb = self.get_supabase()
        if not sb:
            return

        # Check if user has auto-posting enabled
        try:
            prefs_resp = (
                sb.table("user_preferences")
                .select("metadata")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )
            if not prefs_resp.data:
                return

            prefs_meta = prefs_resp.data.get("metadata", {})
            if not prefs_meta.get("linkedin_auto_post", False):
                return
        except Exception:
            return

        # Find pending linkedin_post drafts
        try:
            pending_resp = (
                sb.table("aria_actions")
                .select("id, metadata")
                .eq("user_id", user_id)
                .eq("action_type", "linkedin_post")
                .eq("status", "pending")
                .execute()
            )
            if not pending_resp.data:
                return
        except Exception:
            return

        # Sensitive topic keywords to skip
        sensitive_keywords = [
            "lawsuit", "layoff", "controversy", "scandal", "fired",
            "investigation", "violation", "recall", "death", "adverse",
        ]

        for action in pending_resp.data:
            metadata = action.get("metadata", {})
            variations = metadata.get("variations", [])

            # Find highest-confidence variation
            best_var = None
            best_confidence = 0.0
            best_idx = 0
            for idx, v in enumerate(variations):
                conf = v.get("voice_match_confidence", 0.0)
                if conf > best_confidence:
                    best_confidence = conf
                    best_var = v
                    best_idx = idx

            if best_confidence <= 0.8 or not best_var:
                continue

            # Check for sensitive content
            text = best_var.get("text", "").lower()
            has_sensitive = any(kw in text for kw in sensitive_keywords)
            if has_sensitive:
                continue

            # Auto-approve and publish
            try:
                metadata["selected_variation_index"] = best_idx
                sb.table("aria_actions").update(
                    {"status": "user_approved", "metadata": metadata}
                ).eq("id", action["id"]).execute()

                await self.publish_post(action["id"])

                await self.log_activity(
                    activity_type="linkedin_auto_published",
                    title="LinkedIn post auto-published",
                    description=(
                        f"Auto-published high-confidence draft "
                        f"(confidence: {best_confidence:.0%})"
                    ),
                    confidence=best_confidence,
                    metadata={"action_id": action["id"]},
                )
            except Exception as e:
                logger.warning("Failed to auto-publish draft %s: %s", action["id"], e)
```

**Step 4: Verify lint passes**

Run: `cd /Users/dhruv/aria && python -m ruff check backend/src/agents/capabilities/linkedin.py`

**Step 5: Commit**

```bash
git add backend/src/agents/capabilities/linkedin.py
git commit -m "feat: add publish_post, check_engagement, auto_post_check to LinkedIn capability"
```

---

### Task 4: Social Media API Routes

**Files:**
- Create: `backend/src/api/routes/social.py`

**Step 1: Create the social routes file**

```python
"""Social media API routes for LinkedIn posting and engagement."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from src.api.deps import CurrentUser
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
    """Get Supabase client."""
    from src.db.supabase import SupabaseClient

    return SupabaseClient.get_client()


# ---------- Drafts ----------


@router.get("/drafts")
async def list_drafts(
    current_user: CurrentUser,
    channel: str = Query("linkedin", description="Social channel"),
) -> list[dict[str, Any]]:
    """List pending social media drafts for the current user."""
    sb = _get_supabase()
    try:
        resp = (
            sb.table("aria_actions")
            .select("*")
            .eq("user_id", current_user.id)
            .eq("action_type", f"{channel}_post")
            .eq("status", "pending")
            .order("created_at", desc=True)
            .execute()
        )
        return resp.data or []
    except Exception as e:
        logger.error("Failed to list drafts: %s", e)
        raise HTTPException(status_code=500, detail="Failed to list drafts") from e


@router.put("/drafts/{draft_id}/approve")
async def approve_draft(
    draft_id: str,
    body: DraftApproveRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Approve a draft with optional edits."""
    sb = _get_supabase()
    try:
        action_resp = (
            sb.table("aria_actions")
            .select("*")
            .eq("id", draft_id)
            .eq("user_id", current_user.id)
            .eq("status", "pending")
            .maybe_single()
            .execute()
        )
        if not action_resp.data:
            raise HTTPException(status_code=404, detail="Draft not found or not pending")

        metadata = action_resp.data.get("metadata", {})
        metadata["selected_variation_index"] = body.selected_variation_index
        if body.edited_text is not None:
            metadata["edited_text"] = body.edited_text
        if body.edited_hashtags is not None:
            metadata["edited_hashtags"] = body.edited_hashtags

        update_resp = (
            sb.table("aria_actions")
            .update({"status": "user_approved", "metadata": metadata})
            .eq("id", draft_id)
            .execute()
        )

        logger.info(
            "Draft approved",
            extra={"draft_id": draft_id, "user_id": current_user.id},
        )
        return update_resp.data[0] if update_resp.data else {"id": draft_id, "status": "user_approved"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to approve draft: %s", e)
        raise HTTPException(status_code=500, detail="Failed to approve draft") from e


@router.put("/drafts/{draft_id}/reject")
async def reject_draft(
    draft_id: str,
    body: DraftRejectRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Reject a draft with feedback for learning."""
    sb = _get_supabase()
    try:
        action_resp = (
            sb.table("aria_actions")
            .select("*")
            .eq("id", draft_id)
            .eq("user_id", current_user.id)
            .eq("status", "pending")
            .maybe_single()
            .execute()
        )
        if not action_resp.data:
            raise HTTPException(status_code=404, detail="Draft not found or not pending")

        metadata = action_resp.data.get("metadata", {})
        metadata["rejection_reason"] = body.reason

        update_resp = (
            sb.table("aria_actions")
            .update({"status": "rejected", "metadata": metadata})
            .eq("id", draft_id)
            .execute()
        )

        # Store rejection feedback in procedural_memories for learning
        try:
            import uuid
            from datetime import datetime, timezone

            sb.table("procedural_memories").insert(
                {
                    "id": str(uuid.uuid4()),
                    "user_id": current_user.id,
                    "memory_type": "linkedin_feedback",
                    "title": "LinkedIn draft rejection feedback",
                    "content": body.reason,
                    "metadata": {
                        "draft_id": draft_id,
                        "trigger_type": metadata.get("trigger_type"),
                    },
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            ).execute()
        except Exception as e:
            logger.warning("Failed to store rejection feedback: %s", e)

        logger.info(
            "Draft rejected",
            extra={"draft_id": draft_id, "user_id": current_user.id, "reason": body.reason},
        )
        return update_resp.data[0] if update_resp.data else {"id": draft_id, "status": "rejected"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to reject draft: %s", e)
        raise HTTPException(status_code=500, detail="Failed to reject draft") from e


@router.post("/drafts/{draft_id}/publish")
async def publish_draft(
    draft_id: str,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Publish an approved draft immediately."""
    from src.agents.capabilities.base import UserContext
    from src.agents.capabilities.linkedin import LinkedInCapability

    cap = LinkedInCapability(
        supabase_client=_get_supabase(),
        memory_service=None,
        knowledge_graph=None,
        user_context=UserContext(user_id=current_user.id),
    )
    result = await cap.publish_post(draft_id)

    if not result.success:
        raise HTTPException(status_code=400, detail=result.error or "Publish failed")

    logger.info(
        "Draft published",
        extra={"draft_id": draft_id, "user_id": current_user.id, "post_urn": result.post_urn},
    )
    return {"id": draft_id, "post_urn": result.post_urn, "status": "published"}


@router.post("/drafts/{draft_id}/schedule")
async def schedule_draft(
    draft_id: str,
    body: DraftScheduleRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Schedule a draft for publication at a specific time."""
    sb = _get_supabase()
    try:
        action_resp = (
            sb.table("aria_actions")
            .select("*")
            .eq("id", draft_id)
            .eq("user_id", current_user.id)
            .eq("status", "pending")
            .maybe_single()
            .execute()
        )
        if not action_resp.data:
            raise HTTPException(status_code=404, detail="Draft not found or not pending")

        metadata = action_resp.data.get("metadata", {})
        metadata["selected_variation_index"] = body.selected_variation_index
        metadata["scheduled_time"] = body.scheduled_time
        if body.edited_text is not None:
            metadata["edited_text"] = body.edited_text
        if body.edited_hashtags is not None:
            metadata["edited_hashtags"] = body.edited_hashtags

        update_resp = (
            sb.table("aria_actions")
            .update({"status": "user_approved", "metadata": metadata})
            .eq("id", draft_id)
            .execute()
        )

        # Schedule publication via prospective_memories
        import uuid
        sb.table("prospective_memories").insert(
            {
                "id": str(uuid.uuid4()),
                "user_id": current_user.id,
                "memory_type": "scheduled_task",
                "title": "Publish scheduled LinkedIn post",
                "description": f"Publish LinkedIn post draft {draft_id}",
                "trigger_time": body.scheduled_time,
                "status": "pending",
                "metadata": {
                    "task_type": "linkedin_scheduled_publish",
                    "action_id": draft_id,
                },
            }
        ).execute()

        logger.info(
            "Draft scheduled",
            extra={
                "draft_id": draft_id,
                "user_id": current_user.id,
                "scheduled_time": body.scheduled_time,
            },
        )
        return update_resp.data[0] if update_resp.data else {
            "id": draft_id,
            "status": "scheduled",
            "scheduled_time": body.scheduled_time,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to schedule draft: %s", e)
        raise HTTPException(status_code=500, detail="Failed to schedule draft") from e


# ---------- Published ----------


@router.get("/published")
async def list_published(
    current_user: CurrentUser,
    channel: str = Query("linkedin", description="Social channel"),
) -> list[dict[str, Any]]:
    """List published posts with engagement data."""
    sb = _get_supabase()
    try:
        resp = (
            sb.table("aria_actions")
            .select("*")
            .eq("user_id", current_user.id)
            .eq("action_type", f"{channel}_post")
            .eq("status", "user_approved")
            .not_.is_("completed_at", "null")
            .order("completed_at", desc=True)
            .execute()
        )
        return resp.data or []
    except Exception as e:
        logger.error("Failed to list published posts: %s", e)
        raise HTTPException(status_code=500, detail="Failed to list published posts") from e


# ---------- Replies ----------


@router.put("/replies/{reply_id}/approve")
async def approve_reply(
    reply_id: str,
    body: ReplyApproveRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Approve a draft reply to a LinkedIn comment."""
    sb = _get_supabase()
    try:
        action_resp = (
            sb.table("aria_actions")
            .select("*")
            .eq("id", reply_id)
            .eq("user_id", current_user.id)
            .eq("status", "pending")
            .maybe_single()
            .execute()
        )
        if not action_resp.data:
            raise HTTPException(status_code=404, detail="Reply draft not found")

        metadata = action_resp.data.get("metadata", {})
        if body.edited_text is not None:
            metadata["edited_text"] = body.edited_text

        update_resp = (
            sb.table("aria_actions")
            .update({"status": "user_approved", "metadata": metadata})
            .eq("id", reply_id)
            .execute()
        )

        logger.info(
            "Reply approved",
            extra={"reply_id": reply_id, "user_id": current_user.id},
        )
        return update_resp.data[0] if update_resp.data else {"id": reply_id, "status": "approved"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to approve reply: %s", e)
        raise HTTPException(status_code=500, detail="Failed to approve reply") from e


# ---------- Stats ----------


@router.get("/stats")
async def get_social_stats(
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get aggregated social media posting statistics."""
    sb = _get_supabase()
    try:
        # Get all linkedin posts for this user
        resp = (
            sb.table("aria_actions")
            .select("*")
            .eq("user_id", current_user.id)
            .eq("action_type", "linkedin_post")
            .eq("status", "user_approved")
            .order("completed_at", desc=True)
            .execute()
        )
        posts = resp.data or []

        total_posts = len(posts)
        if total_posts == 0:
            return SocialStatsResponse().model_dump()

        # Calculate averages from engagement_metrics in metadata
        total_likes = 0
        total_comments = 0
        total_shares = 0
        total_impressions = 0
        best_post_id = None
        best_impressions = 0
        posts_with_metrics = 0

        from datetime import datetime, timedelta, timezone

        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        posts_this_week = 0

        for post in posts:
            meta = post.get("metadata", {})
            metrics = meta.get("engagement_metrics", {})
            if metrics:
                posts_with_metrics += 1
                total_likes += metrics.get("likes", 0)
                total_comments += metrics.get("comments", 0)
                total_shares += metrics.get("shares", 0)
                imps = metrics.get("impressions", 0)
                total_impressions += imps
                if imps > best_impressions:
                    best_impressions = imps
                    best_post_id = post["id"]

            completed = post.get("completed_at", "")
            if completed and completed >= week_ago:
                posts_this_week += 1

        # Get posting goal from preferences
        posting_goal = 2
        try:
            prefs_resp = (
                sb.table("user_preferences")
                .select("metadata")
                .eq("user_id", current_user.id)
                .maybe_single()
                .execute()
            )
            if prefs_resp.data:
                prefs_meta = prefs_resp.data.get("metadata", {})
                posting_goal = prefs_meta.get("linkedin_posts_per_week_goal", 2)
        except Exception:
            pass

        denom = max(posts_with_metrics, 1)

        return SocialStatsResponse(
            total_posts=total_posts,
            posts_this_week=posts_this_week,
            avg_likes=round(total_likes / denom, 1),
            avg_comments=round(total_comments / denom, 1),
            avg_shares=round(total_shares / denom, 1),
            avg_impressions=round(total_impressions / denom, 1),
            best_post_id=best_post_id,
            best_post_impressions=best_impressions,
            posting_goal=posting_goal,
            posting_goal_met=posts_this_week >= posting_goal,
        ).model_dump()
    except Exception as e:
        logger.error("Failed to get social stats: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get social stats") from e
```

**Step 2: Register the router in main.py**

In `backend/src/main.py`, add `social` to the imports and register the router.

Add to imports:
```python
    social,
```

Add router registration:
```python
app.include_router(social.router, prefix="/api/v1")
```

**Step 3: Verify lint passes**

Run: `cd /Users/dhruv/aria && python -m ruff check backend/src/api/routes/social.py backend/src/main.py`

**Step 4: Commit**

```bash
git add backend/src/api/routes/social.py backend/src/main.py
git commit -m "feat: add social media API routes for LinkedIn posting workflow"
```

---

### Task 5: Trigger Integrations (signal_radar + meeting_intel + predictive_preexec)

**Files:**
- Modify: `backend/src/agents/capabilities/signal_radar.py` (in `create_alerts` method)
- Modify: `backend/src/agents/capabilities/meeting_intel.py` (in `process_transcript` method)
- Modify: `backend/src/skills/predictive_preexec.py` (add cadence check)

**Step 1: Add LinkedIn draft trigger to signal_radar.py create_alerts**

Find the `create_alerts` method (search for `async def create_alerts` or the notification creation block). After the block that creates notifications for high-relevance signals, add:

```python
            # Trigger LinkedIn post draft for high-relevance signals
            if signal.get("relevance_score", 0) >= 0.7:
                try:
                    from src.agents.capabilities.base import UserContext
                    from src.agents.capabilities.linkedin import LinkedInCapability

                    linkedin_cap = LinkedInCapability(
                        supabase_client=self.get_supabase(),
                        memory_service=self.get_memory(),
                        knowledge_graph=self.get_kg(),
                        user_context=UserContext(user_id=self._user_context.user_id),
                    )
                    await linkedin_cap.draft_post(
                        user_id=self._user_context.user_id,
                        trigger_context={
                            "trigger_type": "signal",
                            "source_data": {
                                "title": signal.get("title", ""),
                                "summary": signal.get("summary", signal.get("description", "")),
                                "signal_type": signal.get("signal_type", ""),
                                "source": signal.get("source", ""),
                            },
                        },
                    )
                except Exception as e:
                    logger.warning("Failed to trigger LinkedIn draft from signal: %s", e)
```

**Step 2: Add LinkedIn draft trigger to meeting_intel.py**

Find the `execute` method in MeetingIntelCapability, specifically after the transcript analysis is complete and insights are stored. Add after the main analysis block:

```python
        # Trigger LinkedIn post if meeting had shareable industry insights
        try:
            key_topics = analysis_result.get("key_topics", [])
            industry_topics = [
                t for t in key_topics
                if any(
                    kw in t.lower()
                    for kw in ["trend", "market", "industry", "innovation", "research", "launch", "pipeline"]
                )
            ]
            if industry_topics:
                from src.agents.capabilities.linkedin import LinkedInCapability

                linkedin_cap = LinkedInCapability(
                    supabase_client=self.get_supabase(),
                    memory_service=self.get_memory(),
                    knowledge_graph=self.get_kg(),
                    user_context=self._user_context,
                )
                await linkedin_cap.draft_post(
                    user_id=self._user_context.user_id,
                    trigger_context={
                        "trigger_type": "meeting",
                        "source_data": {
                            "title": f"Meeting insights: {', '.join(industry_topics[:3])}",
                            "summary": analysis_result.get("summary", ""),
                            "key_topics": industry_topics,
                        },
                    },
                )
        except Exception as e:
            logger.warning("Failed to trigger LinkedIn draft from meeting: %s", e)
```

**Step 3: Add cadence checker to predictive_preexec.py**

Find the `_run_precompute_cycle` method. Add a new category after the existing ones (meeting briefs, follow-ups, battle cards, contact enrichment):

```python
        # 5. LinkedIn cadence drafts — if posting goal not met this week
        try:
            from datetime import timedelta

            week_ago = (now - timedelta(days=7)).isoformat()

            # Count posts published this week
            posts_resp = (
                sb.table("aria_actions")
                .select("id", count="exact")
                .eq("user_id", user_id)
                .eq("action_type", "linkedin_post")
                .eq("status", "user_approved")
                .gte("completed_at", week_ago)
                .execute()
            )
            posts_this_week = posts_resp.count or 0

            # Get posting goal from preferences
            posting_goal = 2
            prefs_resp = (
                sb.table("user_preferences")
                .select("metadata")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )
            if prefs_resp.data:
                prefs_meta = prefs_resp.data.get("metadata", {})
                posting_goal = prefs_meta.get("linkedin_posts_per_week_goal", 2)
                if not prefs_meta.get("linkedin_posting_enabled", False):
                    posting_goal = 0  # Skip if posting disabled

            if posting_goal > 0 and posts_this_week < posting_goal:
                # Get recent signals to curate from
                signals_resp = (
                    sb.table("market_signals")
                    .select("title, summary, signal_type, source")
                    .eq("user_id", user_id)
                    .gte("created_at", week_ago)
                    .order("relevance_score", desc=True)
                    .limit(3)
                    .execute()
                )
                if signals_resp.data:
                    from src.agents.capabilities.base import UserContext
                    from src.agents.capabilities.linkedin import LinkedInCapability

                    linkedin_cap = LinkedInCapability(
                        supabase_client=sb,
                        memory_service=None,
                        knowledge_graph=None,
                        user_context=UserContext(user_id=user_id),
                    )
                    curated_source = "\n".join(
                        f"- {s.get('title', '')}: {s.get('summary', '')[:150]}"
                        for s in signals_resp.data
                    )
                    await linkedin_cap.draft_post(
                        user_id=user_id,
                        trigger_context={
                            "trigger_type": "cadence",
                            "source_data": {
                                "title": "Weekly posting cadence — curated from recent signals",
                                "summary": curated_source,
                            },
                        },
                    )
                    precomputed_count += 1

                    await activity_service.record(
                        user_id=user_id,
                        agent="operator",
                        activity_type="predictive_preexec",
                        title="LinkedIn cadence draft generated",
                        description=(
                            f"Posting goal: {posting_goal}/week, "
                            f"current: {posts_this_week}. "
                            "Generated curated post draft from recent signals."
                        ),
                        confidence=0.8,
                    )
        except Exception as e:
            logger.warning("LinkedIn cadence check failed for %s: %s", user_id, e)
```

**Step 4: Verify lint passes**

Run: `cd /Users/dhruv/aria && python -m ruff check backend/src/agents/capabilities/signal_radar.py backend/src/agents/capabilities/meeting_intel.py backend/src/skills/predictive_preexec.py`

**Step 5: Commit**

```bash
git add backend/src/agents/capabilities/signal_radar.py backend/src/agents/capabilities/meeting_intel.py backend/src/skills/predictive_preexec.py
git commit -m "feat: add LinkedIn draft triggers in signal_radar, meeting_intel, and cadence checker"
```

---

### Task 6: Frontend API Client and React Query Hooks

**Files:**
- Create: `frontend/src/api/social.ts`
- Create: `frontend/src/hooks/useSocial.ts`

**Step 1: Create the API client**

```typescript
import { apiClient } from "./client";

// Types
export interface PostVariation {
  variation_type: "insight" | "educational" | "engagement";
  text: string;
  hashtags: string[];
  voice_match_confidence: number;
}

export interface SocialDraft {
  id: string;
  user_id: string;
  action_type: string;
  status: string;
  metadata: {
    trigger_type: string;
    trigger_source: string;
    variations: PostVariation[];
    suggested_time: string | null;
    suggested_time_reasoning: string;
    selected_variation_index?: number;
    edited_text?: string;
    edited_hashtags?: string[];
    scheduled_time?: string;
    rejection_reason?: string;
    post_urn?: string;
    published_text?: string;
    published_at?: string;
    engagement_metrics?: EngagementStats;
    notable_engagers?: NotableEngager[];
  };
  estimated_minutes_saved: number;
  created_at: string;
  completed_at: string | null;
}

export interface EngagementStats {
  likes: number;
  comments: number;
  shares: number;
  impressions: number;
}

export interface NotableEngager {
  name: string;
  linkedin_url: string | null;
  relationship: string;
  lead_id: string | null;
}

export interface SocialStats {
  total_posts: number;
  posts_this_week: number;
  avg_likes: number;
  avg_comments: number;
  avg_shares: number;
  avg_impressions: number;
  best_post_id: string | null;
  best_post_impressions: number;
  posting_goal: number;
  posting_goal_met: boolean;
}

// API functions
export async function listDrafts(channel = "linkedin"): Promise<SocialDraft[]> {
  const response = await apiClient.get<SocialDraft[]>(`/social/drafts?channel=${channel}`);
  return response.data;
}

export async function approveDraft(
  draftId: string,
  data: {
    selected_variation_index: number;
    edited_text?: string;
    edited_hashtags?: string[];
  },
): Promise<SocialDraft> {
  const response = await apiClient.put<SocialDraft>(`/social/drafts/${draftId}/approve`, data);
  return response.data;
}

export async function rejectDraft(draftId: string, reason: string): Promise<SocialDraft> {
  const response = await apiClient.put<SocialDraft>(`/social/drafts/${draftId}/reject`, { reason });
  return response.data;
}

export async function publishDraft(
  draftId: string,
): Promise<{ id: string; post_urn: string; status: string }> {
  const response = await apiClient.post<{ id: string; post_urn: string; status: string }>(
    `/social/drafts/${draftId}/publish`,
  );
  return response.data;
}

export async function scheduleDraft(
  draftId: string,
  data: {
    selected_variation_index: number;
    scheduled_time: string;
    edited_text?: string;
    edited_hashtags?: string[];
  },
): Promise<SocialDraft> {
  const response = await apiClient.post<SocialDraft>(`/social/drafts/${draftId}/schedule`, data);
  return response.data;
}

export async function listPublished(channel = "linkedin"): Promise<SocialDraft[]> {
  const response = await apiClient.get<SocialDraft[]>(`/social/published?channel=${channel}`);
  return response.data;
}

export async function approveReply(
  replyId: string,
  editedText?: string,
): Promise<SocialDraft> {
  const response = await apiClient.put<SocialDraft>(`/social/replies/${replyId}/approve`, {
    edited_text: editedText ?? null,
  });
  return response.data;
}

export async function getSocialStats(): Promise<SocialStats> {
  const response = await apiClient.get<SocialStats>("/social/stats");
  return response.data;
}
```

**Step 2: Create the React Query hooks**

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  approveDraft,
  approveReply,
  getSocialStats,
  listDrafts,
  listPublished,
  publishDraft,
  rejectDraft,
  scheduleDraft,
} from "@/api/social";

const SOCIAL_KEYS = {
  drafts: (channel: string) => ["social", "drafts", channel] as const,
  published: (channel: string) => ["social", "published", channel] as const,
  stats: ["social", "stats"] as const,
};

export function useSocialDrafts(channel = "linkedin") {
  return useQuery({
    queryKey: SOCIAL_KEYS.drafts(channel),
    queryFn: () => listDrafts(channel),
  });
}

export function useSocialPublished(channel = "linkedin") {
  return useQuery({
    queryKey: SOCIAL_KEYS.published(channel),
    queryFn: () => listPublished(channel),
  });
}

export function useSocialStats() {
  return useQuery({
    queryKey: SOCIAL_KEYS.stats,
    queryFn: getSocialStats,
  });
}

export function useApproveDraft() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      draftId,
      data,
    }: {
      draftId: string;
      data: { selected_variation_index: number; edited_text?: string; edited_hashtags?: string[] };
    }) => approveDraft(draftId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["social"] });
    },
  });
}

export function useRejectDraft() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ draftId, reason }: { draftId: string; reason: string }) =>
      rejectDraft(draftId, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["social"] });
    },
  });
}

export function usePublishDraft() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (draftId: string) => publishDraft(draftId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["social"] });
    },
  });
}

export function useScheduleDraft() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      draftId,
      data,
    }: {
      draftId: string;
      data: {
        selected_variation_index: number;
        scheduled_time: string;
        edited_text?: string;
        edited_hashtags?: string[];
      };
    }) => scheduleDraft(draftId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["social"] });
    },
  });
}

export function useApproveReply() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ replyId, editedText }: { replyId: string; editedText?: string }) =>
      approveReply(replyId, editedText),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["social"] });
    },
  });
}
```

**Step 3: Verify lint passes**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit --pretty 2>&1 | head -30`

**Step 4: Commit**

```bash
git add frontend/src/api/social.ts frontend/src/hooks/useSocial.ts
git commit -m "feat: add social media API client and React Query hooks"
```

---

### Task 7: Social Media Page — SocialPage.tsx

**Files:**
- Create: `frontend/src/pages/SocialPage.tsx`

**Step 1: Create the Social page component**

This is a large file. Create it following the ActionQueue page pattern with DashboardLayout wrapper, dark theme, three sections (Drafts, Scheduled, Published), tab bar, and all CRUD operations.

```typescript
import { useMemo, useState } from "react";
import { DashboardLayout } from "@/components/DashboardLayout";
import { HelpTooltip } from "@/components/HelpTooltip";
import type { PostVariation, SocialDraft } from "@/api/social";
import {
  useSocialDrafts,
  useSocialPublished,
  useSocialStats,
  useApproveDraft,
  useRejectDraft,
  usePublishDraft,
  useScheduleDraft,
  useApproveReply,
} from "@/hooks/useSocial";
import {
  Share2,
  Clock,
  Send,
  ThumbsUp,
  MessageSquare,
  Repeat2,
  Eye,
  X,
  Check,
  Calendar,
  Hash,
  Sparkles,
  BookOpen,
  HelpCircle,
  Target,
  Handshake,
  ChevronDown,
  Loader2,
} from "lucide-react";

// ---------- Variation type labels ----------

const VARIATION_LABELS: Record<string, { label: string; icon: typeof Sparkles }> = {
  insight: { label: "Hot Take", icon: Sparkles },
  educational: { label: "Educational", icon: BookOpen },
  engagement: { label: "Question", icon: HelpCircle },
};

// ---------- Trigger badge ----------

function TriggerBadge({ type }: { type: string }) {
  const colors: Record<string, string> = {
    signal: "bg-blue-500/20 text-blue-400 border-blue-500/30",
    meeting: "bg-purple-500/20 text-purple-400 border-purple-500/30",
    curation: "bg-amber-500/20 text-amber-400 border-amber-500/30",
    milestone: "bg-green-500/20 text-green-400 border-green-500/30",
    cadence: "bg-slate-500/20 text-slate-400 border-slate-500/30",
  };
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${colors[type] || colors.curation}`}
    >
      {type}
    </span>
  );
}

// ---------- Stat pill ----------

function StatPill({
  icon,
  value,
  label,
}: {
  icon: React.ReactNode;
  value: number;
  label: string;
}) {
  return (
    <div className="flex items-center gap-1.5 text-sm text-slate-400" title={label}>
      {icon}
      <span className="text-white font-medium">{value.toLocaleString()}</span>
    </div>
  );
}

// ---------- Reject Modal ----------

function RejectModal({
  isOpen,
  onClose,
  onReject,
  isPending,
}: {
  isOpen: boolean;
  onClose: () => void;
  onReject: (reason: string) => void;
  isPending: boolean;
}) {
  const [reason, setReason] = useState("");
  const presets = ["Too casual", "Wrong tone", "Don't mention this topic", "Not relevant"];

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-6 max-w-md w-full mx-4">
        <h3 className="text-lg font-medium text-white mb-4">Why reject this draft?</h3>
        <div className="flex flex-wrap gap-2 mb-4">
          {presets.map((preset) => (
            <button
              key={preset}
              onClick={() => setReason(preset)}
              className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
                reason === preset
                  ? "bg-primary-600/20 text-primary-400 border-primary-500/30"
                  : "text-slate-400 border-slate-600 hover:border-slate-500"
              }`}
            >
              {preset}
            </button>
          ))}
        </div>
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Or type your feedback..."
          className="w-full bg-slate-900 border border-slate-600 rounded-lg p-3 text-sm text-white placeholder-slate-500 resize-none focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
          rows={3}
        />
        <div className="flex gap-3 mt-4">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-2.5 text-sm text-slate-400 border border-slate-600 rounded-lg hover:bg-slate-700 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => onReject(reason)}
            disabled={!reason.trim() || isPending}
            className="flex-1 px-4 py-2.5 text-sm text-white bg-red-600 hover:bg-red-500 rounded-lg transition-colors disabled:opacity-50"
          >
            {isPending ? "Rejecting..." : "Reject"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------- Draft Card ----------

function DraftCard({
  draft,
  onApproveAndSchedule,
  onApproveAndPublish,
  onReject,
}: {
  draft: SocialDraft;
  onApproveAndSchedule: (id: string, variationIdx: number, text: string, hashtags: string[]) => void;
  onApproveAndPublish: (id: string, variationIdx: number, text: string, hashtags: string[]) => void;
  onReject: (id: string) => void;
}) {
  const meta = draft.metadata;
  const variations = meta.variations || [];
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [editedText, setEditedText] = useState(variations[0]?.text || "");
  const [editedHashtags, setEditedHashtags] = useState<string[]>(variations[0]?.hashtags || []);

  const current = variations[selectedIdx];

  const handleVariationChange = (idx: number) => {
    setSelectedIdx(idx);
    setEditedText(variations[idx]?.text || "");
    setEditedHashtags(variations[idx]?.hashtags || []);
  };

  const removeHashtag = (tag: string) => {
    setEditedHashtags((prev) => prev.filter((t) => t !== tag));
  };

  const varInfo = current ? VARIATION_LABELS[current.variation_type] : null;

  return (
    <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-5 hover:border-slate-600 transition-colors">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <TriggerBadge type={meta.trigger_type} />
          {current && (
            <span className="text-xs text-slate-500">
              Voice match: {Math.round(current.voice_match_confidence * 100)}%
            </span>
          )}
        </div>
        <span className="text-xs text-slate-500">
          {new Date(draft.created_at).toLocaleDateString()}
        </span>
      </div>

      {/* Variation toggle */}
      {variations.length > 1 && (
        <div className="flex gap-1 mb-3">
          {variations.map((v: PostVariation, idx: number) => {
            const info = VARIATION_LABELS[v.variation_type];
            const Icon = info?.icon || Sparkles;
            return (
              <button
                key={idx}
                onClick={() => handleVariationChange(idx)}
                className={`flex items-center gap-1 px-2.5 py-1 text-xs rounded-lg transition-colors ${
                  idx === selectedIdx
                    ? "bg-primary-600/20 text-primary-400 border border-primary-500/30"
                    : "text-slate-500 hover:text-slate-300"
                }`}
              >
                <Icon className="w-3 h-3" />
                {info?.label || v.variation_type}
              </button>
            );
          })}
        </div>
      )}

      {/* Editable post text */}
      <textarea
        value={editedText}
        onChange={(e) => setEditedText(e.target.value)}
        className="w-full bg-slate-900/50 border border-slate-700 rounded-lg p-3 text-sm text-slate-200 resize-none focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent min-h-[120px]"
        rows={5}
      />

      {/* Hashtags */}
      {editedHashtags.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-2">
          {editedHashtags.map((tag) => (
            <span
              key={tag}
              className="inline-flex items-center gap-1 px-2 py-0.5 bg-slate-700/50 text-slate-400 text-xs rounded-full"
            >
              <Hash className="w-3 h-3" />
              {tag.replace("#", "")}
              <button
                onClick={() => removeHashtag(tag)}
                className="hover:text-white transition-colors"
              >
                <X className="w-3 h-3" />
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Suggested time */}
      {meta.suggested_time && (
        <div className="flex items-center gap-2 mt-3 text-xs text-slate-500">
          <Clock className="w-3.5 h-3.5" />
          <span>
            Suggested: {new Date(meta.suggested_time).toLocaleString()}
          </span>
          {meta.suggested_time_reasoning && (
            <span className="text-slate-600">— {meta.suggested_time_reasoning}</span>
          )}
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-2 mt-4 pt-3 border-t border-slate-700">
        <button
          onClick={() => onApproveAndSchedule(draft.id, selectedIdx, editedText, editedHashtags)}
          className="inline-flex items-center gap-1.5 px-3 py-2 text-sm bg-primary-600 hover:bg-primary-500 text-white rounded-lg transition-colors"
        >
          <Calendar className="w-4 h-4" />
          Approve & Schedule
        </button>
        <button
          onClick={() => onApproveAndPublish(draft.id, selectedIdx, editedText, editedHashtags)}
          className="inline-flex items-center gap-1.5 px-3 py-2 text-sm bg-green-600 hover:bg-green-500 text-white rounded-lg transition-colors"
        >
          <Send className="w-4 h-4" />
          Post Now
        </button>
        <button
          onClick={() => onReject(draft.id)}
          className="inline-flex items-center gap-1.5 px-3 py-2 text-sm text-slate-400 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors ml-auto"
        >
          <X className="w-4 h-4" />
          Reject
        </button>
      </div>
    </div>
  );
}

// ---------- Scheduled Card ----------

function ScheduledCard({
  draft,
  onCancel,
}: {
  draft: SocialDraft;
  onCancel: (id: string) => void;
}) {
  const meta = draft.metadata;
  const scheduledTime = meta.scheduled_time;
  const text = meta.edited_text || meta.variations?.[meta.selected_variation_index || 0]?.text || "";

  // Simple countdown
  const timeLeft = scheduledTime ? new Date(scheduledTime).getTime() - Date.now() : 0;
  const hoursLeft = Math.max(0, Math.floor(timeLeft / (1000 * 60 * 60)));
  const minutesLeft = Math.max(0, Math.floor((timeLeft % (1000 * 60 * 60)) / (1000 * 60)));

  return (
    <div className="bg-slate-800/50 border border-amber-500/20 rounded-xl p-5">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Clock className="w-4 h-4 text-amber-400" />
          <span className="text-sm text-amber-400 font-medium">
            {scheduledTime ? new Date(scheduledTime).toLocaleString() : "Scheduled"}
          </span>
        </div>
        {timeLeft > 0 && (
          <span className="text-xs text-slate-500">
            {hoursLeft}h {minutesLeft}m remaining
          </span>
        )}
      </div>
      <p className="text-sm text-slate-300 whitespace-pre-wrap">{text}</p>
      <div className="mt-3">
        <button
          onClick={() => onCancel(draft.id)}
          className="text-xs text-slate-500 hover:text-red-400 transition-colors"
        >
          Cancel publication
        </button>
      </div>
    </div>
  );
}

// ---------- Published Card ----------

function PublishedCard({ draft }: { draft: SocialDraft }) {
  const meta = draft.metadata;
  const text = meta.published_text || meta.edited_text || "";
  const metrics = meta.engagement_metrics;
  const engagers = meta.notable_engagers || [];

  return (
    <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-5">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs text-slate-500">
          Published {meta.published_at ? new Date(meta.published_at).toLocaleDateString() : ""}
        </span>
      </div>

      <p className="text-sm text-slate-300 whitespace-pre-wrap mb-3">{text}</p>

      {/* Engagement stats */}
      {metrics && (
        <div className="flex items-center gap-4 py-2 px-3 bg-slate-900/50 rounded-lg">
          <StatPill icon={<ThumbsUp className="w-4 h-4" />} value={metrics.likes} label="Likes" />
          <StatPill
            icon={<MessageSquare className="w-4 h-4" />}
            value={metrics.comments}
            label="Comments"
          />
          <StatPill icon={<Repeat2 className="w-4 h-4" />} value={metrics.shares} label="Shares" />
          <StatPill
            icon={<Eye className="w-4 h-4" />}
            value={metrics.impressions}
            label="Impressions"
          />
        </div>
      )}

      {/* Notable engagers */}
      {engagers.length > 0 && (
        <div className="mt-3 space-y-1">
          {engagers.map((engager, idx) => (
            <div key={idx} className="flex items-center gap-2 text-xs">
              {engager.relationship === "prospect" ? (
                <Target className="w-3.5 h-3.5 text-amber-400" />
              ) : engager.relationship === "customer" ? (
                <Handshake className="w-3.5 h-3.5 text-green-400" />
              ) : null}
              <span className="text-slate-300">{engager.name}</span>
              {engager.relationship === "prospect" && (
                <span className="px-1.5 py-0.5 bg-amber-500/10 text-amber-400 rounded text-[10px] font-medium">
                  Prospect
                </span>
              )}
              {engager.relationship === "customer" && (
                <span className="px-1.5 py-0.5 bg-green-500/10 text-green-400 rounded text-[10px] font-medium">
                  Customer
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------- Main Page ----------

type SectionTab = "drafts" | "scheduled" | "published";

export function SocialPage() {
  const [activeSection, setActiveSection] = useState<SectionTab>("drafts");
  const [rejectingDraftId, setRejectingDraftId] = useState<string | null>(null);

  // Data
  const { data: drafts, isLoading: draftsLoading } = useSocialDrafts();
  const { data: published, isLoading: publishedLoading } = useSocialPublished();
  const { data: stats } = useSocialStats();

  // Mutations
  const approveDraft = useApproveDraft();
  const rejectDraft = useRejectDraft();
  const publishDraftMut = usePublishDraft();
  const scheduleDraft = useScheduleDraft();

  // Derive scheduled from published (status=user_approved with scheduled_time but no published_at)
  const scheduled = useMemo(() => {
    return (published || []).filter(
      (p) => p.metadata.scheduled_time && !p.metadata.published_at,
    );
  }, [published]);

  const actualPublished = useMemo(() => {
    return (published || []).filter((p) => p.metadata.published_at);
  }, [published]);

  // Handlers
  const handleApproveAndSchedule = (
    draftId: string,
    variationIdx: number,
    text: string,
    hashtags: string[],
  ) => {
    // Schedule for the suggested time or next Tuesday 9am
    const suggestedTime =
      drafts?.find((d) => d.id === draftId)?.metadata.suggested_time ||
      getNextOptimalTime();

    scheduleDraft.mutate({
      draftId,
      data: {
        selected_variation_index: variationIdx,
        scheduled_time: suggestedTime,
        edited_text: text,
        edited_hashtags: hashtags,
      },
    });
  };

  const handleApproveAndPublish = (
    draftId: string,
    variationIdx: number,
    text: string,
    hashtags: string[],
  ) => {
    approveDraft.mutate(
      {
        draftId,
        data: {
          selected_variation_index: variationIdx,
          edited_text: text,
          edited_hashtags: hashtags,
        },
      },
      {
        onSuccess: () => {
          publishDraftMut.mutate(draftId);
        },
      },
    );
  };

  const handleReject = (reason: string) => {
    if (!rejectingDraftId) return;
    rejectDraft.mutate(
      { draftId: rejectingDraftId, reason },
      { onSuccess: () => setRejectingDraftId(null) },
    );
  };

  const handleCancelScheduled = (draftId: string) => {
    // Reject cancels the scheduled post
    rejectDraft.mutate({ draftId, reason: "User cancelled scheduled post" });
  };

  const isLoading = draftsLoading || publishedLoading;

  const sectionCounts = {
    drafts: drafts?.length || 0,
    scheduled: scheduled.length,
    published: actualPublished.length,
  };

  return (
    <DashboardLayout>
      <div className="relative">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-800 via-slate-900 to-slate-900 pointer-events-none" />

        <div className="relative max-w-4xl mx-auto px-4 py-8 lg:px-8">
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-3xl font-display text-white">Social</h1>
                <HelpTooltip
                  content="ARIA drafts LinkedIn posts based on your market signals, meetings, and industry insights. Review, edit, and publish from here."
                  placement="right"
                />
              </div>
              <p className="mt-1 text-slate-400">
                Manage your LinkedIn presence with ARIA-powered content
              </p>
            </div>

            {/* Stats summary */}
            {stats && (
              <div className="flex items-center gap-3">
                <div className="text-right">
                  <p className="text-sm text-slate-400">This week</p>
                  <p className="text-lg font-semibold text-white">
                    {stats.posts_this_week}/{stats.posting_goal}
                    <span className="text-sm text-slate-500 ml-1">posts</span>
                  </p>
                </div>
                <div
                  className={`w-10 h-10 rounded-full flex items-center justify-center ${
                    stats.posting_goal_met
                      ? "bg-green-500/20 text-green-400"
                      : "bg-amber-500/20 text-amber-400"
                  }`}
                >
                  {stats.posting_goal_met ? (
                    <Check className="w-5 h-5" />
                  ) : (
                    <ChevronDown className="w-5 h-5" />
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Channel tabs */}
          <div className="flex gap-2 mb-6">
            <button className="px-4 py-2 text-sm font-medium bg-primary-600/20 text-primary-400 border border-primary-500/30 rounded-lg">
              LinkedIn
            </button>
            <button
              disabled
              className="px-4 py-2 text-sm font-medium text-slate-600 border border-slate-700 rounded-lg cursor-not-allowed"
            >
              More coming soon
            </button>
          </div>

          {/* Section tabs */}
          <div className="flex gap-2 overflow-x-auto pb-2 mb-6">
            {(["drafts", "scheduled", "published"] as const).map((section) => (
              <button
                key={section}
                onClick={() => setActiveSection(section)}
                className={`inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg whitespace-nowrap transition-colors ${
                  activeSection === section
                    ? "bg-primary-600/20 text-primary-400 border border-primary-500/30"
                    : "text-slate-400 hover:text-white hover:bg-slate-800"
                }`}
              >
                {section === "drafts" && <Share2 className="w-4 h-4" />}
                {section === "scheduled" && <Clock className="w-4 h-4" />}
                {section === "published" && <Check className="w-4 h-4" />}
                {section.charAt(0).toUpperCase() + section.slice(1)}
                {sectionCounts[section] > 0 && (
                  <span
                    className={`ml-1 px-1.5 py-0.5 text-xs rounded-full ${
                      activeSection === section
                        ? "bg-primary-500/20 text-primary-400"
                        : "bg-slate-700 text-slate-400"
                    }`}
                  >
                    {sectionCounts[section]}
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Loading */}
          {isLoading && (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="w-6 h-6 text-slate-500 animate-spin" />
            </div>
          )}

          {/* Drafts section */}
          {!isLoading && activeSection === "drafts" && (
            <div className="space-y-4">
              {(drafts || []).length === 0 ? (
                <div className="text-center py-16">
                  <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-slate-800/80 border border-slate-700 mb-4">
                    <Share2 className="w-8 h-8 text-slate-500" />
                  </div>
                  <h3 className="text-lg font-medium text-white mb-2">No drafts yet</h3>
                  <p className="text-sm text-slate-400 max-w-md mx-auto">
                    ARIA will draft LinkedIn posts based on your market signals and meetings.
                    Posts will appear here for your review.
                  </p>
                </div>
              ) : (
                (drafts || []).map((draft, idx) => (
                  <div
                    key={draft.id}
                    className="animate-in fade-in slide-in-from-bottom-4"
                    style={{ animationDelay: `${idx * 30}ms`, animationFillMode: "both" }}
                  >
                    <DraftCard
                      draft={draft}
                      onApproveAndSchedule={handleApproveAndSchedule}
                      onApproveAndPublish={handleApproveAndPublish}
                      onReject={(id) => setRejectingDraftId(id)}
                    />
                  </div>
                ))
              )}
            </div>
          )}

          {/* Scheduled section */}
          {!isLoading && activeSection === "scheduled" && (
            <div className="space-y-4">
              {scheduled.length === 0 ? (
                <div className="text-center py-16">
                  <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-slate-800/80 border border-slate-700 mb-4">
                    <Clock className="w-8 h-8 text-slate-500" />
                  </div>
                  <h3 className="text-lg font-medium text-white mb-2">Nothing scheduled</h3>
                  <p className="text-sm text-slate-400 max-w-md mx-auto">
                    Approve drafts to schedule them for publication.
                  </p>
                </div>
              ) : (
                scheduled.map((draft) => (
                  <ScheduledCard
                    key={draft.id}
                    draft={draft}
                    onCancel={handleCancelScheduled}
                  />
                ))
              )}
            </div>
          )}

          {/* Published section */}
          {!isLoading && activeSection === "published" && (
            <div className="space-y-4">
              {actualPublished.length === 0 ? (
                <div className="text-center py-16">
                  <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-slate-800/80 border border-slate-700 mb-4">
                    <Check className="w-8 h-8 text-slate-500" />
                  </div>
                  <h3 className="text-lg font-medium text-white mb-2">No published posts yet</h3>
                  <p className="text-sm text-slate-400 max-w-md mx-auto">
                    Your published LinkedIn posts and their engagement metrics will appear here.
                  </p>
                </div>
              ) : (
                actualPublished.map((draft, idx) => (
                  <div
                    key={draft.id}
                    className="animate-in fade-in slide-in-from-bottom-4"
                    style={{ animationDelay: `${idx * 30}ms`, animationFillMode: "both" }}
                  >
                    <PublishedCard draft={draft} />
                  </div>
                ))
              )}
            </div>
          )}
        </div>

        {/* Reject modal */}
        <RejectModal
          isOpen={rejectingDraftId !== null}
          onClose={() => setRejectingDraftId(null)}
          onReject={handleReject}
          isPending={rejectDraft.isPending}
        />
      </div>
    </DashboardLayout>
  );
}

// ---------- Helpers ----------

function getNextOptimalTime(): string {
  const now = new Date();
  const day = now.getDay();
  // Find next Tuesday (2) or Wednesday (3)
  let daysUntil = 2 - day;
  if (daysUntil <= 0) daysUntil = 3 - day;
  if (daysUntil <= 0) daysUntil += 7;
  const target = new Date(now);
  target.setDate(target.getDate() + daysUntil);
  target.setHours(14, 0, 0, 0); // 9am EST = 14:00 UTC
  return target.toISOString();
}
```

**Step 2: Commit**

```bash
git add frontend/src/pages/SocialPage.tsx
git commit -m "feat: add Social Media Drafts page for LinkedIn posting workflow"
```

---

### Task 8: Register SocialPage in App Router and Navigation

**Files:**
- Modify: `frontend/src/pages/index.ts` — add export
- Modify: `frontend/src/App.tsx` — add route
- Modify: `frontend/src/components/DashboardLayout.tsx` — add nav item

**Step 1: Add export to pages/index.ts**

Add this line (alphabetically near the S entries):

```typescript
export { SocialPage } from "./SocialPage";
```

**Step 2: Add route to App.tsx**

Add import `SocialPage` to the imports from `@/pages`.

Add this route block (after the `/dashboard/skills` route):

```tsx
      <Route
        path="/social"
        element={
          <ProtectedRoute>
            <SocialPage />
          </ProtectedRoute>
        }
      />
```

**Step 3: Add nav item to DashboardLayout.tsx**

Add to the `navItems` array (after "Email Drafts"):

```typescript
  { name: "Social", href: "/social", icon: "share" },
```

Add a "share" icon to the `icons` Record inside `NavIcon`:

```tsx
    share: (
      <svg
        className="w-5 h-5"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z"
        />
      </svg>
    ),
```

**Step 4: Verify frontend compiles**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit --pretty 2>&1 | head -30`

**Step 5: Commit**

```bash
git add frontend/src/pages/index.ts frontend/src/App.tsx frontend/src/components/DashboardLayout.tsx
git commit -m "feat: register Social page route and add to sidebar navigation"
```

---

### Task 9: Extend User Preferences with LinkedIn Settings

**Files:**
- Modify: `backend/src/models/preferences.py` — add linkedin fields to PreferenceUpdate
- Modify: `frontend/src/pages/PreferencesSettings.tsx` — add LinkedIn toggle section (if the file exists; otherwise integrate where settings are rendered)

**Step 1: Add linkedin preference fields to PreferenceUpdate model**

Add these optional fields to the `PreferenceUpdate` class in `backend/src/models/preferences.py`:

```python
    linkedin_posting_enabled: bool | None = Field(
        None, description="Enable ARIA LinkedIn posting features"
    )
    linkedin_auto_post: bool | None = Field(
        None, description="Allow ARIA to auto-publish high-confidence drafts"
    )
    linkedin_posts_per_week_goal: int | None = Field(
        None, ge=0, le=14, description="Weekly LinkedIn posting goal"
    )
```

Note: These fields will be stored in the `metadata` JSONB column of user_preferences since the table schema uses fixed columns + metadata for extensibility. The preferences service already handles partial updates and metadata merge.

**Step 2: Verify lint passes**

Run: `cd /Users/dhruv/aria && python -m ruff check backend/src/models/preferences.py`

**Step 3: Commit**

```bash
git add backend/src/models/preferences.py
git commit -m "feat: add LinkedIn posting preferences to user preference models"
```

---

### Task 10: Backend Tests for Social Routes

**Files:**
- Create: `backend/tests/test_social.py`

**Step 1: Write tests**

```python
"""Tests for social media API routes."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_supabase():
    """Create a mock Supabase client."""
    client = MagicMock()
    # Chain .table().select().eq()... pattern
    table = MagicMock()
    client.table.return_value = table
    table.select.return_value = table
    table.eq.return_value = table
    table.neq.return_value = table
    table.not_.return_value = table
    table.is_.return_value = table
    table.filter.return_value = table
    table.order.return_value = table
    table.limit.return_value = table
    table.gte.return_value = table
    table.maybe_single.return_value = table
    table.insert.return_value = table
    table.update.return_value = table

    execute_result = MagicMock()
    execute_result.data = []
    execute_result.count = 0
    table.execute.return_value = execute_result

    return client


class TestSocialModels:
    """Test Pydantic models for social features."""

    def test_post_variation_creation(self):
        from src.models.social import PostVariation, PostVariationType

        v = PostVariation(
            variation_type=PostVariationType.INSIGHT,
            text="Hot take: AI is changing pharma sales",
            hashtags=["#pharma", "#AI"],
            voice_match_confidence=0.85,
        )
        assert v.variation_type == PostVariationType.INSIGHT
        assert v.voice_match_confidence == 0.85
        assert len(v.hashtags) == 2

    def test_draft_approve_request_defaults(self):
        from src.models.social import DraftApproveRequest

        req = DraftApproveRequest()
        assert req.selected_variation_index == 0
        assert req.edited_text is None

    def test_draft_reject_requires_reason(self):
        from src.models.social import DraftRejectRequest

        with pytest.raises(Exception):
            DraftRejectRequest()  # Missing required reason

        req = DraftRejectRequest(reason="Too casual")
        assert req.reason == "Too casual"

    def test_engagement_stats_defaults(self):
        from src.models.social import EngagementStats

        stats = EngagementStats()
        assert stats.likes == 0
        assert stats.impressions == 0

    def test_social_stats_response(self):
        from src.models.social import SocialStatsResponse

        stats = SocialStatsResponse(
            total_posts=10,
            posts_this_week=2,
            avg_likes=5.5,
            posting_goal=2,
            posting_goal_met=True,
        )
        assert stats.total_posts == 10
        assert stats.posting_goal_met is True

    def test_trigger_type_enum(self):
        from src.models.social import TriggerType

        assert TriggerType.SIGNAL == "signal"
        assert TriggerType.MEETING == "meeting"
        assert TriggerType.CADENCE == "cadence"


class TestLinkedInDraftPost:
    """Test LinkedIn draft_post capability method."""

    @pytest.mark.asyncio
    async def test_draft_post_returns_empty_on_llm_failure(self):
        from src.agents.capabilities.base import UserContext
        from src.agents.capabilities.linkedin import LinkedInCapability

        mock_sb = MagicMock()
        table = MagicMock()
        mock_sb.table.return_value = table
        table.select.return_value = table
        table.eq.return_value = table
        table.maybe_single.return_value = table
        execute_result = MagicMock()
        execute_result.data = None
        table.execute.return_value = execute_result

        cap = LinkedInCapability(
            supabase_client=mock_sb,
            memory_service=None,
            knowledge_graph=None,
            user_context=UserContext(user_id="test-user"),
        )

        with patch("src.agents.capabilities.linkedin.get_llm_client") as mock_llm:
            mock_client = AsyncMock()
            mock_client.generate_response = AsyncMock(side_effect=Exception("LLM error"))
            mock_llm.return_value = mock_client

            result = await cap.draft_post(
                user_id="test-user",
                trigger_context={"trigger_type": "signal", "source_data": {"title": "Test"}},
            )
            assert result == []
```

**Step 2: Run tests**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_social.py -v`

**Step 3: Commit**

```bash
git add backend/tests/test_social.py
git commit -m "test: add tests for social media models and LinkedIn capability"
```

---

### Task 11: Final Verification and Lint

**Step 1: Run backend linting**

Run: `cd /Users/dhruv/aria && python -m ruff check backend/src/models/social.py backend/src/api/routes/social.py backend/src/agents/capabilities/linkedin.py`

**Step 2: Run frontend type check**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit --pretty 2>&1 | head -50`

**Step 3: Run backend tests**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_social.py -v`

**Step 4: Run frontend lint**

Run: `cd /Users/dhruv/aria/frontend && npm run lint 2>&1 | head -30`

**Step 5: Fix any issues found**

**Step 6: Final commit**

```bash
git add -A
git commit -m "feat: LinkedIn posting capability and Social Media Drafts page — complete implementation"
```
