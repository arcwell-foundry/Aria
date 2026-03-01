"""ARIA Self-Provisioning: Capability Graph, Gap Detection, Resolution Engine.

This module contains the core services for ARIA's self-provisioning system:
- CapabilityGraphService: queries and resolves capability providers
- GapDetectionService: detects capability gaps during goal planning
- ResolutionEngine: generates ranked resolution strategies
- ProvisioningConversation: formats gaps as natural chat messages
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from src.models.capability import CapabilityGap, CapabilityProvider, ResolutionStrategy

logger = logging.getLogger(__name__)

# Map Composio app names to integration types in user_integrations table
_COMPOSIO_APP_TO_INTEGRATION_TYPE: dict[str, str] = {
    "OUTLOOK365": "email",
    "GMAIL": "email",
    "GOOGLE_CALENDAR": "calendar",
    "SALESFORCE": "crm",
    "HUBSPOT": "crm",
    "VEEVA_CRM": "crm",
    "SLACK": "messaging",
}


class CapabilityGraphService:
    """Manages the capability graph — what ARIA can do and at what quality."""

    def __init__(self, db_client: Any) -> None:
        self._db = db_client

    async def get_providers(self, capability_name: str) -> list[CapabilityProvider]:
        """Get all providers for a capability, sorted by quality descending."""
        try:
            result = (
                self._db.table("capability_graph")
                .select("*")
                .eq("capability_name", capability_name)
                .eq("is_active", True)
                .order("quality_score", desc=True)
                .execute()
            )
            return [CapabilityProvider(**r) for r in (result.data or [])]
        except Exception:
            logger.exception(
                "Failed to query capability_graph",
                extra={"capability_name": capability_name},
            )
            return []

    async def get_best_available(
        self, capability_name: str, user_id: str
    ) -> Optional[CapabilityProvider]:
        """Get the highest-quality available provider for a user.

        Availability rules:
        - native → always available
        - composio_oauth/api_key → user has active connection
        - composite → all required sub-capabilities are available
        - user_provided → always available (lowest quality)
        """
        try:
            providers = await self.get_providers(capability_name)
        except Exception:
            logger.exception(
                "Failed to get providers for capability",
                extra={"capability_name": capability_name},
            )
            return None

        for provider in providers:
            if provider.provider_type == "native":
                return provider

            elif provider.provider_type in ("composio_oauth", "composio_api_key"):
                connected = await self._check_user_connection(
                    user_id, provider.composio_app_name
                )
                if connected:
                    return provider

            elif provider.provider_type == "composite":
                all_available = True
                for req_cap in provider.required_capabilities or []:
                    sub = await self.get_best_available(req_cap, user_id)
                    if sub is None:
                        all_available = False
                        break
                if all_available:
                    return provider

            elif provider.provider_type == "user_provided":
                return provider

        return None

    async def _check_user_connection(
        self, user_id: str, composio_app: str | None
    ) -> bool:
        """Check if user has active Composio connection for this app.

        Uses active_integrations view (status = 'active' only).
        """
        if not composio_app:
            return False

        integration_type = _COMPOSIO_APP_TO_INTEGRATION_TYPE.get(composio_app)
        if not integration_type:
            return False

        try:
            result = (
                self._db.table("active_integrations")
                .select("id")
                .eq("user_id", user_id)
                .eq("integration_type", integration_type)
                .limit(1)
                .execute()
            )
            return len(result.data or []) > 0
        except Exception:
            logger.warning(
                "Failed to check user connection",
                extra={"user_id": user_id, "composio_app": composio_app},
            )
            return False


class ResolutionEngine:
    """Generates ranked resolution strategies for capability gaps."""

    def __init__(self, db_client: Any, capability_graph: CapabilityGraphService) -> None:
        self._db = db_client
        self._graph = capability_graph

    async def generate_strategies(
        self,
        capability_name: str,
        user_id: str,
        all_providers: list[CapabilityProvider],
    ) -> list[ResolutionStrategy]:
        """Generate ranked strategies for filling a capability gap.

        Strategy types (in order of preference):
        1. direct_integration — Connect via Composio OAuth
        2. composite — Use existing capabilities to approximate
        3. ecosystem_discovered — Search Composio for solutions
        4. user_provided — Ask the user
        """
        strategies: list[ResolutionStrategy] = []
        tenant_config = await self._get_tenant_config(user_id)

        # Strategy 1: Direct integrations not yet connected
        for provider in all_providers:
            if provider.provider_type in ("composio_oauth", "composio_api_key"):
                connected = await self._graph._check_user_connection(
                    user_id, provider.composio_app_name
                )
                if not connected:
                    if tenant_config and tenant_config.allowed_composio_toolkits:
                        if provider.composio_app_name not in tenant_config.allowed_composio_toolkits:
                            continue
                    strategies.append(
                        ResolutionStrategy(
                            strategy_type="direct_integration",
                            provider_name=provider.provider_name,
                            quality=provider.quality_score,
                            setup_time_seconds=30,
                            user_friction="low",
                            composio_app=provider.composio_app_name,
                            description=f"Connect {provider.composio_app_name} for {provider.description}",
                            action_label=f"Connect {provider.composio_app_name}",
                        )
                    )

        # Strategy 2: Composite capabilities available now
        for provider in all_providers:
            if provider.provider_type == "composite":
                all_deps_met = True
                for req_cap in provider.required_capabilities or []:
                    sub = await self._graph.get_best_available(req_cap, user_id)
                    if sub is None:
                        all_deps_met = False
                        break
                if all_deps_met:
                    strategies.append(
                        ResolutionStrategy(
                            strategy_type="composite",
                            provider_name=provider.provider_name,
                            quality=provider.quality_score,
                            setup_time_seconds=0,
                            user_friction="none",
                            description=provider.description,
                            action_label="Use automatically",
                            auto_usable=True,
                        )
                    )

        # Strategy 3: Ecosystem search (if tenant allows)
        if tenant_config is None or "composio" in (
            tenant_config.allowed_ecosystem_sources or ["composio"]
        ):
            ecosystem_results = self._search_composio_tools(capability_name)
            for result in ecosystem_results[:2]:
                strategies.append(
                    ResolutionStrategy(
                        strategy_type="ecosystem_discovered",
                        provider_name=result.get("toolkit_name", "discovered_tool"),
                        quality=0.75,
                        setup_time_seconds=60,
                        user_friction="low",
                        description=f"Found: {result.get('description', 'External tool')}",
                        action_label=f"Connect {result.get('toolkit_name', 'tool')}",
                        ecosystem_source="composio",
                        ecosystem_data=result,
                    )
                )

        # Strategy 4: User-provided (always available)
        strategies.append(
            ResolutionStrategy(
                strategy_type="user_provided",
                provider_name="ask_user",
                quality=0.40,
                setup_time_seconds=120,
                user_friction="medium",
                description="I'll ask you directly for this information",
                action_label="I'll provide it",
            )
        )

        strategies.sort(key=lambda s: s.quality, reverse=True)
        return strategies

    async def _get_tenant_config(self, user_id: str) -> Any:
        """Look up tenant governance config for this user's company."""
        try:
            # Get user's company_id from user_profiles
            profile_result = (
                self._db.table("user_profiles")
                .select("company_id")
                .eq("id", user_id)
                .limit(1)
                .maybe_single()
                .execute()
            )
            if not profile_result.data or not profile_result.data.get("company_id"):
                return None

            company_id = profile_result.data["company_id"]
            config_result = (
                self._db.table("tenant_capability_config")
                .select("*")
                .eq("tenant_id", company_id)
                .limit(1)
                .maybe_single()
                .execute()
            )
            if not config_result.data:
                return None

            # Return as a simple namespace object
            from types import SimpleNamespace
            return SimpleNamespace(**config_result.data)
        except Exception:
            logger.warning(
                "Failed to load tenant capability config",
                extra={"user_id": user_id},
            )
            return None

    def _search_composio_tools(self, capability_name: str) -> list[dict[str, Any]]:
        """Map capability names to known Composio toolkit names.

        This is a static fallback. When Composio Tool Router API becomes
        available, replace with dynamic search.
        """
        capability_to_toolkits: dict[str, list[str]] = {
            "read_crm_pipeline": ["salesforce", "hubspot", "pipedrive"],
            "read_email": ["outlook365", "gmail"],
            "read_calendar": ["google_calendar", "outlook365"],
            "send_email": ["outlook365", "gmail"],
            "monitor_competitor": ["google_alerts", "mention"],
            "track_patents": ["google_patents"],
        }
        return [
            {"toolkit_name": t, "description": f"{t} integration via Composio"}
            for t in capability_to_toolkits.get(capability_name, [])
        ]


class GapDetectionService:
    """Detects capability gaps during goal planning."""

    # Quality threshold: below this, capability is considered degraded
    _QUALITY_THRESHOLD = 0.7

    def __init__(
        self,
        db_client: Any,
        capability_graph: CapabilityGraphService,
        resolution_engine: ResolutionEngine,
    ) -> None:
        self._db = db_client
        self._graph = capability_graph
        self._resolution = resolution_engine

    async def analyze_capabilities_for_plan(
        self,
        execution_plan: dict[str, Any],
        user_id: str,
    ) -> list[CapabilityGap]:
        """Check each step's required capabilities against available providers.

        Returns gaps with severity and resolution strategies.
        """
        gaps: list[CapabilityGap] = []

        for step in execution_plan.get("steps", []):
            try:
                required = await self._infer_capabilities_for_step(step)
            except Exception:
                logger.warning(
                    "Failed to infer capabilities for step",
                    extra={"step": str(step)[:200]},
                )
                continue

            for cap_name in required:
                best = await self._graph.get_best_available(cap_name, user_id)
                all_providers = await self._graph.get_providers(cap_name)

                if best is None:
                    gaps.append(
                        CapabilityGap(
                            capability=cap_name,
                            step=step,
                            severity="blocking",
                            current_provider=None,
                            current_quality=0,
                            resolutions=await self._resolution.generate_strategies(
                                cap_name, user_id, all_providers
                            ),
                        )
                    )
                elif best.quality_score < self._QUALITY_THRESHOLD:
                    gaps.append(
                        CapabilityGap(
                            capability=cap_name,
                            step=step,
                            severity="degraded",
                            current_provider=best.provider_name,
                            current_quality=best.quality_score,
                            can_proceed=True,
                            resolutions=await self._resolution.generate_strategies(
                                cap_name, user_id, all_providers
                            ),
                        )
                    )

        # Log gaps for demand tracking (best-effort)
        for gap in gaps:
            await self._log_gap(user_id, gap)

        return gaps

    async def _infer_capabilities_for_step(
        self, step: dict[str, Any]
    ) -> list[str]:
        """Use LLM to infer which capabilities a step needs.

        Uses Haiku for cost efficiency.
        """
        try:
            # Get all unique capability names from the graph
            cap_result = self._db.table("capability_graph").select("capability_name").execute()
            unique_caps = sorted(set(r["capability_name"] for r in (cap_result.data or [])))
        except Exception:
            logger.warning("Failed to query capability names, using static list")
            unique_caps = [
                "monitor_competitor", "read_calendar", "read_crm_pipeline",
                "read_email", "research_company", "research_person",
                "research_scientific", "send_email", "track_fda_activity",
                "track_patents",
            ]

        step_desc = step.get("description", step.get("task_description", str(step)))

        prompt = (
            "Given this task step, identify which capabilities are needed.\n\n"
            f"Available capabilities: {', '.join(unique_caps)}\n\n"
            f"Task step: {step_desc}\n\n"
            "Return ONLY a JSON array of capability names needed. "
            'Example: ["research_company", "read_crm_pipeline"]'
        )

        from src.core.llm import LLMClient, TaskType

        llm = LLMClient()
        response = await llm.generate_response(
            messages=[{"role": "user", "content": prompt}],
            system_prompt="You are a capability classifier. Output only valid JSON arrays.",
            temperature=0.0,
            max_tokens=200,
            task=TaskType.SKILL_EXECUTE,
            agent_id="capability_detector",
        )

        try:
            parsed = json.loads(response.strip())
            if isinstance(parsed, list):
                return [c for c in parsed if isinstance(c, str)]
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                "Failed to parse capability inference response",
                extra={"response": response[:200]},
            )
        return []

    async def _log_gap(self, user_id: str, gap: CapabilityGap) -> None:
        """Log a detected gap to capability_gaps_log (best-effort)."""
        try:
            self._db.table("capability_gaps_log").insert({
                "user_id": user_id,
                "capability_name": gap.capability,
                "step_description": gap.step.get("description", str(gap.step)[:500]),
                "best_available_provider": gap.current_provider,
                "best_available_quality": gap.current_quality,
                "strategies_offered": [s.model_dump() for s in gap.resolutions],
                "user_response": "pending",
            }).execute()
        except Exception:
            logger.warning(
                "Failed to log capability gap",
                extra={"capability": gap.capability, "user_id": user_id},
            )
