"""Lightweight Tavus API client for briefing video generation and CVI conversations.

Separate from the full TavusClient in integrations/tavus.py which handles
persona-based CVI sessions. This client provides simple, direct API calls
for one-way video generation and briefing-specific CVI sessions.
"""

import logging
import os

import httpx

logger = logging.getLogger(__name__)


class TavusClient:
    """Client for Tavus video generation and briefing CVI conversations."""

    BASE_URL = "https://tavusapi.com"
    REPLICA_ID = "r5dc7c7d0bcb"

    def __init__(self) -> None:
        self.api_key = os.getenv("TAVUS_API_KEY")
        if not self.api_key:
            raise ValueError("TAVUS_API_KEY not set in environment")

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
        self, briefing_content: dict, user_name: str = "Dhruv"
    ) -> dict:
        """Create a live Tavus CVI conversation pre-loaded with briefing context.

        Args:
            briefing_content: The briefing content dict with calendar, tasks, signals.
            user_name: The user's first name for personalization.

        Returns:
            Dict with conversation_url, conversation_id from Tavus.
        """
        meetings = briefing_content.get("calendar", {}).get("key_meetings", [])[:3]
        tasks = briefing_content.get("tasks", {}).get("overdue", [])[:3]
        signals = briefing_content.get("signals", {})

        meetings_text = (
            "; ".join(
                f"{m.get('time', '?')} {m.get('title', '?')}" for m in meetings
            )
            or "no meetings today"
        )

        top_tasks = (
            "; ".join(
                (t.get("task") or t.get("title", "?"))[:60] for t in tasks[:2]
            )
            or "none"
        )

        comp_signals = (
            "; ".join(
                f"{s.get('company_name', '?')}: {s.get('headline', '')[:60]}"
                for s in signals.get("competitive_intel", [])[:2]
            )
            or "none this week"
        )

        # Get the pre-generated tavus_script if available for richer context
        existing_script = briefing_content.get("tavus_script", "")
        script_context = (
            f"\n\nHere is your pre-generated briefing script to refer to:\n{existing_script[:800]}"
            if existing_script
            else ""
        )

        system_prompt = (
            f"You are ARIA, an autonomous AI colleague for {user_name} at LuminOne, "
            f"a life sciences commercial AI company.\n"
            f"You are conducting {user_name}'s morning briefing via live video call. "
            f"You are warm, direct, and highly intelligent — like a brilliant EA who knows everything.\n\n"
            f"TODAY'S CONTEXT:\n"
            f"Meetings: {meetings_text}\n"
            f"Priority actions: {top_tasks}\n"
            f"Competitor signals: {comp_signals}{script_context}\n\n"
            f"CONVERSATION RULES:\n"
            f"- Address {user_name} by first name only\n"
            f"- Spoken sentences only — no lists, no bullet points, no markdown\n"
            f"- Keep responses under 60 words unless {user_name} asks for detail\n"
            f"- When {user_name} interrupts or asks a question, answer directly then ask \"Shall I continue?\"\n"
            f"- After answering, always offer a specific next action (draft an email, pull a brief, etc.)\n"
            f"- You can see the full briefing data — reference specific names, companies, numbers\n"
            f"- Start with: \"Good morning {user_name}. Ready for your briefing?\" then wait."
        )

        payload = {
            "replica_id": self.REPLICA_ID,
            "conversational_context": system_prompt,
            "custom_greeting": f"Good morning {user_name}. Ready for your briefing?",
            "properties": {
                "max_call_duration": 600,
                "participant_left_timeout": 60,
                "enable_recording": False,
                "apply_conversation_rules": True,
            },
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.BASE_URL}/v2/conversations",
                headers={"x-api-key": self.api_key, "Content-Type": "application/json"},
                json=payload,
            )
            if not resp.is_success:
                logger.error("Tavus CVI error %s: %s", resp.status_code, resp.text)
                resp.raise_for_status()
            return resp.json()

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
