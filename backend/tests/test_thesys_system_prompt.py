"""Tests for Thesys C1 system prompt builder."""
from src.services.thesys_system_prompt import ARIA_C1_SYSTEM_PROMPT, build_system_prompt


class TestBuildSystemPrompt:
    def test_returns_base_prompt_for_none(self) -> None:
        result = build_system_prompt(None)
        assert result == ARIA_C1_SYSTEM_PROMPT

    def test_returns_base_prompt_for_unknown(self) -> None:
        result = build_system_prompt("unknown_type")
        assert result == ARIA_C1_SYSTEM_PROMPT

    def test_pipeline_data_adds_context(self) -> None:
        result = build_system_prompt("pipeline_data")
        assert "Pipeline" in result or "pipeline" in result
        assert ARIA_C1_SYSTEM_PROMPT in result

    def test_briefing_adds_context(self) -> None:
        result = build_system_prompt("briefing")
        assert "Briefing" in result or "briefing" in result

    def test_email_adds_context(self) -> None:
        result = build_system_prompt("email_draft")
        assert "email" in result.lower() or "Email" in result

    def test_lead_adds_context(self) -> None:
        result = build_system_prompt("lead_card")
        assert "Lead" in result or "lead" in result

    def test_all_types_contain_base_rules(self) -> None:
        for ct in ["pipeline_data", "briefing", "email_draft", "lead_card"]:
            result = build_system_prompt(ct)
            assert "ARIA" in result
