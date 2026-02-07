"""Profile Update → Memory Merge Pipeline (US-922).

When a user updates their profile (US-921), this service:
1. Detects what changed (diff between old and new data)
2. Re-researches if company details changed (re-enrichment via US-903)
3. Merges new information into semantic memory with conflict resolution
4. Generates a Memory Delta for user confirmation (US-920)
5. Recalculates readiness scores
6. Logs all changes to the audit trail

Conflict resolution follows the source hierarchy:
    user_stated (0.95) > CRM (0.85) > document (0.80) > web (0.70) > inferred (0.55)
"""

import logging
from typing import Any

from src.db.supabase import SupabaseClient
from src.memory.audit import MemoryOperation, MemoryType, log_memory_operation

logger = logging.getLogger(__name__)

# Fields to ignore when computing diffs (metadata / system fields)
_IGNORED_FIELDS = frozenset(
    {
        "id",
        "created_at",
        "updated_at",
        "company_id",
        "role",
        "stripe_customer_id",
        "subscription_status",
        "subscription_metadata",
        "settings",
    }
)

# Fields whose changes indicate a company-level change requiring re-enrichment
_COMPANY_TRIGGER_FIELDS = frozenset({"name", "website", "industry"})

# Source → confidence mapping per CLAUDE.md hierarchy
_SOURCE_CONFIDENCE: dict[str, float] = {
    "user_stated": 0.95,
    "crm": 0.85,
    "document": 0.80,
    "enrichment_website": 0.70,
    "enrichment_news": 0.70,
    "enrichment_clinical_trials": 0.70,
    "enrichment_leadership": 0.70,
    "inferred": 0.55,
    "inferred_during_onboarding": 0.55,
}

# Map profile field names to semantic memory categories
_FIELD_CATEGORY_MAP: dict[str, str] = {
    "full_name": "contact",
    "title": "leadership",
    "department": "contact",
    "linkedin_url": "contact",
    "communication_preferences": "communication_style",
    "default_tone": "tone",
    "tracked_competitors": "competitive",
    "privacy_exclusions": "communication_style",
    "name": "product",
    "website": "product",
    "industry": "product",
    "sub_vertical": "product",
    "description": "product",
    "key_products": "product",
}


class ProfileMergeService:
    """Detects profile changes and merges into memory systems.

    Triggered by profile saves in US-921. Orchestrates the full pipeline
    from diff detection through memory merge, delta presentation, readiness
    recalculation, and audit logging.
    """

    def __init__(self) -> None:
        """Initialize with database client."""
        self._db = SupabaseClient.get_client()

    async def process_update(
        self,
        user_id: str,
        old_data: dict[str, Any],
        new_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Full merge pipeline triggered by profile save.

        Args:
            user_id: The user who updated their profile.
            old_data: Previous profile data (snapshot before save).
            new_data: New profile data (after save).

        Returns:
            Status dict with changes count, delta_id, and merge result.
        """
        # 1. Diff detection
        changes = self._detect_changes(old_data, new_data)
        if not changes:
            return {"status": "no_changes"}

        # 2. Re-research trigger (if company details changed)
        if self._company_changed(changes):
            await self._trigger_re_enrichment(user_id, new_data)

        # 3. Memory merge with conflict resolution
        merged = await self._merge_changes(user_id, changes)

        # 4. Generate Memory Delta for user confirmation
        delta = await self._generate_delta(user_id, merged)

        # 5. Recalculate readiness
        await self._recalculate_readiness(user_id)

        # 6. Audit log
        await self._audit_changes(user_id, changes, merged)

        return {
            "status": "merged",
            "changes": len(changes),
            "delta_id": delta.get("id"),
            "merged_facts": len(merged),
        }

    def _detect_changes(
        self,
        old: dict[str, Any],
        new: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        """Deep diff between old and new profile data.

        Compares all fields except system metadata. Returns a dict
        of changed fields with old and new values.

        Args:
            old: Previous profile data.
            new: Updated profile data.

        Returns:
            Dict mapping field_name → {"old": ..., "new": ...} for changed fields.
        """
        changes: dict[str, dict[str, Any]] = {}

        all_keys = set(old.keys()) | set(new.keys())

        for key in all_keys:
            if key in _IGNORED_FIELDS:
                continue

            old_val = old.get(key)
            new_val = new.get(key)

            if old_val != new_val:
                changes[key] = {"old": old_val, "new": new_val}

        return changes

    def _company_changed(self, changes: dict[str, Any]) -> bool:
        """Check if company name, website, or industry changed.

        Args:
            changes: Dict of detected changes.

        Returns:
            True if any company-trigger field changed.
        """
        return any(k in changes for k in _COMPANY_TRIGGER_FIELDS)

    async def _trigger_re_enrichment(
        self,
        user_id: str,
        new_data: dict[str, Any],
    ) -> None:
        """Trigger Company Enrichment Engine re-run for updated company.

        Fires asynchronously — the enrichment runs in background and
        will generate its own Memory Delta when complete.

        Args:
            user_id: The user whose company changed.
            new_data: Updated profile/company data with new values.
        """
        try:
            from src.onboarding.enrichment import CompanyEnrichmentEngine

            company_name = new_data.get("name", "")
            website = new_data.get("website", "")
            company_id = new_data.get("id", "")

            if company_name and website:
                engine = CompanyEnrichmentEngine()
                await engine.enrich_company(
                    company_id=company_id,
                    company_name=company_name,
                    website=website,
                    user_id=user_id,
                )
                logger.info(
                    "Re-enrichment triggered for company update",
                    extra={"user_id": user_id, "company_name": company_name},
                )
        except Exception as e:
            logger.warning(
                "Re-enrichment failed (non-blocking)",
                extra={"user_id": user_id, "error": str(e)},
            )

    async def _merge_changes(
        self,
        user_id: str,
        changes: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Cross-reference new info against existing memory.

        For each change:
        - Search for existing facts that match the field/category
        - If existing fact found with lower confidence: supersede it
        - If existing fact found with higher confidence: skip (source hierarchy)
        - If no existing fact: create new user_stated fact

        Conflict resolution: user_stated > CRM > document > web > inferred

        Args:
            user_id: The user's ID.
            changes: Dict of field changes with old/new values.

        Returns:
            List of merged fact dicts that were created or updated.
        """
        merged: list[dict[str, Any]] = []

        for field, change in changes.items():
            new_value = change["new"]
            if new_value is None:
                continue

            category = _FIELD_CATEGORY_MAP.get(field, "general")

            # Format fact text from field change
            fact_text = self._format_fact(field, new_value)

            # Search for existing facts in this category
            try:
                response = (
                    self._db.table("memory_semantic").select("*").eq("user_id", user_id).execute()
                )
                existing = response.data or []
            except Exception:
                existing = []

            # Find conflicting facts (same field/category)
            conflicting = [
                f
                for f in existing
                if isinstance(f, dict)
                and isinstance(f.get("metadata"), dict)
                and f.get("metadata", {}).get("profile_field") == field
            ]

            user_confidence = self._source_confidence("user_stated")

            for conflict in conflicting:
                existing_confidence = float(conflict.get("confidence", 0.5))
                if existing_confidence < user_confidence:
                    # Supersede: reduce confidence of old fact
                    try:
                        self._db.table("memory_semantic").update(
                            {
                                "confidence": min(existing_confidence * 0.3, 0.3),
                                "metadata": {
                                    **(conflict.get("metadata") or {}),
                                    "superseded_by_profile_update": True,
                                },
                            }
                        ).eq("id", conflict["id"]).execute()
                    except Exception as e:
                        logger.warning("Failed to supersede fact: %s", e)

            # Insert new user_stated fact
            previous_value: str | None = str(change["old"]) if change["old"] is not None else None
            metadata: dict[str, Any] = {
                "category": category,
                "profile_field": field,
                "previous_value": previous_value,
            }
            new_fact: dict[str, Any] = {
                "user_id": user_id,
                "fact": fact_text,
                "confidence": user_confidence,
                "source": "user_stated",
                "metadata": metadata,
            }

            try:
                self._db.table("memory_semantic").insert(new_fact).execute()
            except Exception as e:
                logger.warning("Failed to insert merged fact: %s", e)

            merged.append(new_fact)

        return merged

    async def _generate_delta(
        self,
        user_id: str,
        merged: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Generate Memory Delta for user confirmation.

        Uses the MemoryDeltaPresenter (US-920) to create a human-readable
        summary of what ARIA learned from this profile update.

        Args:
            user_id: The user's ID.
            merged: List of merged fact dicts.

        Returns:
            Delta dict with id and presentation data.
        """
        try:
            from src.memory.delta_presenter import MemoryDeltaPresenter

            presenter = MemoryDeltaPresenter()
            deltas = await presenter.generate_delta(user_id=user_id)

            return {
                "id": f"delta-profile-{user_id}",
                "deltas": [d.model_dump() for d in deltas],
                "facts_count": len(merged),
            }
        except Exception as e:
            logger.warning("Delta generation failed: %s", e)
            return {"id": None, "deltas": [], "facts_count": len(merged)}

    async def _recalculate_readiness(self, user_id: str) -> None:
        """Recalculate readiness scores after profile update.

        Profile changes can affect corporate_memory (company data),
        digital_twin (communication preferences), and relationship_graph
        (contact information).

        Args:
            user_id: The user's ID.
        """
        try:
            from src.onboarding.readiness import OnboardingReadinessService

            readiness_service = OnboardingReadinessService()
            await readiness_service.recalculate(user_id)
            logger.info(
                "Readiness recalculated after profile update",
                extra={"user_id": user_id},
            )
        except Exception as e:
            logger.warning(
                "Readiness recalculation failed (non-blocking)",
                extra={"user_id": user_id, "error": str(e)},
            )

    async def _audit_changes(
        self,
        user_id: str,
        changes: dict[str, dict[str, Any]],
        merged: list[dict[str, Any]],
    ) -> None:
        """Log all profile changes to the memory audit trail.

        Records before/after values, source, and timestamp for each
        field that changed. Supports compliance and debugging.

        Args:
            user_id: The user's ID.
            changes: Dict of field changes with old/new values.
            merged: List of merged fact dicts.
        """
        await log_memory_operation(
            user_id=user_id,
            operation=MemoryOperation.UPDATE,
            memory_type=MemoryType.SEMANTIC,
            metadata={
                "action": "profile_merge",
                "fields_changed": list(changes.keys()),
                "facts_merged": len(merged),
                "changes": {
                    field: {
                        "old": str(val["old"]) if val["old"] is not None else None,
                        "new": str(val["new"]) if val["new"] is not None else None,
                    }
                    for field, val in changes.items()
                },
            },
            suppress_errors=True,
        )

    def _source_confidence(self, source: str) -> float:
        """Get confidence level for a given data source.

        Implements the source hierarchy from CLAUDE.md:
        user_stated (0.95) > CRM (0.85) > document (0.80) > web (0.70) > inferred (0.55)

        Args:
            source: The data source identifier.

        Returns:
            Confidence float (0.0-1.0).
        """
        return _SOURCE_CONFIDENCE.get(source, 0.50)

    def _format_fact(self, field: str, value: Any) -> str:
        """Format a profile field change into a human-readable fact.

        Args:
            field: The profile field name.
            value: The new value.

        Returns:
            Human-readable fact string.
        """
        field_labels: dict[str, str] = {
            "full_name": "User's name is {value}",
            "title": "User's title is {value}",
            "department": "User works in the {value} department",
            "linkedin_url": "User's LinkedIn profile is {value}",
            "default_tone": "User prefers {value} communication tone",
            "tracked_competitors": "User tracks these competitors: {value}",
            "name": "Company name is {value}",
            "website": "Company website is {value}",
            "industry": "Company operates in {value}",
            "sub_vertical": "Company sub-vertical is {value}",
            "description": "Company description: {value}",
            "key_products": "Company key products/services: {value}",
        }

        template = field_labels.get(field, f"{field} is {{value}}")

        if isinstance(value, list):
            formatted_value = ", ".join(str(v) for v in value)
        else:
            formatted_value = str(value)

        return template.format(value=formatted_value)
