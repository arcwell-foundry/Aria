"""Tests for capability provisioning services."""

import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.capability import CapabilityGap, CapabilityProvider, ResolutionStrategy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_db_response(data: list[dict] | None = None):
    """Build a mock Supabase response object."""
    resp = MagicMock()
    resp.data = data or []
    return resp


def _make_provider_row(
    capability_name: str,
    provider_name: str,
    provider_type: str,
    quality_score: float,
    composio_app_name: str | None = None,
    composio_action_name: str | None = None,
    required_capabilities: list[str] | None = None,
    **kwargs,
) -> dict:
    """Build a dict that looks like a capability_graph row."""
    row = {
        "id": f"id-{provider_name}",
        "capability_name": capability_name,
        "capability_category": kwargs.get("capability_category", "research"),
        "description": kwargs.get("description", ""),
        "provider_name": provider_name,
        "provider_type": provider_type,
        "quality_score": quality_score,
        "setup_time_seconds": kwargs.get("setup_time_seconds", 0),
        "user_friction": kwargs.get("user_friction", "none"),
        "estimated_cost_per_use": kwargs.get("estimated_cost_per_use", 0),
        "composio_app_name": composio_app_name,
        "composio_action_name": composio_action_name,
        "required_capabilities": required_capabilities,
        "domain_constraint": kwargs.get("domain_constraint"),
        "limitations": kwargs.get("limitations"),
        "life_sciences_priority": kwargs.get("life_sciences_priority", False),
        "is_active": True,
        "health_status": "unknown",
    }
    return row


# ---------------------------------------------------------------------------
# CapabilityGraphService tests
# ---------------------------------------------------------------------------

class TestCapabilityGraphService:
    """Tests for CapabilityGraphService.get_best_available()."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock Supabase client with chainable query builder."""
        db = MagicMock()
        return db

    def _setup_chain(self, db, data):
        """Wire up the chainable .table().select().eq().order().execute() pattern."""
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.order.return_value = chain
        chain.limit.return_value = chain
        chain.execute.return_value = _mock_db_response(data)
        db.table.return_value = chain
        return chain

    @pytest.mark.asyncio
    async def test_get_best_available_native(self, mock_db):
        """Native provider always returns as available."""
        from src.services.capability_provisioning import CapabilityGraphService

        rows = [
            _make_provider_row("research_person", "exa_people_search", "native", 0.80),
        ]
        self._setup_chain(mock_db, rows)

        service = CapabilityGraphService(mock_db)
        result = await service.get_best_available("research_person", "user-1")

        assert result is not None
        assert result.provider_name == "exa_people_search"
        assert result.provider_type == "native"

    @pytest.mark.asyncio
    async def test_get_best_available_composio_connected(self, mock_db):
        """Returns composio provider when user has active connection."""
        from src.services.capability_provisioning import CapabilityGraphService

        rows = [
            _make_provider_row(
                "read_email", "composio_outlook", "composio_oauth", 0.95,
                composio_app_name="OUTLOOK365",
                capability_category="data_access",
            ),
        ]
        self._setup_chain(mock_db, rows)

        service = CapabilityGraphService(mock_db)

        # Mock _check_user_connection to return True
        service._check_user_connection = AsyncMock(return_value=True)

        result = await service.get_best_available("read_email", "user-1")

        assert result is not None
        assert result.provider_name == "composio_outlook"

    @pytest.mark.asyncio
    async def test_get_best_available_composio_not_connected(self, mock_db):
        """Skips composio provider when not connected, falls back to next."""
        from src.services.capability_provisioning import CapabilityGraphService

        rows = [
            _make_provider_row(
                "send_email", "composio_outlook", "composio_oauth", 0.95,
                composio_app_name="OUTLOOK365",
                capability_category="communication",
            ),
            _make_provider_row(
                "send_email", "resend_transactional", "native", 0.70,
                capability_category="communication",
            ),
        ]
        self._setup_chain(mock_db, rows)

        service = CapabilityGraphService(mock_db)
        service._check_user_connection = AsyncMock(return_value=False)

        result = await service.get_best_available("send_email", "user-1")

        assert result is not None
        assert result.provider_name == "resend_transactional"
        assert result.provider_type == "native"

    @pytest.mark.asyncio
    async def test_get_best_available_composite(self, mock_db):
        """Returns composite provider when all sub-capabilities are available."""
        from src.services.capability_provisioning import CapabilityGraphService

        rows = [
            _make_provider_row(
                "read_crm_pipeline", "email_deal_inference", "composite", 0.65,
                required_capabilities=["read_email"],
                capability_category="data_access",
            ),
        ]
        self._setup_chain(mock_db, rows)

        service = CapabilityGraphService(mock_db)

        # Mock recursive call: read_email sub-capability IS available
        original_get_best = service.get_best_available

        async def _mock_get_best(cap_name, user_id):
            if cap_name == "read_email":
                return CapabilityProvider(
                    id="id-native-email",
                    capability_name="read_email",
                    capability_category="data_access",
                    provider_name="composio_outlook",
                    provider_type="composio_oauth",
                    quality_score=0.95,
                )
            return await original_get_best(cap_name, user_id)

        service.get_best_available = _mock_get_best

        result = await service.get_best_available("read_crm_pipeline", "user-1")

        assert result is not None
        assert result.provider_name == "email_deal_inference"
        assert result.provider_type == "composite"

    @pytest.mark.asyncio
    async def test_get_best_available_composite_deps_missing(self, mock_db):
        """Skips composite when sub-capability is unavailable, falls back."""
        from src.services.capability_provisioning import CapabilityGraphService

        rows = [
            _make_provider_row(
                "read_crm_pipeline", "email_deal_inference", "composite", 0.65,
                required_capabilities=["read_email"],
                capability_category="data_access",
            ),
            _make_provider_row(
                "read_crm_pipeline", "user_stated", "user_provided", 0.50,
                capability_category="data_access",
            ),
        ]
        self._setup_chain(mock_db, rows)

        service = CapabilityGraphService(mock_db)

        # Mock recursive call: read_email NOT available
        async def _mock_get_best(cap_name, user_id):
            if cap_name == "read_email":
                return None
            # For other capabilities, use real logic
            providers = await service.get_providers(cap_name)
            for p in providers:
                if p.provider_type == "user_provided":
                    return p
            return None

        service.get_best_available = _mock_get_best

        result = await service.get_best_available("read_crm_pipeline", "user-1")

        assert result is not None
        assert result.provider_name == "user_stated"
        assert result.provider_type == "user_provided"

    @pytest.mark.asyncio
    async def test_graceful_degradation_table_missing(self, mock_db):
        """If capability_graph table query fails, log and return None."""
        from src.services.capability_provisioning import CapabilityGraphService

        mock_db.table.side_effect = Exception("relation does not exist")

        service = CapabilityGraphService(mock_db)
        result = await service.get_best_available("research_person", "user-1")

        assert result is None


class TestResolutionEngine:
    """Tests for ResolutionEngine.generate_strategies()."""

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        return db

    def _setup_chain(self, db, data):
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.order.return_value = chain
        chain.limit.return_value = chain
        chain.maybe_single.return_value = chain
        chain.execute.return_value = _mock_db_response(data)
        db.table.return_value = chain
        return chain

    @pytest.mark.asyncio
    async def test_resolution_strategies_ranked(self, mock_db):
        """Strategies sorted by quality descending."""
        from src.services.capability_provisioning import ResolutionEngine, CapabilityGraphService

        providers = [
            CapabilityProvider(**_make_provider_row(
                "read_email", "composio_outlook", "composio_oauth", 0.95,
                composio_app_name="OUTLOOK365",
                capability_category="data_access",
            )),
            CapabilityProvider(**_make_provider_row(
                "read_email", "composio_gmail", "composio_oauth", 0.95,
                composio_app_name="GMAIL",
                capability_category="data_access",
            )),
        ]

        graph = CapabilityGraphService(mock_db)
        graph._check_user_connection = AsyncMock(return_value=False)

        # No tenant config
        self._setup_chain(mock_db, [])

        engine = ResolutionEngine(mock_db, graph)
        strategies = await engine.generate_strategies("read_email", "user-1", providers)

        # Should have: 2 direct_integration + user_provided at minimum
        assert len(strategies) >= 3

        # Verify sorted by quality descending
        qualities = [s.quality for s in strategies]
        assert qualities == sorted(qualities, reverse=True)

        # Last strategy should be user_provided
        assert strategies[-1].strategy_type == "user_provided"

    @pytest.mark.asyncio
    async def test_resolution_respects_tenant_whitelist(self, mock_db):
        """Excluded toolkits not offered as resolution strategies."""
        from src.services.capability_provisioning import ResolutionEngine, CapabilityGraphService

        providers = [
            CapabilityProvider(**_make_provider_row(
                "read_email", "composio_outlook", "composio_oauth", 0.95,
                composio_app_name="OUTLOOK365",
                capability_category="data_access",
            )),
            CapabilityProvider(**_make_provider_row(
                "read_email", "composio_gmail", "composio_oauth", 0.95,
                composio_app_name="GMAIL",
                capability_category="data_access",
            )),
        ]

        graph = CapabilityGraphService(mock_db)
        graph._check_user_connection = AsyncMock(return_value=False)

        engine = ResolutionEngine(mock_db, graph)

        # Mock tenant config: only OUTLOOK365 is allowed
        engine._get_tenant_config = AsyncMock(return_value=MagicMock(
            allowed_composio_toolkits=["OUTLOOK365"],
            allowed_ecosystem_sources=["composio"],
        ))

        strategies = await engine.generate_strategies("read_email", "user-1", providers)

        # Gmail should NOT appear as a direct_integration option
        direct_strategies = [s for s in strategies if s.strategy_type == "direct_integration"]
        direct_apps = [s.composio_app for s in direct_strategies]
        assert "GMAIL" not in direct_apps
        assert "OUTLOOK365" in direct_apps


class TestGapDetectionService:
    """Tests for GapDetectionService.analyze_capabilities_for_plan()."""

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        return db

    def _setup_chain(self, db, data):
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.order.return_value = chain
        chain.limit.return_value = chain
        chain.maybe_single.return_value = chain
        chain.insert.return_value = chain
        chain.execute.return_value = _mock_db_response(data)
        db.table.return_value = chain
        return chain

    @pytest.mark.asyncio
    async def test_gap_detection_no_gaps(self, mock_db):
        """All capabilities available returns empty gaps list."""
        from src.services.capability_provisioning import (
            CapabilityGraphService,
            GapDetectionService,
            ResolutionEngine,
        )

        self._setup_chain(mock_db, [])

        graph = CapabilityGraphService(mock_db)
        engine = ResolutionEngine(mock_db, graph)
        detector = GapDetectionService(mock_db, graph, engine)

        # Mock infer to return capabilities that are all available
        detector._infer_capabilities_for_step = AsyncMock(return_value=["research_person"])

        # Mock graph to say research_person IS available at high quality
        graph.get_best_available = AsyncMock(return_value=CapabilityProvider(
            id="id-exa", capability_name="research_person",
            capability_category="research", provider_name="exa_people_search",
            provider_type="native", quality_score=0.80,
        ))
        graph.get_providers = AsyncMock(return_value=[])

        plan = {"steps": [{"description": "Research target person"}]}
        gaps = await detector.analyze_capabilities_for_plan(plan, "user-1")

        assert len(gaps) == 0

    @pytest.mark.asyncio
    async def test_gap_detection_blocking(self, mock_db):
        """Missing capability returns blocking gap."""
        from src.services.capability_provisioning import (
            CapabilityGraphService,
            GapDetectionService,
            ResolutionEngine,
        )

        self._setup_chain(mock_db, [])

        graph = CapabilityGraphService(mock_db)
        engine = ResolutionEngine(mock_db, graph)
        detector = GapDetectionService(mock_db, graph, engine)

        detector._infer_capabilities_for_step = AsyncMock(return_value=["read_crm_pipeline"])
        graph.get_best_available = AsyncMock(return_value=None)
        graph.get_providers = AsyncMock(return_value=[])
        engine.generate_strategies = AsyncMock(return_value=[
            ResolutionStrategy(
                strategy_type="user_provided",
                provider_name="ask_user",
                quality=0.40,
            )
        ])

        plan = {"steps": [{"description": "Check pipeline status"}]}
        gaps = await detector.analyze_capabilities_for_plan(plan, "user-1")

        assert len(gaps) == 1
        assert gaps[0].severity == "blocking"
        assert gaps[0].capability == "read_crm_pipeline"

    @pytest.mark.asyncio
    async def test_gap_detection_degraded(self, mock_db):
        """Low-quality available provider returns degraded gap."""
        from src.services.capability_provisioning import (
            CapabilityGraphService,
            GapDetectionService,
            ResolutionEngine,
        )

        self._setup_chain(mock_db, [])

        graph = CapabilityGraphService(mock_db)
        engine = ResolutionEngine(mock_db, graph)
        detector = GapDetectionService(mock_db, graph, engine)

        detector._infer_capabilities_for_step = AsyncMock(return_value=["read_crm_pipeline"])
        graph.get_best_available = AsyncMock(return_value=CapabilityProvider(
            id="id-user", capability_name="read_crm_pipeline",
            capability_category="data_access", provider_name="user_stated",
            provider_type="user_provided", quality_score=0.50,
        ))
        graph.get_providers = AsyncMock(return_value=[])
        engine.generate_strategies = AsyncMock(return_value=[])

        plan = {"steps": [{"description": "Check pipeline"}]}
        gaps = await detector.analyze_capabilities_for_plan(plan, "user-1")

        assert len(gaps) == 1
        assert gaps[0].severity == "degraded"
        assert gaps[0].can_proceed is True
        assert gaps[0].current_quality == 0.50


class TestProvisioningConversation:
    """Tests for ProvisioningConversation.format_gap_message()."""

    @pytest.mark.asyncio
    async def test_provisioning_message_format(self):
        """Gap message includes labeled options (A, B, C, D)."""
        from src.services.capability_provisioning import ProvisioningConversation

        gaps = [
            CapabilityGap(
                capability="read_crm_pipeline",
                step={"description": "Check existing pipeline"},
                severity="blocking",
                resolutions=[
                    ResolutionStrategy(
                        strategy_type="direct_integration",
                        provider_name="composio_salesforce",
                        quality=0.95,
                        setup_time_seconds=30,
                        composio_app="SALESFORCE",
                        action_label="Connect SALESFORCE",
                    ),
                    ResolutionStrategy(
                        strategy_type="user_provided",
                        provider_name="ask_user",
                        quality=0.40,
                        setup_time_seconds=120,
                        action_label="I'll provide it",
                    ),
                ],
            ),
        ]

        conv = ProvisioningConversation()
        message = await conv.format_gap_message(gaps, "Analyze competitive landscape")

        assert "**A.**" in message
        assert "**B.**" in message
        assert "SALESFORCE" in message
        assert "read_crm_pipeline" in message

    @pytest.mark.asyncio
    async def test_provisioning_message_empty_gaps(self):
        """Empty gaps returns empty string."""
        from src.services.capability_provisioning import ProvisioningConversation

        conv = ProvisioningConversation()
        message = await conv.format_gap_message([], "Some goal")

        assert message == ""

    @pytest.mark.asyncio
    async def test_provisioning_message_degraded_shows_upgrade(self):
        """Degraded gap message shows current quality and upgrade option."""
        from src.services.capability_provisioning import ProvisioningConversation

        gaps = [
            CapabilityGap(
                capability="read_crm_pipeline",
                step={"description": "Check pipeline"},
                severity="degraded",
                current_provider="user_stated",
                current_quality=0.50,
                can_proceed=True,
                resolutions=[
                    ResolutionStrategy(
                        strategy_type="direct_integration",
                        provider_name="composio_salesforce",
                        quality=0.95,
                        composio_app="SALESFORCE",
                        action_label="Connect SALESFORCE",
                    ),
                ],
            ),
        ]

        conv = ProvisioningConversation()
        message = await conv.format_gap_message(gaps, "Analyze pipeline")

        assert "50%" in message
        assert "95%" in message
        assert "SALESFORCE" in message


class TestDemandTracking:
    """Tests for capability demand tracking."""

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        return db

    @pytest.mark.asyncio
    async def test_demand_tracking_increments(self, mock_db):
        """Capability demand record incremented after goal execution."""
        from src.services.capability_provisioning import DemandTracker

        # Mock: existing demand row found
        existing_row = {
            "id": "demand-1",
            "times_needed": 2,
            "times_satisfied_directly": 1,
            "times_used_composite": 0,
            "times_used_fallback": 1,
            "avg_quality_achieved": 0.60,
        }

        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.limit.return_value = chain
        chain.execute.return_value = _mock_db_response([existing_row])

        update_chain = MagicMock()
        update_chain.eq.return_value = update_chain
        update_chain.execute.return_value = _mock_db_response([])
        chain.update = MagicMock(return_value=update_chain)

        mock_db.table.return_value = chain

        tracker = DemandTracker(mock_db)
        await tracker.record_capability_usage(
            user_id="user-1",
            goal_type="research",
            capabilities_used=[
                {
                    "name": "research_person",
                    "provider_type": "native",
                    "quality": 0.80,
                    "direct": True,
                },
            ],
        )

        # Verify update was called
        chain.update.assert_called_once()
        update_args = chain.update.call_args[0][0]
        assert update_args["times_needed"] == 3
        assert update_args["times_satisfied_directly"] == 2


class TestOrchestratorIntegration:
    """Test that gap detection integrates with SkillOrchestrator plans."""

    @pytest.mark.asyncio
    async def test_plan_annotated_with_gaps(self):
        """ExecutionPlan dict gets capability_gaps key when gaps exist."""
        from src.services.capability_provisioning import annotate_plan_with_gaps

        mock_db = MagicMock()
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.order.return_value = chain
        chain.limit.return_value = chain
        chain.maybe_single.return_value = chain
        chain.insert.return_value = chain
        chain.execute.return_value = _mock_db_response([])
        mock_db.table.return_value = chain

        # Plan dict (what analyze_task returns serialized)
        plan_dict = {
            "plan_id": "test-plan-1",
            "steps": [
                {"step_number": 1, "description": "Research competitors"},
            ],
        }

        # Mock the gap detector to return one blocking gap
        with patch(
            "src.services.capability_provisioning.GapDetectionService"
        ) as MockDetector:
            mock_instance = AsyncMock()
            mock_instance.analyze_capabilities_for_plan.return_value = [
                CapabilityGap(
                    capability="read_crm_pipeline",
                    step={"description": "Research competitors"},
                    severity="blocking",
                ),
            ]
            MockDetector.return_value = mock_instance

            result = await annotate_plan_with_gaps(plan_dict, "user-1", mock_db)

        assert "capability_gaps" in result
        assert result["has_blocking_gaps"] is True
        assert len(result["capability_gaps"]) == 1
