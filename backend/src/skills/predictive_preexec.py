"""Predictive Pre-Executor (Enhancement 9).

Runs on a cron schedule to pre-generate commonly requested outputs
so the orchestrator can serve instant results instead of re-executing:

- Meeting briefs (24h ahead)
- Follow-up drafts (recent activity)
- Battle card refreshes (>7 days old)
- Contact enrichment (new unenriched leads)

Results are stored in ``skill_working_memory`` with
``status='precomputed'`` and a ``plan_id`` prefixed with
``precompute:`` so the orchestrator can distinguish them from
regular execution results.

Logs all activity to ``aria_activity`` for transparency.
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from src.db.supabase import SupabaseClient
from src.services.activity_service import ActivityService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# How far ahead to pre-generate meeting briefs
MEETING_BRIEF_LOOKAHEAD_HOURS = 24

# Follow-up drafts for activity within this window
FOLLOWUP_ACTIVITY_WINDOW_HOURS = 48

# Battle cards older than this get refreshed
BATTLE_CARD_STALE_DAYS = 7

# Maximum items to process per category per run
MAX_ITEMS_PER_CATEGORY = 20


# ---------------------------------------------------------------------------
# Predictive Pre-Executor
# ---------------------------------------------------------------------------


class PredictivePreExecutor:
    """Pre-generates skill outputs on a cron schedule.

    Stores results in ``skill_working_memory`` with
    ``status='precomputed'`` so the orchestrator can check for
    available precomputed results before re-executing a skill.

    Each precomputed entry has:
    - ``plan_id``: ``precompute:<category>:<user_id>:<timestamp>``
    - ``skill_id``: The skill type that was pre-executed
    - ``status``: ``precomputed``
    - ``output_summary``: JSON-serialised result
    - ``extracted_facts``: Lookup key for the orchestrator
    """

    def __init__(self) -> None:
        self._activity = ActivityService()

    async def run(self) -> dict[str, Any]:
        """Execute all pre-generation categories for all active users.

        Returns:
            Summary dict with counts per category.
        """
        db = SupabaseClient.get_client()
        summary: dict[str, int] = {
            "meeting_briefs": 0,
            "followup_drafts": 0,
            "battle_card_refreshes": 0,
            "contact_enrichments": 0,
            "errors": 0,
        }

        # Get active users (those with completed onboarding)
        try:
            resp = (
                db.table("onboarding_state")
                .select("user_id")
                .not_.is_("completed_at", "null")
                .execute()
            )
            user_ids = [row["user_id"] for row in (resp.data or [])]
        except Exception as exc:
            logger.error("Failed to fetch users for pre-execution: %s", exc)
            return summary

        if not user_ids:
            logger.info("No active users for predictive pre-execution")
            return summary

        logger.info(
            "Predictive pre-executor starting for %d users",
            len(user_ids),
        )

        for user_id in user_ids:
            try:
                briefs = await self._pregenerate_meeting_briefs(db, user_id)
                summary["meeting_briefs"] += briefs
            except Exception as exc:
                logger.warning(
                    "Meeting brief pre-gen failed for user %s: %s",
                    user_id,
                    exc,
                )
                summary["errors"] += 1

            try:
                drafts = await self._pregenerate_followup_drafts(db, user_id)
                summary["followup_drafts"] += drafts
            except Exception as exc:
                logger.warning(
                    "Follow-up draft pre-gen failed for user %s: %s",
                    user_id,
                    exc,
                )
                summary["errors"] += 1

            try:
                cards = await self._refresh_stale_battle_cards(db, user_id)
                summary["battle_card_refreshes"] += cards
            except Exception as exc:
                logger.warning(
                    "Battle card refresh failed for user %s: %s",
                    user_id,
                    exc,
                )
                summary["errors"] += 1

            try:
                enriched = await self._enrich_new_leads(db, user_id)
                summary["contact_enrichments"] += enriched
            except Exception as exc:
                logger.warning(
                    "Contact enrichment pre-gen failed for user %s: %s",
                    user_id,
                    exc,
                )
                summary["errors"] += 1

        logger.info(
            "Predictive pre-executor complete: %s",
            summary,
        )

        return summary

    # ── Meeting briefs (24h ahead) ────────────────────────────────────

    async def _pregenerate_meeting_briefs(
        self,
        db: Any,
        user_id: str,
    ) -> int:
        """Pre-generate meeting briefs for upcoming meetings within 24h.

        Finds meetings that don't already have a precomputed brief
        and generates one using the briefing service.

        Args:
            db: Supabase client.
            user_id: User UUID.

        Returns:
            Number of briefs generated.
        """
        now = datetime.now(UTC)
        lookahead = now + timedelta(hours=MEETING_BRIEF_LOOKAHEAD_HOURS)

        # Find upcoming meetings without precomputed briefs
        try:
            meetings_resp = (
                db.table("meetings")
                .select("id, title, attendees, start_time, metadata")
                .eq("user_id", user_id)
                .gte("start_time", now.isoformat())
                .lte("start_time", lookahead.isoformat())
                .order("start_time")
                .limit(MAX_ITEMS_PER_CATEGORY)
                .execute()
            )
            meetings = meetings_resp.data or []
        except Exception as exc:
            logger.warning("Failed to fetch upcoming meetings: %s", exc)
            return 0

        if not meetings:
            return 0

        # Check which already have precomputed briefs
        meeting_ids = [m["id"] for m in meetings]
        existing = await self._get_existing_precomputed(db, user_id, "meeting_brief", meeting_ids)

        generated = 0
        for meeting in meetings:
            if meeting["id"] in existing:
                continue

            try:
                # Generate brief using the briefing service
                from src.services.briefing import BriefingService

                briefing_service = BriefingService()
                brief = await briefing_service.generate_meeting_brief(
                    user_id=user_id,
                    meeting_id=meeting["id"],
                )

                # Store as precomputed
                await self._store_precomputed(
                    db=db,
                    user_id=user_id,
                    category="meeting_brief",
                    entity_id=meeting["id"],
                    skill_id="meeting_brief",
                    result=brief,
                    metadata={
                        "meeting_title": meeting.get("title", ""),
                        "start_time": meeting.get("start_time", ""),
                    },
                )
                generated += 1

            except Exception as exc:
                logger.warning(
                    "Failed to pre-generate brief for meeting %s: %s",
                    meeting["id"],
                    exc,
                )

        if generated:
            await self._activity.record(
                user_id=user_id,
                agent="operator",
                activity_type="predictive_preexec",
                title=f"Pre-generated {generated} meeting brief(s)",
                description=(
                    f"ARIA proactively prepared {generated} meeting brief(s) "
                    f"for your upcoming meetings in the next {MEETING_BRIEF_LOOKAHEAD_HOURS}h."
                ),
                confidence=0.85,
                metadata={"category": "meeting_brief", "count": generated},
            )

        return generated

    # ── Follow-up drafts (recent activity) ────────────────────────────

    async def _pregenerate_followup_drafts(
        self,
        db: Any,
        user_id: str,
    ) -> int:
        """Pre-generate follow-up email drafts for recent activity.

        Looks for recent meetings that ended without follow-up drafts
        and generates them proactively.

        Args:
            db: Supabase client.
            user_id: User UUID.

        Returns:
            Number of drafts generated.
        """
        now = datetime.now(UTC)
        window_start = now - timedelta(hours=FOLLOWUP_ACTIVITY_WINDOW_HOURS)

        # Find recent meetings that ended and have no follow-up draft
        try:
            recent_resp = (
                db.table("meetings")
                .select("id, title, attendees, end_time, metadata")
                .eq("user_id", user_id)
                .gte("end_time", window_start.isoformat())
                .lte("end_time", now.isoformat())
                .order("end_time", desc=True)
                .limit(MAX_ITEMS_PER_CATEGORY)
                .execute()
            )
            recent_meetings = recent_resp.data or []
        except Exception as exc:
            logger.warning("Failed to fetch recent meetings for follow-up: %s", exc)
            return 0

        if not recent_meetings:
            return 0

        meeting_ids = [m["id"] for m in recent_meetings]
        existing = await self._get_existing_precomputed(db, user_id, "followup_draft", meeting_ids)

        generated = 0
        for meeting in recent_meetings:
            if meeting["id"] in existing:
                continue

            try:
                from src.services.draft_service import DraftService

                draft_service = DraftService()
                draft = await draft_service.generate_followup_draft(
                    user_id=user_id,
                    meeting_id=meeting["id"],
                )

                await self._store_precomputed(
                    db=db,
                    user_id=user_id,
                    category="followup_draft",
                    entity_id=meeting["id"],
                    skill_id="followup_draft",
                    result=draft,
                    metadata={
                        "meeting_title": meeting.get("title", ""),
                        "end_time": meeting.get("end_time", ""),
                    },
                )
                generated += 1

            except Exception as exc:
                logger.warning(
                    "Failed to pre-generate follow-up for meeting %s: %s",
                    meeting["id"],
                    exc,
                )

        if generated:
            await self._activity.record(
                user_id=user_id,
                agent="scribe",
                activity_type="predictive_preexec",
                title=f"Pre-generated {generated} follow-up draft(s)",
                description=(
                    f"ARIA proactively drafted {generated} follow-up email(s) "
                    f"for your recent meetings."
                ),
                confidence=0.80,
                metadata={"category": "followup_draft", "count": generated},
            )

        return generated

    # ── Battle card refreshes (>7 days old) ───────────────────────────

    async def _refresh_stale_battle_cards(
        self,
        db: Any,
        user_id: str,
    ) -> int:
        """Refresh battle cards that are older than BATTLE_CARD_STALE_DAYS.

        Args:
            db: Supabase client.
            user_id: User UUID.

        Returns:
            Number of battle cards refreshed.
        """
        stale_cutoff = (datetime.now(UTC) - timedelta(days=BATTLE_CARD_STALE_DAYS)).isoformat()

        try:
            stale_resp = (
                db.table("battle_cards")
                .select("id, competitor_name, metadata")
                .eq("user_id", user_id)
                .lte("updated_at", stale_cutoff)
                .limit(MAX_ITEMS_PER_CATEGORY)
                .execute()
            )
            stale_cards = stale_resp.data or []
        except Exception as exc:
            logger.warning("Failed to fetch stale battle cards: %s", exc)
            return 0

        if not stale_cards:
            return 0

        card_ids = [c["id"] for c in stale_cards]
        existing = await self._get_existing_precomputed(
            db, user_id, "battle_card_refresh", card_ids
        )

        refreshed = 0
        for card in stale_cards:
            if card["id"] in existing:
                continue

            try:
                from src.services.battle_card_service import BattleCardService

                bc_service = BattleCardService()
                updated = await bc_service.refresh_battle_card(
                    user_id=user_id,
                    battle_card_id=card["id"],
                )

                await self._store_precomputed(
                    db=db,
                    user_id=user_id,
                    category="battle_card_refresh",
                    entity_id=card["id"],
                    skill_id="battle_card_refresh",
                    result=updated,
                    metadata={
                        "competitor_name": card.get("competitor_name", ""),
                    },
                )
                refreshed += 1

            except Exception as exc:
                logger.warning(
                    "Failed to refresh battle card %s: %s",
                    card["id"],
                    exc,
                )

        if refreshed:
            await self._activity.record(
                user_id=user_id,
                agent="analyst",
                activity_type="predictive_preexec",
                title=f"Refreshed {refreshed} stale battle card(s)",
                description=(
                    f"ARIA proactively refreshed {refreshed} battle card(s) "
                    f"that were more than {BATTLE_CARD_STALE_DAYS} days old."
                ),
                confidence=0.80,
                metadata={"category": "battle_card_refresh", "count": refreshed},
            )

        return refreshed

    # ── Contact enrichment (new unenriched leads) ─────────────────────

    async def _enrich_new_leads(
        self,
        db: Any,
        user_id: str,
    ) -> int:
        """Enrich new leads that haven't been enriched yet.

        Finds leads without enrichment data in lead_memory_stakeholders
        and runs contact enrichment proactively.

        Args:
            db: Supabase client.
            user_id: User UUID.

        Returns:
            Number of leads enriched.
        """
        # Find leads without enrichment
        try:
            leads_resp = (
                db.table("leads")
                .select("id, contact_name, company_name, title")
                .eq("user_id", user_id)
                .is_("enriched_at", "null")
                .order("created_at", desc=True)
                .limit(MAX_ITEMS_PER_CATEGORY)
                .execute()
            )
            unenriched_leads = leads_resp.data or []
        except Exception as exc:
            logger.warning("Failed to fetch unenriched leads: %s", exc)
            return 0

        if not unenriched_leads:
            return 0

        enriched = 0
        for lead in unenriched_leads:
            name = lead.get("contact_name", "")
            company = lead.get("company_name", "")
            if not name:
                continue

            try:
                from src.agents.capabilities.base import UserContext
                from src.agents.capabilities.contact_enricher import (
                    ContactEnricherCapability,
                )

                ctx = UserContext(user_id=user_id)
                capability = ContactEnricherCapability(
                    supabase_client=db,
                    memory_service=None,
                    knowledge_graph=None,
                    user_context=ctx,
                )

                result = await capability.enrich_contact(
                    name=name,
                    company=company,
                    role=lead.get("title", ""),
                )

                # Store as precomputed
                await self._store_precomputed(
                    db=db,
                    user_id=user_id,
                    category="contact_enrichment",
                    entity_id=lead["id"],
                    skill_id="contact_enrichment",
                    result=result.model_dump(mode="json"),
                    metadata={
                        "contact_name": name,
                        "company": company,
                    },
                )

                # Mark lead as enriched (non-critical)
                import contextlib

                with contextlib.suppress(Exception):
                    db.table("leads").update({"enriched_at": datetime.now(UTC).isoformat()}).eq(
                        "id", lead["id"]
                    ).execute()

                enriched += 1

            except Exception as exc:
                logger.warning(
                    "Failed to enrich lead %s: %s",
                    lead["id"],
                    exc,
                )

        if enriched:
            await self._activity.record(
                user_id=user_id,
                agent="hunter",
                activity_type="predictive_preexec",
                title=f"Enriched {enriched} new lead(s)",
                description=(
                    f"ARIA proactively enriched {enriched} new lead(s) "
                    f"with profile intelligence and contact data."
                ),
                confidence=0.80,
                metadata={"category": "contact_enrichment", "count": enriched},
            )

        return enriched

    # ── Storage helpers ───────────────────────────────────────────────

    async def _store_precomputed(
        self,
        *,
        db: Any,
        user_id: str,
        category: str,
        entity_id: str,
        skill_id: str,
        result: Any,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Store a precomputed result in skill_working_memory.

        Args:
            db: Supabase client.
            user_id: User UUID.
            category: Pre-execution category.
            entity_id: ID of the entity this result is for.
            skill_id: Skill type identifier.
            result: The precomputed result (dict or serialisable).
            metadata: Extra metadata.
        """
        now = datetime.now(UTC)
        plan_id = f"precompute:{category}:{user_id}:{now.strftime('%Y%m%d%H%M%S')}"

        record = {
            "plan_id": plan_id,
            "step_number": 0,
            "skill_id": skill_id,
            "input_summary": json.dumps(metadata or {}),
            "output_summary": json.dumps(result, default=str),
            "artifacts": json.dumps([]),
            "extracted_facts": json.dumps(
                {
                    "category": category,
                    "entity_id": entity_id,
                    "user_id": user_id,
                }
            ),
            "next_step_hints": json.dumps([]),
            "status": "precomputed",
            "execution_time_ms": 0,
        }

        try:
            db.table("skill_working_memory").insert(record).execute()
        except Exception as exc:
            logger.warning(
                "Failed to store precomputed result: %s",
                exc,
                extra={"category": category, "entity_id": entity_id},
            )

    async def _get_existing_precomputed(
        self,
        db: Any,
        user_id: str,
        category: str,
        entity_ids: list[str],
    ) -> set[str]:
        """Check which entities already have fresh precomputed results.

        Args:
            db: Supabase client.
            user_id: User UUID.
            category: Pre-execution category.
            entity_ids: Entity IDs to check.

        Returns:
            Set of entity IDs that already have precomputed results.
        """
        if not entity_ids:
            return set()

        # Look for recent precomputed entries (within last 24h)
        cutoff = (datetime.now(UTC) - timedelta(hours=24)).isoformat()

        try:
            resp = (
                db.table("skill_working_memory")
                .select("extracted_facts")
                .eq("status", "precomputed")
                .eq("skill_id", category)
                .gte("created_at", cutoff)
                .like("plan_id", f"precompute:{category}:{user_id}:%")
                .execute()
            )

            existing: set[str] = set()
            for row in resp.data or []:
                facts = row.get("extracted_facts")
                if isinstance(facts, str):
                    try:
                        facts = json.loads(facts)
                    except json.JSONDecodeError:
                        continue
                if isinstance(facts, dict):
                    eid = facts.get("entity_id", "")
                    if eid in entity_ids:
                        existing.add(eid)

            return existing

        except Exception as exc:
            logger.warning("Failed to check existing precomputed: %s", exc)
            return set()


# ---------------------------------------------------------------------------
# Orchestrator integration: check for precomputed results
# ---------------------------------------------------------------------------


async def get_precomputed_result(
    user_id: str,
    skill_id: str,
    entity_id: str,
) -> dict[str, Any] | None:
    """Check if a precomputed result exists for a skill + entity.

    The orchestrator should call this before re-executing a skill.
    Results are valid for 24 hours.

    Args:
        user_id: User UUID.
        skill_id: The skill type to check.
        entity_id: The entity ID to check.

    Returns:
        Precomputed result dict, or None if not available.
    """
    db = SupabaseClient.get_client()
    cutoff = (datetime.now(UTC) - timedelta(hours=24)).isoformat()

    try:
        query = (
            db.table("skill_working_memory")
            .select("output_summary, extracted_facts, created_at")
            .eq("status", "precomputed")
            .eq("skill_id", skill_id)
            .gte("created_at", cutoff)
            .like("plan_id", f"precompute:{skill_id}:{user_id}:%")
            .order("created_at", desc=True)
        )

        resp = query.limit(20).execute()

        # Filter by entity_id from extracted_facts
        import json as _json

        for row in resp.data or []:
            facts = row.get("extracted_facts", "")
            if isinstance(facts, str):
                try:
                    facts = _json.loads(facts)
                except _json.JSONDecodeError:
                    continue
            if isinstance(facts, dict) and facts.get("entity_id") == entity_id:
                resp.data = [row]
                break
        else:
            resp.data = []

        if not resp.data:
            return None

        row = resp.data[0]
        output = row.get("output_summary", "")
        if isinstance(output, str):
            try:
                return json.loads(output)
            except json.JSONDecodeError:
                return None
        return output

    except Exception as exc:
        logger.warning("Failed to check precomputed result: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Cron entry point
# ---------------------------------------------------------------------------


async def run_predictive_preexec_cron() -> None:
    """Cron entry point for the predictive pre-executor.

    Designed to run every 30 minutes via the APScheduler.
    """
    executor = PredictivePreExecutor()
    try:
        summary = await executor.run()
        logger.info("Predictive pre-executor cron complete: %s", summary)
    except Exception:
        logger.exception("Predictive pre-executor cron failed")
