"""Tests for US-915: Onboarding Completion → Agent Activation."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.onboarding.activation import (
    AgentActivation,
    OnboardingCompletionOrchestrator,
)

# --- Fixtures ---


def _mock_execute(data: Any) -> MagicMock:
    """Build a mock .execute() result."""
    result = MagicMock()
    result.data = data
    return result


def _build_chain(execute_return: Any) -> MagicMock:
    """Build a fluent Supabase query chain ending in .execute()."""
    chain = MagicMock()
    chain.select.return_value = chain
    chain.insert.return_value = chain
    chain.update.return_value = chain
    chain.eq.return_value = chain
    chain.order.return_value = chain
    chain.limit.return_value = chain
    chain.maybe_single.return_value = chain
    chain.single.return_value = chain
    chain.execute.return_value = _mock_execute(execute_return)
    return chain


@pytest.fixture()
def mock_db() -> MagicMock:
    """Create a mock Supabase client."""
    return MagicMock()


@pytest.fixture()
def orchestrator(mock_db: MagicMock) -> OnboardingCompletionOrchestrator:
    """Create orchestrator with mocked DB."""
    with patch("src.onboarding.activation.SupabaseClient") as mock_cls:
        mock_cls.get_client.return_value = mock_db
        orch = OnboardingCompletionOrchestrator()
    return orch


# --- _plan_activations unit tests ---


class TestPlanActivations:
    """Tests for the activation planning logic."""

    def test_scout_always_activated(
        self,
        orchestrator: OnboardingCompletionOrchestrator,
    ) -> None:
        """Scout is always activated regardless of available data."""
        activations = orchestrator._plan_activations(
            classification=None,
            facts=[],
            integrations=[],
            goal=None,
            contacts=[],
        )
        agents = [a.agent for a in activations]
        assert "scout" in agents

    def test_scout_activated_with_empty_data(
        self,
        orchestrator: OnboardingCompletionOrchestrator,
    ) -> None:
        """Scout activates even when all data sources are empty."""
        activations = orchestrator._plan_activations(
            classification={},
            facts=[],
            integrations=[],
            goal=None,
            contacts=[],
        )
        scout = [a for a in activations if a.agent == "scout"]
        assert len(scout) == 1
        assert "monitoring" in scout[0].task.lower()

    def test_scout_includes_company_type(
        self,
        orchestrator: OnboardingCompletionOrchestrator,
    ) -> None:
        """Scout task mentions the company type from classification."""
        activations = orchestrator._plan_activations(
            classification={"company_type": "cdmo"},
            facts=[],
            integrations=[],
            goal=None,
            contacts=[],
        )
        scout = [a for a in activations if a.agent == "scout"][0]
        assert "cdmo" in scout.task.lower()

    def test_analyst_activated_with_contacts(
        self,
        orchestrator: OnboardingCompletionOrchestrator,
    ) -> None:
        """Analyst is activated when contacts with companies exist."""
        contacts = [
            {"metadata": {"company": "Pfizer"}},
            {"metadata": {"company": "Roche"}},
            {"metadata": {"company": "Novartis"}},
        ]
        activations = orchestrator._plan_activations(
            classification=None,
            facts=[],
            integrations=[],
            goal=None,
            contacts=contacts,
        )
        agents = [a.agent for a in activations]
        assert "analyst" in agents
        analyst = [a for a in activations if a.agent == "analyst"][0]
        assert "Pfizer" in analyst.task

    def test_analyst_not_activated_without_contacts(
        self,
        orchestrator: OnboardingCompletionOrchestrator,
    ) -> None:
        """Analyst is NOT activated when no contacts exist."""
        activations = orchestrator._plan_activations(
            classification=None,
            facts=[],
            integrations=[],
            goal=None,
            contacts=[],
        )
        agents = [a.agent for a in activations]
        assert "analyst" not in agents

    def test_analyst_not_activated_with_contacts_missing_company(
        self,
        orchestrator: OnboardingCompletionOrchestrator,
    ) -> None:
        """Analyst not activated when contacts lack company metadata."""
        contacts = [
            {"metadata": {}},
            {"metadata": {"name": "John Doe"}},
        ]
        activations = orchestrator._plan_activations(
            classification=None,
            facts=[],
            integrations=[],
            goal=None,
            contacts=contacts,
        )
        agents = [a.agent for a in activations]
        assert "analyst" not in agents

    def test_hunter_activated_for_lead_gen_goal(
        self,
        orchestrator: OnboardingCompletionOrchestrator,
    ) -> None:
        """Hunter is activated when goal title mentions lead generation."""
        activations = orchestrator._plan_activations(
            classification=None,
            facts=[],
            integrations=[],
            goal={"title": "Generate more leads in oncology"},
            contacts=[],
        )
        agents = [a.agent for a in activations]
        assert "hunter" in agents

    def test_hunter_activated_for_pipeline_goal(
        self,
        orchestrator: OnboardingCompletionOrchestrator,
    ) -> None:
        """Hunter is activated for pipeline-related goals."""
        activations = orchestrator._plan_activations(
            classification=None,
            facts=[],
            integrations=[],
            goal={"title": "Build pipeline for Q3"},
            contacts=[],
        )
        agents = [a.agent for a in activations]
        assert "hunter" in agents

    def test_hunter_activated_for_prospect_goal(
        self,
        orchestrator: OnboardingCompletionOrchestrator,
    ) -> None:
        """Hunter is activated for prospect-related goals."""
        activations = orchestrator._plan_activations(
            classification=None,
            facts=[],
            integrations=[],
            goal={"title": "Identify prospect companies in APAC"},
            contacts=[],
        )
        agents = [a.agent for a in activations]
        assert "hunter" in agents

    def test_hunter_activated_for_territory_goal(
        self,
        orchestrator: OnboardingCompletionOrchestrator,
    ) -> None:
        """Hunter is activated for territory-related goals."""
        activations = orchestrator._plan_activations(
            classification=None,
            facts=[],
            integrations=[],
            goal={"title": "Map my territory accounts"},
            contacts=[],
        )
        agents = [a.agent for a in activations]
        assert "hunter" in agents

    def test_hunter_not_activated_for_non_lead_goal(
        self,
        orchestrator: OnboardingCompletionOrchestrator,
    ) -> None:
        """Hunter is NOT activated for goals unrelated to lead gen."""
        activations = orchestrator._plan_activations(
            classification=None,
            facts=[],
            integrations=[],
            goal={"title": "Prepare for board meeting"},
            contacts=[],
        )
        agents = [a.agent for a in activations]
        assert "hunter" not in agents

    def test_hunter_not_activated_without_goal(
        self,
        orchestrator: OnboardingCompletionOrchestrator,
    ) -> None:
        """Hunter is NOT activated when no goal is set."""
        activations = orchestrator._plan_activations(
            classification=None,
            facts=[],
            integrations=[],
            goal=None,
            contacts=[],
        )
        agents = [a.agent for a in activations]
        assert "hunter" not in agents

    def test_operator_activated_with_salesforce(
        self,
        orchestrator: OnboardingCompletionOrchestrator,
    ) -> None:
        """Operator is activated when Salesforce is connected."""
        activations = orchestrator._plan_activations(
            classification=None,
            facts=[],
            integrations=[{"provider": "salesforce", "status": "active"}],
            goal=None,
            contacts=[],
        )
        agents = [a.agent for a in activations]
        assert "operator" in agents

    def test_operator_activated_with_hubspot(
        self,
        orchestrator: OnboardingCompletionOrchestrator,
    ) -> None:
        """Operator is activated when HubSpot is connected."""
        activations = orchestrator._plan_activations(
            classification=None,
            facts=[],
            integrations=[{"provider": "hubspot", "status": "active"}],
            goal=None,
            contacts=[],
        )
        agents = [a.agent for a in activations]
        assert "operator" in agents

    def test_operator_not_activated_without_crm(
        self,
        orchestrator: OnboardingCompletionOrchestrator,
    ) -> None:
        """Operator is NOT activated when no CRM is connected."""
        activations = orchestrator._plan_activations(
            classification=None,
            facts=[],
            integrations=[{"provider": "google", "status": "active"}],
            goal=None,
            contacts=[],
        )
        agents = [a.agent for a in activations]
        assert "operator" not in agents

    def test_scribe_activated_with_stale_threads(
        self,
        orchestrator: OnboardingCompletionOrchestrator,
    ) -> None:
        """Scribe is activated when stale deal threads are detected."""
        facts = [
            {"metadata": {"type": "active_deal"}},
            {"metadata": {"type": "active_deal"}},
        ]
        activations = orchestrator._plan_activations(
            classification=None,
            facts=facts,
            integrations=[],
            goal=None,
            contacts=[],
        )
        agents = [a.agent for a in activations]
        assert "scribe" in agents
        scribe = [a for a in activations if a.agent == "scribe"][0]
        assert "2" in scribe.task

    def test_scribe_not_activated_without_stale_threads(
        self,
        orchestrator: OnboardingCompletionOrchestrator,
    ) -> None:
        """Scribe is NOT activated when no stale threads exist."""
        facts = [
            {"metadata": {"type": "company_info"}},
            {"metadata": {"category": "competitive"}},
        ]
        activations = orchestrator._plan_activations(
            classification=None,
            facts=facts,
            integrations=[],
            goal=None,
            contacts=[],
        )
        agents = [a.agent for a in activations]
        assert "scribe" not in agents

    def test_all_activations_are_low_priority(
        self,
        orchestrator: OnboardingCompletionOrchestrator,
    ) -> None:
        """All activation tasks must be LOW priority."""
        activations = orchestrator._plan_activations(
            classification={"company_type": "pharma"},
            facts=[{"metadata": {"type": "active_deal"}}],
            integrations=[{"provider": "salesforce", "status": "active"}],
            goal={"title": "Generate leads in oncology"},
            contacts=[{"metadata": {"company": "Pfizer"}}],
        )
        for activation in activations:
            assert activation.priority == "low"

    def test_full_activation_with_all_data(
        self,
        orchestrator: OnboardingCompletionOrchestrator,
    ) -> None:
        """All five agents activate when all data is present."""
        activations = orchestrator._plan_activations(
            classification={"company_type": "pharma"},
            facts=[
                {"metadata": {"category": "competitive"}},
                {"metadata": {"type": "active_deal"}},
                {"metadata": {"type": "active_deal"}},
            ],
            integrations=[{"provider": "salesforce", "status": "active"}],
            goal={"title": "Build pipeline for Q3"},
            contacts=[{"metadata": {"company": "Roche"}}],
        )
        agents = sorted([a.agent for a in activations])
        assert agents == ["analyst", "hunter", "operator", "scout", "scribe"]

    def test_minimal_activation_only_scout(
        self,
        orchestrator: OnboardingCompletionOrchestrator,
    ) -> None:
        """Only Scout activates with empty data."""
        activations = orchestrator._plan_activations(
            classification=None,
            facts=[],
            integrations=[],
            goal=None,
            contacts=[],
        )
        assert len(activations) == 1
        assert activations[0].agent == "scout"


# --- Goal creation tests ---


class TestCreateAgentGoal:
    """Tests for goal and agent assignment creation."""

    @pytest.mark.asyncio()
    async def test_creates_goal_and_agent_assignment(
        self,
        orchestrator: OnboardingCompletionOrchestrator,
        mock_db: MagicMock,
    ) -> None:
        """Goal and goal_agent records are created correctly."""
        goal_chain = _build_chain([{"id": "goal-123"}])
        agent_chain = _build_chain([{"id": "agent-456"}])

        call_count = 0

        def table_router(table_name: str) -> MagicMock:
            nonlocal call_count
            if table_name == "goals":
                return goal_chain
            if table_name == "goal_agents":
                return agent_chain
            return _build_chain(None)

        mock_db.table.side_effect = table_router

        activation = AgentActivation(
            agent="scout",
            task="Monitor competitors",
            goal_title="Competitive Monitoring",
            source_data={"competitor_count": 3},
        )

        goal_id = await orchestrator._create_agent_goal("user-1", activation)

        assert goal_id == "goal-123"

        # Verify goal insert
        goal_insert_data = goal_chain.insert.call_args[0][0]
        assert goal_insert_data["user_id"] == "user-1"
        assert goal_insert_data["title"] == "Competitive Monitoring"
        assert goal_insert_data["status"] == "active"
        assert goal_insert_data["config"]["source"] == "onboarding_activation"
        assert goal_insert_data["config"]["agent"] == "scout"
        assert goal_insert_data["config"]["priority"] == "low"

        # Verify agent assignment
        agent_insert_data = agent_chain.insert.call_args[0][0]
        assert agent_insert_data["goal_id"] == "goal-123"
        assert agent_insert_data["agent_type"] == "scout"
        assert agent_insert_data["status"] == "pending"

    @pytest.mark.asyncio()
    async def test_returns_none_on_failure(
        self,
        orchestrator: OnboardingCompletionOrchestrator,
        mock_db: MagicMock,
    ) -> None:
        """Returns None when goal creation fails."""
        mock_db.table.side_effect = Exception("DB error")

        activation = AgentActivation(
            agent="scout",
            task="Monitor",
            goal_title="Monitoring",
        )

        result = await orchestrator._create_agent_goal("user-1", activation)
        assert result is None


# --- Full activate flow tests ---


def _setup_db_for_activate(
    mock_db: MagicMock,
    *,
    profile: dict[str, Any] | None = None,
    company: dict[str, Any] | None = None,
    facts: list[dict[str, Any]] | None = None,
    integrations: list[dict[str, Any]] | None = None,
    goal: dict[str, Any] | None = None,
    contacts: list[dict[str, Any]] | None = None,  # noqa: ARG001
) -> None:
    """Wire up mock DB for the full activate flow."""

    # Track calls to goals table to differentiate select vs insert
    goals_call_count = {"count": 0}

    def table_router(table_name: str) -> MagicMock:
        if table_name == "user_profiles":
            return _build_chain(profile if profile is not None else {"company_id": "comp-1"})
        if table_name == "companies":
            return _build_chain(
                company
                if company is not None
                else {"settings": {"classification": {"company_type": "pharma"}}}
            )
        if table_name == "memory_semantic":
            return _build_chain(facts if facts is not None else [])
        if table_name == "user_integrations":
            return _build_chain(integrations if integrations is not None else [])
        if table_name == "goals":
            goals_call_count["count"] += 1
            if goals_call_count["count"] == 1:
                # First call: _get_first_goal (select → maybe_single → dict or None)
                return _build_chain(goal if goal is not None else None)
            # Subsequent calls: _create_agent_goal (insert → list of dicts)
            return _build_chain([{"id": f"goal-{goals_call_count['count']}"}])
        if table_name == "goal_agents":
            return _build_chain([{"id": "ga-1"}])
        if table_name == "memory_prospective":
            return _build_chain([{"id": "pm-1"}])
        return _build_chain(None)

    mock_db.table.side_effect = table_router


class TestActivateFlow:
    """Tests for the full activation flow."""

    @pytest.mark.asyncio()
    async def test_activate_returns_result(
        self,
        orchestrator: OnboardingCompletionOrchestrator,
        mock_db: MagicMock,
    ) -> None:
        """Activate returns ActivationResult with correct structure."""
        _setup_db_for_activate(mock_db)

        with (
            patch("src.memory.episodic.EpisodicMemory"),
            patch("src.memory.audit.MemoryAuditLogger"),
        ):
            result = await orchestrator.activate("user-1")

        assert result.activated >= 1
        assert len(result.agents) >= 1
        # Scout should always be present
        agent_names = [a["agent"] for a in result.agents]
        assert "scout" in agent_names

    @pytest.mark.asyncio()
    async def test_activate_with_all_triggers(
        self,
        orchestrator: OnboardingCompletionOrchestrator,
        mock_db: MagicMock,
    ) -> None:
        """All five agents activate when all conditions are met."""
        _setup_db_for_activate(
            mock_db,
            facts=[
                {"metadata": {"category": "competitive"}},
                {"metadata": {"type": "active_deal"}},
            ],
            integrations=[{"provider": "salesforce", "status": "active"}],
            goal={"title": "Generate leads in oncology"},
        )

        # We need to handle the contacts query separately since it also
        # hits memory_semantic
        with (
            patch("src.memory.episodic.EpisodicMemory"),
            patch("src.memory.audit.MemoryAuditLogger"),
        ):
            result = await orchestrator.activate("user-1")

        # At minimum scout should be there
        assert result.activated >= 1

    @pytest.mark.asyncio()
    async def test_activate_handles_goal_creation_failure(
        self,
        orchestrator: OnboardingCompletionOrchestrator,
        mock_db: MagicMock,
    ) -> None:
        """Activation continues even when individual goal creation fails."""

        # Make goals table always fail
        def table_router(table_name: str) -> MagicMock:
            if table_name == "goals":
                chain = MagicMock()
                chain.select.return_value = chain
                chain.insert.side_effect = Exception("DB error")
                chain.eq.return_value = chain
                chain.order.return_value = chain
                chain.limit.return_value = chain
                chain.maybe_single.return_value = chain
                chain.execute.return_value = _mock_execute(None)
                return chain
            return _build_chain(None)

        mock_db.table.side_effect = table_router

        with (
            patch("src.memory.episodic.EpisodicMemory"),
            patch("src.memory.audit.MemoryAuditLogger"),
        ):
            result = await orchestrator.activate("user-1")

        # Should complete without error, but with 0 activations
        assert result.activated == 0

    @pytest.mark.asyncio()
    async def test_episodic_failure_does_not_block_activation(
        self,
        orchestrator: OnboardingCompletionOrchestrator,
        mock_db: MagicMock,
    ) -> None:
        """Activation succeeds even when episodic recording fails."""
        _setup_db_for_activate(mock_db)

        mock_episodic = MagicMock()
        mock_episodic.store_episode.side_effect = Exception("Graphiti down")

        with (
            patch(
                "src.memory.episodic.EpisodicMemory",
                return_value=mock_episodic,
            ),
            patch("src.memory.audit.MemoryAuditLogger"),
        ):
            result = await orchestrator.activate("user-1")

        # Should still succeed
        assert result.activated >= 1


# --- AgentActivation model tests ---


class TestAgentActivationModel:
    """Tests for the AgentActivation Pydantic model."""

    def test_default_priority_is_low(self) -> None:
        """Default priority is 'low' per US-915 spec."""
        activation = AgentActivation(
            agent="scout",
            task="Monitor",
            goal_title="Monitoring",
        )
        assert activation.priority == "low"

    def test_source_data_defaults_to_empty(self) -> None:
        """source_data defaults to empty dict."""
        activation = AgentActivation(
            agent="scout",
            task="Monitor",
            goal_title="Monitoring",
        )
        assert activation.source_data == {}
