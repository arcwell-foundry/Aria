"""Tests for Tavus perception tools in ARIA persona layers."""

from src.integrations.tavus_persona import ARIA_PERSONA_LAYERS


class TestPerceptionTools:
    """Verify perception_tools and perception_tool_prompt in ARIA_PERSONA_LAYERS."""

    def test_perception_layers_has_perception_tools(self) -> None:
        """perception key must contain perception_tools with exactly 2 tools."""
        perception = ARIA_PERSONA_LAYERS["perception"]
        assert "perception_tools" in perception, "Missing 'perception_tools' key"
        tools = perception["perception_tools"]
        assert isinstance(tools, list), "perception_tools must be a list"
        assert len(tools) == 2, f"Expected 2 tools, got {len(tools)}"

    def test_perception_layers_has_perception_tool_prompt(self) -> None:
        """perception key must contain perception_tool_prompt mentioning both tool names."""
        perception = ARIA_PERSONA_LAYERS["perception"]
        assert "perception_tool_prompt" in perception, "Missing 'perception_tool_prompt' key"
        prompt = perception["perception_tool_prompt"]
        assert isinstance(prompt, str), "perception_tool_prompt must be a string"
        assert "adapt_to_confusion" in prompt, "Prompt must mention adapt_to_confusion"
        assert "note_engagement_drop" in prompt, "Prompt must mention note_engagement_drop"

    def test_adapt_to_confusion_tool_schema(self) -> None:
        """adapt_to_confusion tool must have correct params and required fields."""
        tools = ARIA_PERSONA_LAYERS["perception"]["perception_tools"]
        # Find the adapt_to_confusion tool
        tool = next(
            (t for t in tools if t.get("function", {}).get("name") == "adapt_to_confusion"),
            None,
        )
        assert tool is not None, "adapt_to_confusion tool not found"
        assert tool["type"] == "function"

        func = tool["function"]
        assert "description" in func, "Tool must have a description"

        params = func["parameters"]
        assert params["type"] == "object"
        props = params["properties"]

        # confusion_indicator — string, required
        assert "confusion_indicator" in props
        assert props["confusion_indicator"]["type"] == "string"

        # topic — string, required
        assert "topic" in props
        assert props["topic"]["type"] == "string"

        required = params["required"]
        assert "confusion_indicator" in required
        assert "topic" in required

    def test_note_engagement_drop_tool_schema(self) -> None:
        """note_engagement_drop tool must have correct params and required fields."""
        tools = ARIA_PERSONA_LAYERS["perception"]["perception_tools"]
        # Find the note_engagement_drop tool
        tool = next(
            (t for t in tools if t.get("function", {}).get("name") == "note_engagement_drop"),
            None,
        )
        assert tool is not None, "note_engagement_drop tool not found"
        assert tool["type"] == "function"

        func = tool["function"]
        assert "description" in func, "Tool must have a description"

        params = func["parameters"]
        assert params["type"] == "object"
        props = params["properties"]

        # disengagement_type — string, required
        assert "disengagement_type" in props
        assert props["disengagement_type"]["type"] == "string"

        # topic — string, required
        assert "topic" in props
        assert props["topic"]["type"] == "string"

        required = params["required"]
        assert "disengagement_type" in required
        assert "topic" in required
