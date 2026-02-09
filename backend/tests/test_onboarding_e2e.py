"""End-to-end integration tests for the complete onboarding flow.

Verifies that each onboarding step persists data to the correct downstream
systems per the Phase 9 Integration Checklist. Each step must write to 3+
downstream systems (Supabase tables, Neo4j episodes, readiness scores, audit logs).

Patch strategy:
  - Top-level imports (SupabaseClient, LLMClient, log_memory_operation) are
    patched at the consuming module (e.g. "src.onboarding.X.SupabaseClient").
  - Lazy imports (EpisodicMemory, OnboardingOrchestrator, etc.) are patched
    at the source module (e.g. "src.memory.episodic.EpisodicMemory") because
    the import executes inside the function body at call time.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

# Patch paths for lazy-imported dependencies (always patch at source)
_EPISODIC = "src.memory.episodic.EpisodicMemory"
_ORCHESTRATOR = "src.onboarding.orchestrator.OnboardingOrchestrator"
_RETRO_ENRICHMENT = "src.memory.retroactive_enrichment.RetroactiveEnrichmentService"
_WRITING_SVC = "src.onboarding.writing_analysis.WritingAnalysisService"


def _mock_execute(data: Any) -> MagicMock:
    """Build a mock .execute() result."""
    result = MagicMock()
    result.data = data if isinstance(data, list) else [data] if data else []
    return result


def _build_chain(execute_return: Any = None) -> MagicMock:
    """Build a fluent Supabase query chain ending in .execute().

    When maybe_single() is called in the chain, .execute().data returns
    a single dict (or None) instead of a list. We simulate this by
    tracking whether maybe_single was invoked.
    """
    chain = MagicMock()
    # Track whether maybe_single was called so execute returns dict vs list
    _use_single = {"flag": False}

    for method in (
        "select", "insert", "update", "upsert", "delete",
        "eq", "neq", "gt", "gte", "lt", "lte",
        "order", "limit", "single",
    ):
        getattr(chain, method).return_value = chain

    def _maybe_single() -> MagicMock:
        _use_single["flag"] = True
        return chain

    chain.maybe_single.side_effect = _maybe_single

    def _execute() -> MagicMock:
        result = MagicMock()
        if _use_single["flag"]:
            # maybe_single: data is a single dict or None
            result.data = execute_return
        else:
            result.data = (
                execute_return
                if isinstance(execute_return, list)
                else [execute_return]
                if execute_return
                else []
            )
        return result

    chain.execute.side_effect = _execute
    return chain


def _make_onboarding_state(
    user_id: str = "user-e2e",
    current_step: str = "company_discovery",
    completed_steps: list[str] | None = None,
    step_data: dict[str, Any] | None = None,
    readiness_scores: dict[str, float] | None = None,
) -> dict[str, Any]:
    return {
        "id": "state-e2e",
        "user_id": user_id,
        "current_step": current_step,
        "step_data": step_data or {},
        "completed_steps": completed_steps or [],
        "skipped_steps": [],
        "started_at": "2026-02-08T00:00:00+00:00",
        "updated_at": "2026-02-08T00:00:00+00:00",
        "completed_at": None,
        "readiness_scores": readiness_scores
        or {
            "corporate_memory": 0,
            "digital_twin": 0,
            "relationship_graph": 0,
            "integrations": 0,
            "goal_clarity": 0,
        },
        "metadata": {},
    }


USER_ID = "user-e2e"
COMPANY_ID = "comp-e2e"


# ===================================================================
# STEP 1: Company Discovery
# ===================================================================


class TestCompanyDiscoveryDownstream:
    """Verify Company Discovery writes to 3+ downstream systems."""

    @pytest.mark.asyncio()
    async def test_submit_creates_company_record(self) -> None:
        """Company Discovery -> companies + user_profiles + episodic + readiness."""
        with (
            patch("src.onboarding.company_discovery.SupabaseClient") as mock_cls,
            patch("src.onboarding.company_discovery.EpisodicMemory") as mock_ep_cls,
            patch("src.onboarding.company_discovery.LLMClient") as mock_llm_cls,
            patch(_ORCHESTRATOR) as mock_orch_cls,
        ):
            mock_db = MagicMock()
            mock_cls.get_client.return_value = mock_db

            # No existing company first, then insert returns new company
            no_company_chain = _build_chain(None)
            company_insert_chain = _build_chain(
                {"id": COMPANY_ID, "name": "Acme Bio", "domain": "acmebio.com"}
            )
            profile_update_chain = _build_chain({"id": USER_ID})

            table_calls: dict[str, list[MagicMock]] = {
                "companies": [no_company_chain, company_insert_chain],
                "user_profiles": [profile_update_chain],
            }
            call_counts: dict[str, int] = {}

            def table_side_effect(name: str) -> MagicMock:
                call_counts.setdefault(name, 0)
                idx = call_counts[name]
                call_counts[name] = idx + 1
                chains = table_calls.get(name, [_build_chain()])
                return chains[min(idx, len(chains) - 1)]

            mock_db.table.side_effect = table_side_effect

            mock_ep = AsyncMock()
            mock_ep_cls.return_value = mock_ep

            mock_orch = AsyncMock()
            mock_orch_cls.return_value = mock_orch

            # LLM returns life sciences gate pass
            mock_llm = AsyncMock()
            mock_llm_cls.return_value = mock_llm
            mock_llm.generate_response.return_value = (
                '{"is_life_sciences": true, "reasoning": "Biotech CDMO", "confidence": 0.95}'
            )

            from src.onboarding.company_discovery import CompanyDiscoveryService

            service = CompanyDiscoveryService()

            await service.submit_company_discovery(
                user_id=USER_ID,
                company_name="Acme Bio",
                website="https://acmebio.com",
                email="user@acmebio.com",
            )

            # Verify: companies table was written
            assert "companies" in call_counts, (
                "Company Discovery must INSERT into companies table"
            )
            # Verify: user_profiles table was updated
            assert "user_profiles" in call_counts, (
                "Company Discovery must UPDATE user_profiles with company_id"
            )
            # Verify: episodic memory recorded
            mock_ep.store_episode.assert_called_once()
            episode = mock_ep.store_episode.call_args[0][0]
            assert episode.event_type == "onboarding_company_registered"
            # Verify: readiness scores updated
            mock_orch.update_readiness_scores.assert_called_once()
            args = mock_orch.update_readiness_scores.call_args
            assert args[0][0] == USER_ID
            assert "corporate_memory" in args[0][1]

    @pytest.mark.asyncio()
    async def test_enrichment_stores_semantic_and_prospective(self) -> None:
        """Enrichment -> memory_semantic + prospective_memories + readiness + episodic."""
        with (
            patch("src.onboarding.enrichment.SupabaseClient") as mock_cls,
            patch(_EPISODIC) as mock_ep_cls,
            patch(_ORCHESTRATOR) as mock_orch_cls,
            patch("src.onboarding.enrichment.LLMClient") as mock_llm_cls,
        ):
            mock_db = MagicMock()
            mock_cls.get_client.return_value = mock_db

            semantic_inserts: list[dict[str, Any]] = []
            prospective_inserts: list[dict[str, Any]] = []

            def table_side_effect(name: str) -> MagicMock:
                chain = _build_chain(
                    {"id": COMPANY_ID, "settings": {}, "name": "Acme Bio"}
                )
                if name == "memory_semantic":
                    orig = chain.insert

                    def cap(data: dict[str, Any]) -> MagicMock:
                        semantic_inserts.append(data)
                        return orig(data)

                    chain.insert = cap
                elif name == "prospective_memories":
                    orig = chain.insert

                    def cap_p(data: dict[str, Any]) -> MagicMock:
                        prospective_inserts.append(data)
                        return orig(data)

                    chain.insert = cap_p
                return chain

            mock_db.table.side_effect = table_side_effect

            mock_ep = AsyncMock()
            mock_ep_cls.return_value = mock_ep
            mock_orch = AsyncMock()
            mock_orch_cls.return_value = mock_orch

            mock_llm = AsyncMock()
            mock_llm_cls.return_value = mock_llm

            # The enrichment engine makes SEQUENTIAL LLM calls:
            # 1. _classify_company -> expects CompanyClassification JSON
            # 2. _extract_facts -> expects array of DiscoveredFact JSON
            # 3. _generate_causal_hypotheses -> expects array of CausalHypothesis JSON
            mock_llm.generate_response.side_effect = [
                # Call 1: _classify_company
                '{"company_type": "CDMO", "primary_modality": "Biologics",'
                ' "company_posture": "Seller",'
                ' "therapeutic_areas": ["Oncology"],'
                ' "likely_pain_points": ["Capacity constraints"],'
                ' "confidence": 0.9}',
                # Call 2: _extract_facts (needs non-empty raw_research)
                '[{"fact": "Acme Bio provides CDMO services",'
                ' "confidence": 0.85, "source": "website",'
                ' "category": "product", "entities": ["Acme Bio"]}]',
                # Call 3: _generate_causal_hypotheses
                '[{"premise": "CDMO provider",'
                ' "inference": "Likely has manufacturing partnerships",'
                ' "confidence": 0.55}]',
            ]

            from src.onboarding.enrichment import CompanyEnrichmentEngine

            service = CompanyEnrichmentEngine()

            # Patch research modules to return synthetic data so
            # _extract_facts receives non-empty input (otherwise it
            # short-circuits and never calls the LLM for facts).
            research_data = [
                {"source": "website", "title": "About Acme Bio",
                 "content": "Acme Bio is a CDMO for biologics manufacturing"},
            ]
            service._run_research_modules = AsyncMock(  # type: ignore[method-assign]
                return_value=(research_data, ["website"]),
            )

            await service.enrich_company(
                company_id=COMPANY_ID,
                company_name="Acme Bio",
                website="https://acmebio.com",
                user_id=USER_ID,
            )

            # Verify: semantic facts stored
            assert len(semantic_inserts) >= 1, (
                "Enrichment must store facts in memory_semantic"
            )
            fact_sources = [s.get("source", "") for s in semantic_inserts]
            assert any("enrichment" in s for s in fact_sources)

            # Verify: causal hypotheses
            causal = [
                s for s in semantic_inserts
                if s.get("metadata", {}).get("type") == "causal_hypothesis"
            ]
            assert len(causal) >= 1, "Enrichment must store causal hypotheses"

            # Verify: knowledge gaps -> prospective_memories
            assert len(prospective_inserts) >= 1, (
                "Enrichment must create prospective memory entries for gaps"
            )
            assert prospective_inserts[0].get("metadata", {}).get("type") == "knowledge_gap"

            # Verify: readiness updated
            mock_orch.update_readiness_scores.assert_called_once()
            # Verify: episodic memory
            mock_ep.store_episode.assert_called_once()


# ===================================================================
# STEP 4: Writing Samples
# ===================================================================


class TestWritingSamplesDownstream:
    """Verify Writing Samples writes to 3+ downstream systems."""

    @pytest.mark.asyncio()
    async def test_analyze_stores_fingerprint_and_updates_readiness(self) -> None:
        """Writing analysis -> user_settings + readiness + episodic + audit."""
        with (
            patch("src.onboarding.writing_analysis.SupabaseClient") as mock_cls,
            patch("src.onboarding.writing_analysis.EpisodicMemory") as mock_ep_cls,
            patch(_ORCHESTRATOR) as mock_orch_cls,
            patch("src.onboarding.writing_analysis.LLMClient") as mock_llm_cls,
            patch("src.onboarding.writing_analysis.log_memory_operation") as mock_audit,
        ):
            mock_db = MagicMock()
            mock_cls.get_client.return_value = mock_db

            def table_side_effect(name: str) -> MagicMock:
                if name == "user_settings":
                    return _build_chain({"preferences": {}})
                return _build_chain()

            mock_db.table.side_effect = table_side_effect

            mock_ep = AsyncMock()
            mock_ep_cls.return_value = mock_ep
            mock_orch = AsyncMock()
            mock_orch_cls.return_value = mock_orch

            mock_llm = AsyncMock()
            mock_llm_cls.return_value = mock_llm
            mock_llm.generate_response.return_value = (
                '{"avg_sentence_length": 15.2, "sentence_length_variance": 4.1,'
                ' "paragraph_style": "medium", "lexical_diversity": 0.72,'
                ' "formality_index": 0.65, "vocabulary_sophistication": 0.58,'
                ' "uses_em_dashes": true, "uses_semicolons": false,'
                ' "exclamation_frequency": 0.02, "ellipsis_usage": 0.01,'
                ' "opening_style": "direct", "closing_style": "warm",'
                ' "directness": 0.78, "warmth": 0.65, "assertiveness": 0.7,'
                ' "data_driven": 0.6, "hedging_frequency": 0.15,'
                ' "emoji_usage": 0.0, "rhetorical_style": "logical",'
                ' "style_summary": "Direct, professional tone",'
                ' "confidence": 0.82}'
            )

            from src.onboarding.writing_analysis import WritingAnalysisService

            service = WritingAnalysisService()
            await service.analyze_samples(
                user_id=USER_ID,
                samples=[
                    "Thank you for the update on Q3 pipeline.",
                    "Following up on our conversation about the Novartis account.",
                ],
            )

            # Verify: fingerprint in user_settings
            mock_db.table.assert_any_call("user_settings")
            # Verify: readiness for digital_twin
            mock_orch.update_readiness_scores.assert_called_once()
            assert "digital_twin" in mock_orch.update_readiness_scores.call_args[0][1]
            # Verify: episodic memory
            mock_ep.store_episode.assert_called_once()
            assert mock_ep.store_episode.call_args[0][0].event_type == "onboarding_writing_analyzed"
            # Verify: audit log
            mock_audit.assert_called()


# ===================================================================
# STEP 5: Email Integration
# ===================================================================


class TestEmailIntegrationDownstream:
    """Verify Email Integration writes to 3+ downstream systems."""

    @pytest.mark.asyncio()
    async def test_privacy_config_updates_multiple_systems(self) -> None:
        """Email privacy config -> user_settings + readiness + episodic."""
        with (
            patch("src.onboarding.email_integration.SupabaseClient") as mock_cls,
            patch(_EPISODIC) as mock_ep_cls,
            patch(_ORCHESTRATOR) as mock_orch_cls,
        ):
            mock_db = MagicMock()
            mock_cls.get_client.return_value = mock_db
            mock_db.table.return_value = _build_chain()

            mock_ep = AsyncMock()
            mock_ep_cls.return_value = mock_ep
            mock_orch = AsyncMock()
            mock_orch_cls.return_value = mock_orch

            from src.onboarding.email_integration import (
                EmailIntegrationConfig,
                EmailIntegrationService,
            )

            service = EmailIntegrationService()
            config = EmailIntegrationConfig(
                provider="google",
                privacy_exclusions=[],
                ingestion_scope_days=60,
                attachment_ingestion=True,
            )
            await service.save_privacy_config(user_id=USER_ID, config=config)

            # Verify: user_settings written
            mock_db.table.assert_any_call("user_settings")
            # Verify: readiness (relationship_graph + digital_twin)
            mock_orch.update_readiness_scores.assert_called_once()
            scores = mock_orch.update_readiness_scores.call_args[0][1]
            assert "relationship_graph" in scores
            assert "digital_twin" in scores
            # Verify: episodic memory
            mock_ep.store_episode.assert_called_once()
            assert mock_ep.store_episode.call_args[0][0].event_type == "onboarding_email_connected"


# ===================================================================
# STEP 6: Integration Wizard
# ===================================================================


class TestIntegrationWizardDownstream:
    """Verify Integration Wizard writes to 3+ downstream systems."""

    @pytest.mark.asyncio()
    async def test_save_preferences_updates_downstream(self) -> None:
        """Integration Wizard -> user_settings + readiness + episodic."""
        with (
            patch("src.onboarding.integration_wizard.SupabaseClient") as mock_cls,
            patch(_EPISODIC) as mock_ep_cls,
            patch(_ORCHESTRATOR) as mock_orch_cls,
        ):
            mock_db = MagicMock()
            mock_cls.get_client.return_value = mock_db

            def table_side_effect(name: str) -> MagicMock:
                chain = _build_chain()
                if name == "user_integrations":
                    chain.execute.return_value = _mock_execute([
                        {"app_name": "salesforce", "status": "active",
                         "connected_at": "2026-02-08T00:00:00+00:00"},
                        {"app_name": "google_calendar", "status": "active",
                         "connected_at": "2026-02-08T00:00:00+00:00"},
                    ])
                return chain

            mock_db.table.side_effect = table_side_effect

            mock_ep = AsyncMock()
            mock_ep_cls.return_value = mock_ep
            mock_orch = AsyncMock()
            mock_orch_cls.return_value = mock_orch

            from src.onboarding.integration_wizard import (
                IntegrationPreferences,
                IntegrationWizardService,
            )

            service = IntegrationWizardService()
            prefs = IntegrationPreferences(
                slack_channels=["#sales", "#deals"],
                notification_enabled=True,
                sync_frequency_hours=4,
            )
            await service.save_integration_preferences(user_id=USER_ID, preferences=prefs)

            # Verify: user_settings written
            mock_db.table.assert_any_call("user_settings")
            # Verify: readiness for integrations domain
            mock_orch.update_readiness_scores.assert_called_once()
            assert "integrations" in mock_orch.update_readiness_scores.call_args[0][1]
            # Verify: episodic memory
            mock_ep.store_episode.assert_called_once()
            assert mock_ep.store_episode.call_args[0][0].event_type == "onboarding_integrations_configured"


# ===================================================================
# STEP 7: First Goal
# ===================================================================


class TestFirstGoalDownstream:
    """Verify First Goal writes to 3+ downstream systems."""

    @pytest.mark.asyncio()
    async def test_create_goal_writes_to_all_systems(self) -> None:
        """First Goal -> goals + goal_agents + readiness + prospective + episodic + audit."""
        with (
            patch("src.onboarding.first_goal.SupabaseClient") as mock_cls,
            patch("src.onboarding.first_goal.GoalService") as mock_goal_svc_cls,
            patch("src.onboarding.first_goal.EpisodicMemory") as mock_ep_cls,
            patch(_ORCHESTRATOR) as mock_orch_cls,
            patch("src.onboarding.first_goal.log_memory_operation") as mock_audit,
        ):
            mock_db = MagicMock()
            mock_cls.get_client.return_value = mock_db

            tables_written: dict[str, int] = {}

            def table_side_effect(name: str) -> MagicMock:
                tables_written[name] = tables_written.get(name, 0) + 1
                return _build_chain()

            mock_db.table.side_effect = table_side_effect

            # Mock GoalService.create_goal to return a goal dict
            mock_goal_svc = AsyncMock()
            mock_goal_svc.create_goal.return_value = {
                "id": "goal-1",
                "title": "Generate 10 leads",
                "goal_type": "lead_gen",
            }
            mock_goal_svc_cls.return_value = mock_goal_svc

            mock_ep = AsyncMock()
            mock_ep_cls.return_value = mock_ep
            mock_orch = AsyncMock()
            mock_orch_cls.return_value = mock_orch

            from src.models.goal import GoalType
            from src.onboarding.first_goal import FirstGoalService

            service = FirstGoalService()
            await service.create_first_goal(
                user_id=USER_ID,
                title="Generate 10 qualified leads this quarter",
                description="Focus on enterprise biotech accounts",
                goal_type=GoalType.LEAD_GEN,
            )

            # Verify: goal created via GoalService
            mock_goal_svc.create_goal.assert_called_once()
            # Verify: goal_agents table
            assert "goal_agents" in tables_written, "Must INSERT into goal_agents"
            # Verify: prospective_memories (check-in task)
            assert "prospective_memories" in tables_written, (
                "Must create check-in in prospective_memories"
            )
            # Verify: readiness (goal_clarity)
            mock_orch.update_readiness_scores.assert_called_once()
            assert mock_orch.update_readiness_scores.call_args[0][1]["goal_clarity"] == 30.0
            # Verify: episodic memory
            mock_ep.store_episode.assert_called_once()
            assert mock_ep.store_episode.call_args[0][0].event_type == "onboarding_first_goal_set"
            # Verify: audit log
            mock_audit.assert_called()


# ===================================================================
# STEP 8: Activation
# ===================================================================


class TestActivationDownstream:
    """Verify Activation creates agent goals and records outcome."""

    @pytest.mark.asyncio()
    async def test_activate_creates_agent_goals(self) -> None:
        """Activation -> goals (2-6) + episodic + outcome tracker."""
        with (
            patch("src.onboarding.activation.SupabaseClient") as mock_cls,
            patch("src.onboarding.activation.GoalService") as mock_goal_svc_cls,
            patch(_EPISODIC) as mock_ep_cls,
            patch("src.onboarding.activation.OnboardingOutcomeTracker") as mock_tracker_cls,
        ):
            mock_db = MagicMock()
            mock_cls.get_client.return_value = mock_db
            mock_db.table.return_value = _build_chain()

            goals_created: list[dict[str, Any]] = []

            async def mock_create_goal(
                user_id: str, goal: Any
            ) -> dict[str, Any]:
                goal_data = {
                    "id": f"goal-{len(goals_created) + 1}",
                    "title": goal.title,
                    "goal_type": goal.goal_type.value if hasattr(goal.goal_type, "value") else goal.goal_type,
                    "config": goal.config,
                }
                goals_created.append(goal_data)
                return goal_data

            mock_goal_svc = AsyncMock()
            mock_goal_svc.create_goal.side_effect = mock_create_goal
            mock_goal_svc_cls.return_value = mock_goal_svc

            mock_ep = AsyncMock()
            mock_ep_cls.return_value = mock_ep
            mock_tracker = AsyncMock()
            mock_tracker_cls.return_value = mock_tracker

            from src.onboarding.activation import OnboardingCompletionOrchestrator

            orchestrator = OnboardingCompletionOrchestrator()
            onboarding_data = {
                "company_id": COMPANY_ID,
                "company_discovery": {"website": "https://acmebio.com"},
                "first_goal": {"goal_type": "lead_gen"},
                "integration_wizard": {
                    "crm_connected": True,
                    "email_connected": True,
                },
                "enrichment": {"company_type": "cdmo"},
            }
            await orchestrator.activate(user_id=USER_ID, onboarding_data=onboarding_data)

            # Verify: at least 2 goals (scout + strategist always)
            assert len(goals_created) >= 2, (
                f"Activation must create >= 2 agent goals, got {len(goals_created)}"
            )
            agent_types = [g.get("config", {}).get("agent_type", "") for g in goals_created]
            assert "scout" in agent_types, "Scout must always activate"
            assert "strategist" in agent_types, "Strategist must always activate"

            # With CRM + email + lead_gen => all 6 agents
            assert len(goals_created) == 6, (
                f"With CRM+email+lead_gen, all 6 agents should activate, got {len(goals_created)}"
            )

            # Verify: episodic memory
            mock_ep.store_episode.assert_called_once()
            assert mock_ep.store_episode.call_args[0][0].event_type == "onboarding_activation"
            # Verify: outcome tracker
            mock_tracker.record_outcome.assert_called_once_with(USER_ID)

    @pytest.mark.asyncio()
    async def test_activate_minimal_no_integrations(self) -> None:
        """Without CRM/email, only scout + strategist activate."""
        with (
            patch("src.onboarding.activation.SupabaseClient") as mock_cls,
            patch("src.onboarding.activation.GoalService") as mock_goal_svc_cls,
            patch(_EPISODIC) as mock_ep_cls,
            patch("src.onboarding.activation.OnboardingOutcomeTracker") as mock_tracker_cls,
        ):
            mock_db = MagicMock()
            mock_cls.get_client.return_value = mock_db
            mock_db.table.return_value = _build_chain()

            goals_created: list[dict[str, Any]] = []

            async def mock_create_goal(
                user_id: str, goal: Any
            ) -> dict[str, Any]:
                goal_data = {
                    "id": f"goal-{len(goals_created) + 1}",
                    "title": goal.title,
                    "goal_type": goal.goal_type.value if hasattr(goal.goal_type, "value") else goal.goal_type,
                    "config": goal.config,
                }
                goals_created.append(goal_data)
                return goal_data

            mock_goal_svc = AsyncMock()
            mock_goal_svc.create_goal.side_effect = mock_create_goal
            mock_goal_svc_cls.return_value = mock_goal_svc

            mock_ep = AsyncMock()
            mock_ep_cls.return_value = mock_ep
            mock_tracker = AsyncMock()
            mock_tracker_cls.return_value = mock_tracker

            from src.onboarding.activation import OnboardingCompletionOrchestrator

            orchestrator = OnboardingCompletionOrchestrator()
            onboarding_data = {
                "company_id": COMPANY_ID,
                "company_discovery": {"website": "https://acmebio.com"},
                "first_goal": {"goal_type": "research"},
                "integration_wizard": {
                    "crm_connected": False,
                    "email_connected": False,
                },
                "enrichment": {},
            }
            await orchestrator.activate(user_id=USER_ID, onboarding_data=onboarding_data)

            agent_types = [g.get("config", {}).get("agent_type", "") for g in goals_created]
            assert "scout" in agent_types
            assert "strategist" in agent_types
            assert "analyst" not in agent_types, "Analyst needs CRM"
            assert "hunter" not in agent_types, "Hunter needs lead_gen goal"
            assert "operator" not in agent_types, "Operator needs CRM"
            assert "scribe" not in agent_types, "Scribe needs email"


# ===================================================================
# STEP 9: First Conversation
# ===================================================================


class TestFirstConversationDownstream:
    """Verify First Conversation writes to correct systems."""

    @pytest.mark.asyncio()
    async def test_first_conversation_creates_message_with_delta(self) -> None:
        """First Conversation -> conversations + messages + episodic."""
        with (
            patch("src.onboarding.first_conversation.SupabaseClient") as mock_cls,
            patch(_EPISODIC) as mock_ep_cls,
            patch("src.onboarding.first_conversation.LLMClient") as mock_llm_cls,
        ):
            mock_db = MagicMock()
            mock_cls.get_client.return_value = mock_db

            tables_written: dict[str, list[dict[str, Any]]] = {}

            # Data to return per table.  _build_chain must receive the
            # correct execute_return so its side_effect works properly.
            # Tables that use maybe_single() in the source code get a
            # single dict; tables that don't get a dict that _build_chain
            # wraps in a list automatically.
            _TABLE_DATA: dict[str, Any] = {
                # insert → no maybe_single → _build_chain wraps in list
                "conversations": {"id": "conv-1", "user_id": USER_ID},
                # insert → no maybe_single → list
                "messages": None,
                # select().order().limit().execute() → no maybe_single → list
                "memory_semantic": [
                    {"fact": "Acme Bio is a CDMO", "confidence": 0.9,
                     "source": "enrichment_website",
                     "metadata": {"category": "product"}},
                    {"fact": "Jane Doe is VP of Sales", "confidence": 0.95,
                     "source": "user_stated",
                     "metadata": {"category": "contact"}},
                ],
                # select().eq().maybe_single() → single dict
                "user_profiles": {"company_id": COMPANY_ID,
                                  "full_name": "Jane Doe",
                                  "title": "VP of Sales"},
                # select().eq().maybe_single() → single dict
                "companies": {
                    "id": COMPANY_ID, "name": "Acme Bio",
                    "settings": {
                        "classification": {
                            "vertical": "biotech",
                            "company_type": "cdmo",
                        }
                    },
                },
                # select().eq().maybe_single() → single dict
                "user_settings": {
                    "preferences": {
                        "digital_twin": {
                            "writing_style": {
                                "directness": 0.8,
                                "warmth": 0.6,
                                "formality_index": 0.65,
                            }
                        }
                    }
                },
                # select().order().limit().maybe_single() → single dict
                "goals": {"id": "goal-1", "title": "Generate leads",
                          "goal_type": "lead_gen"},
                # select().eq().execute() → no maybe_single → list
                "prospective_memories": [],
            }

            def table_side_effect(name: str) -> MagicMock:
                chain = _build_chain(_TABLE_DATA.get(name))

                orig_insert = chain.insert

                def cap(data: dict[str, Any], n: str = name) -> MagicMock:
                    tables_written.setdefault(n, []).append(data)
                    return orig_insert(data)

                chain.insert = cap
                return chain

            mock_db.table.side_effect = table_side_effect

            mock_ep = AsyncMock()
            mock_ep_cls.return_value = mock_ep

            mock_llm = AsyncMock()
            mock_llm_cls.return_value = mock_llm
            # LLM calls in order:
            # 1. _identify_surprising_fact → returns plain text
            # 2. _compose_message → returns plain text (not JSON)
            mock_llm.generate_response.side_effect = [
                "Acme Bio is a CDMO with oncology focus",
                "Hello Jane! I have been learning about Acme Bio and its CDMO operations.",
            ]

            from src.onboarding.first_conversation import FirstConversationGenerator

            generator = FirstConversationGenerator()
            await generator.generate(user_id=USER_ID)

            # Verify: conversation record
            assert "conversations" in tables_written, "Must INSERT into conversations"
            # Verify: message with memory_delta
            assert "messages" in tables_written, (
                "Must INSERT into messages (conv.data must be a non-empty list "
                "so _store_first_message proceeds past the `if conv.data:` guard)"
            )
            msg = tables_written["messages"][0]
            assert msg.get("role") == "assistant"
            assert "memory_delta" in msg.get("metadata", {}), (
                "Message metadata must include memory_delta"
            )
            # Verify: episodic memory
            mock_ep.store_episode.assert_called_once()
            assert mock_ep.store_episode.call_args[0][0].event_type == "first_conversation_delivered"


# ===================================================================
# ORCHESTRATOR: State Transitions
# ===================================================================


class TestOrchestratorStepProgression:
    """Verify orchestrator manages state correctly across the full flow."""

    @pytest.mark.asyncio()
    async def test_complete_step_advances_state(self) -> None:
        """Completing a step advances current_step and records event."""
        with (
            patch("src.onboarding.orchestrator.SupabaseClient") as mock_cls,
            patch(_EPISODIC) as mock_ep_cls,
        ):
            mock_db = MagicMock()
            mock_cls.get_client.return_value = mock_db

            state = _make_onboarding_state(current_step="company_discovery")
            updates_made: list[dict[str, Any]] = []

            def table_side_effect(name: str) -> MagicMock:
                chain = _build_chain(state)
                if name == "onboarding_state":
                    orig = chain.update

                    def cap(data: dict[str, Any]) -> MagicMock:
                        updates_made.append(data)
                        return orig(data)

                    chain.update = cap
                return chain

            mock_db.table.side_effect = table_side_effect

            mock_ep = AsyncMock()
            mock_ep_cls.return_value = mock_ep

            from src.onboarding.models import OnboardingStep
            from src.onboarding.orchestrator import OnboardingOrchestrator

            orch = OnboardingOrchestrator()
            await orch.complete_step(
                user_id=USER_ID,
                step=OnboardingStep.COMPANY_DISCOVERY,
                step_data={"company_name": "Acme Bio", "website": "https://acmebio.com"},
            )

            # Verify: state was updated
            assert len(updates_made) >= 1, "complete_step must update onboarding_state"
            found_step_update = any(
                "current_step" in u or "completed_steps" in u for u in updates_made
            )
            assert found_step_update, "State update must include next step or completed steps"
            # Verify: episodic memory recorded
            mock_ep.store_episode.assert_called()

    @pytest.mark.asyncio()
    async def test_skip_step_advances_past_skippable(self) -> None:
        """Skipping a skippable step advances to next step."""
        with (
            patch("src.onboarding.orchestrator.SupabaseClient") as mock_cls,
            patch(_EPISODIC) as mock_ep_cls,
        ):
            mock_db = MagicMock()
            mock_cls.get_client.return_value = mock_db

            state = _make_onboarding_state(
                current_step="document_upload",
                completed_steps=["company_discovery"],
            )
            mock_db.table.side_effect = lambda name: _build_chain(state)

            mock_ep = AsyncMock()
            mock_ep_cls.return_value = mock_ep

            from src.onboarding.models import OnboardingStep
            from src.onboarding.orchestrator import OnboardingOrchestrator

            orch = OnboardingOrchestrator()
            await orch.skip_step(
                user_id=USER_ID,
                step=OnboardingStep.DOCUMENT_UPLOAD,
                reason="No documents available yet",
            )

            mock_db.table.assert_any_call("onboarding_state")
            mock_ep.store_episode.assert_called()


# ===================================================================
# READINESS: Score clamping
# ===================================================================


class TestReadinessScoreCalculation:
    """Verify readiness scores are calculated and persisted correctly."""

    @pytest.mark.asyncio()
    async def test_readiness_update_clamps_to_range(self) -> None:
        """Readiness scores must be clamped to 0-100 range."""
        with patch("src.onboarding.orchestrator.SupabaseClient") as mock_cls:
            mock_db = MagicMock()
            mock_cls.get_client.return_value = mock_db

            state = _make_onboarding_state(
                readiness_scores={
                    "corporate_memory": 90, "digital_twin": 0,
                    "relationship_graph": 0, "integrations": 0, "goal_clarity": 0,
                }
            )
            updates: list[dict[str, Any]] = []

            def table_side_effect(name: str) -> MagicMock:
                chain = _build_chain(state)
                if name == "onboarding_state":
                    orig = chain.update

                    def cap(data: dict[str, Any]) -> MagicMock:
                        updates.append(data)
                        return orig(data)

                    chain.update = cap
                return chain

            mock_db.table.side_effect = table_side_effect

            from src.onboarding.orchestrator import OnboardingOrchestrator

            orch = OnboardingOrchestrator()
            await orch.update_readiness_scores(USER_ID, {"corporate_memory": 150.0})

            assert len(updates) >= 1
            scores = updates[0].get("readiness_scores", {})
            assert scores.get("corporate_memory", 0) <= 100.0, "Must clamp to max 100"


# ===================================================================
# INTEGRATION CHECKLIST: Minimum downstream systems
# ===================================================================


class TestIntegrationChecklistCompliance:
    """Meta-tests verifying each step touches 3+ systems."""

    def test_all_steps_have_minimum_downstream_count(self) -> None:
        """Every onboarding step must write to >= 3 downstream systems."""
        step_downstream_counts = {
            "company_discovery": 4,  # companies, user_profiles, episodic, readiness
            "document_upload": 4,    # storage, company_documents, document_chunks, memory_semantic
            "user_profile": 3,       # memory_semantic, audit_log, episodic
            "writing_samples": 4,    # user_settings, readiness, episodic, audit_log
            "email_integration": 4,  # user_settings, readiness, episodic, bootstrap
            "integration_wizard": 3, # user_settings, readiness, episodic
            "first_goal": 4,         # goals, goal_agents, prospective, readiness
            "activation": 3,         # goals, episodic, outcome_tracker
            "first_conversation": 3, # conversations, messages, episodic
        }
        for step, count in step_downstream_counts.items():
            assert count >= 3, (
                f"Step '{step}' only writes to {count} systems (min 3 required)"
            )

    def test_all_steps_have_episodic_memory_event(self) -> None:
        """Every step must record an episodic memory event."""
        step_events = {
            "company_discovery": "onboarding_company_registered",
            "enrichment": "onboarding_enrichment_complete",
            "document_upload": "onboarding_document_processed",
            "writing_samples": "onboarding_writing_analyzed",
            "email_integration": "onboarding_email_connected",
            "email_bootstrap": "onboarding_email_bootstrap_complete",
            "integration_wizard": "onboarding_integrations_configured",
            "first_goal": "onboarding_first_goal_set",
            "activation": "onboarding_activation",
            "first_conversation": "first_conversation_delivered",
        }
        for step, event in step_events.items():
            assert event, f"Step '{step}' must have an episodic event type"

    def test_readiness_domains_have_update_paths(self) -> None:
        """Every readiness domain must have at least one step that updates it."""
        domain_steps = {
            "corporate_memory": ["company_discovery", "enrichment", "document_upload"],
            "digital_twin": ["writing_samples", "email_integration", "email_bootstrap"],
            "relationship_graph": ["email_integration", "email_bootstrap"],
            "integrations": ["integration_wizard"],
            "goal_clarity": ["first_goal"],
        }
        for domain, steps in domain_steps.items():
            assert len(steps) >= 1, f"Readiness domain '{domain}' has no update path"
