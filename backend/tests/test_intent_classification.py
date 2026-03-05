"""Tests for ChatService intent classification — deterministic pattern matching.

Validates that the _match_goal_trigger and _match_quick_action static methods
correctly classify requests without needing an LLM call.

Three-way classification:
- is_goal=true: Complex tasks requiring external research or multi-step workflows
- is_quick_action=true: Requests answerable from data ARIA already has
- is_conversational (both false): Casual conversation, feedback, explanations
"""

import pytest

from src.services.chat import ChatService


class TestMatchQuickAction:
    """Tests for the deterministic quick action pattern matcher.

    Quick actions are requests answerable from data ARIA already has:
    calendar, emails, signals, tasks, contacts, battle cards.
    """

    # --- Meeting Prep (quick action - data exists in calendar/battle_cards) ---

    @pytest.mark.parametrize(
        "message",
        [
            "Prepare for my meeting with Roche next Tuesday",
            "Build a meeting brief for the Sanofi call",
            "Get ready for my presentation tomorrow",
            "Brief me on my upcoming demo",
        ],
    )
    def test_meeting_prep_patterns_match(self, message: str) -> None:
        result = ChatService._match_quick_action(message)
        assert result is not None, f"Expected quick_action match for: {message}"
        assert result["is_goal"] is False
        assert result["is_quick_action"] is True
        assert result["action_type"] == "meeting_prep"

    # --- Calendar Queries (quick action - data exists in calendar_events) ---

    @pytest.mark.parametrize(
        "message",
        [
            "What meetings do I have today?",
            "Show me my calendar for tomorrow",
            "Any upcoming appointments this week?",
            "When is my next call with the client?",
        ],
    )
    def test_calendar_query_patterns_match(self, message: str) -> None:
        result = ChatService._match_quick_action(message)
        assert result is not None, f"Expected quick_action match for: {message}"
        assert result["is_goal"] is False
        assert result["is_quick_action"] is True
        assert result["action_type"] == "calendar_query"

    # --- Signal Review (quick action - data exists in market_signals) ---

    @pytest.mark.parametrize(
        "message",
        [
            "Show me the latest market signals",
            "Review any recent competitor news",
            "What intelligence alerts do I have?",
            "Monitor Catalent for any news about acquisitions",
        ],
    )
    def test_signal_review_patterns_match(self, message: str) -> None:
        result = ChatService._match_quick_action(message)
        assert result is not None, f"Expected quick_action match for: {message}"
        assert result["is_goal"] is False
        assert result["is_quick_action"] is True
        assert result["action_type"] == "signal_review"

    # --- Draft Review (quick action - data exists in email_drafts) ---

    @pytest.mark.parametrize(
        "message",
        [
            "Show me my pending email drafts",
            "Any drafts waiting for review?",
            "How many email replies are pending?",
        ],
    )
    def test_draft_review_patterns_match(self, message: str) -> None:
        result = ChatService._match_quick_action(message)
        assert result is not None, f"Expected quick_action match for: {message}"
        assert result["is_goal"] is False
        assert result["is_quick_action"] is True
        assert result["action_type"] == "draft_review"

    # --- Task Review (quick action - data exists in goals) ---

    @pytest.mark.parametrize(
        "message",
        [
            "What tasks do I have open?",
            "Show me my action items",
            "Any overdue goals I should check?",
            "How many pending tasks are there?",
        ],
    )
    def test_task_review_patterns_match(self, message: str) -> None:
        result = ChatService._match_quick_action(message)
        assert result is not None, f"Expected quick_action match for: {message}"
        assert result["is_goal"] is False
        assert result["is_quick_action"] is True
        assert result["action_type"] == "task_review"

    # --- Pipeline Review (quick action - data exists in leads) ---

    @pytest.mark.parametrize(
        "message",
        [
            "Show me my pipeline",
            "What does my funnel look like?",
            "How are my deals tracking?",
        ],
    )
    def test_pipeline_review_patterns_match(self, message: str) -> None:
        result = ChatService._match_quick_action(message)
        assert result is not None, f"Expected quick_action match for: {message}"
        assert result["is_goal"] is False
        assert result["is_quick_action"] is True
        assert result["action_type"] == "pipeline_review"

    # --- Competitive Lookup (quick action - data exists in battle_cards) ---

    @pytest.mark.parametrize(
        "message",
        [
            "What does the Thermo Fisher battle card say?",
            "Tell me about vs Lonza competitive positioning",
            "Show me the competitive comparison against CDMOs",
        ],
    )
    def test_competitive_lookup_patterns_match(self, message: str) -> None:
        result = ChatService._match_quick_action(message)
        assert result is not None, f"Expected quick_action match for: {message}"
        assert result["is_goal"] is False
        assert result["is_quick_action"] is True
        assert result["action_type"] == "competitive_lookup"


class TestMatchGoalTrigger:
    """Tests for the deterministic goal trigger pattern matcher.

    Goals are complex tasks requiring external research or multi-step workflows.
    Quick actions take priority - if a message matches a quick action pattern,
    _match_goal_trigger returns None.
    """

    # --- Lead Generation Patterns ---

    @pytest.mark.parametrize(
        "message",
        [
            "Find 10 bioprocessing companies in the Northeast US",
            "Find me 5 companies that sell lab equipment",
            "Identify prospects in the pharma space",
            "Discover potential vendors for clinical trial management",
            "Source companies that do gene therapy manufacturing",
            "List all firms in the CDMO space",
            "Find leads in the biotech sector",
            "Identify accounts in the Northeast territory",
        ],
    )
    def test_lead_gen_patterns_match(self, message: str) -> None:
        result = ChatService._match_goal_trigger(message)
        assert result is not None, f"Expected goal match for: {message}"
        assert result["is_goal"] is True
        assert result["goal_type"] == "lead_gen"

    # --- Research Patterns ---

    @pytest.mark.parametrize(
        "message",
        [
            "Research the competitive landscape for cell therapy",
            "Investigate Moderna's pipeline strategy",
            "Look into the gene therapy market",
            "Dig into the biosimilar space",
            "Explore the contract manufacturing industry",
            "Research competitors in the CDMO sector",
        ],
    )
    def test_research_patterns_match(self, message: str) -> None:
        result = ChatService._match_goal_trigger(message)
        assert result is not None, f"Expected goal match for: {message}"
        assert result["is_goal"] is True
        assert result["goal_type"] == "research"

    # --- Outreach Patterns ---

    @pytest.mark.parametrize(
        "message",
        [
            "Draft an email to the VP of Sales at Genentech",
            "Write a follow-up email for last week's meeting",
            "Compose an outreach message for new prospects",
            "Prepare a proposal for the Q3 renewal",
            "Create a cold intro email for the biotech leads",
            "Draft a follow up message to Dr. Smith",
        ],
    )
    def test_outreach_patterns_match(self, message: str) -> None:
        result = ChatService._match_goal_trigger(message)
        assert result is not None, f"Expected goal match for: {message}"
        assert result["is_goal"] is True
        assert result["goal_type"] == "outreach"

    # --- Analysis Patterns ---

    @pytest.mark.parametrize(
        "message",
        [
            "Analyze my pipeline for Q3",
            "Assess the deal pipeline health",
            "Evaluate our territory coverage",
            "Review the opportunity funnel",
            "Audit the current deals in the portfolio",
        ],
    )
    def test_analysis_patterns_match(self, message: str) -> None:
        result = ChatService._match_goal_trigger(message)
        assert result is not None, f"Expected goal match for: {message}"
        assert result["is_goal"] is True
        assert result["goal_type"] == "analysis"

    # --- Competitive Intel Patterns (BUILD new, not LOOKUP existing) ---

    @pytest.mark.parametrize(
        "message",
        [
            "Build a battle card for Thermo Fisher",
            "Create a competitive analysis vs Lonza",
            "Generate a comparison report for CDMOs",
            "Generate a competitive strategy for the Catalent pitch",
        ],
    )
    def test_competitive_intel_patterns_match(self, message: str) -> None:
        result = ChatService._match_goal_trigger(message)
        assert result is not None, f"Expected goal match for: {message}"
        assert result["is_goal"] is True
        assert result["goal_type"] == "competitive_intel"

    # --- Territory Patterns ---

    @pytest.mark.parametrize(
        "message",
        [
            "Map my territory for the Northeast region",
            "Plan our market entry strategy for Europe",
        ],
    )
    def test_territory_patterns_match(self, message: str) -> None:
        result = ChatService._match_goal_trigger(message)
        assert result is not None, f"Expected goal match for: {message}"
        assert result["is_goal"] is True
        assert result["goal_type"] == "territory"

    # --- Monitor/Track Patterns (SET UP new monitoring, not REVIEW existing) ---

    @pytest.mark.parametrize(
        "message",
        [
            "Track competitor pricing changes",
            "Watch for trigger signals in my accounts",
            "Alert me when there are market changes in cell therapy",
        ],
    )
    def test_monitor_patterns_match(self, message: str) -> None:
        result = ChatService._match_goal_trigger(message)
        assert result is not None, f"Expected goal match for: {message}"
        assert result["is_goal"] is True
        assert result["goal_type"] == "research"

    # --- Non-goal messages should NOT match ---

    @pytest.mark.parametrize(
        "message",
        [
            "Hello, how are you?",
            "What is ARIA?",
            "Thanks for the help",
            "Good morning",
            "Can you explain what a CDMO is?",
            "What's the weather like?",
            "Tell me about yourself",
            "How does your memory system work?",
            "What did we discuss yesterday?",
            "That looks great, thanks!",
        ],
    )
    def test_non_goal_messages_dont_match(self, message: str) -> None:
        result = ChatService._match_goal_trigger(message)
        assert result is None, f"Should NOT match as goal: {message}"

    # --- Result structure ---

    def test_match_returns_correct_structure(self) -> None:
        result = ChatService._match_goal_trigger(
            "Find 10 bioprocessing companies in the Northeast US"
        )
        assert result is not None
        assert "is_goal" in result
        assert "goal_title" in result
        assert "goal_type" in result
        assert "goal_description" in result
        assert result["is_goal"] is True
        assert len(result["goal_title"]) > 0
        assert len(result["goal_description"]) > 0

    def test_title_truncated_at_100_chars(self) -> None:
        long_message = "Find companies in the " + "pharmaceutical " * 20 + "sector"
        result = ChatService._match_goal_trigger(long_message)
        assert result is not None
        assert len(result["goal_title"]) <= 100


class TestQuickActionTakesPriority:
    """Tests that quick action patterns take priority over goal patterns.

    When a message matches both a quick action and a goal pattern,
    _match_goal_trigger should return None so the quick action is used.
    """

    @pytest.mark.parametrize(
        "message",
        [
            "Prepare for my meeting with Roche next Tuesday",
            "Show me the latest market signals",
        ],
    )
    def test_quick_action_prevents_goal_match(self, message: str) -> None:
        """Messages that match quick actions should NOT match as goals."""
        # First verify it matches as a quick action
        quick_result = ChatService._match_quick_action(message)
        assert quick_result is not None, f"Expected quick_action match for: {message}"

        # Then verify _match_goal_trigger returns None (lets quick action take priority)
        goal_result = ChatService._match_goal_trigger(message)
        assert goal_result is None, f"Should NOT match as goal when quick action exists: {message}"
