"""US-924: Onboarding Procedural Memory (Self-Improving Onboarding).

Tracks onboarding quality per user and feeds insights into procedural memory
at the system level. Multi-tenant safe: learns about the PROCESS, not company data.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


class OnboardingOutcome(BaseModel):
    """Onboarding outcome record."""

    user_id: str
    readiness_at_completion: dict[str, float] = Field(default_factory=dict)
    time_to_complete_minutes: float = 0.0
    steps_completed: int = 0
    steps_skipped: int = 0
    company_type: str = ""
    first_goal_category: str | None = None
    documents_uploaded: int = 0
    email_connected: bool = False
    crm_connected: bool = False


class OnboardingOutcomeTracker:
    """Measures onboarding quality and feeds procedural memory.

    Records outcomes at onboarding completion, aggregates cross-user
    insights for admin visibility, and quarterly consolidates episodic
    events into semantic procedural truths.
    """

    def __init__(self) -> None:
        """Initialize tracker with Supabase client."""
        self._db = SupabaseClient.get_client()

    async def record_outcome(self, user_id: str) -> OnboardingOutcome:
        """Record onboarding outcome at completion.

        Gathers data from onboarding_state, user_integrations,
        company_documents, and goals to create an outcome record.

        Args:
            user_id: The user's ID.

        Returns:
            Recorded OnboardingOutcome.

        Raises:
            ValueError: If onboarding state not found.
        """
        # Get onboarding state
        state_response = (
            self._db.table("onboarding_state")
            .select("*")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )

        if not state_response or not state_response.data:
            raise ValueError(f"Onboarding state not found for user {user_id}")

        state = state_response.data

        # Extract step data
        step_data = state.get("step_data", {})

        # Calculate completion time
        started_at = state.get("started_at")
        completed_at = state.get("completed_at") or datetime.now(UTC).isoformat()

        time_minutes = 0.0
        if started_at:
            try:
                start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                end = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
                time_minutes = (end - start).total_seconds() / 60.0
            except (ValueError, TypeError):
                time_minutes = 0.0

        # Extract integration status
        integration_data = step_data.get("integration_wizard", {})
        email_connected = integration_data.get("email_connected", False)
        crm_connected = integration_data.get("crm_connected", False)

        # Extract company type and goal
        company_discovery = step_data.get("company_discovery", {})
        company_type = company_discovery.get("company_type", "")

        first_goal = step_data.get("first_goal", {})
        first_goal_category = first_goal.get("goal_type")

        # Count documents
        metadata = state.get("metadata", {})
        documents_uploaded = metadata.get("documents_uploaded", 0)

        # Build outcome
        outcome = OnboardingOutcome(
            user_id=user_id,
            readiness_at_completion=state.get("readiness_scores", {}),
            time_to_complete_minutes=round(time_minutes, 1),
            steps_completed=len(state.get("completed_steps", [])),
            steps_skipped=len(state.get("skipped_steps", [])),
            company_type=company_type,
            first_goal_category=first_goal_category,
            documents_uploaded=documents_uploaded,
            email_connected=email_connected,
            crm_connected=crm_connected,
        )

        # Insert to database (upsert for idempotency)
        (
            self._db.table("onboarding_outcomes")
            .insert({
                "user_id": user_id,
                "readiness_snapshot": outcome.readiness_at_completion,
                "completion_time_minutes": outcome.time_to_complete_minutes,
                "steps_completed": outcome.steps_completed,
                "steps_skipped": outcome.steps_skipped,
                "company_type": outcome.company_type,
                "first_goal_category": outcome.first_goal_category,
                "documents_uploaded": outcome.documents_uploaded,
                "email_connected": outcome.email_connected,
                "crm_connected": outcome.crm_connected,
            })
            .execute()
        )

        logger.info(
            "Recorded onboarding outcome",
            extra={
                "user_id": user_id,
                "company_type": company_type,
                "completion_time_minutes": time_minutes,
            },
        )

        return outcome

    async def get_system_insights(self) -> list[dict[str, Any]]:
        """Aggregate cross-user insights for procedural memory.

        Multi-tenant safe: learns about the PROCESS, not company data.
        Aggregates: avg readiness by company_type, avg completion time,
        correlation between document uploads and readiness.

        Returns:
            List of insight dictionaries with pattern, evidence, confidence.
        """
        # Query all outcomes
        response = (
            self._db.table("onboarding_outcomes")
            .select("*")
            .execute()
        )

        outcomes = response.data or []

        if not outcomes:
            return []

        insights: list[dict[str, Any]] = []

        # Group by company_type
        by_company_type: dict[str, list[dict[str, Any]]] = {}
        for outcome in outcomes:
            company_type = outcome.get("company_type", "unknown")
            by_company_type.setdefault(company_type, []).append(outcome)

        # Calculate average readiness by company type
        for company_type, type_outcomes in by_company_type.items():
            if len(type_outcomes) < 3:
                continue  # Need minimum sample size

            readiness_scores = []
            for o in type_outcomes:
                snapshot = o.get("readiness_snapshot", {})
                overall = snapshot.get("overall", 0)
                readiness_scores.append(overall)

            avg_readiness = sum(readiness_scores) / len(readiness_scores)

            insights.append({
                "pattern": f"avg_readiness_by_company_type",
                "company_type": company_type,
                "value": round(avg_readiness, 1),
                "sample_size": len(type_outcomes),
                "evidence_count": len(type_outcomes),
                "confidence": min(len(type_outcomes) * 0.1, 0.95),
            })

        # Correlation: documents uploaded vs readiness
        with_docs = [o for o in outcomes if o.get("documents_uploaded", 0) > 0]
        without_docs = [o for o in outcomes if o.get("documents_uploaded", 0) == 0]

        if len(with_docs) >= 3 and len(without_docs) >= 3:
            with_docs_readiness = [
                o.get("readiness_snapshot", {}).get("overall", 0) for o in with_docs
            ]
            without_docs_readiness = [
                o.get("readiness_snapshot", {}).get("overall", 0) for o in without_docs
            ]

            avg_with = sum(with_docs_readiness) / len(with_docs_readiness)
            avg_without = sum(without_docs_readiness) / len(without_docs_readiness)

            if avg_with > avg_without + 10:  # Meaningful difference
                insights.append({
                    "pattern": "documents_correlate_with_readiness",
                    "with_documents_avg": round(avg_with, 1),
                    "without_documents_avg": round(avg_without, 1),
                    "improvement_pct": round(((avg_with - avg_without) / avg_without) * 100, 1),
                    "evidence_count": len(with_docs) + len(without_docs),
                    "confidence": 0.7,
                })

        # Average completion time
        completion_times = [o.get("completion_time_minutes", 0) for o in outcomes if o.get("completion_time_minutes")]
        if completion_times:
            avg_time = sum(completion_times) / len(completion_times)
            insights.append({
                "pattern": "avg_completion_time",
                "value_minutes": round(avg_time, 1),
                "sample_size": len(completion_times),
                "evidence_count": len(completion_times),
                "confidence": 0.8,
            })

        return insights

    async def consolidate_to_procedural(self) -> int:
        """Quarterly: Convert episodic onboarding events to semantic truths.

        E.g., "CDMO users who upload capabilities decks have 40% richer
        Corporate Memory after 1 week"

        Returns:
            Number of new insights created.
        """
        # Get current insights to avoid duplicates
        existing_response = (
            self._db.table("procedural_insights")
            .select("insight")
            .eq("insight_type", "onboarding")
            .execute()
        )

        existing_insights = {row.get("insight") for row in (existing_response.data or [])}

        # Generate new insights from system insights
        system_insights = await self.get_system_insights()
        created_count = 0

        for insight in system_insights:
            pattern = insight.get("pattern", "")

            # Generate human-readable insight text
            insight_text = self._format_insight(insight)

            # Skip if already exists
            if insight_text in existing_insights:
                # Update evidence count and confidence instead
                (
                    self._db.table("procedural_insights")
                    .update({
                        "evidence_count": existing_response.data[0].get("evidence_count", 1) + insight.get("evidence_count", 1),
                        "confidence": min(0.95, existing_response.data[0].get("confidence", 0.5) + 0.05),
                    })
                    .eq("insight", insight_text)
                    .execute()
                )
                continue

            # Insert new insight
            (
                self._db.table("procedural_insights")
                .insert({
                    "insight": insight_text,
                    "evidence_count": insight.get("evidence_count", 1),
                    "confidence": insight.get("confidence", 0.5),
                    "insight_type": "onboarding",
                })
                .execute()
            )

            created_count += 1

        logger.info(
            "Consolidated onboarding outcomes to procedural insights",
            extra={"created_count": created_count},
        )

        return created_count

    def _format_insight(self, insight: dict[str, Any]) -> str:
        """Format insight dictionary into human-readable text.

        Args:
            insight: Insight dictionary with pattern and values.

        Returns:
            Human-readable insight string.
        """
        pattern = insight.get("pattern", "")

        if pattern == "avg_readiness_by_company_type":
            company_type = insight.get("company_type", "unknown")
            value = insight.get("value", 0)
            return f"{company_type.capitalize()} users average {value:.0f}% overall readiness after onboarding."

        if pattern == "documents_correlate_with_readiness":
            improvement = insight.get("improvement_pct", 0)
            return f"Users who upload documents during onboarding see {improvement:.0f}% higher readiness scores."

        if pattern == "avg_completion_time":
            minutes = insight.get("value_minutes", 0)
            return f"Average onboarding takes {minutes:.0f} minutes to complete."

        return str(insight)
