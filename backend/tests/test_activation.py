"""Tests for US-915: Onboarding Completion → Agent Activation."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.onboarding.activation import OnboardingCompletionOrchestrator


@pytest.fixture
def mock_db():
    """Mock Supabase client."""
    return MagicMock()


@pytest.fixture
def mock_llm():
    """Mock LLM client."""
    return MagicMock()


@pytest.fixture
def mock_goal_service():
    """Mock GoalService."""
    service = MagicMock()
    service.create_goal = AsyncMock()
    return service


@pytest.fixture
def activator(mock_db, mock_llm, mock_goal_service):
    """Create OnboardingCompletionOrchestrator with mocked dependencies."""
    with patch("src.onboarding.activation.SupabaseClient.get_client", return_value=mock_db):
        with patch("src.onboarding.activation.LLMClient", return_value=mock_llm):
            with patch("src.onboarding.activation.GoalService", return_value=mock_goal_service):
                return OnboardingCompletionOrchestrator()


class TestOnboardingCompletionOrchestrator:
    """Test suite for OnboardingCompletionOrchestrator."""

    @pytest.mark.asyncio
    async def test_activate_all_agents_with_crm_and_lead_gen(self, activator, mock_goal_service):
        """Test activation with CRM connected and lead_gen goal."""
        # Setup mock responses
        mock_goal_service.create_goal.side_effect = [
            {"id": "goal-1"},  # Scout
            {"id": "goal-2"},  # Analyst
            {"id": "goal-3"},  # Hunter
            {"id": "goal-4"},  # Operator
            {"id": "goal-5"},  # Scribe
        ]

        onboarding_data = {
            "company_id": "company-123",
            "company_discovery": {"website": "example.com"},
            "enrichment": {"competitors": ["competitor1.com", "competitor2.com"]},
            "integration_wizard": {
                "crm_connected": True,
                "email_connected": True,
            },
            "first_goal": {"goal_type": "lead_gen", "description": "Generate 50 leads"},
        }

        with patch.object(activator, "_record_activation_event", new_callable=AsyncMock):
            result = await activator.activate("user-123", onboarding_data)

        # Verify all agents were activated
        assert result["user_id"] == "user-123"
        assert "activated_at" in result
        assert result["activations"]["scout"] is not None
        assert result["activations"]["analyst"] is not None
        assert result["activations"]["hunter"] is not None
        assert result["activations"]["operator"] is not None
        assert result["activations"]["scribe"] is not None

        # Verify goals were created
        assert mock_goal_service.create_goal.call_count == 5

    @pytest.mark.asyncio
    async def test_activate_without_crm_skips_analyst_operator(self, activator, mock_goal_service):
        """Test activation without CRM skips Analyst and Operator."""
        mock_goal_service.create_goal.side_effect = [
            {"id": "goal-1"},  # Scout
            {"id": "goal-2"},  # Scribe (email not connected either)
        ]

        onboarding_data = {
            "company_id": "company-123",
            "company_discovery": {"website": "example.com"},
            "enrichment": {},
            "integration_wizard": {
                "crm_connected": False,
                "email_connected": False,
            },
            "first_goal": {"goal_type": "research"},
        }

        with patch.object(activator, "_record_activation_event", new_callable=AsyncMock):
            result = await activator.activate("user-123", onboarding_data)

        # Verify Scout still activated
        assert result["activations"]["scout"] is not None
        # Verify Analyst and Operator skipped
        assert result["activations"]["analyst"] is None
        assert result["activations"]["operator"] is None
        assert result["activations"]["scribe"] is None
        # Hunter not activated (no lead_gen goal)
        assert result["activations"]["hunter"] is None

        # Only Scout goal created
        assert mock_goal_service.create_goal.call_count == 1

    @pytest.mark.asyncio
    async def test_activate_scout_uses_competitors_from_enrichment(
        self, activator, mock_goal_service
    ):
        """Test Scout activation uses competitors from enrichment."""
        mock_goal_service.create_goal.return_value = {"id": "goal-1"}

        onboarding_data = {
            "company_id": "company-123",
            "company_discovery": {"website": "mycompany.com"},
            "enrichment": {"competitors": ["comp1.com", "comp2.com", "comp3.com", "comp4.com"]},
            "integration_wizard": {"crm_connected": False},
            "first_goal": {"goal_type": "research"},
        }

        with patch.object(activator, "_record_activation_event", new_callable=AsyncMock):
            await activator.activate("user-123", onboarding_data)

        # Verify Scout goal was created with competitors
        call_args = mock_goal_service.create_goal.call_args
        goal_data = call_args[0][1]  # Second positional arg is GoalCreate

        assert goal_data.config["entities"] == [
            "comp1.com",
            "comp2.com",
            "comp3.com",
            "comp4.com",
        ]
        assert goal_data.config["agent"] == "scout"

    @pytest.mark.asyncio
    async def test_activate_scout_fallback_to_company_domain(self, activator, mock_goal_service):
        """Test Scout activation falls back to company domain without competitors."""
        mock_goal_service.create_goal.return_value = {"id": "goal-1"}

        onboarding_data = {
            "company_id": "company-123",
            "company_discovery": {"website": "mycompany.com"},
            "enrichment": {},  # No competitors
            "integration_wizard": {"crm_connected": False},
            "first_goal": {"goal_type": "research"},
        }

        with patch.object(activator, "_record_activation_event", new_callable=AsyncMock):
            await activator.activate("user-123", onboarding_data)

        # Verify Scout goal was created with company domain as fallback
        call_args = mock_goal_service.create_goal.call_args
        goal_data = call_args[0][1]

        assert goal_data.config["entities"] == ["mycompany.com"]

    @pytest.mark.asyncio
    async def test_activate_without_email_skips_scribe(self, activator, mock_goal_service):
        """Test activation without email skips Scribe."""
        mock_goal_service.create_goal.side_effect = [
            {"id": "goal-1"},  # Scout
            {"id": "goal-2"},  # Analyst (CRM connected)
            {"id": "goal-3"},  # Operator (CRM connected)
        ]

        onboarding_data = {
            "company_id": "company-123",
            "company_discovery": {"website": "example.com"},
            "enrichment": {},
            "integration_wizard": {
                "crm_connected": True,
                "email_connected": False,  # No email
            },
            "first_goal": {"goal_type": "research"},
        }

        with patch.object(activator, "_record_activation_event", new_callable=AsyncMock):
            result = await activator.activate("user-123", onboarding_data)

        # Verify Scribe skipped
        assert result["activations"]["scribe"] is None
        # Others activated
        assert result["activations"]["scout"] is not None
        assert result["activations"]["analyst"] is not None
        assert result["activations"]["operator"] is not None

    @pytest.mark.asyncio
    async def test_activate_without_lead_gen_skips_hunter(self, activator, mock_goal_service):
        """Test activation without lead_gen goal skips Hunter."""
        mock_goal_service.create_goal.side_effect = [
            {"id": "goal-1"},
        ] * 4  # Scout, Analyst, Operator, Scribe

        onboarding_data = {
            "company_id": "company-123",
            "company_discovery": {"website": "example.com"},
            "enrichment": {},
            "integration_wizard": {
                "crm_connected": True,
                "email_connected": True,
            },
            "first_goal": {"goal_type": "research"},  # Not lead_gen
        }

        with patch.object(activator, "_record_activation_event", new_callable=AsyncMock):
            result = await activator.activate("user-123", onboarding_data)

        # Verify Hunter skipped
        assert result["activations"]["hunter"] is None
        # Others activated
        assert result["activations"]["scout"] is not None

    @pytest.mark.asyncio
    async def test_activate_handles_agent_failure_gracefully(self, activator, mock_goal_service):
        """Test activation continues even if one agent fails."""
        # Scout succeeds, Analyst fails, rest succeed
        mock_goal_service.create_goal.side_effect = [
            {"id": "goal-1"},  # Scout succeeds
            Exception("Analyst failed"),  # Analyst fails
            {"id": "goal-3"},  # Hunter succeeds
            {"id": "goal-4"},  # Operator succeeds
            {"id": "goal-5"},  # Scribe succeeds
        ]

        onboarding_data = {
            "company_id": "company-123",
            "company_discovery": {"website": "example.com"},
            "enrichment": {},
            "integration_wizard": {
                "crm_connected": True,
                "email_connected": True,
            },
            "first_goal": {"goal_type": "lead_gen"},
        }

        with patch.object(activator, "_record_activation_event", new_callable=AsyncMock):
            # Should not raise exception
            result = await activator.activate("user-123", onboarding_data)

        # Verify other agents still activated
        assert result["activations"]["scout"] is not None
        assert result["activations"]["analyst"] is None  # Failed
        assert result["activations"]["hunter"] is not None
        assert result["activations"]["operator"] is not None
        assert result["activations"]["scribe"] is not None

    @pytest.mark.asyncio
    async def test_activate_records_episodic_event(self, activator, mock_goal_service):
        """Test activation records event to episodic memory."""
        mock_goal_service.create_goal.side_effect = [{"id": "goal-1"}]

        onboarding_data = {
            "company_id": "company-123",
            "company_discovery": {"website": "example.com"},
            "enrichment": {},
            "integration_wizard": {"crm_connected": False},
            "first_goal": {"goal_type": "research"},
        }

        mock_episodic_memory = MagicMock()
        mock_episodic_memory.store_episode = AsyncMock()

        with patch("src.memory.episodic.EpisodicMemory", return_value=mock_episodic_memory):
            await activator.activate("user-123", onboarding_data)

        # Verify episodic event was recorded
        assert mock_episodic_memory.store_episode.call_count == 1
        episode_arg = mock_episodic_memory.store_episode.call_args[0][0]
        assert episode_arg.event_type == "onboarding_activation"
        assert "Post-onboarding activation" in episode_arg.content

    @pytest.mark.asyncio
    async def test_activate_goals_have_correct_source_and_priority(
        self, activator, mock_goal_service
    ):
        """Test all created goals have onboarding_activation source and low priority."""
        mock_goal_service.create_goal.return_value = {"id": "goal-1"}

        onboarding_data = {
            "company_id": "company-123",
            "company_discovery": {"website": "example.com"},
            "enrichment": {},
            "integration_wizard": {"crm_connected": True, "email_connected": True},
            "first_goal": {"goal_type": "lead_gen"},
        }

        with patch.object(activator, "_record_activation_event", new_callable=AsyncMock):
            await activator.activate("user-123", onboarding_data)

        # Verify each goal has correct config
        for call in mock_goal_service.create_goal.call_args_list:
            goal_data = call[0][1]  # Second positional arg is GoalCreate
            assert goal_data.config["source"] == "onboarding_activation"
            assert goal_data.config["priority"] == "low"
            assert "agent" in goal_data.config

    @pytest.mark.asyncio
    async def test_activate_includes_strategist(self, activator, mock_goal_service):
        """Strategist agent is activated with full onboarding data."""
        mock_goal_service.create_goal.side_effect = [
            {"id": "goal-1"},  # Scout
            {"id": "goal-2"},  # Analyst
            {"id": "goal-3"},  # Hunter
            {"id": "goal-4"},  # Operator
            {"id": "goal-5"},  # Scribe
            {"id": "goal-6"},  # Strategist
        ]

        onboarding_data = {
            "company_id": "company-123",
            "company_discovery": {"website": "example.com"},
            "enrichment": {"competitors": ["c1.com"]},
            "integration_wizard": {"crm_connected": True, "email_connected": True},
            "first_goal": {"goal_type": "lead_gen", "description": "Generate leads"},
        }

        with patch.object(activator, "_record_activation_event", new_callable=AsyncMock):
            result = await activator.activate("user-123", onboarding_data)

        assert result["activations"]["strategist"] is not None
        assert "goal_id" in result["activations"]["strategist"]

    @pytest.mark.asyncio
    async def test_activate_strategist_without_integrations(self, activator, mock_goal_service):
        """Strategist activates even without CRM/email — no gating."""
        mock_goal_service.create_goal.side_effect = [
            {"id": "goal-1"},  # Scout
            {"id": "goal-2"},  # Strategist
        ]

        onboarding_data = {
            "company_id": "company-123",
            "company_discovery": {"website": "example.com"},
            "enrichment": {},
            "integration_wizard": {"crm_connected": False, "email_connected": False},
            "first_goal": {},
        }

        with patch.object(activator, "_record_activation_event", new_callable=AsyncMock):
            result = await activator.activate("user-123", onboarding_data)

        assert result["activations"]["strategist"] is not None
