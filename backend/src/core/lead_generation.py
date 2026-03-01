"""Lead generation workflow service (US-939).

Orchestrates the lead generation pipeline: ICP management,
Hunter agent discovery, lead scoring, review workflow,
pipeline views, and outreach initiation.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from src.agents.hunter import HunterAgent
from src.core.llm import LLMClient
from src.db.supabase import SupabaseClient
from src.memory.lead_memory import LeadMemoryService, TriggerType
from src.models.lead_generation import (
    DiscoveredLeadResponse,
    ICPDefinition,
    ICPResponse,
    LeadScoreBreakdown,
    OutreachRequest,
    OutreachResponse,
    PipelineStage,
    PipelineStageSummary,
    PipelineSummary,
    ReviewStatus,
    ScoreFactor,
)

logger = logging.getLogger(__name__)


class LeadGenerationService:
    """Service for orchestrating the lead generation workflow.

    Manages ICP profiles, triggers Hunter agent discovery, scores
    and stores discovered leads, handles the review workflow,
    provides pipeline views, and initiates outreach.
    """

    def _get_client(self) -> Any:
        """Get the Supabase client instance.

        Returns:
            Initialized Supabase client.
        """
        return SupabaseClient.get_client()

    # ------------------------------------------------------------------
    # ICP Management
    # ------------------------------------------------------------------

    async def save_icp(self, user_id: str, icp_data: ICPDefinition) -> ICPResponse:
        """Save or update an Ideal Customer Profile for a user.

        If an ICP already exists for the user, the version is incremented
        and the data is updated. Otherwise a new record is created with
        version 1.

        Args:
            user_id: The user's UUID.
            icp_data: ICP definition to store.

        Returns:
            ICPResponse with the persisted ICP data.
        """
        client = self._get_client()
        now = datetime.now(UTC).isoformat()

        # Check for existing ICP
        existing = (
            client.table("lead_icp_profiles")
            .select("*")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )

        if existing.data:
            # Update existing ICP: increment version
            new_version = existing.data["version"] + 1
            updated = (
                client.table("lead_icp_profiles")
                .update(
                    {
                        "icp_data": icp_data.model_dump(),
                        "version": new_version,
                        "updated_at": now,
                    }
                )
                .eq("id", existing.data["id"])
                .execute()
            )
            row = updated.data[0]
        else:
            # Insert new ICP
            new_id = str(uuid4())
            inserted = (
                client.table("lead_icp_profiles")
                .insert(
                    {
                        "id": new_id,
                        "user_id": user_id,
                        "icp_data": icp_data.model_dump(),
                        "version": 1,
                        "created_at": now,
                        "updated_at": now,
                    }
                )
                .execute()
            )
            row = inserted.data[0]

        logger.info(
            "Saved ICP profile",
            extra={
                "user_id": user_id,
                "icp_id": row["id"],
                "version": row["version"],
            },
        )

        return ICPResponse(
            id=row["id"],
            user_id=row["user_id"],
            icp_data=ICPDefinition(**row["icp_data"]),
            version=row["version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def get_icp(self, user_id: str) -> ICPResponse | None:
        """Retrieve the ICP profile for a user.

        Args:
            user_id: The user's UUID.

        Returns:
            ICPResponse if found, None otherwise.
        """
        client = self._get_client()

        result = (
            client.table("lead_icp_profiles")
            .select("*")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )

        if not result.data:
            return None

        row = result.data
        return ICPResponse(
            id=row["id"],
            user_id=row["user_id"],
            icp_data=ICPDefinition(**row["icp_data"]),
            version=row["version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # ------------------------------------------------------------------
    # Lead Discovery
    # ------------------------------------------------------------------

    async def discover_leads(
        self,
        user_id: str,
        icp_id: str,
        target_count: int,
    ) -> list[DiscoveredLeadResponse]:
        """Run the Hunter agent to discover leads matching an ICP.

        Fetches the ICP from the database, builds a Hunter agent task,
        executes the agent, scores each lead, and persists results.

        Args:
            user_id: The user's UUID.
            icp_id: ID of the ICP profile to use for discovery.
            target_count: Number of leads to target.

        Returns:
            List of discovered lead responses.

        Raises:
            ValueError: If the ICP is not found.
        """
        client = self._get_client()

        # Fetch ICP data
        icp_row = (
            client.table("lead_icp_profiles")
            .select("*")
            .eq("id", icp_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )

        if not icp_row.data:
            raise ValueError(f"ICP profile not found: {icp_id}")

        icp_def = ICPDefinition(**icp_row.data["icp_data"])

        # Build Hunter agent task from ICP fields
        size_str = ""
        if icp_def.company_size.get("min") and icp_def.company_size.get("max"):
            size_str = f"{icp_def.company_size['min']}-{icp_def.company_size['max']}"

        hunter_task: dict[str, Any] = {
            "icp": {
                "industry": icp_def.industry[0] if icp_def.industry else "",
                "size": size_str,
                "geography": icp_def.geographies,
            },
            "target_count": target_count,
            "exclusions": icp_def.exclusions,
        }

        # Execute Hunter agent
        llm_client = LLMClient()
        agent = HunterAgent(llm_client=llm_client, user_id=user_id)
        result = await agent.execute(hunter_task)

        if not result.success or not result.data:
            logger.warning(
                "Hunter agent returned no leads",
                extra={"user_id": user_id, "icp_id": icp_id},
            )
            return []

        # Process each lead
        now = datetime.now(UTC).isoformat()
        discovered: list[DiscoveredLeadResponse] = []

        for lead_data in result.data:
            company = lead_data.get("company", {})
            contacts = lead_data.get("contacts", [])
            fit_score_raw: float = lead_data.get("fit_score", 0.0)
            fit_reasons: list[str] = lead_data.get("fit_reasons", [])
            gaps: list[str] = lead_data.get("gaps", [])
            source: str = lead_data.get("source", "hunter_pro")

            # Compute score breakdown with 4 factors
            score_breakdown = self._compute_score_breakdown(
                fit_score=fit_score_raw,
                company=company,
                contacts=contacts,
                fit_reasons=fit_reasons,
                gaps=gaps,
            )

            lead_id = str(uuid4())
            company_name = company.get("name", "Unknown")

            # Collect signals from company data
            signals: list[str] = []
            if company.get("funding_stage"):
                signals.append(f"funding:{company['funding_stage']}")
            if company.get("technologies"):
                signals.append("tech_stack_available")

            # Store in discovered_leads table
            row_data = {
                "id": lead_id,
                "user_id": user_id,
                "icp_id": icp_id,
                "company_name": company_name,
                "company_data": company,
                "contacts": contacts,
                "fit_score": score_breakdown.overall_score,
                "score_breakdown": score_breakdown.model_dump(),
                "signals": signals,
                "review_status": ReviewStatus.PENDING.value,
                "reviewed_at": None,
                "source": source,
                "lead_memory_id": None,
                "created_at": now,
                "updated_at": now,
            }
            client.table("discovered_leads").insert(row_data).execute()

            discovered.append(
                DiscoveredLeadResponse(
                    id=lead_id,
                    user_id=user_id,
                    icp_id=icp_id,
                    company_name=company_name,
                    company_data=company,
                    contacts=contacts,
                    fit_score=score_breakdown.overall_score,
                    score_breakdown=score_breakdown,
                    signals=signals,
                    review_status=ReviewStatus.PENDING,
                    reviewed_at=None,
                    source=source,
                    lead_memory_id=None,
                    created_at=now,
                    updated_at=now,
                )
            )

        logger.info(
            "Discovered leads",
            extra={
                "user_id": user_id,
                "icp_id": icp_id,
                "count": len(discovered),
            },
        )

        # Auto-approve high-confidence leads (fit_score >= 85)
        auto_approved = 0
        for lead in discovered:
            if lead.fit_score >= 85:
                try:
                    await self.review_lead(
                        user_id=user_id,
                        lead_id=lead.id,
                        action=ReviewStatus.APPROVED,
                    )
                    auto_approved += 1
                except Exception:
                    logger.debug(
                        "Auto-approve failed for lead %s", lead.id, exc_info=True,
                    )

        if auto_approved:
            logger.info(
                "Auto-approved high-confidence leads",
                extra={
                    "user_id": user_id,
                    "auto_approved": auto_approved,
                    "total_discovered": len(discovered),
                },
            )

        return discovered

    def _compute_score_breakdown(
        self,
        fit_score: float,
        company: dict[str, Any],
        contacts: list[dict[str, Any]],
        fit_reasons: list[str],
        gaps: list[str],
    ) -> LeadScoreBreakdown:
        """Compute a four-factor score breakdown for a discovered lead.

        Factors:
        - ICP Fit (weight 0.40): derived from the Hunter agent's fit_score.
        - Timing Signals (weight 0.25): based on signal presence (funding, hiring, etc.).
        - Relationship Proximity (weight 0.20): based on contacts found.
        - Engagement Signals (weight 0.15): based on company data completeness.

        Args:
            fit_score: Raw fit score (0-100) from the Hunter agent.
            company: Enriched company data dictionary.
            contacts: List of contact dictionaries found.
            fit_reasons: Reasons for the fit score.
            gaps: Gaps identified during scoring.

        Returns:
            LeadScoreBreakdown with overall score and factor details.
        """
        # Factor 1: ICP Fit (weight 0.40) -- proportional to fit_score
        icp_fit_score = min(100, max(0, int(fit_score)))
        icp_fit_explanation = (
            f"Matches: {', '.join(fit_reasons[:3])}" if fit_reasons else "No strong matches"
        )
        if gaps:
            icp_fit_explanation += f". Gaps: {', '.join(gaps[:2])}"

        # Factor 2: Timing Signals (weight 0.25)
        timing_score = 0
        timing_details: list[str] = []
        if company.get("funding_stage"):
            timing_score += 40
            timing_details.append(f"Funding: {company['funding_stage']}")
        if company.get("technologies"):
            timing_score += 20
            timing_details.append("Tech stack identified")
        if company.get("revenue"):
            timing_score += 20
            timing_details.append("Revenue data available")
        if company.get("founded_year"):
            timing_score += 20
            timing_details.append(f"Founded: {company['founded_year']}")
        timing_score = min(100, timing_score)
        timing_explanation = (
            "; ".join(timing_details) if timing_details else "No timing signals detected"
        )

        # Factor 3: Relationship Proximity (weight 0.20)
        contact_count = len(contacts)
        if contact_count >= 4:
            relationship_score = 100
        elif contact_count >= 2:
            relationship_score = 70
        elif contact_count >= 1:
            relationship_score = 40
        else:
            relationship_score = 0
        relationship_explanation = (
            f"{contact_count} contact(s) found" if contact_count > 0 else "No contacts identified"
        )

        # Factor 4: Engagement Signals (weight 0.15)
        completeness_fields = [
            "name",
            "domain",
            "industry",
            "size",
            "geography",
            "website",
            "linkedin_url",
            "funding_stage",
            "revenue",
        ]
        filled = sum(1 for f in completeness_fields if company.get(f))
        engagement_score = min(100, int((filled / len(completeness_fields)) * 100))
        engagement_explanation = (
            f"Company data {filled}/{len(completeness_fields)} fields populated"
        )

        factors = [
            ScoreFactor(
                name="ICP Fit",
                score=icp_fit_score,
                weight=0.40,
                explanation=icp_fit_explanation,
            ),
            ScoreFactor(
                name="Timing Signals",
                score=timing_score,
                weight=0.25,
                explanation=timing_explanation,
            ),
            ScoreFactor(
                name="Relationship Proximity",
                score=relationship_score,
                weight=0.20,
                explanation=relationship_explanation,
            ),
            ScoreFactor(
                name="Engagement Signals",
                score=engagement_score,
                weight=0.15,
                explanation=engagement_explanation,
            ),
        ]

        overall = int(sum(f.score * f.weight for f in factors))
        overall = min(100, max(0, overall))

        return LeadScoreBreakdown(overall_score=overall, factors=factors)

    # ------------------------------------------------------------------
    # Lead Listing & Review
    # ------------------------------------------------------------------

    async def list_discovered(
        self,
        user_id: str,
        status_filter: ReviewStatus | None = None,
    ) -> list[DiscoveredLeadResponse]:
        """List discovered leads for a user, optionally filtered by review status.

        Args:
            user_id: The user's UUID.
            status_filter: Optional review status to filter by.

        Returns:
            List of DiscoveredLeadResponse ordered by fit_score descending.
        """
        client = self._get_client()

        query = client.table("discovered_leads").select("*").eq("user_id", user_id)

        if status_filter is not None:
            query = query.eq("review_status", status_filter.value)

        query = query.order("fit_score", desc=True)
        result = query.execute()

        if not result.data:
            return []

        return [self._row_to_discovered_lead(row) for row in result.data]

    async def review_lead(
        self,
        user_id: str,
        lead_id: str,
        action: ReviewStatus,
    ) -> DiscoveredLeadResponse | None:
        """Review a discovered lead (approve, reject, or save).

        If approved, creates a Lead Memory entry via LeadMemoryService
        and links it back to the discovered lead record.

        Args:
            user_id: The user's UUID.
            lead_id: The discovered lead's UUID.
            action: Review action to take.

        Returns:
            Updated DiscoveredLeadResponse, or None if lead not found.
        """
        client = self._get_client()
        now = datetime.now(UTC).isoformat()

        # Fetch the existing lead
        existing = (
            client.table("discovered_leads")
            .select("*")
            .eq("id", lead_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )

        if not existing.data:
            return None

        update_data: dict[str, Any] = {
            "review_status": action.value,
            "reviewed_at": now,
            "updated_at": now,
        }

        # If approved, create a Lead Memory entry
        if action == ReviewStatus.APPROVED:
            lead_memory_service = LeadMemoryService()
            lead_memory = await lead_memory_service.create(
                user_id=user_id,
                company_name=existing.data["company_name"],
                trigger=TriggerType.MANUAL,
            )
            update_data["lead_memory_id"] = lead_memory.id

        # Update the discovered lead
        updated = (
            client.table("discovered_leads")
            .update(update_data)
            .eq("id", lead_id)
            .eq("user_id", user_id)
            .execute()
        )

        if not updated.data:
            return None

        row = updated.data[0]

        logger.info(
            "Reviewed lead",
            extra={
                "user_id": user_id,
                "lead_id": lead_id,
                "action": action.value,
                "lead_memory_id": row.get("lead_memory_id"),
            },
        )

        return self._row_to_discovered_lead(row)

    # ------------------------------------------------------------------
    # Score Explanation
    # ------------------------------------------------------------------

    async def get_score_explanation(
        self,
        user_id: str,
        lead_id: str,
    ) -> LeadScoreBreakdown | None:
        """Get the score breakdown for a discovered lead.

        Args:
            user_id: The user's UUID.
            lead_id: The discovered lead's UUID.

        Returns:
            LeadScoreBreakdown if found, None otherwise.
        """
        client = self._get_client()

        result = (
            client.table("discovered_leads")
            .select("score_breakdown")
            .eq("id", lead_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )

        if not result.data or not result.data.get("score_breakdown"):
            return None

        breakdown_data = result.data["score_breakdown"]
        # Handle both string and dict representations
        if isinstance(breakdown_data, str):
            breakdown_data = json.loads(breakdown_data)

        return LeadScoreBreakdown(**breakdown_data)

    # ------------------------------------------------------------------
    # Pipeline View
    # ------------------------------------------------------------------

    async def get_pipeline(self, user_id: str) -> PipelineSummary:
        """Build a pipeline summary from Lead Memory records.

        Groups lead memories by lifecycle stage and maps them to
        pipeline stages:
        - lead -> prospect
        - lead (health_score >= 60) -> qualified
        - opportunity -> opportunity
        - account -> customer

        Args:
            user_id: The user's UUID.

        Returns:
            PipelineSummary with stage counts and values.
        """
        client = self._get_client()

        result = (
            client.table("lead_memories")
            .select("lifecycle_stage,health_score,expected_value")
            .eq("user_id", user_id)
            .execute()
        )

        rows = result.data or []

        # Aggregate by pipeline stage
        stage_data: dict[PipelineStage, dict[str, Any]] = {
            PipelineStage.PROSPECT: {"count": 0, "total_value": 0.0},
            PipelineStage.QUALIFIED: {"count": 0, "total_value": 0.0},
            PipelineStage.OPPORTUNITY: {"count": 0, "total_value": 0.0},
            PipelineStage.CUSTOMER: {"count": 0, "total_value": 0.0},
        }

        for row in rows:
            lifecycle = row.get("lifecycle_stage", "lead")
            expected_value = float(row.get("expected_value") or 0)
            health_score = row.get("health_score", 0)

            if lifecycle == "lead":
                # All leads go to prospect stage
                stage_data[PipelineStage.PROSPECT]["count"] += 1
                stage_data[PipelineStage.PROSPECT]["total_value"] += expected_value
                # Leads with health_score >= 60 also count as qualified
                if health_score >= 60:
                    stage_data[PipelineStage.QUALIFIED]["count"] += 1
                    stage_data[PipelineStage.QUALIFIED]["total_value"] += expected_value
            elif lifecycle == "opportunity":
                stage_data[PipelineStage.OPPORTUNITY]["count"] += 1
                stage_data[PipelineStage.OPPORTUNITY]["total_value"] += expected_value
            elif lifecycle == "account":
                stage_data[PipelineStage.CUSTOMER]["count"] += 1
                stage_data[PipelineStage.CUSTOMER]["total_value"] += expected_value

        stages = [
            PipelineStageSummary(
                stage=stage,
                count=data["count"],
                total_value=data["total_value"],
            )
            for stage, data in stage_data.items()
        ]

        total_leads = sum(s.count for s in stages)
        total_value = sum(s.total_value for s in stages)

        return PipelineSummary(
            stages=stages,
            total_leads=total_leads,
            total_pipeline_value=total_value,
        )

    # ------------------------------------------------------------------
    # Outreach
    # ------------------------------------------------------------------

    async def initiate_outreach(
        self,
        user_id: str,
        lead_id: str,
        request: OutreachRequest,
    ) -> OutreachResponse | None:
        """Initiate an outreach draft for a lead.

        Verifies the lead exists (in either discovered_leads or lead_memories)
        and returns a draft outreach response.

        Args:
            user_id: The user's UUID.
            lead_id: The lead's UUID.
            request: Outreach request with subject, message, and tone.

        Returns:
            OutreachResponse with draft content, or None if lead not found.
        """
        client = self._get_client()

        # Check discovered_leads first
        discovered = (
            client.table("discovered_leads")
            .select("id")
            .eq("id", lead_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )

        if not discovered.data:
            # Check lead_memories
            lead_memory = (
                client.table("lead_memories")
                .select("id")
                .eq("id", lead_id)
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )
            if not lead_memory.data:
                return None

        now = datetime.now(UTC)

        logger.info(
            "Initiated outreach draft",
            extra={
                "user_id": user_id,
                "lead_id": lead_id,
                "tone": request.tone,
            },
        )

        return OutreachResponse(
            id=str(uuid4()),
            lead_id=lead_id,
            draft_subject=request.subject,
            draft_body=request.message,
            status="draft",
            created_at=now,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _row_to_discovered_lead(self, row: dict[str, Any]) -> DiscoveredLeadResponse:
        """Convert a database row to a DiscoveredLeadResponse.

        Args:
            row: Dictionary from the discovered_leads table.

        Returns:
            DiscoveredLeadResponse model instance.
        """
        breakdown_data = row.get("score_breakdown")
        score_breakdown = None
        if breakdown_data:
            if isinstance(breakdown_data, str):
                breakdown_data = json.loads(breakdown_data)
            score_breakdown = LeadScoreBreakdown(**breakdown_data)

        return DiscoveredLeadResponse(
            id=row["id"],
            user_id=row["user_id"],
            icp_id=row.get("icp_id"),
            company_name=row["company_name"],
            company_data=row.get("company_data", {}),
            contacts=row.get("contacts", []),
            fit_score=row.get("fit_score", 0),
            score_breakdown=score_breakdown,
            signals=row.get("signals", []),
            review_status=ReviewStatus(row.get("review_status", "pending")),
            reviewed_at=row.get("reviewed_at"),
            source=row.get("source", "unknown"),
            lead_memory_id=row.get("lead_memory_id"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
