"""Tests for ChatService intent classification — deterministic pattern matching.

Validates that the _match_goal_trigger static method correctly classifies
obvious action-oriented requests without needing an LLM call.
"""

import pytest

from src.services.chat import ChatService


class TestMatchGoalTrigger:
    """Tests for the deterministic goal trigger pattern matcher."""

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

    # --- Competitive Intel Patterns ---

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

    # --- Meeting Prep Patterns ---

    @pytest.mark.parametrize(
        "message",
        [
            "Prepare for my meeting with Roche next Tuesday",
            "Build a meeting brief for the Sanofi call",
            "Create a presentation deck for the QBR",
            "Put together an agenda for the partner meeting",
        ],
    )
    def test_meeting_prep_patterns_match(self, message: str) -> None:
        result = ChatService._match_goal_trigger(message)
        assert result is not None, f"Expected goal match for: {message}"
        assert result["is_goal"] is True
        assert result["goal_type"] == "meeting_prep"

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

    # --- Monitor/Track Patterns ---

    @pytest.mark.parametrize(
        "message",
        [
            "Monitor Catalent for any news about acquisitions",
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
