"""Tests for streaming endpoint Digital Twin + priming context integration.

Verifies:
- _build_system_prompt() includes "Writing Style Fingerprint" when style_guidelines is provided
- _build_system_prompt() includes "Conversation Continuity" when priming_context is provided
- Both sections are absent when the respective args are None
"""

from contextlib import contextmanager
from typing import Any, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.memory.priming import ConversationContext
from src.models.cognitive_load import CognitiveLoadState, LoadLevel


@contextmanager
def mock_chat_service_deps() -> Generator[None, None, None]:
    """Context manager to mock all ChatService constructor dependencies."""
    mock_load_state = CognitiveLoadState(
        level=LoadLevel.LOW,
        score=0.2,
        factors={},
        recommendation="detailed",
    )
    with patch("src.services.chat.get_supabase_client") as mock_get_db:
        mock_get_db.return_value = MagicMock()
        with patch("src.services.chat.CognitiveLoadMonitor") as mock_monitor_class:
            mock_monitor = MagicMock()
            mock_monitor.estimate_load = AsyncMock(return_value=mock_load_state)
            mock_monitor_class.return_value = mock_monitor
            yield


def _make_load_state() -> CognitiveLoadState:
    return CognitiveLoadState(
        level=LoadLevel.LOW,
        score=0.2,
        factors={},
        recommendation="detailed",
    )


def _make_priming_context(text: str = "Last session you discussed Lonza pricing.") -> ConversationContext:
    return ConversationContext(
        recent_episodes=[{"summary": "Discussed Lonza pricing", "date": "2026-02-10"}],
        open_threads=[{"thread": "Follow up on Catalent RFP"}],
        salient_facts=[{"fact": "User prefers concise responses"}],
        relevant_entities=[{"name": "Lonza", "type": "company"}],
        formatted_context=text,
    )


# ============================================================================
# _build_system_prompt includes style_guidelines
# ============================================================================


class TestBuildSystemPromptWithStyleGuidelines:
    """Verify _build_system_prompt outputs 'Writing Style Fingerprint' section."""

    def test_includes_writing_style_fingerprint_header(self) -> None:
        """When style_guidelines is provided, the prompt should contain the header."""
        with mock_chat_service_deps():
            from src.services.chat import ChatService

            service = ChatService()
            prompt = service._build_system_prompt(
                memories=[],
                load_state=_make_load_state(),
                proactive_insights=[],
                personality=None,
                style_guidelines="Use short sentences. Avoid jargon.",
                priming_context=None,
            )

        assert "Writing Style Fingerprint" in prompt

    def test_includes_style_guidelines_content(self) -> None:
        """The actual guidelines text should appear in the prompt."""
        with mock_chat_service_deps():
            from src.services.chat import ChatService

            service = ChatService()
            prompt = service._build_system_prompt(
                memories=[],
                load_state=_make_load_state(),
                proactive_insights=[],
                personality=None,
                style_guidelines="Prefer bullet points over paragraphs.",
                priming_context=None,
            )

        assert "Prefer bullet points over paragraphs." in prompt

    def test_excludes_writing_style_when_none(self) -> None:
        """When style_guidelines is None, no Writing Style section should appear."""
        with mock_chat_service_deps():
            from src.services.chat import ChatService

            service = ChatService()
            prompt = service._build_system_prompt(
                memories=[],
                load_state=_make_load_state(),
                proactive_insights=[],
                personality=None,
                style_guidelines=None,
                priming_context=None,
            )

        assert "Writing Style Fingerprint" not in prompt


# ============================================================================
# _build_system_prompt includes priming_context
# ============================================================================


class TestBuildSystemPromptWithPrimingContext:
    """Verify _build_system_prompt outputs 'Conversation Continuity' section."""

    def test_includes_conversation_continuity_header(self) -> None:
        """When priming_context is provided, the prompt should contain the header."""
        ctx = _make_priming_context()

        with mock_chat_service_deps():
            from src.services.chat import ChatService

            service = ChatService()
            prompt = service._build_system_prompt(
                memories=[],
                load_state=_make_load_state(),
                proactive_insights=[],
                personality=None,
                style_guidelines=None,
                priming_context=ctx,
            )

        assert "Conversation Continuity" in prompt

    def test_includes_priming_formatted_context(self) -> None:
        """The formatted_context text should appear in the prompt."""
        ctx = _make_priming_context("You left off discussing Catalent's Q4 proposal.")

        with mock_chat_service_deps():
            from src.services.chat import ChatService

            service = ChatService()
            prompt = service._build_system_prompt(
                memories=[],
                load_state=_make_load_state(),
                proactive_insights=[],
                personality=None,
                style_guidelines=None,
                priming_context=ctx,
            )

        assert "You left off discussing Catalent's Q4 proposal." in prompt

    def test_excludes_conversation_continuity_when_none(self) -> None:
        """When priming_context is None, no Conversation Continuity section should appear."""
        with mock_chat_service_deps():
            from src.services.chat import ChatService

            service = ChatService()
            prompt = service._build_system_prompt(
                memories=[],
                load_state=_make_load_state(),
                proactive_insights=[],
                personality=None,
                style_guidelines=None,
                priming_context=None,
            )

        assert "Conversation Continuity" not in prompt

    def test_excludes_continuity_when_formatted_context_empty(self) -> None:
        """When priming_context has an empty formatted_context, the section should be skipped."""
        ctx = ConversationContext(
            recent_episodes=[],
            open_threads=[],
            salient_facts=[],
            relevant_entities=[],
            formatted_context="",
        )

        with mock_chat_service_deps():
            from src.services.chat import ChatService

            service = ChatService()
            prompt = service._build_system_prompt(
                memories=[],
                load_state=_make_load_state(),
                proactive_insights=[],
                personality=None,
                style_guidelines=None,
                priming_context=ctx,
            )

        assert "Conversation Continuity" not in prompt


# ============================================================================
# _build_system_prompt with both style + priming together
# ============================================================================


class TestBuildSystemPromptWithBothContextLayers:
    """Verify both style_guidelines and priming_context can coexist in the prompt."""

    def test_both_sections_present(self) -> None:
        """Both Writing Style and Conversation Continuity sections should appear."""
        ctx = _make_priming_context()

        with mock_chat_service_deps():
            from src.services.chat import ChatService

            service = ChatService()
            prompt = service._build_system_prompt(
                memories=[],
                load_state=_make_load_state(),
                proactive_insights=[],
                personality=None,
                style_guidelines="Direct tone. Short paragraphs.",
                priming_context=ctx,
            )

        assert "Writing Style Fingerprint" in prompt
        assert "Conversation Continuity" in prompt
        assert "Direct tone. Short paragraphs." in prompt
        assert "Last session you discussed Lonza pricing." in prompt

    def test_style_appears_before_priming(self) -> None:
        """Writing Style section should appear before Conversation Continuity."""
        ctx = _make_priming_context()

        with mock_chat_service_deps():
            from src.services.chat import ChatService

            service = ChatService()
            prompt = service._build_system_prompt(
                memories=[],
                load_state=_make_load_state(),
                proactive_insights=[],
                personality=None,
                style_guidelines="Use active voice.",
                priming_context=ctx,
            )

        style_pos = prompt.index("Writing Style Fingerprint")
        priming_pos = prompt.index("Conversation Continuity")
        assert style_pos < priming_pos
