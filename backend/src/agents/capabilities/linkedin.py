"""LinkedIn Intelligence capability for ARIA agents.

Provides LinkedIn-based intelligence gathering for sales teams:
- Profile enrichment from public LinkedIn data
- Activity monitoring for key contacts
- Connection request drafting with Digital Twin style matching

Uses httpx for web requests as an initial implementation.
LinkedIn API OAuth integration can be added later for richer data.
"""

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx

from src.agents.capabilities.base import BaseCapability, CapabilityResult
from src.core.llm import LLMClient
from src.core.task_types import TaskType
from src.db.supabase import SupabaseClient
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

logger = logging.getLogger(__name__)

# Request configuration
_TIMEOUT = httpx.Timeout(15.0, connect=5.0)
_USER_AGENT = "Mozilla/5.0 (compatible; ARIA-Intelligence/1.0; +https://aria-ai.com/bot)"
_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


class LinkedInIntelligenceCapability(BaseCapability):
    """LinkedIn intelligence gathering for HunterAgent and ScribeAgent.

    Provides three core operations:
    - enrich_profile: Extract professional information from a LinkedIn URL
    - monitor_activity: Check for recent profile changes
    - draft_connection_request: Generate personalized outreach using Digital Twin

    Data classifications: INTERNAL (profile data), CONFIDENTIAL (outreach strategy).
    """

    capability_name = "linkedin-intelligence"
    agent_types = ["HunterAgent", "ScribeAgent"]
    oauth_scopes: list[str] = []

    async def can_handle(self, task: dict[str, Any]) -> float:
        """Return confidence score for handling LinkedIn-related tasks."""
        task_type = task.get("type", "").lower()
        description = task.get("description", "").lower()

        # High confidence for explicit LinkedIn tasks
        if task_type in (
            "linkedin_enrich",
            "linkedin_monitor",
            "linkedin_connect",
            "linkedin_research",
        ):
            return 0.95

        # Medium confidence for tasks mentioning LinkedIn
        text = f"{task_type} {description}"
        linkedin_keywords = ["linkedin", "connection request", "profile enrichment"]
        if any(kw in text for kw in linkedin_keywords):
            return 0.8

        # Low confidence for general contact research
        contact_keywords = ["contact research", "prospect research", "enrich contact"]
        if any(kw in text for kw in contact_keywords):
            return 0.4

        return 0.0

    async def execute(
        self,
        task: dict[str, Any],
        context: dict[str, Any],
    ) -> CapabilityResult:
        """Execute a LinkedIn intelligence task.

        Routes to the appropriate method based on task type.

        Args:
            task: Task specification with 'type' and relevant parameters.
            context: Runtime context (memory, working memory, etc.).

        Returns:
            CapabilityResult with enrichment data or drafted content.
        """
        _ = context  # Available for future memory-aware enrichment
        task_type = task.get("type", "")

        try:
            if task_type in ("linkedin_enrich", "linkedin_research"):
                url = task.get("linkedin_url", "")
                if not url:
                    return CapabilityResult(
                        success=False,
                        error="linkedin_url is required for profile enrichment",
                    )
                return await self.enrich_profile(url)

            elif task_type == "linkedin_monitor":
                url = task.get("linkedin_url", "")
                if not url:
                    return CapabilityResult(
                        success=False,
                        error="linkedin_url is required for activity monitoring",
                    )
                return await self.monitor_activity(url)

            elif task_type == "linkedin_connect":
                profile = task.get("profile", {})
                connection_context = task.get("context", "")
                if not profile:
                    return CapabilityResult(
                        success=False,
                        error="profile dict is required for connection request drafting",
                    )
                return await self.draft_connection_request(profile, connection_context)

            else:
                # Try to infer from task description
                description = task.get("description", "").lower()
                if "enrich" in description or "research" in description:
                    url = task.get("linkedin_url", "")
                    if url:
                        return await self.enrich_profile(url)
                return CapabilityResult(
                    success=False,
                    error=f"Unsupported LinkedIn task type: {task_type}",
                )

        except Exception as e:
            logger.exception("LinkedIn capability execution failed")
            return CapabilityResult(
                success=False,
                error=f"LinkedIn intelligence failed: {e}",
            )

    def get_data_classes_accessed(self) -> list[str]:
        """Declare data classification levels accessed."""
        return ["internal", "confidential"]

    async def enrich_profile(self, linkedin_url: str) -> CapabilityResult:
        """Enrich a contact profile from a LinkedIn URL.

        Fetches the public LinkedIn profile page and uses LLM to extract
        structured professional information.

        Args:
            linkedin_url: Full LinkedIn profile URL.

        Returns:
            CapabilityResult with extracted profile data.
        """
        if not linkedin_url or "linkedin.com" not in linkedin_url:
            return CapabilityResult(
                success=False,
                error=f"Invalid LinkedIn URL: {linkedin_url}",
            )

        logger.info(
            "Enriching LinkedIn profile",
            extra={"url": linkedin_url},
        )

        # Fetch profile page
        page_content = await self._fetch_page(linkedin_url)

        if not page_content:
            return CapabilityResult(
                success=False,
                error="Failed to fetch LinkedIn profile page",
                data={"url": linkedin_url, "fallback": True},
            )

        # Use LLM to extract structured data from page content
        llm = LLMClient()
        extraction_prompt = (
            "Extract professional information from this LinkedIn profile page content. "
            "Return valid JSON with these fields:\n"
            "{\n"
            '  "name": "Full Name",\n'
            '  "headline": "Professional headline",\n'
            '  "current_company": "Company name",\n'
            '  "current_title": "Job title",\n'
            '  "location": "City, State/Country",\n'
            '  "summary": "Professional summary (first 200 chars)",\n'
            '  "experience": [{"company": "", "title": "", "duration": ""}],\n'
            '  "education": [{"school": "", "degree": "", "field": ""}],\n'
            '  "skills": ["skill1", "skill2"],\n'
            '  "connections_estimate": "500+",\n'
            '  "profile_completeness": "high|medium|low"\n'
            "}\n\n"
            f"Page content:\n{page_content[:8000]}"
        )

        try:
            raw_response = await llm.generate_response(
                messages=[{"role": "user", "content": extraction_prompt}],
                system_prompt=(
                    "You are a data extraction specialist. "
                    "Extract structured professional data from LinkedIn pages. "
                    "Output ONLY valid JSON."
                ),
                temperature=0.1,
                max_tokens=1000,
                task=TaskType.HUNTER_ENRICH,
                agent_id="linkedin",
            )

            # Strip markdown fences if present
            text = raw_response.strip()
            if text.startswith("```"):
                text = text[text.index("\n") + 1 :]
            if text.endswith("```"):
                text = text[:-3].rstrip()

            profile_data = json.loads(text)

            await self.log_activity(
                activity_type="linkedin_enrichment",
                title=f"Enriched LinkedIn profile: {profile_data.get('name', 'Unknown')}",
                description=(
                    f"Extracted professional data from {linkedin_url}. "
                    f"Current: {profile_data.get('current_title', 'N/A')} "
                    f"at {profile_data.get('current_company', 'N/A')}"
                ),
                confidence=0.75,
                metadata={"linkedin_url": linkedin_url},
            )

            return CapabilityResult(
                success=True,
                data=profile_data,
                extracted_facts=[
                    {
                        "type": "linkedin_profile",
                        "url": linkedin_url,
                        "name": profile_data.get("name"),
                        "company": profile_data.get("current_company"),
                        "title": profile_data.get("current_title"),
                    }
                ],
            )

        except (json.JSONDecodeError, Exception) as e:
            logger.warning("Failed to parse LinkedIn extraction: %s", e)
            return CapabilityResult(
                success=False,
                error=f"Failed to extract profile data: {e}",
                data={"url": linkedin_url, "raw_content_length": len(page_content)},
            )

    async def monitor_activity(self, linkedin_url: str) -> CapabilityResult:
        """Check for recent activity changes on a LinkedIn profile.

        Fetches the profile and looks for signals of change (new role,
        new posts, status updates).

        Args:
            linkedin_url: Full LinkedIn profile URL.

        Returns:
            CapabilityResult with activity signals.
        """
        if not linkedin_url or "linkedin.com" not in linkedin_url:
            return CapabilityResult(
                success=False,
                error=f"Invalid LinkedIn URL: {linkedin_url}",
            )

        logger.info(
            "Monitoring LinkedIn activity",
            extra={"url": linkedin_url},
        )

        page_content = await self._fetch_page(linkedin_url)

        if not page_content:
            return CapabilityResult(
                success=False,
                error="Failed to fetch LinkedIn profile for monitoring",
                data={"url": linkedin_url},
            )

        llm = LLMClient()
        monitor_prompt = (
            "Analyze this LinkedIn profile page for recent activity signals. "
            "Return valid JSON:\n"
            "{\n"
            '  "profile_url": "url",\n'
            '  "current_role": {"company": "", "title": ""},\n'
            '  "activity_signals": [\n'
            '    {"type": "role_change|post|engagement|certification", '
            '"description": "", "recency": "recent|moderate|old"}\n'
            "  ],\n"
            '  "engagement_level": "high|medium|low|inactive",\n'
            '  "notable_changes": ["change1", "change2"],\n'
            '  "outreach_timing": "good|neutral|poor",\n'
            '  "outreach_reasoning": "Why this timing assessment"\n'
            "}\n\n"
            f"Page content:\n{page_content[:8000]}"
        )

        try:
            raw_response = await llm.generate_response(
                messages=[{"role": "user", "content": monitor_prompt}],
                system_prompt=(
                    "You are a sales intelligence analyst. "
                    "Detect professional activity signals from LinkedIn profiles. "
                    "Output ONLY valid JSON."
                ),
                temperature=0.2,
                max_tokens=800,
                task=TaskType.SCOUT_FILTER,
                agent_id="linkedin",
            )

            text = raw_response.strip()
            if text.startswith("```"):
                text = text[text.index("\n") + 1 :]
            if text.endswith("```"):
                text = text[:-3].rstrip()

            activity_data = json.loads(text)
            activity_data["profile_url"] = linkedin_url

            return CapabilityResult(
                success=True,
                data=activity_data,
            )

        except Exception as e:
            logger.warning("Failed to analyze LinkedIn activity: %s", e)
            return CapabilityResult(
                success=False,
                error=f"Activity analysis failed: {e}",
            )

    async def draft_connection_request(
        self,
        profile: dict[str, Any],
        context: str,
    ) -> CapabilityResult:
        """Draft a personalized LinkedIn connection request.

        Uses LLM with Digital Twin style matching to generate an authentic,
        personalized connection request message.

        Args:
            profile: Contact profile dict (name, title, company, etc.).
            context: Business context for the connection (e.g., "exploring partnership").

        Returns:
            CapabilityResult with drafted message and alternatives.
        """
        logger.info(
            "Drafting connection request",
            extra={
                "contact_name": profile.get("name", "Unknown"),
                "context": context[:100],
            },
        )

        # Load Digital Twin style if available
        style_guidance = ""
        try:
            from src.memory.digital_twin import DigitalTwin

            twin = DigitalTwin()
            user_id = self._user_context.user_id
            guidelines = await twin.get_style_guidelines(user_id)
            if guidelines:
                style_guidance = f"\n\nMatch this writing style:\n{guidelines}"
        except Exception as e:
            logger.debug("Could not load Digital Twin style: %s", e)

        llm = LLMClient()
        draft_prompt = (
            "Draft a personalized LinkedIn connection request message. "
            "Keep it under 300 characters (LinkedIn limit). "
            "Be authentic, specific, and professional.\n\n"
            f"Contact: {profile.get('name', 'Unknown')}\n"
            f"Title: {profile.get('current_title', profile.get('title', 'N/A'))}\n"
            f"Company: {profile.get('current_company', profile.get('company', 'N/A'))}\n"
            f"Context: {context}\n"
            f"{style_guidance}\n\n"
            "Return valid JSON:\n"
            "{\n"
            '  "primary_message": "The recommended connection request message",\n'
            '  "alternative_messages": ["Alt 1", "Alt 2"],\n'
            '  "tone": "professional|casual|warm|direct",\n'
            '  "personalization_hooks": ["What makes this personalized"],\n'
            '  "follow_up_suggestion": "Suggested follow-up after connection"\n'
            "}"
        )

        try:
            raw_response = await llm.generate_response(
                messages=[{"role": "user", "content": draft_prompt}],
                system_prompt=(
                    "You are an expert sales copywriter specializing in "
                    "LinkedIn outreach for life sciences professionals. "
                    "Output ONLY valid JSON."
                ),
                temperature=0.7,
                max_tokens=600,
                task=TaskType.SCRIBE_DRAFT_EMAIL,
                agent_id="linkedin",
            )

            text = raw_response.strip()
            if text.startswith("```"):
                text = text[text.index("\n") + 1 :]
            if text.endswith("```"):
                text = text[:-3].rstrip()

            draft_data = json.loads(text)

            await self.log_activity(
                activity_type="linkedin_draft",
                title=f"Drafted connection request for {profile.get('name', 'Unknown')}",
                description=(
                    f"Generated personalized LinkedIn outreach for "
                    f"{profile.get('name', 'Unknown')} at "
                    f"{profile.get('current_company', profile.get('company', 'N/A'))}"
                ),
                confidence=0.85,
                metadata={
                    "contact_name": profile.get("name"),
                    "tone": draft_data.get("tone"),
                },
            )

            return CapabilityResult(
                success=True,
                data=draft_data,
            )

        except Exception as e:
            logger.warning("Failed to draft connection request: %s", e)
            return CapabilityResult(
                success=False,
                error=f"Connection request drafting failed: {e}",
            )

    async def draft_post(
        self,
        user_id: str,
        trigger_context: dict[str, Any],
    ) -> list[PostDraft]:
        """Draft LinkedIn post variations based on a trigger context.

        Generates three post variations (insight, educational, engagement)
        using the user's Digital Twin voice and therapeutic area context.

        Args:
            user_id: Authenticated user UUID.
            trigger_context: Dict with 'trigger_type', 'trigger_source',
                and 'content' describing what prompted the post.

        Returns:
            List of PostDraft objects stored in the action queue.
        """
        logger.info(
            "Drafting LinkedIn post",
            extra={
                "user_id": user_id,
                "trigger_type": trigger_context.get("trigger_type", ""),
            },
        )

        db = SupabaseClient.get_client()

        # Load Digital Twin voice profile for style matching
        voice_profile = ""
        try:
            twin_resp = (
                db.table("digital_twin_profiles")
                .select("*")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            if twin_resp.data:
                profile = twin_resp.data[0]
                voice_profile = (
                    f"Tone: {profile.get('tone', 'professional')}\n"
                    f"Style: {profile.get('writing_style', '')}\n"
                    f"Vocabulary: {profile.get('vocabulary_patterns', '')}\n"
                )
        except Exception as e:
            logger.debug("Could not load Digital Twin voice profile: %s", e)

        # Load user preferences for therapeutic area context
        therapeutic_context = ""
        try:
            pref_resp = (
                db.table("user_preferences").select("*").eq("user_id", user_id).limit(1).execute()
            )
            if pref_resp.data:
                prefs = pref_resp.data[0]
                metadata = prefs.get("metadata", {}) or {}
                ta = metadata.get("therapeutic_area", "")
                if ta:
                    therapeutic_context = f"Therapeutic area focus: {ta}\n"
        except Exception as e:
            logger.debug("Could not load user preferences: %s", e)

        trigger_type_str = trigger_context.get("trigger_type", "signal")
        trigger_source = trigger_context.get("trigger_source", "")
        content = trigger_context.get("content", "")

        prompt = (
            "You are a LinkedIn content strategist for a life sciences sales professional.\n"
            "Generate exactly 3 post variations as a JSON array.\n\n"
            f"Trigger: {trigger_type_str} — {trigger_source}\n"
            f"Content/Context: {content}\n"
            f"{therapeutic_context}"
            f"{voice_profile}\n"
            "Return ONLY valid JSON in this exact format:\n"
            "[\n"
            "  {\n"
            '    "variation_type": "insight",\n'
            '    "text": "Post text here...",\n'
            '    "hashtags": ["#hashtag1", "#hashtag2"],\n'
            '    "voice_match_confidence": 0.85\n'
            "  },\n"
            "  {\n"
            '    "variation_type": "educational",\n'
            '    "text": "Post text here...",\n'
            '    "hashtags": ["#hashtag1", "#hashtag2"],\n'
            '    "voice_match_confidence": 0.85\n'
            "  },\n"
            "  {\n"
            '    "variation_type": "engagement",\n'
            '    "text": "Post text here...",\n'
            '    "hashtags": ["#hashtag1", "#hashtag2"],\n'
            '    "voice_match_confidence": 0.85\n'
            "  }\n"
            "]\n\n"
            "Each variation should be 100-300 words, authentic, and professional. "
            "voice_match_confidence should be 0.0-1.0 reflecting how well the text "
            "matches the user's voice profile."
        )

        llm = LLMClient()
        try:
            raw_response = await llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=(
                    "You are a LinkedIn content strategist for life sciences professionals. "
                    "Output ONLY valid JSON — no markdown fences, no commentary."
                ),
                temperature=0.7,
                max_tokens=2000,
                task=TaskType.STRATEGIST_PLAN,
                agent_id="linkedin",
            )

            # Strip markdown fences if present
            text = raw_response.strip()
            if text.startswith("```"):
                text = text[text.index("\n") + 1 :]
            if text.endswith("```"):
                text = text[:-3].rstrip()

            variations_raw: list[dict[str, Any]] = json.loads(text)
        except Exception as e:
            logger.warning("Failed to generate LinkedIn post drafts: %s", e)
            return []

        # Parse into PostVariation objects
        variations: list[PostVariation] = []
        for v in variations_raw:
            try:
                variation = PostVariation(
                    variation_type=PostVariationType(v.get("variation_type", "insight")),
                    text=v.get("text", ""),
                    hashtags=v.get("hashtags", []),
                    voice_match_confidence=float(v.get("voice_match_confidence", 0.0)),
                )
                variations.append(variation)
            except Exception as e:
                logger.debug("Skipping invalid variation: %s", e)

        if not variations:
            logger.warning("No valid variations produced for LinkedIn post draft")
            return []

        # Store as an action in aria_actions
        action_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()

        try:
            trigger_type_enum = TriggerType(trigger_type_str)
        except ValueError:
            trigger_type_enum = TriggerType.SIGNAL

        action_payload = {
            "trigger_type": trigger_type_enum.value,
            "trigger_source": trigger_source,
            "variations": [v.model_dump() for v in variations],
            "suggested_time": trigger_context.get("suggested_time"),
            "suggested_time_reasoning": trigger_context.get("suggested_time_reasoning", ""),
        }

        try:
            db.table("aria_actions").insert(
                {
                    "id": action_id,
                    "user_id": user_id,
                    "action_type": "linkedin_post",
                    "status": "pending",
                    "title": f"LinkedIn post draft: {trigger_source[:80]}",
                    "description": f"Generated {len(variations)} post variations",
                    "payload": json.dumps(action_payload),
                    "metadata": json.dumps({"trigger_type": trigger_type_enum.value}),
                    "created_at": now,
                }
            ).execute()
        except Exception as e:
            logger.warning("Failed to store LinkedIn post draft in actions: %s", e)

        # Log activity
        await self.log_activity(
            activity_type="linkedin_post_draft",
            title=f"Drafted LinkedIn post: {trigger_source[:60]}",
            description=(
                f"Generated {len(variations)} LinkedIn post variations "
                f"from {trigger_type_enum.value} trigger."
            ),
            confidence=0.80,
            metadata={
                "action_id": action_id,
                "trigger_type": trigger_type_enum.value,
                "variation_count": len(variations),
            },
        )

        draft = PostDraft(
            action_id=action_id,
            trigger_type=trigger_type_enum,
            trigger_source=trigger_source,
            variations=variations,
            suggested_time=trigger_context.get("suggested_time"),
            suggested_time_reasoning=trigger_context.get("suggested_time_reasoning", ""),
            created_at=now,
        )

        return [draft]

    async def publish_post(self, action_id: str) -> PublishResult:
        """Publish an approved LinkedIn post draft via the LinkedIn API.

        Retrieves the approved draft from aria_actions, obtains the user's
        OAuth token, posts to LinkedIn, updates the action status, and
        schedules engagement checks.

        Args:
            action_id: The aria_actions row ID for the approved draft.

        Returns:
            PublishResult indicating success or failure.
        """
        db = SupabaseClient.get_client()
        user_id = self._user_context.user_id

        # Load the approved draft
        try:
            action_resp = (
                db.table("aria_actions")
                .select("*")
                .eq("id", action_id)
                .eq("user_id", user_id)
                .single()
                .execute()
            )
            action = action_resp.data
        except Exception as e:
            logger.warning("Failed to load action %s: %s", action_id, e)
            return PublishResult(success=False, error=f"Draft not found: {e}")

        if not action:
            return PublishResult(success=False, error="Draft not found")

        payload = action.get("payload", {})
        if isinstance(payload, str):
            payload = json.loads(payload)

        # Get user's LinkedIn OAuth token
        try:
            token_resp = (
                db.table("user_integrations")
                .select("access_token")
                .eq("user_id", user_id)
                .eq("provider", "linkedin")
                .eq("status", "active")
                .single()
                .execute()
            )
            access_token = token_resp.data.get("access_token", "") if token_resp.data else ""
        except Exception as e:
            logger.warning("Failed to get LinkedIn OAuth token: %s", e)
            return PublishResult(success=False, error="LinkedIn not connected")

        if not access_token:
            return PublishResult(success=False, error="LinkedIn OAuth token not found")

        # Get LinkedIn profile URN
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                profile_resp = await client.get(
                    "https://api.linkedin.com/v2/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                profile_resp.raise_for_status()
                profile_data = profile_resp.json()
                person_urn = f"urn:li:person:{profile_data.get('sub', '')}"
        except Exception as e:
            logger.warning("Failed to get LinkedIn profile URN: %s", e)
            return PublishResult(success=False, error=f"LinkedIn profile lookup failed: {e}")

        # Select the variation text (first variation by default)
        variations = payload.get("variations", [])
        selected_idx = payload.get("selected_variation_index", 0)
        if not variations:
            return PublishResult(success=False, error="No variations in draft")

        selected = variations[min(selected_idx, len(variations) - 1)]
        post_text = payload.get("edited_text") or selected.get("text", "")
        hashtags = payload.get("edited_hashtags") or selected.get("hashtags", [])
        if hashtags:
            post_text = post_text + "\n\n" + " ".join(hashtags)

        # POST to LinkedIn UGC API
        ugc_body = {
            "author": person_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": post_text},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                publish_resp = await client.post(
                    "https://api.linkedin.com/v2/ugcPosts",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                        "X-Restli-Protocol-Version": "2.0.0",
                    },
                    json=ugc_body,
                )
                publish_resp.raise_for_status()
                post_urn = publish_resp.headers.get("X-RestLi-Id", "")
        except Exception as e:
            logger.warning("Failed to publish LinkedIn post: %s", e)
            return PublishResult(success=False, error=f"LinkedIn publish failed: {e}")

        # Update aria_actions with post_urn and status
        now = datetime.now(UTC).isoformat()
        try:
            existing_meta = action.get("metadata", {})
            if isinstance(existing_meta, str):
                existing_meta = json.loads(existing_meta)
            existing_meta["post_urn"] = post_urn
            existing_meta["published_at"] = now

            db.table("aria_actions").update(
                {
                    "status": "user_approved",
                    "metadata": json.dumps(existing_meta),
                }
            ).eq("id", action_id).execute()
        except Exception as e:
            logger.warning("Failed to update action status: %s", e)

        # Schedule engagement checks at 1h, 4h, 24h, 48h
        check_offsets_hours = [1, 4, 24, 48]
        for offset_h in check_offsets_hours:
            try:
                check_time = datetime.now(UTC)
                from datetime import timedelta

                check_time = check_time + timedelta(hours=offset_h)
                db.table("prospective_memories").insert(
                    {
                        "id": str(uuid.uuid4()),
                        "user_id": user_id,
                        "memory_type": "engagement_check",
                        "title": f"Check LinkedIn post engagement ({offset_h}h)",
                        "description": f"Check engagement for post {post_urn}",
                        "trigger_time": check_time.isoformat(),
                        "metadata": json.dumps({"post_urn": post_urn, "action_id": action_id}),
                        "status": "pending",
                        "created_at": now,
                    }
                ).execute()
            except Exception as e:
                logger.debug("Failed to schedule engagement check at %dh: %s", offset_h, e)

        # Log activity
        await self.log_activity(
            activity_type="linkedin_post_published",
            title="Published LinkedIn post",
            description=f"Successfully published LinkedIn post (URN: {post_urn})",
            confidence=0.95,
            metadata={"action_id": action_id, "post_urn": post_urn},
        )

        return PublishResult(success=True, post_urn=post_urn)

    async def check_engagement(
        self,
        post_urn: str,
        user_id: str,
    ) -> EngagementReport:
        """Check engagement metrics for a published LinkedIn post.

        Fetches social actions (likes, comments, shares), cross-references
        engagers with lead_memory_stakeholders, and creates notifications
        when prospects engage.

        Args:
            post_urn: LinkedIn post URN identifier.
            user_id: Authenticated user UUID.

        Returns:
            EngagementReport with stats and notable engagers.
        """
        db = SupabaseClient.get_client()

        # Get OAuth token
        access_token = ""
        try:
            token_resp = (
                db.table("user_integrations")
                .select("access_token")
                .eq("user_id", user_id)
                .eq("provider", "linkedin")
                .eq("status", "active")
                .single()
                .execute()
            )
            access_token = token_resp.data.get("access_token", "") if token_resp.data else ""
        except Exception as e:
            logger.warning("Failed to get LinkedIn token for engagement check: %s", e)

        stats = EngagementStats()
        notable_engagers: list[EngagerInfo] = []

        if access_token:
            # GET social actions for the post
            try:
                encoded_urn = post_urn.replace(":", "%3A")
                async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                    actions_resp = await client.get(
                        f"https://api.linkedin.com/v2/socialActions/{encoded_urn}",
                        headers={"Authorization": f"Bearer {access_token}"},
                    )
                    actions_resp.raise_for_status()
                    data = actions_resp.json()

                    stats = EngagementStats(
                        likes=data.get("likesSummary", {}).get("totalLikes", 0),
                        comments=data.get("commentsSummary", {}).get("totalFirstLevelComments", 0),
                        shares=data.get("sharesSummary", {}).get("totalShares", 0),
                        impressions=data.get("impressionsSummary", {}).get("totalImpressions", 0),
                    )
            except Exception as e:
                logger.warning("Failed to fetch engagement stats: %s", e)

            # Get likes list and cross-reference with stakeholders
            try:
                async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                    likes_resp = await client.get(
                        f"https://api.linkedin.com/v2/socialActions/{encoded_urn}/likes",
                        headers={"Authorization": f"Bearer {access_token}"},
                    )
                    likes_resp.raise_for_status()
                    likes_data = likes_resp.json()

                    # Load stakeholders for cross-reference
                    stakeholders_resp = (
                        db.table("lead_memory_stakeholders")
                        .select("id, name, linkedin_url")
                        .eq("user_id", user_id)
                        .execute()
                    )
                    stakeholder_urns: dict[str, dict[str, Any]] = {}
                    if stakeholders_resp.data:
                        for s in stakeholders_resp.data:
                            if s.get("linkedin_url"):
                                stakeholder_urns[s["linkedin_url"]] = s

                    for like in likes_data.get("elements", []):
                        actor_urn = like.get("actor", "")
                        actor_name = like.get("actorName", actor_urn)
                        # Check if this engager is a known stakeholder
                        is_known = actor_urn in stakeholder_urns
                        engager = EngagerInfo(
                            name=actor_name,
                            linkedin_url=actor_urn,
                            relationship="known_stakeholder" if is_known else "",
                            lead_id=stakeholder_urns.get(actor_urn, {}).get("id"),
                        )
                        notable_engagers.append(engager)
            except Exception as e:
                logger.debug("Failed to fetch likes list: %s", e)

        # Store engagement metrics in aria_actions metadata
        try:
            actions_resp_db = (
                db.table("aria_actions")
                .select("id, metadata")
                .eq("user_id", user_id)
                .eq("action_type", "linkedin_post")
                .execute()
            )
            if actions_resp_db.data:
                for act in actions_resp_db.data:
                    meta = act.get("metadata", {})
                    if isinstance(meta, str):
                        meta = json.loads(meta)
                    if meta.get("post_urn") == post_urn:
                        meta["engagement_metrics"] = stats.model_dump()
                        meta["engagement_checked_at"] = datetime.now(UTC).isoformat()
                        db.table("aria_actions").update({"metadata": json.dumps(meta)}).eq(
                            "id", act["id"]
                        ).execute()
                        break
        except Exception as e:
            logger.debug("Failed to store engagement metrics: %s", e)

        # Create notification if a known prospect engaged
        known_engagers = [e for e in notable_engagers if e.relationship == "known_stakeholder"]
        if known_engagers:
            try:
                db.table("notifications").insert(
                    {
                        "id": str(uuid.uuid4()),
                        "user_id": user_id,
                        "type": "prospect_engagement",
                        "title": f"{len(known_engagers)} prospect(s) engaged with your LinkedIn post",
                        "body": ", ".join(e.name for e in known_engagers[:5]),
                        "metadata": json.dumps(
                            {"post_urn": post_urn, "engager_count": len(known_engagers)}
                        ),
                        "read": False,
                        "created_at": datetime.now(UTC).isoformat(),
                    }
                ).execute()
            except Exception as e:
                logger.debug("Failed to create engagement notification: %s", e)

        return EngagementReport(
            stats=stats,
            notable_engagers=notable_engagers,
        )

    async def auto_post_check(self, user_id: str) -> None:
        """Check for and auto-publish qualifying LinkedIn post drafts.

        Checks if the user has enabled linkedin_auto_post in preferences,
        then finds pending drafts with voice_match_confidence > 0.8 and
        no sensitive keywords, and auto-publishes them.

        Args:
            user_id: Authenticated user UUID.
        """
        db = SupabaseClient.get_client()

        # Check user preferences for auto-post setting
        try:
            pref_resp = (
                db.table("user_preferences")
                .select("metadata")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            if not pref_resp.data:
                return
            metadata = pref_resp.data[0].get("metadata", {})
            if isinstance(metadata, str):
                metadata = json.loads(metadata)
            if not metadata.get("linkedin_auto_post", False):
                return
        except Exception as e:
            logger.debug("Failed to check auto-post preferences: %s", e)
            return

        # Find pending linkedin_post drafts
        try:
            drafts_resp = (
                db.table("aria_actions")
                .select("*")
                .eq("user_id", user_id)
                .eq("action_type", "linkedin_post")
                .eq("status", "pending")
                .execute()
            )
            if not drafts_resp.data:
                return
        except Exception as e:
            logger.debug("Failed to query pending drafts: %s", e)
            return

        sensitive_keywords = [
            "confidential",
            "internal only",
            "not for distribution",
            "proprietary",
            "trade secret",
            "nda",
            "under embargo",
        ]

        for draft_action in drafts_resp.data:
            payload = draft_action.get("payload", {})
            if isinstance(payload, str):
                payload = json.loads(payload)

            variations = payload.get("variations", [])
            if not variations:
                continue

            # Find a variation with high enough confidence
            best_variation = None
            best_idx = 0
            for idx, v in enumerate(variations):
                confidence = float(v.get("voice_match_confidence", 0.0))
                if confidence > 0.8:
                    text_lower = v.get("text", "").lower()
                    has_sensitive = any(kw in text_lower for kw in sensitive_keywords)
                    if not has_sensitive and (
                        best_variation is None
                        or confidence > float(best_variation.get("voice_match_confidence", 0.0))
                    ):
                        best_variation = v
                        best_idx = idx

            if best_variation is None:
                continue

            # Mark as auto-approved and publish
            try:
                payload["selected_variation_index"] = best_idx
                db.table("aria_actions").update(
                    {
                        "status": "approved",
                        "payload": json.dumps(payload),
                        "metadata": json.dumps(
                            {
                                **(
                                    json.loads(draft_action.get("metadata", "{}"))
                                    if isinstance(draft_action.get("metadata"), str)
                                    else (draft_action.get("metadata") or {})
                                ),
                                "auto_approved": True,
                                "auto_approved_at": datetime.now(UTC).isoformat(),
                            }
                        ),
                    }
                ).eq("id", draft_action["id"]).execute()

                result = await self.publish_post(draft_action["id"])
                if result.success:
                    logger.info(
                        "Auto-published LinkedIn post %s",
                        draft_action["id"],
                    )
                else:
                    logger.warning(
                        "Auto-publish failed for %s: %s",
                        draft_action["id"],
                        result.error,
                    )
            except Exception as e:
                logger.warning("Auto-publish error for %s: %s", draft_action["id"], e)

    async def _fetch_page(self, url: str) -> str | None:
        """Fetch a web page and return its text content.

        Args:
            url: URL to fetch.

        Returns:
            Page text content, or None if fetch failed.
        """
        try:
            async with httpx.AsyncClient(
                timeout=_TIMEOUT,
                headers=_HEADERS,
                follow_redirects=True,
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.text

        except httpx.HTTPStatusError as e:
            logger.warning(
                "LinkedIn page returned HTTP %d for %s",
                e.response.status_code,
                url,
            )
            return None
        except httpx.RequestError as e:
            logger.warning("Failed to fetch LinkedIn page %s: %s", url, e)
            return None
