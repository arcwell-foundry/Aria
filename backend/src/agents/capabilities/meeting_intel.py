"""Meeting Intelligence capability for AnalystAgent and ScribeAgent.

Provides deep meeting analysis for ARIA: processing raw transcripts (from
uploaded files or ``video_transcript_entries``) through LLM-powered extraction
of action items, commitments, objections, sentiment shifts, and decision
points.  Generates coaching insights on talk-to-listen ratio, question
patterns, and objection handling.  Produces CRM-ready meeting summaries queued
for automatic push.

Key responsibilities:
- Extract structured intelligence from meeting transcripts via LLM
- Generate sales coaching insights from conversation dynamics
- Auto-generate CRM-ready summaries queued via integration_push_queue
- Write action items to prospective_memories (future tasks)
- Write commitments to lead_memory_events
- Update lead_memories.last_activity_at
"""

import json
import logging
import time
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from src.agents.capabilities.base import BaseCapability, CapabilityResult
from src.core.llm import LLMClient
from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


# ── Pydantic models ──────────────────────────────────────────────────────


class CommitmentOwner(str, Enum):
    """Who made the commitment."""

    OURS = "ours"
    THEIRS = "theirs"


class ActionItem(BaseModel):
    """A concrete follow-up task extracted from a meeting."""

    description: str
    assignee: str | None = None
    due_hint: str | None = Field(None, description="Relative due date hint, e.g. 'by Friday'")
    priority: str = Field("medium", description="low | medium | high")


class Commitment(BaseModel):
    """A promise or commitment made during the meeting."""

    description: str
    owner: CommitmentOwner
    party_name: str | None = Field(None, description="Name of person who committed")
    deadline_hint: str | None = None


class Objection(BaseModel):
    """An objection or concern raised during the meeting."""

    description: str
    raised_by: str | None = None
    addressed: bool = False
    resolution: str | None = None


class SentimentShift(BaseModel):
    """A notable change in sentiment during the conversation."""

    timestamp_hint: str | None = Field(None, description="Approximate point in conversation")
    from_sentiment: str
    to_sentiment: str
    trigger: str = Field(..., description="What caused the shift")


class DecisionPoint(BaseModel):
    """A decision made or deferred during the meeting."""

    description: str
    decision: str | None = Field(None, description="What was decided, if resolved")
    status: str = Field("decided", description="decided | deferred | open")
    stakeholders: list[str] = Field(default_factory=list)


class MeetingAnalysis(BaseModel):
    """Full structured analysis of a meeting transcript."""

    meeting_id: str
    summary: str
    action_items: list[ActionItem] = Field(default_factory=list)
    commitments: list[Commitment] = Field(default_factory=list)
    objections: list[Objection] = Field(default_factory=list)
    sentiment_shifts: list[SentimentShift] = Field(default_factory=list)
    decision_points: list[DecisionPoint] = Field(default_factory=list)
    key_topics: list[str] = Field(default_factory=list)
    overall_sentiment: str = "neutral"
    participants_detected: list[str] = Field(default_factory=list)


class CoachingInsights(BaseModel):
    """Sales coaching insights derived from meeting dynamics."""

    talk_to_listen_ratio: float | None = Field(
        None, description="Ratio of rep talk time to prospect talk time"
    )
    question_count: int = 0
    open_question_count: int = 0
    closed_question_count: int = 0
    longest_monologue_seconds: float | None = None
    objection_handling_score: float | None = Field(
        None, ge=0, le=100, description="Effectiveness score 0-100"
    )
    recommendations: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    improvement_areas: list[str] = Field(default_factory=list)


# ── LLM prompts ──────────────────────────────────────────────────────────

_TRANSCRIPT_ANALYSIS_SYSTEM = """\
You are an expert sales meeting analyst for a Life Sciences commercial team.
You analyze meeting transcripts and extract structured intelligence.

You MUST return valid JSON matching the schema provided.  Do NOT wrap in
markdown code fences.  Return ONLY the JSON object."""

_TRANSCRIPT_ANALYSIS_PROMPT = """\
Analyze the following meeting transcript and extract structured intelligence.

Return a JSON object with these fields:
- "summary": A concise 2-3 sentence summary of the meeting.
- "action_items": Array of {{"description": str, "assignee": str|null, \
"due_hint": str|null, "priority": "low"|"medium"|"high"}}
- "commitments": Array of {{"description": str, "owner": "ours"|"theirs", \
"party_name": str|null, "deadline_hint": str|null}}
- "objections": Array of {{"description": str, "raised_by": str|null, \
"addressed": bool, "resolution": str|null}}
- "sentiment_shifts": Array of {{"timestamp_hint": str|null, \
"from_sentiment": str, "to_sentiment": str, "trigger": str}}
- "decision_points": Array of {{"description": str, "decision": str|null, \
"status": "decided"|"deferred"|"open", "stakeholders": [str]}}
- "key_topics": Array of short topic labels.
- "overall_sentiment": "positive"|"neutral"|"negative"|"mixed"
- "participants_detected": Array of participant names found in transcript.

TRANSCRIPT:
{transcript}"""

_COACHING_SYSTEM = """\
You are an expert sales coach for Life Sciences commercial teams.
Analyze meeting dynamics and provide actionable coaching insights.

You MUST return valid JSON matching the schema provided.  Do NOT wrap in
markdown code fences.  Return ONLY the JSON object."""

_COACHING_PROMPT = """\
Based on the following meeting analysis, generate sales coaching insights.

Focus on:
1. Talk-to-listen ratio estimation (from participant balance)
2. Question patterns (open vs closed questions asked by the rep)
3. Objection handling effectiveness
4. Strengths demonstrated
5. Specific improvement recommendations

Return a JSON object:
- "talk_to_listen_ratio": float|null (e.g. 1.5 means rep talked 1.5x more)
- "question_count": int
- "open_question_count": int
- "closed_question_count": int
- "longest_monologue_seconds": float|null
- "objection_handling_score": float|null (0-100)
- "recommendations": [str] — specific, actionable coaching tips
- "strengths": [str] — what the rep did well
- "improvement_areas": [str] — areas to work on

MEETING ANALYSIS:
{analysis}"""

_CRM_SUMMARY_SYSTEM = """\
You are a concise CRM note writer for a Life Sciences sales team.
Write professional, scannable meeting summaries suitable for a CRM activity log.
Keep it under 500 words.  Use bullet points for action items and next steps."""

_CRM_SUMMARY_PROMPT = """\
Write a CRM-ready meeting summary from the following analysis.

Include:
- Meeting outcome (1 sentence)
- Key discussion points (bullets)
- Decisions made
- Action items with owners
- Next steps
- Any risks or concerns

MEETING ANALYSIS:
{analysis}"""


# ── Capability ───────────────────────────────────────────────────────────


class MeetingIntelligenceCapability(BaseCapability):
    """Meeting intelligence: transcript analysis, coaching, CRM summaries.

    Processes raw meeting transcripts through LLM-powered extraction to
    surface action items, commitments, objections, sentiment shifts, and
    decision points.  Generates coaching insights and CRM-ready summaries.

    Designed for AnalystAgent (deep analysis) and ScribeAgent (note-taking).
    """

    capability_name: str = "meeting-intelligence"
    agent_types: list[str] = ["AnalystAgent", "ScribeAgent"]
    oauth_scopes: list[str] = []
    data_classes: list[str] = ["INTERNAL", "CONFIDENTIAL"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._llm = LLMClient()

    # ── BaseCapability abstract interface ──────────────────────────────

    async def can_handle(self, task: dict[str, Any]) -> float:
        """Return confidence for meeting-intelligence tasks."""
        task_type = task.get("type", "")
        if task_type in {
            "process_transcript",
            "generate_coaching",
            "auto_generate_crm_summary",
        }:
            return 0.95
        if "transcript" in task_type.lower() or "debrief" in task_type.lower():
            return 0.7
        if "meeting" in task_type.lower():
            return 0.5
        return 0.0

    async def execute(
        self,
        task: dict[str, Any],
        context: dict[str, Any],  # noqa: ARG002
    ) -> CapabilityResult:
        """Route to the correct method based on task type."""
        start = time.monotonic()
        user_id = self._user_context.user_id
        task_type = task.get("type", "")

        try:
            if task_type == "process_transcript":
                transcript_text = task.get("transcript_text", "")
                meeting_id = task.get("meeting_id", str(uuid.uuid4()))
                lead_id = task.get("lead_id")
                analysis = await self.process_transcript(
                    transcript_text,
                    meeting_id,
                    lead_id=lead_id,
                )
                data: dict[str, Any] = {
                    "analysis": analysis.model_dump(),
                    "meeting_id": meeting_id,
                }

            elif task_type == "generate_coaching":
                analysis_data = task.get("analysis", {})
                analysis = MeetingAnalysis(**analysis_data)
                coaching = await self.generate_coaching(analysis)
                data = {"coaching": coaching.model_dump()}

            elif task_type == "auto_generate_crm_summary":
                analysis_data = task.get("analysis", {})
                analysis = MeetingAnalysis(**analysis_data)
                lead_id = task.get("lead_id")
                summary = await self.auto_generate_crm_summary(
                    analysis,
                    lead_id=lead_id,
                )
                data = {"crm_summary": summary, "meeting_id": analysis.meeting_id}

            else:
                return CapabilityResult(
                    success=False,
                    error=f"Unknown task type: {task_type}",
                    execution_time_ms=int((time.monotonic() - start) * 1000),
                )

            elapsed = int((time.monotonic() - start) * 1000)
            return CapabilityResult(success=True, data=data, execution_time_ms=elapsed)

        except Exception as exc:
            elapsed = int((time.monotonic() - start) * 1000)
            logger.exception(
                "Meeting intelligence task failed",
                extra={"user_id": user_id, "task_type": task_type},
            )
            return CapabilityResult(
                success=False,
                error=str(exc),
                execution_time_ms=elapsed,
            )

    def get_data_classes_accessed(self) -> list[str]:
        """Meeting transcripts contain internal and confidential data."""
        return ["internal", "confidential"]

    # ── Public methods ─────────────────────────────────────────────────

    async def process_transcript(
        self,
        transcript_text: str,
        meeting_id: str,
        *,
        lead_id: str | None = None,
    ) -> MeetingAnalysis:
        """Analyze a raw transcript and extract structured intelligence.

        Calls the LLM to extract action items, commitments, objections,
        sentiment shifts, and decision points.  Persists results:
        - Action items → ``prospective_memories`` (future tasks)
        - Commitments → ``lead_memory_events``
        - Updates ``lead_memories.last_activity_at``
        - Stores insights in ``meeting_debriefs.insights``

        Args:
            transcript_text: Raw meeting transcript text.
            meeting_id: Identifier for the meeting (calendar event ID or UUID).
            lead_id: Optional lead_memory ID to link results to.

        Returns:
            Structured MeetingAnalysis with all extracted intelligence.
        """
        user_id = self._user_context.user_id

        # ── 1. LLM extraction ────────────────────────────────────────
        prompt = _TRANSCRIPT_ANALYSIS_PROMPT.format(transcript=transcript_text)
        raw_response = await self._llm.generate_response(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=_TRANSCRIPT_ANALYSIS_SYSTEM,
            max_tokens=4096,
            temperature=0.3,
        )

        parsed = _parse_json_response(raw_response)
        analysis = MeetingAnalysis(meeting_id=meeting_id, **parsed)

        # ── 2. Resolve lead_id from attendees if not provided ────────
        if not lead_id and analysis.participants_detected:
            lead_id = await self._find_linked_lead(
                user_id,
                analysis.participants_detected,
            )

        # ── 3. Persist action items → prospective_memories ───────────
        await self._write_action_items(user_id, meeting_id, analysis.action_items)

        # ── 4. Persist commitments → lead_memory_events ──────────────
        if lead_id:
            await self._write_commitments(
                user_id,
                lead_id,
                meeting_id,
                analysis.commitments,
            )
            await self._update_lead_last_activity(lead_id)

        # ── 5. Store insights in meeting_debriefs ────────────────────
        await self._store_debrief_insights(user_id, meeting_id, analysis)

        # ── 6. Activity log ──────────────────────────────────────────
        await self.log_activity(
            activity_type="transcript_analyzed",
            title=f"Meeting transcript analyzed: {meeting_id}",
            description=(
                f"Extracted {len(analysis.action_items)} action items, "
                f"{len(analysis.commitments)} commitments, "
                f"{len(analysis.objections)} objections, "
                f"{len(analysis.decision_points)} decisions"
            ),
            confidence=0.85,
            related_entity_type="lead" if lead_id else None,
            related_entity_id=lead_id,
            metadata={
                "meeting_id": meeting_id,
                "action_item_count": len(analysis.action_items),
                "commitment_count": len(analysis.commitments),
                "objection_count": len(analysis.objections),
                "decision_count": len(analysis.decision_points),
                "overall_sentiment": analysis.overall_sentiment,
                "linked_lead_id": lead_id,
            },
        )

        return analysis

    async def generate_coaching(
        self,
        analysis: MeetingAnalysis,
    ) -> CoachingInsights:
        """Generate sales coaching insights from a meeting analysis.

        Evaluates talk-to-listen ratio, question patterns, objection
        handling effectiveness and produces actionable recommendations.
        Stores insights in the corresponding ``meeting_debriefs`` row.

        Args:
            analysis: Previously extracted MeetingAnalysis.

        Returns:
            CoachingInsights with scores and recommendations.
        """
        user_id = self._user_context.user_id
        analysis_json = analysis.model_dump_json()

        prompt = _COACHING_PROMPT.format(analysis=analysis_json)
        raw_response = await self._llm.generate_response(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=_COACHING_SYSTEM,
            max_tokens=2048,
            temperature=0.4,
        )

        parsed = _parse_json_response(raw_response)
        coaching = CoachingInsights(**parsed)

        # Persist coaching into meeting_debriefs.insights
        await self._store_coaching_insights(
            user_id,
            analysis.meeting_id,
            coaching,
        )

        await self.log_activity(
            activity_type="coaching_generated",
            title=f"Coaching insights generated: {analysis.meeting_id}",
            description=(
                f"Objection handling score: {coaching.objection_handling_score}, "
                f"{len(coaching.recommendations)} recommendations"
            ),
            confidence=0.80,
            metadata={
                "meeting_id": analysis.meeting_id,
                "talk_to_listen_ratio": coaching.talk_to_listen_ratio,
                "objection_handling_score": coaching.objection_handling_score,
                "recommendation_count": len(coaching.recommendations),
            },
        )

        return coaching

    async def auto_generate_crm_summary(
        self,
        analysis: MeetingAnalysis,
        *,
        lead_id: str | None = None,
    ) -> str:
        """Create a CRM-ready meeting summary and queue for push.

        Generates a professional, scannable summary suitable for CRM
        activity logs and queues it in ``integration_push_queue`` for
        automatic CRM synchronisation.

        Args:
            analysis: Previously extracted MeetingAnalysis.
            lead_id: Optional lead_memory ID for CRM association.

        Returns:
            The generated CRM summary text.
        """
        user_id = self._user_context.user_id
        analysis_json = analysis.model_dump_json()

        prompt = _CRM_SUMMARY_PROMPT.format(analysis=analysis_json)
        summary = await self._llm.generate_response(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=_CRM_SUMMARY_SYSTEM,
            max_tokens=1024,
            temperature=0.3,
        )

        # Queue for CRM push
        await self._queue_crm_push(
            user_id,
            analysis.meeting_id,
            summary,
            lead_id=lead_id,
        )

        await self.log_activity(
            activity_type="crm_summary_generated",
            title=f"CRM summary generated: {analysis.meeting_id}",
            description="Meeting summary queued for CRM push",
            confidence=0.85,
            related_entity_type="lead" if lead_id else None,
            related_entity_id=lead_id,
            metadata={
                "meeting_id": analysis.meeting_id,
                "summary_length": len(summary),
                "linked_lead_id": lead_id,
            },
        )

        return summary

    # ── Private helpers ────────────────────────────────────────────────

    async def _write_action_items(
        self,
        user_id: str,
        meeting_id: str,
        action_items: list[ActionItem],
    ) -> None:
        """Write action items as prospective memory entries (future tasks).

        Args:
            user_id: Authenticated user UUID.
            meeting_id: Source meeting identifier.
            action_items: Extracted action items to persist.
        """
        if not action_items:
            return

        client = SupabaseClient.get_client()
        now = datetime.now(UTC)

        rows = []
        for item in action_items:
            rows.append(
                {
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "memory_type": "task",
                    "title": item.description,
                    "description": item.description,
                    "priority": item.priority,
                    "status": "pending",
                    "source": "meeting_transcript",
                    "source_id": meeting_id,
                    "metadata": {
                        "assignee": item.assignee,
                        "due_hint": item.due_hint,
                        "meeting_id": meeting_id,
                    },
                    "created_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                }
            )

        try:
            client.table("prospective_memories").insert(rows).execute()
            logger.info(
                "Wrote action items to prospective_memories",
                extra={
                    "user_id": user_id,
                    "meeting_id": meeting_id,
                    "count": len(rows),
                },
            )
        except Exception:
            logger.exception(
                "Failed to write action items to prospective_memories",
                extra={"user_id": user_id, "meeting_id": meeting_id},
            )

    async def _write_commitments(
        self,
        user_id: str,
        lead_id: str,
        meeting_id: str,
        commitments: list[Commitment],
    ) -> None:
        """Write commitments as lead_memory_events.

        Args:
            user_id: Authenticated user UUID.
            lead_id: Associated lead_memory UUID.
            meeting_id: Source meeting identifier.
            commitments: Extracted commitments to persist.
        """
        if not commitments:
            return

        client = SupabaseClient.get_client()
        now = datetime.now(UTC)

        rows = []
        for commitment in commitments:
            direction = "outbound" if commitment.owner == CommitmentOwner.OURS else "inbound"
            rows.append(
                {
                    "id": str(uuid.uuid4()),
                    "lead_memory_id": lead_id,
                    "event_type": "meeting",
                    "direction": direction,
                    "subject": f"Commitment: {commitment.description[:120]}",
                    "content": json.dumps(
                        {
                            "type": "commitment",
                            "description": commitment.description,
                            "owner": commitment.owner.value,
                            "party_name": commitment.party_name,
                            "deadline_hint": commitment.deadline_hint,
                            "meeting_id": meeting_id,
                        }
                    ),
                    "participants": [commitment.party_name] if commitment.party_name else [],
                    "occurred_at": now.isoformat(),
                    "source": "meeting_transcript",
                    "source_id": meeting_id,
                    "created_at": now.isoformat(),
                }
            )

        try:
            client.table("lead_memory_events").insert(rows).execute()
            logger.info(
                "Wrote commitments to lead_memory_events",
                extra={
                    "user_id": user_id,
                    "lead_id": lead_id,
                    "meeting_id": meeting_id,
                    "count": len(rows),
                },
            )
        except Exception:
            logger.exception(
                "Failed to write commitments to lead_memory_events",
                extra={"user_id": user_id, "lead_id": lead_id},
            )

    async def _update_lead_last_activity(self, lead_id: str) -> None:
        """Touch lead_memories.last_activity_at for the linked lead.

        Args:
            lead_id: lead_memory UUID to update.
        """
        client = SupabaseClient.get_client()
        now = datetime.now(UTC)

        try:
            client.table("lead_memories").update(
                {"last_activity_at": now.isoformat(), "updated_at": now.isoformat()},
            ).eq("id", lead_id).execute()
        except Exception:
            logger.warning(
                "Failed to update lead_memories.last_activity_at",
                extra={"lead_id": lead_id},
                exc_info=True,
            )

    async def _store_debrief_insights(
        self,
        user_id: str,
        meeting_id: str,
        analysis: MeetingAnalysis,
    ) -> None:
        """Upsert analysis insights into the meeting_debriefs row.

        If a debrief row already exists for this meeting, updates the
        ``insights`` column.  Otherwise creates a new row.

        Args:
            user_id: Authenticated user UUID.
            meeting_id: Meeting identifier.
            analysis: Full meeting analysis to store.
        """
        client = SupabaseClient.get_client()
        now = datetime.now(UTC)

        insights_payload = {
            "summary": analysis.summary,
            "action_items": [a.model_dump() for a in analysis.action_items],
            "commitments": [c.model_dump() for c in analysis.commitments],
            "objections": [o.model_dump() for o in analysis.objections],
            "sentiment_shifts": [s.model_dump() for s in analysis.sentiment_shifts],
            "decision_points": [d.model_dump() for d in analysis.decision_points],
            "key_topics": analysis.key_topics,
            "overall_sentiment": analysis.overall_sentiment,
            "participants": analysis.participants_detected,
        }

        try:
            existing = (
                client.table("meeting_debriefs")
                .select("id")
                .eq("user_id", user_id)
                .eq("meeting_id", meeting_id)
                .maybe_single()
                .execute()
            )

            if existing.data:
                client.table("meeting_debriefs").update(
                    {"insights": insights_payload, "updated_at": now.isoformat()},
                ).eq("id", existing.data["id"]).execute()
            else:
                client.table("meeting_debriefs").insert(
                    {
                        "id": str(uuid.uuid4()),
                        "user_id": user_id,
                        "meeting_id": meeting_id,
                        "meeting_title": analysis.summary[:120],
                        "meeting_time": now.isoformat(),
                        "outcome": analysis.overall_sentiment,
                        "insights": insights_payload,
                        "follow_up_needed": len(analysis.action_items) > 0,
                        "created_at": now.isoformat(),
                    }
                ).execute()

        except Exception:
            logger.exception(
                "Failed to store debrief insights",
                extra={"user_id": user_id, "meeting_id": meeting_id},
            )

    async def _store_coaching_insights(
        self,
        user_id: str,
        meeting_id: str,
        coaching: CoachingInsights,
    ) -> None:
        """Merge coaching insights into the meeting_debriefs row.

        Args:
            user_id: Authenticated user UUID.
            meeting_id: Meeting identifier.
            coaching: Generated coaching insights.
        """
        client = SupabaseClient.get_client()
        now = datetime.now(UTC)

        try:
            existing = (
                client.table("meeting_debriefs")
                .select("id, insights")
                .eq("user_id", user_id)
                .eq("meeting_id", meeting_id)
                .maybe_single()
                .execute()
            )

            if existing.data:
                current_insights = existing.data.get("insights") or {}
                current_insights["coaching"] = coaching.model_dump()
                client.table("meeting_debriefs").update(
                    {"insights": current_insights, "updated_at": now.isoformat()},
                ).eq("id", existing.data["id"]).execute()
            else:
                logger.warning(
                    "No meeting_debriefs row to store coaching; creating one",
                    extra={"user_id": user_id, "meeting_id": meeting_id},
                )
                client.table("meeting_debriefs").insert(
                    {
                        "id": str(uuid.uuid4()),
                        "user_id": user_id,
                        "meeting_id": meeting_id,
                        "meeting_title": meeting_id,
                        "meeting_time": now.isoformat(),
                        "outcome": "neutral",
                        "insights": {"coaching": coaching.model_dump()},
                        "follow_up_needed": False,
                        "created_at": now.isoformat(),
                    }
                ).execute()

        except Exception:
            logger.exception(
                "Failed to store coaching insights",
                extra={"user_id": user_id, "meeting_id": meeting_id},
            )

    async def _queue_crm_push(
        self,
        user_id: str,
        meeting_id: str,
        summary: str,
        *,
        lead_id: str | None = None,
    ) -> None:
        """Queue the CRM summary for push via integration_push_queue.

        Args:
            user_id: Authenticated user UUID.
            meeting_id: Meeting identifier.
            summary: Generated CRM summary text.
            lead_id: Optional lead_memory ID for CRM association.
        """
        client = SupabaseClient.get_client()
        now = datetime.now(UTC)

        row = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "push_type": "meeting_summary",
            "entity_type": "meeting",
            "entity_id": meeting_id,
            "payload": {
                "summary": summary,
                "meeting_id": meeting_id,
                "lead_id": lead_id,
            },
            "status": "pending",
            "created_at": now.isoformat(),
        }

        try:
            client.table("integration_push_queue").insert(row).execute()
            logger.info(
                "CRM summary queued for push",
                extra={
                    "user_id": user_id,
                    "meeting_id": meeting_id,
                    "lead_id": lead_id,
                },
            )
        except Exception:
            logger.exception(
                "Failed to queue CRM summary for push",
                extra={"user_id": user_id, "meeting_id": meeting_id},
            )

    async def _find_linked_lead(
        self,
        user_id: str,
        participant_names: list[str],
    ) -> str | None:
        """Try to match participant names to an existing lead_memory.

        Searches lead_memories by company_name partial match against
        detected participant names as a heuristic.

        Args:
            user_id: Authenticated user UUID.
            participant_names: Detected participant names from transcript.

        Returns:
            lead_memory UUID if a match is found, else None.
        """
        if not participant_names:
            return None

        client = SupabaseClient.get_client()
        for name in participant_names:
            try:
                resp = (
                    client.table("lead_memories")
                    .select("id")
                    .eq("user_id", user_id)
                    .ilike("company_name", f"%{name}%")
                    .limit(1)
                    .execute()
                )
                if resp.data:
                    return str(resp.data[0]["id"])
            except Exception:
                continue
        return None


# ── Module-level helpers ──────────────────────────────────────────────────


def _parse_json_response(raw: str) -> dict[str, Any]:
    """Parse LLM JSON response, stripping markdown fences if present.

    Args:
        raw: Raw text from LLM that should be JSON.

    Returns:
        Parsed dictionary.

    Raises:
        ValueError: If response cannot be parsed as JSON.
    """
    text = raw.strip()

    # Strip markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json) and last line (```)
        lines = [line for line in lines if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        return dict(json.loads(text))
    except json.JSONDecodeError as exc:
        logger.warning(
            "Failed to parse LLM JSON response",
            extra={"raw_length": len(raw), "first_100": raw[:100]},
        )
        raise ValueError(f"LLM response is not valid JSON: {exc}") from exc
