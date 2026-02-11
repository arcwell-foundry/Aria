"""Tests for chat stream envelope fields (rich_content, ui_commands, suggestions)."""

from src.api.routes.chat import _analyze_ui_commands, _generate_suggestions


def test_analyze_ui_commands_navigation():
    """Detect navigation intent in ARIA response."""
    response = "Let me show you the pipeline for Lonza. Here's what I found."
    commands = _analyze_ui_commands(response)
    assert isinstance(commands, list)
    assert len(commands) == 1
    assert commands[0]["action"] == "navigate"
    assert commands[0]["route"] == "/pipeline"


def test_analyze_ui_commands_empty_for_plain():
    """No UI commands for plain conversational response."""
    response = "Good morning! How can I help you today?"
    commands = _analyze_ui_commands(response)
    assert commands == []


def test_analyze_ui_commands_battle_card():
    """Detect battle card navigation intent."""
    response = "Here's the battle card for Catalent with their latest positioning."
    commands = _analyze_ui_commands(response)
    assert len(commands) == 1
    assert commands[0]["route"] == "/intelligence/battle-cards"


def test_generate_suggestions_returns_list():
    """Suggestions should be a list of follow-up prompts."""
    message = "I've analyzed the competitive landscape for Lonza."
    conversation = [
        {"role": "user", "content": "What do you know about Lonza?"},
        {"role": "assistant", "content": message},
    ]
    suggestions = _generate_suggestions(message, conversation)
    assert isinstance(suggestions, list)
    assert len(suggestions) <= 4
    assert len(suggestions) >= 2


def test_generate_suggestions_contextual_battle_card():
    """Suggestions should relate to battle card context."""
    message = "Here's the battle card for Catalent."
    conversation = [
        {"role": "user", "content": "Show me Catalent's battle card"},
        {"role": "assistant", "content": message},
    ]
    suggestions = _generate_suggestions(message, conversation)
    assert isinstance(suggestions, list)
    assert "Compare with other competitors" in suggestions


def test_generate_suggestions_pipeline():
    """Pipeline context should generate pipeline-specific suggestions."""
    message = "Your pipeline shows 12 active deals worth $2.4M."
    conversation = [
        {"role": "user", "content": "How's my pipeline?"},
        {"role": "assistant", "content": message},
    ]
    suggestions = _generate_suggestions(message, conversation)
    assert "Which deals need attention?" in suggestions


def test_generate_suggestions_minimum_two():
    """Should always return at least 2 suggestions."""
    message = "Hello, I'm ARIA."
    conversation = []
    suggestions = _generate_suggestions(message, conversation)
    assert len(suggestions) >= 2
