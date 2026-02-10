"""CRM Deep Sync capability for the OperatorAgent.

Provides bidirectional CRM synchronization, pipeline anomaly monitoring,
and forecast intelligence as a composable BaseCapability. Delegates to
existing CRMSyncService, DeepSyncService, and CRMAuditService for the
heavy lifting and uses the notifications table for pipeline alerts.

HubSpot is the primary target (most common in life sciences).
"""

import logging
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from src.agents.capabilities.base import BaseCapability, CapabilityResult
from src.core.exceptions import CRMConnectionError, CRMSyncError
from src.db.supabase import SupabaseClient
from src.integrations.domain import IntegrationType
from src.integrations.oauth import get_oauth_client
from src.services.crm_audit import CRMAuditOperation, get_crm_audit_service

logger = logging.getLogger(__name__)

# ── HubSpot deal stage → ARIA lifecycle_stage mapping ──────────────────────
HUBSPOT_STAGE_MAP: dict[str, str] = {
    "appointmentscheduled": "lead",
    "qualifiedtobuy": "lead",
    "presentationscheduled": "opportunity",
    "decisionmakerboughtin": "opportunity",
    "contractsent": "opportunity",
    "closedwon": "account",
    "closedlost": "account",
}

SALESFORCE_STAGE_MAP: dict[str, str] = {
    "Prospecting": "lead",
    "Qualification": "lead",
    "Proposal": "opportunity",
    "Negotiation": "opportunity",
    "Closed Won": "account",
    "Closed Lost": "account",
}

# Fields where CRM wins (manual / structured)
CRM_WINS_FIELDS: set[str] = {
    "lifecycle_stage",
    "expected_value",
    "expected_close_date",
    "status",
}

# Fields where ARIA wins (auto-enriched / computed)
ARIA_WINS_FIELDS: set[str] = {
    "health_score",
    "insights",
    "stakeholder_map",
}

# Pipeline stage ordering for regression detection
_STAGE_ORDER: dict[str, int] = {
    "lead": 0,
    "opportunity": 1,
    "account": 2,
}

# Maximum days a deal can sit in a stage before being flagged
_MAX_DAYS_IN_STAGE: int = 30

# ── Pydantic-free result dataclasses ──────────────────────────────────────


class SyncResult:
    """Lightweight result for bidirectional sync."""

    def __init__(
        self,
        *,
        pulled: int = 0,
        pushed: int = 0,
        conflicts_resolved: int = 0,
        errors: list[dict[str, Any]] | None = None,
    ) -> None:
        self.pulled = pulled
        self.pushed = pushed
        self.conflicts_resolved = conflicts_resolved
        self.errors = errors or []

    def to_dict(self) -> dict[str, Any]:
        """Serialise to JSON-friendly dict."""
        return {
            "pulled": self.pulled,
            "pushed": self.pushed,
            "conflicts_resolved": self.conflicts_resolved,
            "errors": self.errors,
        }


class Alert:
    """A single pipeline anomaly alert."""

    def __init__(
        self,
        *,
        deal_id: str,
        deal_name: str,
        alert_type: str,
        message: str,
        severity: str = "medium",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.deal_id = deal_id
        self.deal_name = deal_name
        self.alert_type = alert_type
        self.message = message
        self.severity = severity
        self.metadata = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        """Serialise to JSON-friendly dict."""
        return {
            "deal_id": self.deal_id,
            "deal_name": self.deal_name,
            "alert_type": self.alert_type,
            "message": self.message,
            "severity": self.severity,
            "metadata": self.metadata,
        }


class ForecastReport:
    """Aggregated pipeline forecast."""

    def __init__(
        self,
        *,
        total_pipeline: float,
        weighted_pipeline: float,
        deals_by_stage: dict[str, int],
        value_by_stage: dict[str, float],
        quota_target: float | None = None,
        quota_attainment_pct: float | None = None,
        at_risk_value: float = 0.0,
        generated_at: str | None = None,
    ) -> None:
        self.total_pipeline = total_pipeline
        self.weighted_pipeline = weighted_pipeline
        self.deals_by_stage = deals_by_stage
        self.value_by_stage = value_by_stage
        self.quota_target = quota_target
        self.quota_attainment_pct = quota_attainment_pct
        self.at_risk_value = at_risk_value
        self.generated_at = generated_at or datetime.now(UTC).isoformat()

    def to_dict(self) -> dict[str, Any]:
        """Serialise to JSON-friendly dict."""
        return {
            "total_pipeline": self.total_pipeline,
            "weighted_pipeline": self.weighted_pipeline,
            "deals_by_stage": self.deals_by_stage,
            "value_by_stage": self.value_by_stage,
            "quota_target": self.quota_target,
            "quota_attainment_pct": self.quota_attainment_pct,
            "at_risk_value": self.at_risk_value,
            "generated_at": self.generated_at,
        }


# ── Stage-weight factors for weighted forecast ─────────────────────────────
_STAGE_WEIGHTS: dict[str, float] = {
    "lead": 0.10,
    "opportunity": 0.40,
    "account": 1.00,  # closed-won
}


# ── Capability implementation ──────────────────────────────────────────────


class CRMDeepSyncCapability(BaseCapability):
    """Bidirectional CRM sync, pipeline monitoring, and forecast intelligence.

    Designed primarily for HubSpot (most common in life sciences) but also
    supports Salesforce. Uses Composio for OAuth and the existing
    ``integration_sync_state`` / ``integration_sync_log`` tables for
    tracking.
    """

    capability_name: str = "crm-deep-sync"
    agent_types: list[str] = ["OperatorAgent"]
    oauth_scopes: list[str] = ["hubspot_crm", "salesforce_api"]
    data_classes: list[str] = ["INTERNAL", "CONFIDENTIAL"]

    # ── BaseCapability abstract interface ──────────────────────────────────

    async def can_handle(self, task: dict[str, Any]) -> float:
        """Return confidence for CRM-related tasks."""
        task_type = task.get("type", "")
        if task_type in {
            "crm_sync",
            "crm_deep_sync",
            "pipeline_monitor",
            "forecast",
        }:
            return 0.95
        if "crm" in task_type.lower() or "pipeline" in task_type.lower():
            return 0.7
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
            if task_type in {"crm_sync", "crm_deep_sync"}:
                result = await self.sync_bidirectional(user_id)
                data = result.to_dict()
            elif task_type == "pipeline_monitor":
                alerts = await self.monitor_pipeline(user_id)
                data = {"alerts": [a.to_dict() for a in alerts]}
            elif task_type == "forecast":
                report = await self.forecast_intelligence(user_id)
                data = report.to_dict()
            else:
                return CapabilityResult(
                    success=False,
                    error=f"Unknown task type: {task_type}",
                    execution_time_ms=int((time.monotonic() - start) * 1000),
                )

            elapsed_ms = int((time.monotonic() - start) * 1000)
            await self.log_activity(
                activity_type="crm_deep_sync",
                title=f"CRM deep-sync: {task_type}",
                description=f"Completed {task_type} for user {user_id}",
                confidence=0.85,
                metadata={"task_type": task_type, **data},
            )
            return CapabilityResult(success=True, data=data, execution_time_ms=elapsed_ms)

        except (CRMSyncError, CRMConnectionError) as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            logger.exception("CRM deep-sync capability failed")
            return CapabilityResult(
                success=False,
                error=str(exc),
                execution_time_ms=elapsed_ms,
            )

    def get_data_classes_accessed(self) -> list[str]:
        """Declare data classification levels."""
        return ["internal", "confidential"]

    # ── Public methods ─────────────────────────────────────────────────────

    async def sync_bidirectional(self, user_id: str) -> SyncResult:
        """Pull changes from CRM, push ARIA changes to CRM.

        Conflict resolution:
        - CRM wins for manual / structured fields (stage, value, date, status).
        - ARIA wins for auto-enriched fields (health_score, insights, stakeholder_map).
        Every operation is written to the ``crm_audit_log`` table.

        Args:
            user_id: Authenticated user UUID.

        Returns:
            SyncResult with pull/push counts and conflict data.
        """
        audit = get_crm_audit_service()
        client = SupabaseClient.get_client()

        # Determine CRM provider for this user
        provider, connection_id = await self._get_crm_provider(user_id)
        stage_map = HUBSPOT_STAGE_MAP if provider == "hubspot" else SALESFORCE_STAGE_MAP

        pulled = 0
        pushed = 0
        conflicts_resolved = 0
        errors: list[dict[str, Any]] = []

        # ── PULL phase ─────────────────────────────────────────────────
        try:
            deals = await self._fetch_deals(provider, connection_id)
        except Exception as exc:
            logger.exception("Failed to fetch deals from CRM")
            errors.append({"phase": "pull", "error": str(exc)})
            deals = []

        for deal in deals:
            try:
                crm_id = self._extract_deal_id(deal, provider)
                deal_name = self._extract_deal_name(deal, provider)

                # Find matching lead memory
                lead_resp = (
                    client.table("lead_memories")
                    .select("*")
                    .eq("user_id", user_id)
                    .eq("crm_id", crm_id)
                    .maybe_single()
                    .execute()
                )

                if not lead_resp.data:
                    # No local lead — skip (will be created via DeepSyncService)
                    continue

                lead = lead_resp.data
                lead_id = str(lead["id"])
                updates: dict[str, Any] = {}

                # Compare fields and resolve conflicts
                field_mappings = self._get_field_mappings(provider)
                for crm_field, aria_field in field_mappings.items():
                    crm_value = deal.get(crm_field)
                    if crm_value is None:
                        continue
                    aria_value = lead.get(aria_field)

                    if crm_value == aria_value:
                        continue

                    # Transform lifecycle_stage through stage map
                    resolved_crm_value = crm_value
                    if aria_field == "lifecycle_stage":
                        resolved_crm_value = stage_map.get(str(crm_value), str(crm_value))

                    winner = self._resolve_field(aria_field)

                    if winner == "crm":
                        updates[aria_field] = resolved_crm_value
                        conflicts_resolved += 1
                        await audit.log_conflict(
                            user_id=user_id,
                            lead_memory_id=lead_id,
                            provider=provider,
                            field=aria_field,
                            aria_value=aria_value,
                            crm_value=crm_value,
                            resolution="crm_wins",
                            resolved_value=resolved_crm_value,
                        )
                    else:
                        # ARIA wins — queue push for this field later
                        conflicts_resolved += 1
                        await audit.log_conflict(
                            user_id=user_id,
                            lead_memory_id=lead_id,
                            provider=provider,
                            field=aria_field,
                            aria_value=aria_value,
                            crm_value=crm_value,
                            resolution="aria_wins",
                            resolved_value=aria_value,
                        )

                if updates:
                    updates["updated_at"] = datetime.now(UTC).isoformat()
                    client.table("lead_memories").update(updates).eq("id", lead_id).eq(
                        "user_id", user_id
                    ).execute()
                    pulled += 1

                    await audit.log_sync_operation(
                        user_id=user_id,
                        lead_memory_id=lead_id,
                        operation=CRMAuditOperation.PULL,
                        provider=provider,
                        success=True,
                        details={
                            "fields_updated": list(updates.keys()),
                            "deal_name": deal_name,
                        },
                    )

            except Exception as exc:
                logger.warning(
                    "Failed to pull deal",
                    extra={"deal": deal, "error": str(exc)},
                )
                errors.append({"phase": "pull", "deal": str(deal.get("id", "")), "error": str(exc)})

        # ── PUSH phase ─────────────────────────────────────────────────
        # Push ARIA-enriched fields back to CRM for leads that have crm_id
        try:
            leads_resp = (
                client.table("lead_memories")
                .select("id, crm_id, crm_provider, health_score, insights, stakeholder_map")
                .eq("user_id", user_id)
                .not_.is_("crm_id", "null")
                .execute()
            )
            leads_to_push = leads_resp.data or []
        except Exception as exc:
            logger.warning("Failed to query leads for push", extra={"error": str(exc)})
            leads_to_push = []

        oauth_client = get_oauth_client()
        for lead in leads_to_push:
            try:
                crm_id = str(lead["crm_id"])
                lead_provider = str(lead.get("crm_provider", provider))
                lead_id = str(lead["id"])
                health_score = lead.get("health_score")

                if health_score is None:
                    continue

                # Push health score as a custom field note
                tagged_note = (
                    f"[ARIA] Health Score: {health_score}/100 "
                    f"(updated {datetime.now(UTC).strftime('%Y-%m-%d %H:%M')} UTC)"
                )

                if lead_provider == "hubspot":
                    action = "hubspot_create_note"
                    params = {
                        "object_id": crm_id,
                        "object_type": "deal",
                        "content": tagged_note,
                    }
                else:
                    action = "salesforce_create_note"
                    params = {
                        "parent_id": crm_id,
                        "title": f"ARIA Health Update - {datetime.now(UTC).strftime('%Y-%m-%d')}",
                        "body": tagged_note,
                    }

                await oauth_client.execute_action(
                    connection_id=connection_id,
                    action=action,
                    params=params,
                )
                pushed += 1

                await audit.log_sync_operation(
                    user_id=user_id,
                    lead_memory_id=lead_id,
                    operation=CRMAuditOperation.PUSH,
                    provider=lead_provider,
                    success=True,
                    details={"action": action, "health_score": health_score},
                )

            except Exception as exc:
                logger.warning(
                    "Failed to push lead to CRM",
                    extra={"lead_id": lead.get("id"), "error": str(exc)},
                )
                errors.append(
                    {
                        "phase": "push",
                        "lead_id": str(lead.get("id", "")),
                        "error": str(exc),
                    }
                )

        # ── Update sync state ──────────────────────────────────────────
        now = datetime.now(UTC)
        integration_type = (
            IntegrationType.HUBSPOT if provider == "hubspot" else IntegrationType.SALESFORCE
        )
        await self._update_sync_state(
            user_id=user_id,
            integration_type=integration_type,
            status="success" if not errors else "partial",
            next_sync_at=now + timedelta(minutes=15),
        )

        await self._log_sync(
            user_id=user_id,
            integration_type=integration_type,
            sync_type="bidirectional",
            status="success" if not errors else "partial",
            records_processed=pulled + pushed,
            records_succeeded=pulled + pushed - len(errors),
            records_failed=len(errors),
            error_details={"errors": errors} if errors else None,
        )

        return SyncResult(
            pulled=pulled,
            pushed=pushed,
            conflicts_resolved=conflicts_resolved,
            errors=errors,
        )

    async def monitor_pipeline(self, user_id: str) -> list[Alert]:
        """Detect pipeline anomalies and write alerts to notifications.

        Anomaly types:
        - ``deal_stuck``: Deal has not moved stages for > 30 days.
        - ``deal_backward``: Deal moved to an earlier stage.
        - ``close_date_passed``: Expected close date is in the past.

        Args:
            user_id: Authenticated user UUID.

        Returns:
            List of Alert objects (also persisted to notifications table).
        """
        client = SupabaseClient.get_client()
        alerts: list[Alert] = []
        now = datetime.now(UTC)

        # Fetch all active leads with CRM data
        resp = (
            client.table("lead_memories")
            .select(
                "id, company_name, crm_id, lifecycle_stage, expected_close_date, updated_at, metadata"
            )
            .eq("user_id", user_id)
            .not_.is_("crm_id", "null")
            .execute()
        )
        leads = resp.data or []

        for lead in leads:
            lead_id = str(lead["id"])
            deal_name = str(lead.get("company_name", "Unknown"))
            crm_id = str(lead.get("crm_id", ""))
            stage = str(lead.get("lifecycle_stage", ""))
            close_date_str = lead.get("expected_close_date")
            updated_at_str = lead.get("updated_at")

            # ── Check: deal stuck ──────────────────────────────────────
            if updated_at_str and stage not in {"account", "closedwon", "closedlost"}:
                try:
                    updated_at = datetime.fromisoformat(str(updated_at_str).replace("Z", "+00:00"))
                    days_since = (now - updated_at).days
                    if days_since > _MAX_DAYS_IN_STAGE:
                        alert = Alert(
                            deal_id=crm_id,
                            deal_name=deal_name,
                            alert_type="deal_stuck",
                            message=(
                                f"{deal_name} has been in '{stage}' stage for "
                                f"{days_since} days without updates."
                            ),
                            severity="high" if days_since > 60 else "medium",
                            metadata={"lead_id": lead_id, "days_stuck": days_since},
                        )
                        alerts.append(alert)
                except (ValueError, TypeError):
                    pass

            # ── Check: deal moving backward ────────────────────────────
            metadata = lead.get("metadata") or {}
            previous_stage = metadata.get("crm_previous_stage")
            if previous_stage and stage:
                prev_order = _STAGE_ORDER.get(previous_stage, -1)
                curr_order = _STAGE_ORDER.get(stage, -1)
                if prev_order > curr_order >= 0:
                    alert = Alert(
                        deal_id=crm_id,
                        deal_name=deal_name,
                        alert_type="deal_backward",
                        message=(
                            f"{deal_name} moved backward from '{previous_stage}' to '{stage}'."
                        ),
                        severity="high",
                        metadata={
                            "lead_id": lead_id,
                            "previous_stage": previous_stage,
                            "current_stage": stage,
                        },
                    )
                    alerts.append(alert)

            # ── Check: expected close date passed ──────────────────────
            if close_date_str and stage not in {"account", "closedwon", "closedlost"}:
                try:
                    close_date = datetime.fromisoformat(str(close_date_str).replace("Z", "+00:00"))
                    if close_date < now:
                        days_overdue = (now - close_date).days
                        alert = Alert(
                            deal_id=crm_id,
                            deal_name=deal_name,
                            alert_type="close_date_passed",
                            message=(
                                f"{deal_name} expected close date was "
                                f"{close_date.strftime('%Y-%m-%d')}, "
                                f"{days_overdue} days ago."
                            ),
                            severity="high" if days_overdue > 14 else "medium",
                            metadata={"lead_id": lead_id, "days_overdue": days_overdue},
                        )
                        alerts.append(alert)
                except (ValueError, TypeError):
                    pass

        # ── Persist alerts to notifications table ──────────────────────
        for alert in alerts:
            try:
                client.table("notifications").insert(
                    {
                        "id": str(uuid.uuid4()),
                        "user_id": user_id,
                        "type": "signal_detected",
                        "title": f"Pipeline Alert: {alert.alert_type.replace('_', ' ').title()}",
                        "message": alert.message,
                        "metadata": {
                            "alert_type": alert.alert_type,
                            "severity": alert.severity,
                            "deal_id": alert.deal_id,
                            **alert.metadata,
                        },
                    }
                ).execute()
            except Exception as exc:
                logger.warning(
                    "Failed to persist pipeline alert",
                    extra={"alert": alert.to_dict(), "error": str(exc)},
                )

        logger.info(
            "Pipeline monitoring complete",
            extra={"user_id": user_id, "alerts_count": len(alerts)},
        )
        return alerts

    async def forecast_intelligence(self, user_id: str) -> ForecastReport:
        """Aggregate pipeline data and compare to user quotas.

        Calculates:
        - Total pipeline value across all active deals.
        - Weighted pipeline using stage-based probability weights.
        - Deal counts and value broken down by stage.
        - Quota attainment percentage (if a quota exists for the current period).
        - At-risk value (deals with alerts from monitor_pipeline).

        Args:
            user_id: Authenticated user UUID.

        Returns:
            ForecastReport with aggregated metrics.
        """
        client = SupabaseClient.get_client()
        now = datetime.now(UTC)

        # Fetch all leads with pipeline data
        resp = (
            client.table("lead_memories")
            .select("id, lifecycle_stage, expected_value, expected_close_date, updated_at")
            .eq("user_id", user_id)
            .not_.is_("crm_id", "null")
            .execute()
        )
        leads = resp.data or []

        total_pipeline = 0.0
        weighted_pipeline = 0.0
        deals_by_stage: dict[str, int] = {}
        value_by_stage: dict[str, float] = {}
        at_risk_value = 0.0

        for lead in leads:
            stage = str(lead.get("lifecycle_stage", "lead"))
            value = float(lead.get("expected_value") or 0)
            close_date_str = lead.get("expected_close_date")
            updated_at_str = lead.get("updated_at")

            # Skip closed-lost deals
            if stage in {"closedlost"}:
                continue

            total_pipeline += value
            weight = _STAGE_WEIGHTS.get(stage, 0.10)
            weighted_pipeline += value * weight

            deals_by_stage[stage] = deals_by_stage.get(stage, 0) + 1
            value_by_stage[stage] = value_by_stage.get(stage, 0.0) + value

            # Flag at-risk if stuck or overdue
            is_at_risk = False
            if updated_at_str and stage not in {"account", "closedwon"}:
                try:
                    updated_at = datetime.fromisoformat(str(updated_at_str).replace("Z", "+00:00"))
                    if (now - updated_at).days > _MAX_DAYS_IN_STAGE:
                        is_at_risk = True
                except (ValueError, TypeError):
                    pass

            if close_date_str and stage not in {"account", "closedwon"}:
                try:
                    close_date = datetime.fromisoformat(str(close_date_str).replace("Z", "+00:00"))
                    if close_date < now:
                        is_at_risk = True
                except (ValueError, TypeError):
                    pass

            if is_at_risk:
                at_risk_value += value

        # ── Fetch quota for current period ─────────────────────────────
        current_period = f"{now.year}-Q{(now.month - 1) // 3 + 1}"
        quota_target: float | None = None
        quota_attainment_pct: float | None = None

        try:
            quota_resp = (
                client.table("user_quotas")
                .select("target_value, actual_value")
                .eq("user_id", user_id)
                .eq("period", current_period)
                .maybe_single()
                .execute()
            )
            if quota_resp.data:
                quota_target = float(quota_resp.data.get("target_value", 0))
                actual_value = float(quota_resp.data.get("actual_value", 0))
                if quota_target > 0:
                    quota_attainment_pct = round((actual_value / quota_target) * 100, 1)
        except Exception as exc:
            logger.warning(
                "Failed to fetch quota",
                extra={"user_id": user_id, "period": current_period, "error": str(exc)},
            )

        return ForecastReport(
            total_pipeline=round(total_pipeline, 2),
            weighted_pipeline=round(weighted_pipeline, 2),
            deals_by_stage=deals_by_stage,
            value_by_stage={k: round(v, 2) for k, v in value_by_stage.items()},
            quota_target=quota_target,
            quota_attainment_pct=quota_attainment_pct,
            at_risk_value=round(at_risk_value, 2),
        )

    # ── Private helpers ────────────────────────────────────────────────────

    async def _get_crm_provider(self, user_id: str) -> tuple[str, str]:
        """Return ``(provider_name, composio_connection_id)`` for the user.

        Tries HubSpot first (primary for life sciences), then Salesforce.

        Raises:
            CRMConnectionError: If no CRM integration is connected.
        """
        client = SupabaseClient.get_client()

        for provider in ("hubspot", "salesforce"):
            resp = (
                client.table("user_integrations")
                .select("composio_connection_id")
                .eq("user_id", user_id)
                .eq("integration_type", provider)
                .eq("status", "active")
                .maybe_single()
                .execute()
            )
            if resp.data and resp.data.get("composio_connection_id"):
                return provider, str(resp.data["composio_connection_id"])

        raise CRMConnectionError(
            provider="crm",
            message="No active CRM integration (HubSpot or Salesforce) found for user",
        )

    async def _fetch_deals(self, provider: str, connection_id: str) -> list[dict[str, Any]]:
        """Fetch deals/opportunities from CRM via Composio."""
        oauth_client = get_oauth_client()

        action = "hubspot_get_deals" if provider == "hubspot" else "salesforce_get_opportunities"

        result = await oauth_client.execute_action(
            connection_id=connection_id,
            action=action,
            params={},
        )
        deals = result.get("data", [])
        return deals if isinstance(deals, list) else []

    @staticmethod
    def _extract_deal_id(deal: dict[str, Any], provider: str) -> str:
        """Extract the external deal ID from CRM payload."""
        if provider == "hubspot":
            return str(deal.get("dealId") or deal.get("id", ""))
        return str(deal.get("Id") or deal.get("id", ""))

    @staticmethod
    def _extract_deal_name(deal: dict[str, Any], provider: str) -> str:
        """Extract human-readable deal name from CRM payload."""
        if provider == "hubspot":
            return str(deal.get("dealname") or deal.get("properties", {}).get("dealname", ""))
        return str(deal.get("Name") or deal.get("name", ""))

    @staticmethod
    def _get_field_mappings(provider: str) -> dict[str, str]:
        """CRM field → ARIA field name mappings."""
        if provider == "salesforce":
            return {
                "StageName": "lifecycle_stage",
                "Amount": "expected_value",
                "CloseDate": "expected_close_date",
                "Status__c": "status",
            }
        return {
            "dealstage": "lifecycle_stage",
            "amount": "expected_value",
            "closedate": "expected_close_date",
            "hs_deal_status": "status",
        }

    @staticmethod
    def _resolve_field(aria_field: str) -> str:
        """Return ``'crm'`` or ``'aria'`` indicating who wins for *field*."""
        if aria_field in CRM_WINS_FIELDS:
            return "crm"
        if aria_field in ARIA_WINS_FIELDS:
            return "aria"
        # Default: ARIA wins for unknown computed fields
        return "aria"

    async def _update_sync_state(
        self,
        user_id: str,
        integration_type: IntegrationType,
        status: str,
        next_sync_at: datetime | None,
        error_message: str | None = None,
    ) -> None:
        """Upsert into ``integration_sync_state``."""
        try:
            client = SupabaseClient.get_client()
            now = datetime.now(UTC)

            existing = (
                client.table("integration_sync_state")
                .select("id")
                .eq("user_id", user_id)
                .eq("integration_type", integration_type.value)
                .maybe_single()
                .execute()
            )

            data: dict[str, Any] = {
                "user_id": user_id,
                "integration_type": integration_type.value,
                "last_sync_at": now.isoformat(),
                "last_sync_status": status,
                "last_sync_error": error_message,
                "next_sync_at": next_sync_at.isoformat() if next_sync_at else None,
                "updated_at": now.isoformat(),
            }

            if existing.data:
                client.table("integration_sync_state").update(data).eq("user_id", user_id).eq(
                    "integration_type", integration_type.value
                ).execute()
            else:
                data["id"] = str(uuid.uuid4())
                data["created_at"] = now.isoformat()
                client.table("integration_sync_state").insert(data).execute()

        except Exception as exc:
            logger.warning(
                "Failed to update sync state",
                extra={
                    "user_id": user_id,
                    "integration_type": integration_type.value,
                    "error": str(exc),
                },
            )

    async def _log_sync(
        self,
        user_id: str,
        integration_type: IntegrationType,
        sync_type: str,
        status: str,
        records_processed: int,
        records_succeeded: int,
        records_failed: int,
        error_details: dict[str, Any] | None = None,
    ) -> None:
        """Insert into ``integration_sync_log``."""
        try:
            client = SupabaseClient.get_client()
            now = datetime.now(UTC)

            client.table("integration_sync_log").insert(
                {
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "integration_type": integration_type.value,
                    "sync_type": sync_type,
                    "status": status,
                    "records_processed": records_processed,
                    "records_succeeded": records_succeeded,
                    "records_failed": records_failed,
                    "error_details": error_details,
                    "completed_at": now.isoformat(),
                    "created_at": now.isoformat(),
                }
            ).execute()
        except Exception as exc:
            logger.warning(
                "Failed to log sync operation",
                extra={
                    "user_id": user_id,
                    "integration_type": integration_type.value,
                    "error": str(exc),
                },
            )
