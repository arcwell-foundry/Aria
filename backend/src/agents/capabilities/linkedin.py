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
from src.db.supabase import SupabaseClient
from src.models.social import (
    PostDraft,
    PostVariation,
    PostVariationType,
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
