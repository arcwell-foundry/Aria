"""Tests for ARIA chat response envelope."""

import pytest


class TestChatResponseEnvelope:
    """Verify chat response includes the full ARIA envelope."""

    def test_response_model_has_rich_content_field(self):
        from src.api.routes.chat import ChatResponse
        fields = ChatResponse.model_fields
        assert "rich_content" in fields

    def test_response_model_has_ui_commands_field(self):
        from src.api.routes.chat import ChatResponse
        fields = ChatResponse.model_fields
        assert "ui_commands" in fields

    def test_response_model_has_suggestions_field(self):
        from src.api.routes.chat import ChatResponse
        fields = ChatResponse.model_fields
        assert "suggestions" in fields

    def test_response_defaults_to_empty_arrays(self):
        from src.api.routes.chat import ChatResponse
        resp = ChatResponse(
            message="Hello",
            conversation_id="test-123",
        )
        assert resp.rich_content == []
        assert resp.ui_commands == []
        assert resp.suggestions == []
        assert resp.citations == []

    def test_ui_command_model_validates(self):
        from src.api.routes.chat import UICommand
        cmd = UICommand(action="navigate", route="/pipeline")
        assert cmd.action == "navigate"
        assert cmd.route == "/pipeline"

    def test_rich_content_model_validates(self):
        from src.api.routes.chat import RichContent
        rc = RichContent(type="battle_card", data={"company": "Lonza"})
        assert rc.type == "battle_card"
        assert rc.data == {"company": "Lonza"}
