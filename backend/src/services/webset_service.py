"""WebsetService for polling and importing Webset results.

Phase 3: Websets Integration for Bulk Lead Generation.

This service polls pending Webset jobs from Exa and imports
discovered leads into the discovered_leads table for review.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from src.agents.capabilities.enrichment_providers.exa_provider import ExaEnrichmentProvider
from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


class ImportResult(BaseModel):
    """Result of importing leads from a Webset."""

    webset_id: str
    job_id: str
    items_found: int = 0
    items_imported: int = 0
    items_skipped: int = 0
    status: str = "pending"
    error: str | None = None


class WebsetService:
    """Polls and imports Webset results into discovered_leads.

    The service is called by a scheduler job every 5 minutes to:
    1. Query webset_jobs where status in ('pending', 'processing')
    2. For each, call get_webset() to check status
    3. If items available, call list_webset_items()
    4. Transform items to discovered_leads format
    5. Insert into discovered_leads table
    6. Update webset_jobs.items_imported count
    7. Mark completed/failed as appropriate
    """

    def __init__(self) -> None:
        """Initialize the WebsetService."""
        self._exa_provider: ExaEnrichmentProvider | None = None

    def _get_exa_provider(self) -> ExaEnrichmentProvider | None:
        """Lazily initialize and return the ExaEnrichmentProvider."""
        if self._exa_provider is None:
            try:
                self._exa_provider = ExaEnrichmentProvider()
                logger.info("WebsetService: ExaEnrichmentProvider initialized")
            except Exception as e:
                logger.warning(
                    "WebsetService: Failed to initialize ExaEnrichmentProvider: %s",
                    e,
                )
        return self._exa_provider

    async def poll_pending_websets(self) -> dict[str, int]:
        """Check all pending webset_jobs and import new items.

        Returns:
            Dict with summary stats: total_jobs, items_imported, jobs_completed, errors.
        """
        db = SupabaseClient.get_client()
        exa = self._get_exa_provider()

        if not exa:
            logger.warning("WebsetService: Exa provider not available")
            return {
                "total_jobs": 0,
                "items_imported": 0,
                "jobs_completed": 0,
                "errors": 0,
            }

        # Query pending and processing jobs
        result = (
            db.table("webset_jobs").select("*").in_("status", ["pending", "processing"]).execute()
        )

        jobs = result.data or []
        if not jobs:
            logger.debug("WebsetService: No pending webset jobs")
            return {
                "total_jobs": 0,
                "items_imported": 0,
                "jobs_completed": 0,
                "errors": 0,
            }

        logger.info("WebsetService: Processing %d pending webset jobs", len(jobs))

        total_imported = 0
        jobs_completed = 0
        errors = 0

        for job in jobs:  # type: ignore[assignment]
            try:
                import_result = await self._process_webset_job(job, db, exa)
                total_imported += import_result.items_imported
                if import_result.status == "completed":
                    jobs_completed += 1
                if import_result.error:
                    errors += 1
            except Exception:
                logger.exception(
                    "WebsetService: Failed to process job %s",
                    job.get("id"),  # type: ignore[union-attr]
                )
                errors += 1

        return {
            "total_jobs": len(jobs),
            "items_imported": total_imported,
            "jobs_completed": jobs_completed,
            "errors": errors,
        }

    async def _process_webset_job(
        self,
        job: dict[str, Any],
        db: Any,
        exa: ExaEnrichmentProvider,
    ) -> ImportResult:
        """Process a single webset job.

        Args:
            job: Webset job record from database.
            db: Supabase client.
            exa: ExaEnrichmentProvider instance.

        Returns:
            ImportResult with import statistics.
        """
        job_id = job["id"]
        webset_id = job["webset_id"]
        user_id = job["user_id"]
        items_already_imported = job.get("items_imported", 0)

        logger.info(
            "WebsetService: Processing job %s (webset=%s)",
            job_id,
            webset_id,
        )

        # Get Webset status from Exa
        webset_status = await exa.get_webset(webset_id)
        status = webset_status.get("status", "unknown")

        if status == "failed":
            # Mark job as failed
            self._update_job_status(db, job_id, "failed", error="Exa reported failure")
            return ImportResult(
                webset_id=webset_id,
                job_id=job_id,
                status="failed",
                error="Exa reported failure",
            )

        # Fetch items from Webset
        items_result = await exa.list_webset_items(webset_id, limit=200)
        items = items_result.get("items", [])

        if not items:
            # No items yet, update status if needed
            if status == "completed":
                self._update_job_status(db, job_id, "completed")
            return ImportResult(
                webset_id=webset_id,
                job_id=job_id,
                items_found=0,
                status=status,
            )

        logger.info(
            "WebsetService: Found %d items in webset %s",
            len(items),
            webset_id,
        )

        # Import new items (skip already imported)
        new_items = items[items_already_imported:]
        imported_count = 0
        skipped_count = 0

        for item in new_items:
            try:
                lead_record = self._transform_item_to_lead(
                    item=item,
                    user_id=user_id,
                    job_id=job_id,
                    search_query=job.get("search_query", ""),
                )

                # Check if lead already exists
                existing = (
                    db.table("discovered_leads")
                    .select("id")
                    .eq("user_id", user_id)
                    .eq("company_name", lead_record["company_name"])
                    .maybe_single()
                    .execute()
                )

                if existing.data:
                    skipped_count += 1
                    continue

                # Insert new lead
                db.table("discovered_leads").insert(lead_record).execute()
                imported_count += 1

            except Exception as e:
                logger.warning(
                    "WebsetService: Failed to import item %s: %s",
                    item.get("id", "unknown"),
                    e,
                )
                skipped_count += 1

        # Update job with new import count
        total_imported = items_already_imported + imported_count
        now = datetime.now(UTC).isoformat()

        update_data: dict[str, Any] = {
            "items_imported": total_imported,
            "updated_at": now,
        }

        # Mark completed if webset is done and we've imported all items
        if status == "completed" and total_imported >= len(items):
            update_data["status"] = "completed"
        elif status == "processing":
            update_data["status"] = "processing"

        db.table("webset_jobs").update(update_data).eq("id", job_id).execute()

        logger.info(
            "WebsetService: Job %s imported %d items, skipped %d",
            job_id,
            imported_count,
            skipped_count,
        )

        return ImportResult(
            webset_id=webset_id,
            job_id=job_id,
            items_found=len(items),
            items_imported=imported_count,
            items_skipped=skipped_count,
            status=update_data.get("status", status),
        )

    def _transform_item_to_lead(
        self,
        item: dict[str, Any],
        user_id: str,
        job_id: str,
        search_query: str,  # noqa: ARG002 - kept for future use
    ) -> dict[str, Any]:
        """Transform a Webset item to discovered_lead schema.

        Args:
            item: Item from Exa Webset.
            user_id: User who initiated the job.
            job_id: Webset job ID.
            search_query: Original search query.

        Returns:
            Dict matching discovered_leads table schema.
        """
        now = datetime.now(UTC).isoformat()
        lead_id = str(uuid4())

        # Extract company data from item
        company_name = item.get("name", "Unknown Company")

        # Build company_data JSONB
        company_data: dict[str, Any] = {
            "name": company_name,
            "domain": item.get("domain", ""),
            "website": item.get("url", ""),
            "description": item.get("description", ""),
            "industry": item.get("industry", ""),
            "founded_year": item.get("foundedYear") or item.get("founded_year"),
            "employee_count": item.get("employeeCount") or item.get("employee_count"),
            "headquarters": item.get("headquarters"),
            "revenue": item.get("revenue"),
            "funding_stage": item.get("fundingStage") or item.get("funding_stage"),
        }

        # Extract contacts from enrichments
        contacts: list[dict[str, Any]] = []
        raw_contacts = item.get("contacts", [])
        if isinstance(raw_contacts, list):
            for contact in raw_contacts:
                contacts.append(
                    {
                        "name": contact.get("name", ""),
                        "title": contact.get("title", ""),
                        "email": contact.get("email", ""),
                        "phone": contact.get("phone", ""),
                        "linkedin_url": contact.get("linkedin_url", ""),
                    }
                )

        # Also check enrichment results in raw_data
        raw_data = item.get("rawData", item.get("raw_data", {}))
        if isinstance(raw_data, dict):
            # Extract any additional contacts from enrichment
            enriched_contacts = raw_data.get("contacts", [])
            if isinstance(enriched_contacts, list):
                for contact in enriched_contacts:
                    if contact not in contacts:
                        contacts.append(contact)

        # Compute fit score based on data completeness
        fit_score = self._compute_fit_score(company_data, contacts)

        # Collect signals
        signals: list[str] = []
        if company_data.get("funding_stage"):
            signals.append(f"funding:{company_data['funding_stage']}")
        if company_data.get("employee_count"):
            signals.append("employee_data_available")
        if contacts:
            signals.append("contacts_found")

        return {
            "id": lead_id,
            "user_id": user_id,
            "icp_id": None,  # Webset jobs don't link to ICP directly
            "company_name": company_name,
            "company_data": company_data,
            "contacts": contacts,
            "fit_score": fit_score,
            "score_breakdown": {},  # Computed later by LeadGenerationService
            "signals": signals,
            "review_status": "pending",
            "reviewed_at": None,
            "source": "webset",
            "webset_job_id": job_id,
            "lead_memory_id": None,
            "created_at": now,
            "updated_at": now,
        }

    def _compute_fit_score(
        self,
        company_data: dict[str, Any],
        contacts: list[dict[str, Any]],
    ) -> int:
        """Compute a simple fit score based on data completeness.

        This is a preliminary score. Full 4-factor scoring is done
        by LeadGenerationService._compute_score_breakdown.

        Args:
            company_data: Company information dict.
            contacts: List of contact dicts.

        Returns:
            Fit score (0-100).
        """
        score = 0

        # Company data completeness (60 points max)
        important_fields = [
            "name",
            "domain",
            "description",
            "industry",
            "headquarters",
            "funding_stage",
        ]
        filled = sum(1 for f in important_fields if company_data.get(f))
        score += int((filled / len(important_fields)) * 60)

        # Contact availability (40 points max)
        if contacts:
            # Up to 20 points for having contacts
            contact_score = min(20, len(contacts) * 10)
            score += contact_score

            # Up to 20 points for contact quality (having emails)
            emails = sum(1 for c in contacts if c.get("email"))
            if emails > 0:
                score += min(20, emails * 10)

        return min(100, max(0, score))

    def _update_job_status(
        self,
        db: Any,
        job_id: str,
        status: str,
        error: str | None = None,
    ) -> None:
        """Update job status in database.

        Args:
            db: Supabase client.
            job_id: Job UUID.
            status: New status value.
            error: Optional error message.
        """
        now = datetime.now(UTC).isoformat()
        update_data: dict[str, Any] = {
            "status": status,
            "updated_at": now,
        }
        if error:
            update_data["error_message"] = error

        try:
            db.table("webset_jobs").update(update_data).eq("id", job_id).execute()
        except Exception:
            logger.exception(
                "WebsetService: Failed to update job %s status",
                job_id,
            )

    async def import_webset_now(self, webset_id: str) -> ImportResult:
        """Force immediate import of a specific Webset.

        Called by webhook handler when items.completed event is received.

        Args:
            webset_id: The Exa Webset ID.

        Returns:
            ImportResult with import statistics.
        """
        db = SupabaseClient.get_client()

        # Find the job for this webset
        result = (
            db.table("webset_jobs").select("*").eq("webset_id", webset_id).maybe_single().execute()
        )

        if not result.data:
            logger.warning(
                "WebsetService: No job found for webset %s",
                webset_id,
            )
            return ImportResult(
                webset_id=webset_id,
                job_id="",
                status="failed",
                error="Job not found",
            )

        job_data = result.data  # type: ignore[assignment]

        exa = self._get_exa_provider()
        if not exa:
            return ImportResult(
                webset_id=webset_id,
                job_id=result.data["id"],
                status="failed",
                error="Exa provider not available",
            )

        return await self._process_webset_job(job_data, db, exa)
