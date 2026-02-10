"""Skill Discovery Agent for ARIA.

Background service that analyzes user behavior to identify skill gaps
and recommends marketplace skills to fill them. Runs weekly or on-demand.

Pipeline:
1. analyze_usage_gaps — query execution plans, conversations, activity
2. search_marketplace — match gaps to skills_index entries
3. recommend — generate natural language recommendations, notify user

Usage::

    agent = SkillDiscoveryAgent()
    recommendations = await agent.run_on_demand(user_id="...")
    # Or scheduled:
    recommendations = await agent.run_weekly(user_id="...")
"""

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from src.core.llm import LLMClient
from src.db.supabase import SupabaseClient
from src.security.trust_levels import TRUST_DATA_ACCESS, SkillTrustLevel
from src.skills.index import SkillIndex, SkillIndexEntry

logger = logging.getLogger(__name__)

# Deduplication window — skip gaps that already have a recent recommendation
DEDUP_WINDOW_DAYS = 7

# Maximum recommendations per gap
MAX_SKILLS_PER_GAP = 5

# Scoring weights for marketplace ranking
WEIGHT_RELEVANCE = 0.40
WEIGHT_SECURITY = 0.25
WEIGHT_COMMUNITY = 0.20
WEIGHT_LIFE_SCIENCES = 0.15

# Thresholds for gap detection queries
SLOW_EXECUTION_THRESHOLD_MS = 30_000  # 30 seconds
MAX_GAPS_PER_RUN = 10
MAX_EVIDENCE_ROWS = 50


@dataclass
class GapReport:
    """An identified usage gap where ARIA is underserving the user.

    Attributes:
        user_id: The user this gap belongs to.
        gap_type: Category of gap detected.
        description: LLM-generated human-readable summary.
        evidence: Source rows from queries (execution plans, conversations, activity).
        frequency: How many times this gap was observed.
        last_seen: Most recent occurrence.
        keywords: Extracted search terms for marketplace matching.
    """

    user_id: str
    gap_type: str  # "slow_execution" | "failed_task" | "unhandled_request" | "manual_workaround"
    description: str
    evidence: list[dict[str, Any]] = field(default_factory=list)
    frequency: int = 1
    last_seen: datetime = field(default_factory=lambda: datetime.now(UTC))
    keywords: list[str] = field(default_factory=list)


@dataclass
class SkillRecommendation:
    """A marketplace skill scored against a usage gap.

    Attributes:
        skill: The skill entry from the index.
        relevance_score: 0.0-1.0 keyword match to the gap.
        trust_level: Security trust classification.
        data_access: What data classes this skill requires.
        life_sciences_relevant: Whether the skill is tagged for life sciences.
        install_count: Community adoption signal.
        composite_score: Weighted final score used for ranking.
    """

    skill: SkillIndexEntry
    relevance_score: float
    trust_level: SkillTrustLevel
    data_access: list[str]
    life_sciences_relevant: bool
    install_count: int | None = None
    composite_score: float = 0.0


@dataclass
class Recommendation:
    """A complete recommendation: gap + matched skills + message.

    Attributes:
        gap: The usage gap this recommendation addresses.
        skills: Top marketplace skill matches, ranked by composite score.
        message: LLM-generated conversational recommendation text.
        created_at: When this recommendation was generated.
    """

    gap: GapReport
    skills: list[SkillRecommendation]
    message: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class SkillDiscoveryAgent:
    """Background service for skill gap analysis and recommendation.

    Analyzes user behavior across execution plans, conversations, and
    activity to identify unmet needs, then searches the skills marketplace
    for matching solutions.
    """

    def __init__(self) -> None:
        """Initialize the discovery agent."""
        self._client = SupabaseClient.get_client()
        self._skill_index = SkillIndex()
        self._llm = LLMClient()

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    async def run_weekly(self, user_id: str) -> list[Recommendation]:
        """Run the full discovery pipeline for a user (scheduler entry).

        Args:
            user_id: The user to analyze.

        Returns:
            List of recommendations generated and delivered.
        """
        logger.info("Running weekly skill discovery", extra={"user_id": user_id})
        return await self._run_pipeline(user_id)

    async def run_on_demand(self, user_id: str) -> list[Recommendation]:
        """Run the full discovery pipeline on demand (API entry).

        Args:
            user_id: The user to analyze.

        Returns:
            List of recommendations generated and delivered.
        """
        logger.info("Running on-demand skill discovery", extra={"user_id": user_id})
        return await self._run_pipeline(user_id)

    async def refresh_index(self) -> int:
        """Refresh skills_index from skills.sh API.

        Returns:
            Number of skills synced.
        """
        logger.info("Refreshing skills index from skills.sh")
        return await self._skill_index.sync_from_skills_sh()

    # ------------------------------------------------------------------
    # Core pipeline
    # ------------------------------------------------------------------

    async def _run_pipeline(self, user_id: str) -> list[Recommendation]:
        """Execute the full gap-analysis-to-recommendation pipeline.

        Args:
            user_id: The user to analyze.

        Returns:
            List of delivered recommendations.
        """
        # Step 1: Detect gaps
        gaps = await self.analyze_usage_gaps(user_id)
        if not gaps:
            logger.info("No usage gaps detected", extra={"user_id": user_id})
            return []

        # Step 2: Search marketplace for each gap
        gap_matches: list[tuple[GapReport, list[SkillRecommendation]]] = []
        for gap in gaps:
            matches = await self.search_marketplace(gap)
            if matches:
                gap_matches.append((gap, matches))

        if not gap_matches:
            logger.info(
                "No marketplace matches found for gaps",
                extra={"user_id": user_id, "gap_count": len(gaps)},
            )
            return []

        # Step 3: Generate recommendations and deliver
        recommendations = await self.recommend(user_id, gap_matches)
        return recommendations

    # ------------------------------------------------------------------
    # Step 1: Gap analysis
    # ------------------------------------------------------------------

    async def analyze_usage_gaps(self, user_id: str) -> list[GapReport]:
        """Analyze user behavior to identify skill gaps.

        Queries execution plans, conversations, and activity to find
        patterns where ARIA is underperforming.

        Args:
            user_id: The user to analyze.

        Returns:
            Gap reports sorted by frequency descending.
        """
        raw_evidence: list[dict[str, Any]] = []

        # Query 1: Slow or failed execution plans
        failed_plans = await self._query_failed_executions(user_id)
        raw_evidence.extend(failed_plans)

        # Query 2: Unhandled conversation requests
        unhandled = await self._query_unhandled_requests(user_id)
        raw_evidence.extend(unhandled)

        # Query 3: Repeated manual workarounds
        workarounds = await self._query_manual_workarounds(user_id)
        raw_evidence.extend(workarounds)

        if not raw_evidence:
            return []

        # Synthesize evidence into structured gap reports via LLM
        gaps = await self._synthesize_gaps(user_id, raw_evidence)
        return gaps

    async def _query_failed_executions(self, user_id: str) -> list[dict[str, Any]]:
        """Query skill_execution_plans for failed or slow executions.

        Args:
            user_id: The user to query.

        Returns:
            Evidence rows with source type annotation.
        """
        evidence: list[dict[str, Any]] = []
        cutoff = (datetime.now(UTC) - timedelta(days=30)).isoformat()

        try:
            # Failed plans
            failed_resp = (
                self._client.table("skill_execution_plans")
                .select("id,plan_dag,risk_level,status,created_at")
                .eq("user_id", user_id)
                .eq("status", "failed")
                .gte("created_at", cutoff)
                .order("created_at", desc=True)
                .limit(MAX_EVIDENCE_ROWS)
                .execute()
            )
            for row in failed_resp.data or []:
                evidence.append(
                    {
                        "source": "failed_task",
                        "plan_id": row["id"],
                        "plan_dag": row.get("plan_dag"),
                        "risk_level": row.get("risk_level"),
                        "created_at": row.get("created_at"),
                    }
                )

            # Slow plans (completed but took too long)
            slow_resp = (
                self._client.table("skill_execution_plans")
                .select("id,plan_dag,risk_level,status,created_at,updated_at")
                .eq("user_id", user_id)
                .eq("status", "completed")
                .gte("created_at", cutoff)
                .order("created_at", desc=True)
                .limit(MAX_EVIDENCE_ROWS)
                .execute()
            )
            for row in slow_resp.data or []:
                # Estimate execution time from created_at to updated_at
                created = row.get("created_at", "")
                updated = row.get("updated_at", "")
                if created and updated:
                    try:
                        t_start = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
                        t_end = datetime.fromisoformat(str(updated).replace("Z", "+00:00"))
                        duration_ms = (t_end - t_start).total_seconds() * 1000
                        if duration_ms > SLOW_EXECUTION_THRESHOLD_MS:
                            evidence.append(
                                {
                                    "source": "slow_execution",
                                    "plan_id": row["id"],
                                    "plan_dag": row.get("plan_dag"),
                                    "duration_ms": duration_ms,
                                    "created_at": created,
                                }
                            )
                    except (ValueError, TypeError):
                        pass

        except Exception as e:
            logger.warning("Error querying execution plans: %s", e)

        return evidence

    async def _query_unhandled_requests(self, user_id: str) -> list[dict[str, Any]]:
        """Query messages for conversations where ARIA couldn't fully help.

        Args:
            user_id: The user to query.

        Returns:
            Evidence rows with source type annotation.
        """
        evidence: list[dict[str, Any]] = []
        cutoff = (datetime.now(UTC) - timedelta(days=30)).isoformat()

        try:
            resp = (
                self._client.table("messages")
                .select("id,content,role,created_at")
                .eq("user_id", user_id)
                .eq("role", "user")
                .gte("created_at", cutoff)
                .order("created_at", desc=True)
                .limit(MAX_EVIDENCE_ROWS)
                .execute()
            )
            for row in resp.data or []:
                evidence.append(
                    {
                        "source": "unhandled_request",
                        "message_id": row["id"],
                        "content": row.get("content", "")[:500],  # Truncate for LLM context
                        "created_at": row.get("created_at"),
                    }
                )

        except Exception as e:
            logger.warning("Error querying messages: %s", e)

        return evidence

    async def _query_manual_workarounds(self, user_id: str) -> list[dict[str, Any]]:
        """Query aria_activity for repeated manual patterns.

        Args:
            user_id: The user to query.

        Returns:
            Evidence rows with source type annotation.
        """
        evidence: list[dict[str, Any]] = []
        cutoff = (datetime.now(UTC) - timedelta(days=30)).isoformat()

        try:
            resp = (
                self._client.table("aria_activity")
                .select("id,activity_type,title,metadata,created_at")
                .eq("user_id", user_id)
                .gte("created_at", cutoff)
                .order("created_at", desc=True)
                .limit(MAX_EVIDENCE_ROWS)
                .execute()
            )

            # Group by activity_type to find repetitive patterns
            type_counts: dict[str, list[dict[str, Any]]] = {}
            for row in resp.data or []:
                activity_type = row.get("activity_type", "unknown")
                if activity_type not in type_counts:
                    type_counts[activity_type] = []
                type_counts[activity_type].append(row)

            # Only include types that occur 3+ times (indicates manual repetition)
            for activity_type, rows in type_counts.items():
                if len(rows) >= 3:
                    evidence.append(
                        {
                            "source": "manual_workaround",
                            "activity_type": activity_type,
                            "frequency": len(rows),
                            "sample_titles": [r.get("title", "") for r in rows[:3]],
                            "last_seen": rows[0].get("created_at"),
                        }
                    )

        except Exception as e:
            logger.warning("Error querying activity: %s", e)

        return evidence

    async def _synthesize_gaps(
        self,
        user_id: str,
        evidence: list[dict[str, Any]],
    ) -> list[GapReport]:
        """Use LLM to synthesize raw evidence into structured gap reports.

        Args:
            user_id: The user these gaps belong to.
            evidence: Combined evidence from all query sources.

        Returns:
            Structured gap reports with keywords for marketplace search.
        """
        system_prompt = (
            "You are ARIA's Skill Discovery Agent. Analyze the following user behavior "
            "evidence to identify skill gaps — areas where the user needs help that "
            "existing skills don't adequately address.\n\n"
            "For each gap you identify, provide:\n"
            "- gap_type: one of 'slow_execution', 'failed_task', 'unhandled_request', "
            "'manual_workaround'\n"
            "- description: A clear, specific description of the unmet need\n"
            "- frequency: How many evidence items support this gap\n"
            "- keywords: 3-5 search terms to find skills that address this gap "
            "(e.g., 'clinical trials', 'competitor monitoring', 'patent search')\n\n"
            "Merge related evidence into a single gap when appropriate. "
            "Return at most 10 gaps, ranked by frequency and severity.\n\n"
            'Return valid JSON: {"gaps": [{"gap_type": ..., "description": ..., '
            '"frequency": ..., "keywords": [...]}]}'
        )

        # Truncate evidence to fit context
        evidence_text = json.dumps(evidence[:MAX_EVIDENCE_ROWS], default=str)

        try:
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": f"Evidence:\n{evidence_text}"}],
                system_prompt=system_prompt,
                max_tokens=2048,
                temperature=0.3,
            )

            parsed = json.loads(response)
            gap_list = parsed.get("gaps", [])

            reports: list[GapReport] = []
            for gap_data in gap_list[:MAX_GAPS_PER_RUN]:
                reports.append(
                    GapReport(
                        user_id=user_id,
                        gap_type=gap_data.get("gap_type", "unhandled_request"),
                        description=gap_data.get("description", ""),
                        evidence=evidence,
                        frequency=gap_data.get("frequency", 1),
                        last_seen=datetime.now(UTC),
                        keywords=gap_data.get("keywords", []),
                    )
                )

            reports.sort(key=lambda g: g.frequency, reverse=True)
            return reports

        except (json.JSONDecodeError, KeyError) as e:
            logger.error("Failed to parse LLM gap synthesis response: %s", e)
            return []
        except Exception as e:
            logger.error("LLM gap synthesis failed: %s", e)
            return []

    # ------------------------------------------------------------------
    # Step 2: Marketplace search
    # ------------------------------------------------------------------

    async def search_marketplace(self, gap: GapReport) -> list[SkillRecommendation]:
        """Search the skills marketplace for skills that match a gap.

        Uses gap keywords to search the skills index, then scores and
        ranks candidates by relevance, security, community adoption,
        and life sciences relevance.

        Args:
            gap: The usage gap to find skills for.

        Returns:
            Skill recommendations sorted by composite score, max 5 per gap.
        """
        if not gap.keywords:
            return []

        # Search across all keywords, deduplicate
        seen_ids: set[str] = set()
        candidates: list[SkillIndexEntry] = []

        for keyword in gap.keywords:
            results = await self._skill_index.search(keyword, limit=20)
            for entry in results:
                if entry.id not in seen_ids:
                    seen_ids.add(entry.id)
                    candidates.append(entry)

        if not candidates:
            return []

        # Score each candidate
        recommendations: list[SkillRecommendation] = []
        for skill in candidates:
            relevance = self._compute_relevance(gap, skill)
            security = self._compute_security_score(skill)
            community = self._compute_community_score(skill)
            ls_bonus = 1.0 if skill.life_sciences_relevant else 0.0

            composite = (
                WEIGHT_RELEVANCE * relevance
                + WEIGHT_SECURITY * security
                + WEIGHT_COMMUNITY * community
                + WEIGHT_LIFE_SCIENCES * ls_bonus
            )

            # Get data access classes for this trust level
            allowed_classes = TRUST_DATA_ACCESS.get(skill.trust_level, [])

            recommendations.append(
                SkillRecommendation(
                    skill=skill,
                    relevance_score=relevance,
                    trust_level=skill.trust_level,
                    data_access=[dc.value for dc in allowed_classes],
                    life_sciences_relevant=skill.life_sciences_relevant,
                    install_count=None,  # Populated below if available
                    composite_score=composite,
                )
            )

        # Fetch install counts from skills_index for community context
        await self._populate_install_counts(recommendations)

        # Sort by composite score and return top N
        recommendations.sort(key=lambda r: r.composite_score, reverse=True)
        return recommendations[:MAX_SKILLS_PER_GAP]

    @staticmethod
    def _compute_relevance(gap: GapReport, skill: SkillIndexEntry) -> float:
        """Score keyword overlap between gap and skill.

        Args:
            gap: The gap with keywords.
            skill: The skill to score.

        Returns:
            Float in [0.0, 1.0].
        """
        if not gap.keywords:
            return 0.0

        searchable = f"{skill.skill_name} {skill.description or ''}"
        searchable_lower = searchable.lower()

        # Also include tags
        tag_text = " ".join(skill.tags).lower()
        searchable_lower = f"{searchable_lower} {tag_text}"

        matches = sum(1 for kw in gap.keywords if kw.lower() in searchable_lower)
        return min(matches / len(gap.keywords), 1.0)

    @staticmethod
    def _compute_security_score(skill: SkillIndexEntry) -> float:
        """Score a skill's security posture.

        CORE and VERIFIED skills score highest. COMMUNITY skills that
        only need PUBLIC data score moderately. Skills requesting
        sensitive data score low.

        Args:
            skill: The skill to evaluate.

        Returns:
            Float in [0.0, 1.0].
        """
        trust_scores: dict[SkillTrustLevel, float] = {
            SkillTrustLevel.CORE: 1.0,
            SkillTrustLevel.VERIFIED: 0.9,
            SkillTrustLevel.USER: 0.6,
            SkillTrustLevel.COMMUNITY: 0.4,
        }
        base = trust_scores.get(skill.trust_level, 0.3)

        # Penalize skills that declare broad permissions
        permission_count = len(skill.declared_permissions)
        if permission_count > 5:
            base *= 0.7
        elif permission_count > 3:
            base *= 0.85

        return base

    @staticmethod
    def _compute_community_score(_skill: SkillIndexEntry) -> float:
        """Score community adoption using a log scale.

        Returns 0.0 as a placeholder — actual community scores are
        computed in _populate_install_counts after fetching install_count
        from the database.

        Args:
            _skill: The skill to evaluate (unused here, resolved in populate step).

        Returns:
            Float in [0.0, 1.0].
        """
        return 0.0

    async def _populate_install_counts(self, recommendations: list[SkillRecommendation]) -> None:
        """Fetch install counts from skills_index and update recommendations.

        Args:
            recommendations: Recommendations to update in place.
        """
        if not recommendations:
            return

        skill_ids = [r.skill.id for r in recommendations]

        try:
            resp = (
                self._client.table("skills_index")
                .select("id,install_count")
                .in_("id", skill_ids)
                .execute()
            )
            count_map: dict[str, int] = {}
            max_count = 1
            for row in resp.data or []:
                count = row.get("install_count", 0) or 0
                count_map[str(row["id"])] = count
                if count > max_count:
                    max_count = count

            for rec in recommendations:
                raw_count = count_map.get(rec.skill.id, 0)
                rec.install_count = raw_count

                # Normalized log-scale community score
                community_score = (
                    math.log1p(raw_count) / math.log1p(max_count) if max_count > 0 else 0.0
                )

                # Recompute composite score with actual community data
                rec.composite_score = (
                    WEIGHT_RELEVANCE * rec.relevance_score
                    + WEIGHT_SECURITY * self._compute_security_score(rec.skill)
                    + WEIGHT_COMMUNITY * community_score
                    + WEIGHT_LIFE_SCIENCES * (1.0 if rec.life_sciences_relevant else 0.0)
                )

        except Exception as e:
            logger.warning("Failed to fetch install counts: %s", e)

    # ------------------------------------------------------------------
    # Step 3: Recommendation delivery
    # ------------------------------------------------------------------

    async def recommend(
        self,
        user_id: str,
        gap_matches: list[tuple[GapReport, list[SkillRecommendation]]] | None = None,
    ) -> list[Recommendation]:
        """Generate and deliver recommendations for a user.

        If gap_matches is None, runs the full pipeline (analyze + search).

        Args:
            user_id: The user to recommend to.
            gap_matches: Pre-computed gap-to-skill matches, or None to compute.

        Returns:
            List of recommendations that were delivered.
        """
        if gap_matches is None:
            gaps = await self.analyze_usage_gaps(user_id)
            gap_matches = []
            for gap in gaps:
                matches = await self.search_marketplace(gap)
                if matches:
                    gap_matches.append((gap, matches))

        if not gap_matches:
            return []

        # Filter out gaps with recent recommendations (deduplication)
        gap_matches = await self._filter_recent_recommendations(user_id, gap_matches)
        if not gap_matches:
            logger.info(
                "All gaps already have recent recommendations",
                extra={"user_id": user_id},
            )
            return []

        # Generate natural language messages via LLM
        messages = await self._generate_recommendation_messages(gap_matches)

        # Build and deliver recommendations
        recommendations: list[Recommendation] = []
        for i, (gap, skills) in enumerate(gap_matches):
            message = messages[i] if i < len(messages) else self._fallback_message(gap, skills)

            rec = Recommendation(
                gap=gap,
                skills=skills,
                message=message,
            )
            recommendations.append(rec)

            # Deliver notification
            await self._deliver_notification(user_id, rec)

            # Log to aria_activity for dashboard
            await self._log_activity(user_id, rec)

        logger.info(
            "Delivered skill recommendations",
            extra={"user_id": user_id, "count": len(recommendations)},
        )
        return recommendations

    async def _filter_recent_recommendations(
        self,
        user_id: str,
        gap_matches: list[tuple[GapReport, list[SkillRecommendation]]],
    ) -> list[tuple[GapReport, list[SkillRecommendation]]]:
        """Remove gaps that already have a recent recommendation.

        Args:
            user_id: The user to check.
            gap_matches: Gap-to-skill pairs to filter.

        Returns:
            Filtered list excluding recently-recommended gaps.
        """
        cutoff = (datetime.now(UTC) - timedelta(days=DEDUP_WINDOW_DAYS)).isoformat()

        try:
            resp = (
                self._client.table("aria_activity")
                .select("metadata")
                .eq("user_id", user_id)
                .eq("activity_type", "skill_recommendation")
                .gte("created_at", cutoff)
                .execute()
            )

            # Collect keywords from recent recommendations
            recent_keywords: set[str] = set()
            for row in resp.data or []:
                meta = row.get("metadata") or {}
                for kw in meta.get("gap_keywords", []):
                    recent_keywords.add(kw.lower())

            if not recent_keywords:
                return gap_matches

            # Filter out gaps whose keywords overlap significantly with recent recs
            filtered: list[tuple[GapReport, list[SkillRecommendation]]] = []
            for gap, skills in gap_matches:
                gap_kw_set = {kw.lower() for kw in gap.keywords}
                overlap = gap_kw_set & recent_keywords
                # If more than half the keywords were already recommended, skip
                if len(overlap) <= len(gap_kw_set) / 2:
                    filtered.append((gap, skills))

            return filtered

        except Exception as e:
            logger.warning("Failed to check recent recommendations: %s", e)
            return gap_matches

    async def _generate_recommendation_messages(
        self,
        gap_matches: list[tuple[GapReport, list[SkillRecommendation]]],
    ) -> list[str]:
        """Use LLM to generate conversational recommendation messages.

        Args:
            gap_matches: Gap-to-skill pairs to generate messages for.

        Returns:
            List of message strings, one per gap_match.
        """
        system_prompt = (
            "You are ARIA, an AI assistant for life sciences sales teams. "
            "Generate brief, conversational recommendation messages for your user. "
            "Each message should:\n"
            "1. Acknowledge the pattern you noticed (without being creepy)\n"
            "2. Name the specific skill you're recommending\n"
            "3. Explain what it does in one sentence\n"
            "4. State the data access level (e.g., 'PUBLIC data access only')\n"
            "5. End with a question inviting the user to install it\n\n"
            "Keep each message to 2-3 sentences. Be helpful, not pushy.\n\n"
            'Return valid JSON: {"messages": ["message1", "message2", ...]}'
        )

        # Build context for the LLM
        summaries: list[dict[str, Any]] = []
        for gap, skills in gap_matches:
            top_skill = skills[0] if skills else None
            summaries.append(
                {
                    "gap_description": gap.description,
                    "gap_frequency": gap.frequency,
                    "top_skill_name": top_skill.skill.skill_name if top_skill else "N/A",
                    "top_skill_description": (
                        top_skill.skill.description[:200]
                        if top_skill and top_skill.skill.description
                        else "N/A"
                    ),
                    "trust_level": top_skill.trust_level.value if top_skill else "N/A",
                    "data_access": top_skill.data_access if top_skill else [],
                    "life_sciences": top_skill.life_sciences_relevant if top_skill else False,
                }
            )

        try:
            response = await self._llm.generate_response(
                messages=[
                    {
                        "role": "user",
                        "content": f"Generate recommendations for these gaps:\n{json.dumps(summaries, default=str)}",
                    }
                ],
                system_prompt=system_prompt,
                max_tokens=2048,
                temperature=0.7,
            )

            parsed = json.loads(response)
            return parsed.get("messages", [])

        except (json.JSONDecodeError, KeyError) as e:
            logger.error("Failed to parse LLM recommendation messages: %s", e)
            return [self._fallback_message(gap, skills) for gap, skills in gap_matches]
        except Exception as e:
            logger.error("LLM recommendation message generation failed: %s", e)
            return [self._fallback_message(gap, skills) for gap, skills in gap_matches]

    @staticmethod
    def _fallback_message(gap: GapReport, skills: list[SkillRecommendation]) -> str:
        """Generate a simple fallback message without LLM.

        Args:
            gap: The usage gap.
            skills: Matched skills.

        Returns:
            A basic recommendation message.
        """
        if not skills:
            return f"I noticed a pattern in your usage: {gap.description}"

        top = skills[0]
        trust_label = top.trust_level.value.capitalize()
        access_label = ", ".join(top.data_access[:2]) if top.data_access else "PUBLIC"
        return (
            f"I noticed you've been working on tasks related to: {gap.description}. "
            f"I found a {trust_label} skill — {top.skill.skill_name} — that might help. "
            f"It requires {access_label} data access. Would you like to install it?"
        )

    async def _deliver_notification(self, user_id: str, rec: Recommendation) -> None:
        """Send a notification to the user about a recommendation.

        Uses NotificationService to create an in-app notification.

        Args:
            user_id: The user to notify.
            rec: The recommendation to notify about.
        """
        try:
            # Lazy import to avoid circular dependencies
            from src.models.notification import NotificationType
            from src.services.notification_service import NotificationService

            top_skill = rec.skills[0] if rec.skills else None
            metadata: dict[str, Any] = {
                "recommendation_type": "skill_discovery",
                "gap_type": rec.gap.gap_type,
                "gap_keywords": rec.gap.keywords,
                "skill_count": len(rec.skills),
            }
            if top_skill:
                metadata["top_skill_id"] = top_skill.skill.id
                metadata["top_skill_name"] = top_skill.skill.skill_name
                metadata["top_skill_trust"] = top_skill.trust_level.value

            await NotificationService.create_notification(
                user_id=user_id,
                type=NotificationType.SIGNAL_DETECTED,
                title="Skill Recommendation",
                message=rec.message,
                link="/skills",
                metadata=metadata,
            )

        except Exception as e:
            logger.warning("Failed to deliver recommendation notification: %s", e)

    async def _log_activity(self, user_id: str, rec: Recommendation) -> None:
        """Log the recommendation to aria_activity for dashboard display.

        Args:
            user_id: The user who received the recommendation.
            rec: The recommendation to log.
        """
        try:
            top_skill = rec.skills[0] if rec.skills else None
            self._client.table("aria_activity").insert(
                {
                    "user_id": user_id,
                    "activity_type": "skill_recommendation",
                    "title": f"Skill recommended: {top_skill.skill.skill_name if top_skill else 'N/A'}",
                    "description": rec.message,
                    "metadata": {
                        "gap_type": rec.gap.gap_type,
                        "gap_keywords": rec.gap.keywords,
                        "gap_frequency": rec.gap.frequency,
                        "recommended_skills": [
                            {
                                "skill_id": s.skill.id,
                                "skill_name": s.skill.skill_name,
                                "composite_score": round(s.composite_score, 3),
                                "trust_level": s.trust_level.value,
                            }
                            for s in rec.skills
                        ],
                    },
                }
            ).execute()

        except Exception as e:
            logger.warning("Failed to log recommendation activity: %s", e)
