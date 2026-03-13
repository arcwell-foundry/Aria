"""Lightweight Tavus API client for briefing video generation and CVI conversations.

Separate from the full TavusClient in integrations/tavus.py which handles
persona-based CVI sessions. This client provides simple, direct API calls
for one-way video generation and briefing-specific CVI sessions.
"""

import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from src.core.config import settings

logger = logging.getLogger(__name__)


def _build_json_patch(payload: dict) -> list[dict]:
    """Convert a persona payload dict into JSON Patch (RFC 6902) operations.

    Uses ``add`` instead of ``replace`` so the operation succeeds regardless of
    whether the field already exists on the persona. For nested dicts inside
    ``layers``, each sub-layer (llm, perception, vqa, etc.) is replaced as a
    whole object to avoid partial-path issues.
    """
    ops: list[dict] = []
    for key, value in payload.items():
        if key == "layers" and isinstance(value, dict):
            # Replace each sub-layer as a whole object
            for layer_name, layer_config in value.items():
                ops.append({
                    "op": "add",
                    "path": f"/layers/{layer_name}",
                    "value": layer_config,
                })
        else:
            ops.append({"op": "add", "path": f"/{key}", "value": value})
    return ops


class TavusClient:
    """Client for Tavus video generation and briefing CVI conversations."""

    BASE_URL = "https://tavusapi.com"
    REPLICA_ID = "r5dc7c7d0bcb"

    def __init__(self) -> None:
        if not settings.TAVUS_API_KEY:
            raise ValueError("TAVUS_API_KEY not set in environment")
        self.api_key = settings.TAVUS_API_KEY.get_secret_value()
        self.replica_id = self.REPLICA_ID

    @staticmethod
    def _time_greeting() -> str:
        hour = datetime.now(ZoneInfo("America/New_York")).hour
        if hour < 12:
            return "Good morning"
        elif hour < 17:
            return "Good afternoon"
        return "Good evening"

    async def create_or_update_aria_persona(
        self, backend_url: str, llm_secret: str
    ) -> str:
        """Create or update the ARIA persona on Tavus with custom LLM wiring.

        Configures:
        - ARIA's own FastAPI endpoint as the LLM brain
        - Raven-1 perception model (emotion + face detection)
        - Speculative inference for low-latency responses

        Args:
            backend_url: The backend's public URL (e.g. https://app.onrender.com).
            llm_secret: The shared secret for Tavus→ARIA LLM auth.

        Returns:
            The persona_id string.
        """
        # Echo mode: Tavus routes all LLM calls to our base_url.
        # system_prompt and context must be empty — our LLM endpoint
        # builds the full prompt per-conversation using the user_id
        # from conversational_context.
        payload = {
            "persona_name": "ARIA - LuminOne",
            "pipeline_mode": "echo",
            "system_prompt": "",
            "context": "",
            "default_replica_id": self.replica_id,
            "layers": {
                "llm": {
                    "model": "claude-haiku-4-5-20251001",
                    "base_url": f"{backend_url}/api/tavus",
                    "api_key": llm_secret,
                    "speculative_inference": True,
                    "extra_body": {
                        "temperature": 0.3,
                    },
                },
            },
        }
        # NOTE: enable_closed_captions is set per-conversation, not on persona

        headers = {"x-api-key": self.api_key, "Content-Type": "application/json"}

        existing_persona_id = settings.TAVUS_PERSONA_ID or None

        async with httpx.AsyncClient(timeout=30.0) as client:
            if existing_persona_id:
                # Update existing persona — Tavus PATCH requires JSON Patch (RFC 6902)
                patch_ops = _build_json_patch(payload)
                resp = await client.patch(
                    f"{self.BASE_URL}/v2/personas/{existing_persona_id}",
                    json=patch_ops,
                    headers=headers,
                )
            else:
                # Create new persona — POST accepts flat JSON payload
                resp = await client.post(
                    f"{self.BASE_URL}/v2/personas",
                    json=payload,
                    headers=headers,
                )

            if not resp.is_success:
                logger.error(
                    "Tavus persona create/update error %s: %s",
                    resp.status_code,
                    resp.text,
                )
                resp.raise_for_status()

            data = resp.json()
            persona_id = data.get("persona_id") or existing_persona_id

        logger.info(
            "ARIA Persona ID: %s — add TAVUS_PERSONA_ID=%s to .env",
            persona_id,
            persona_id,
        )

        return persona_id

    async def create_video_briefing(self, script: str, briefing_date: str) -> dict:
        """Call Tavus /v2/videos to generate a one-way video from script.

        Args:
            script: The spoken briefing script text.
            briefing_date: ISO date string for video naming.

        Returns:
            Dict with video_id, hosted_url, and other Tavus response fields.
        """
        payload = {
            "replica_id": self.REPLICA_ID,
            "script": script,
            "video_name": f"ARIA Morning Briefing {briefing_date}",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.BASE_URL}/v2/videos",
                headers={"x-api-key": self.api_key, "Content-Type": "application/json"},
                json=payload,
            )
            if not resp.is_success:
                logger.error("Tavus video error %s: %s", resp.status_code, resp.text)
                resp.raise_for_status()
            return resp.json()

    async def create_cvi_conversation(
        self,
        briefing_content: dict,
        user_name: str = "Dhruv",
        user_id: str = "",
    ) -> dict:
        """Create a live Tavus CVI conversation pre-loaded with briefing context.

        When a persona_id is configured (TAVUS_PERSONA_ID), the persona's custom
        LLM endpoint handles all intelligence.  The conversational_context here
        provides session-specific data the LLM needs.

        Args:
            briefing_content: The briefing content dict with calendar, tasks, signals.
            user_name: The user's first name for personalization.
            user_id: The user's UUID — injected into context for custom LLM auth.

        Returns:
            Dict with conversation_url, conversation_id from Tavus.
        """
        # --- Build one-liner summaries for conversational_context ---
        meetings = briefing_content.get("calendar", {}).get("key_meetings", [])[:3]
        tasks = briefing_content.get("tasks", {}).get("overdue", [])[:3]
        signals = briefing_content.get("signals", {})

        meetings_one_liner = (
            "; ".join(
                f"{m.get('time', '?')} {m.get('title', '?')}" for m in meetings
            )
            or "no meetings today"
        )

        actions_one_liner = (
            "; ".join(
                (t.get("task") or t.get("title", "?"))[:60] for t in tasks[:2]
            )
            or "none"
        )

        email_drafts = briefing_content.get("email_summary", {})
        email_one_liner = (
            f"{email_drafts.get('drafts_waiting', 0)} drafts waiting"
            if email_drafts.get("drafts_waiting")
            else "no pending drafts"
        )

        comp_signals = (
            "; ".join(
                f"{s.get('company_name', '?')}: {s.get('headline', '')[:60]}"
                for s in signals.get("competitive_intel", [])[:2]
            )
            or "none this week"
        )

        briefing_date = briefing_content.get("generated_at", "today")[:10]

        # Conversational context — the custom LLM endpoint receives this in the
        # system message and uses it to identify the user + seed briefing data.
        conversational_context = (
            f"user_id:{user_id}\n"
            f"User: {user_name}\n"
            f"Today's briefing context:\n"
            f"Meetings: {meetings_one_liner}\n"
            f"Priority actions: {actions_one_liner}\n"
            f"Email drafts: {email_one_liner}\n"
            f"Top signals: {comp_signals}"
        )

        # --- Build payload ---
        persona_id = settings.TAVUS_PERSONA_ID or None

        payload: dict = {
            "replica_id": self.REPLICA_ID,
            "conversation_name": f"ARIA Briefing - {briefing_date}",
            "conversational_context": conversational_context,
            "custom_greeting": f"{self._time_greeting()}, {user_name}.",
            "properties": {
                "max_call_duration": 1800,       # 30 min max
                "participant_left_timeout": 120,  # end if user gone 2 min
                "enable_recording": False,
                "apply_greenscreen": False,
                "enable_closed_captions": False,
            },
        }

        if persona_id:
            payload["persona_id"] = persona_id

        logger.info(
            "[TAVUS] Creating conversation with body: %s",
            json.dumps(payload, indent=2),
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.BASE_URL}/v2/conversations",
                headers={"x-api-key": self.api_key, "Content-Type": "application/json"},
                json=payload,
            )
            if not resp.is_success:
                logger.error("Tavus CVI error %s: %s", resp.status_code, resp.text)
                resp.raise_for_status()
            response_data = resp.json()
            logger.info(
                "[TAVUS] Conversation created: %s",
                json.dumps(response_data, indent=2)[:500],
            )

            # Append prejoin=false to skip Daily.co join screen
            conversation_url = response_data.get("conversation_url", "")
            if conversation_url and "?" not in conversation_url:
                conversation_url += "?prejoin=false"
            elif conversation_url and "prejoin=false" not in conversation_url:
                conversation_url += "&prejoin=false"
            response_data["conversation_url"] = conversation_url

            return response_data

    async def end_conversation(self, conversation_id: str) -> bool:
        """Terminate an active Tavus CVI conversation to stop billing.

        Args:
            conversation_id: The Tavus conversation ID to terminate.

        Returns:
            True if the conversation was terminated or already gone.
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.delete(
                f"{self.BASE_URL}/v2/conversations/{conversation_id}",
                headers={"x-api-key": self.api_key},
            )
        logger.info(
            "Tavus end_conversation %s: status=%s", conversation_id, resp.status_code
        )
        # 404 = already ended, still ok
        return resp.status_code in (200, 204, 404)

    async def get_video_status(self, video_id: str) -> dict:
        """Check status of a generated video.

        Args:
            video_id: The Tavus video ID to check.

        Returns:
            Dict with status, hosted_url, and other Tavus response fields.
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{self.BASE_URL}/v2/videos/{video_id}",
                headers={"x-api-key": self.api_key},
            )
            resp.raise_for_status()
            return resp.json()
