"""US-925: Continuous Onboarding Loop (Ambient Gap Filling).

Background service that proactively fills knowledge gaps after formal
onboarding ends. Generates natural conversation prompts — NOT pop-ups —
woven into ARIA's natural interaction.

Builds on:
- US-912: KnowledgeGapDetector (identifies what ARIA doesn't know)
- US-913: OnboardingReadinessService (readiness sub-scores)
- US-924: OnboardingOutcomeTracker (procedural memory)

Theory of Mind: Don't nag busy users. Space prompts. Detect receptivity.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from src.db.supabase import SupabaseClient
from src.onboarding.readiness import OnboardingReadinessService

logger = logging.getLogger(__name__)

# Domains that are NOT readiness sub-scores
_EXCLUDED_KEYS = {"overall", "confidence_modifier"}


class AmbientGapFiller:
    """Proactively fills knowledge gaps through natural interaction.

    Runs daily. If any readiness sub-score < threshold (default 60%),
    generates a natural prompt to surface in the next ARIA conversation.

    Theory of Mind aware: Don't nag busy users. Space prompts.
    """

    THRESHOLD = 60.0
    MIN_DAYS_BETWEEN_PROMPTS = 3
    MAX_PROMPTS_PER_WEEK = 2

    def __init__(self) -> None:
        """Initialize with database client and readiness service."""
        self._db = SupabaseClient.get_client()
        self._readiness_service = OnboardingReadinessService()

    async def check_and_generate(self, user_id: str) -> dict[str, Any] | None:
        """Check gaps and generate ambient prompt if appropriate.

        Steps:
        1. Get readiness scores
        2. Find domains below threshold
        3. Check spacing (don't nag)
        4. Check weekly limit
        5. Pick highest-impact gap (lowest score)
        6. Generate natural prompt
        7. Store for next conversation pickup
        8. Track generation event

        Args:
            user_id: The user to check and generate prompts for.

        Returns:
            Prompt dict if generated, None if no prompt needed or suppressed.
        """
        try:
            # 1. Check readiness scores
            readiness = await self._get_readiness(user_id)

            if not readiness:
                return None

            # 2. Find domains below threshold
            low_domains: dict[str, float] = {}
            for key, value in readiness.items():
                if key in _EXCLUDED_KEYS:
                    continue
                if not isinstance(value, (int, float)):
                    continue
                if value < self.THRESHOLD:
                    low_domains[key] = float(value)

            if not low_domains:
                return None

            # 3. Check spacing — don't nag
            last_prompt = await self._get_last_prompt_time(user_id)
            if last_prompt and self._too_soon(last_prompt):
                return None

            # 4. Check weekly limit
            weekly_count = await self._get_weekly_prompt_count(user_id)
            if weekly_count >= self.MAX_PROMPTS_PER_WEEK:
                return None

            # 5. Pick highest-impact gap (lowest score)
            priority_domain = min(low_domains, key=low_domains.get)  # type: ignore[arg-type]

            # 6. Generate natural prompt
            prompt = await self._generate_prompt(priority_domain, low_domains[priority_domain])

            # 7. Store for next conversation pickup
            await self._store_pending_prompt(user_id, prompt)

            # 8. Track
            await self._record_prompt_generated(user_id, prompt)

            return prompt

        except Exception:
            logger.exception(
                "Error in ambient gap check",
                extra={"user_id": user_id},
            )
            return None

    def _too_soon(self, last_prompt_time: datetime) -> bool:
        """Check if last prompt was too recent.

        Args:
            last_prompt_time: Timestamp of last generated prompt.

        Returns:
            True if we should wait before sending another prompt.
        """
        min_gap = timedelta(days=self.MIN_DAYS_BETWEEN_PROMPTS)
        return datetime.now(UTC) - last_prompt_time < min_gap

    async def _get_readiness(self, user_id: str) -> dict[str, Any]:
        """Get readiness scores as a dict.

        Args:
            user_id: The user to get scores for.

        Returns:
            Dict of domain → score mappings.
        """
        breakdown = await self._readiness_service.get_readiness(user_id)
        return breakdown.model_dump()

    async def _get_last_prompt_time(self, user_id: str) -> datetime | None:
        """Get timestamp of most recent ambient prompt for user.

        Args:
            user_id: The user to check.

        Returns:
            Datetime of last prompt, or None if no prompts exist.
        """
        try:
            response = (
                self._db.table("ambient_prompts")
                .select("created_at")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if response.data and len(response.data) > 0:
                row = response.data[0]
                if isinstance(row, dict) and row.get("created_at"):
                    ts = row["created_at"]
                    if isinstance(ts, str):
                        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return None
        except Exception:
            logger.warning(
                "Failed to get last prompt time",
                extra={"user_id": user_id},
            )
            return None

    async def _get_weekly_prompt_count(self, user_id: str) -> int:
        """Count prompts generated for user in the last 7 days.

        Args:
            user_id: The user to count for.

        Returns:
            Number of prompts generated in the past week.
        """
        try:
            week_ago = (datetime.now(UTC) - timedelta(days=7)).isoformat()
            response = (
                self._db.table("ambient_prompts")
                .select("id")
                .eq("user_id", user_id)
                .gte("created_at", week_ago)
                .execute()
            )
            return len(response.data or [])
        except Exception:
            logger.warning(
                "Failed to get weekly prompt count",
                extra={"user_id": user_id},
            )
            return 0

    async def _generate_prompt(self, domain: str, score: float) -> dict[str, Any]:
        """Generate a natural, non-intrusive prompt for a gap domain.

        Each domain has a carefully crafted prompt that feels like
        natural conversation, not a system notification.

        Args:
            domain: The readiness domain to fill.
            score: Current readiness score for the domain.

        Returns:
            Prompt dict with domain, prompt text, score, and type.
        """
        prompts: dict[str, str] = {
            "digital_twin": (
                "I'd love to match your writing style more closely. "
                "Could you forward me a few recent emails? Even 3-4 "
                "would make a big difference in how I draft for you."
            ),
            "corporate_memory": (
                "I have some gaps in my understanding of your company's "
                "product lineup. When you have a moment, could you share "
                "a capabilities deck or product sheet?"
            ),
            "relationship_graph": (
                "I'd be much more effective if I knew more about your "
                "key contacts. Who are the 3-5 people you interact with most?"
            ),
            "integrations": (
                "Connecting your calendar would let me prepare meeting "
                "briefs automatically. Want to set that up?"
            ),
            "goal_clarity": (
                "What's the most important thing you're working on this "
                "week? Setting a specific goal helps me prioritize what "
                "I work on."
            ),
        }

        return {
            "domain": domain,
            "prompt": prompts.get(
                domain,
                f"I'd like to learn more about your {domain.replace('_', ' ')}.",
            ),
            "score": score,
            "type": "ambient_gap_fill",
        }

    async def _store_pending_prompt(self, user_id: str, prompt: dict[str, Any]) -> None:
        """Store prompt in ambient_prompts table for chat service pickup.

        Args:
            user_id: The user to store the prompt for.
            prompt: The generated prompt data.
        """
        try:
            self._db.table("ambient_prompts").insert(
                {
                    "user_id": user_id,
                    "domain": prompt["domain"],
                    "prompt": prompt["prompt"],
                    "score": prompt["score"],
                    "status": "pending",
                    "metadata": {
                        "type": prompt["type"],
                        "generated_at": datetime.now(UTC).isoformat(),
                    },
                }
            ).execute()
        except Exception:
            logger.exception(
                "Failed to store pending prompt",
                extra={"user_id": user_id},
            )

    async def _record_prompt_generated(self, user_id: str, prompt: dict[str, Any]) -> None:
        """Record prompt generation event for tracking.

        Args:
            user_id: The user who received the prompt.
            prompt: The generated prompt data.
        """
        logger.info(
            "Ambient gap prompt generated",
            extra={
                "user_id": user_id,
                "domain": prompt["domain"],
                "score": prompt["score"],
            },
        )

    async def get_pending_prompt(self, user_id: str) -> dict[str, Any] | None:
        """Get pending ambient prompt for next conversation.

        Called by chat service before generating ARIA response to
        weave gap-filling into natural interaction.

        Args:
            user_id: The user to get a pending prompt for.

        Returns:
            Prompt dict or None if no pending prompts.
        """
        try:
            maybe_single = (
                self._db.table("ambient_prompts")
                .select("*")
                .eq("user_id", user_id)
                .eq("status", "pending")
                .order("created_at", desc=False)
                .limit(1)
                .maybe_single()
            )
            response = maybe_single.execute() if maybe_single else None
            if response and response.data and isinstance(response.data, dict):
                # Mark as delivered
                prompt_id = response.data.get("id")
                if prompt_id:
                    (
                        self._db.table("ambient_prompts")
                        .update(
                            {
                                "status": "delivered",
                                "delivered_at": datetime.now(UTC).isoformat(),
                            }
                        )
                        .eq("id", prompt_id)
                        .execute()
                    )
                return dict(response.data)
            return None
        except Exception:
            logger.exception(
                "Failed to get pending prompt",
                extra={"user_id": user_id},
            )
            return None

    async def record_outcome(self, user_id: str, prompt_id: str, outcome: str) -> None:
        """Track prompt engagement outcome.

        Records whether user engaged, dismissed, or deferred the prompt.
        Engaged outcomes feed into procedural memory for better future
        prompt strategies.

        Args:
            user_id: The user who responded.
            prompt_id: The ambient_prompts row ID.
            outcome: One of "engaged", "dismissed", "deferred".
        """
        try:
            # Update prompt status
            self._db.table("ambient_prompts").update(
                {
                    "status": outcome,
                    "resolved_at": datetime.now(UTC).isoformat(),
                }
            ).eq("id", prompt_id).execute()

            # For engaged outcomes, record to procedural memory
            if outcome == "engaged":
                # Fetch prompt details for context
                maybe_prompt = (
                    self._db.table("ambient_prompts").select("*").eq("id", prompt_id).maybe_single()
                )
                prompt_response = maybe_prompt.execute() if maybe_prompt else None
                if (
                    prompt_response
                    and prompt_response.data
                    and isinstance(prompt_response.data, dict)
                ):
                    domain = prompt_response.data.get("domain", "unknown")
                    self._db.table("procedural_insights").insert(
                        {
                            "insight": (
                                f"Ambient gap-fill prompt for {domain} was effective — user engaged"
                            ),
                            "insight_type": "ambient_gap_fill",
                            "evidence_count": 1,
                            "confidence": 0.6,
                        }
                    ).execute()

            logger.info(
                "Ambient prompt outcome recorded",
                extra={
                    "user_id": user_id,
                    "prompt_id": prompt_id,
                    "outcome": outcome,
                },
            )
        except Exception:
            logger.exception(
                "Failed to record prompt outcome",
                extra={
                    "user_id": user_id,
                    "prompt_id": prompt_id,
                },
            )
