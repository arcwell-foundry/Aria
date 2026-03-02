"""Tests for Thesys C1 custom actions."""

import pytest


class TestGetAriaCustomActions:
    def test_returns_dict_with_all_nine_actions(self) -> None:
        """All 9 ARIA custom actions are present."""
        from src.services.thesys_actions import get_aria_custom_actions

        actions = get_aria_custom_actions()

        assert "approve_goal" in actions
        assert "modify_goal" in actions
        assert "approve_email" in actions
        assert "edit_email" in actions
        assert "dismiss_email" in actions
        assert "investigate_signal" in actions
        assert "view_lead_detail" in actions
        assert "execute_task" in actions
        assert "view_battle_card" in actions

    def test_each_action_has_valid_json_schema(self) -> None:
        """Each action returns a valid JSON schema with properties."""
        from src.services.thesys_actions import get_aria_custom_actions

        actions = get_aria_custom_actions()

        for action_name, schema in actions.items():
            assert "properties" in schema, f"{action_name} missing properties"
            assert "type" in schema, f"{action_name} missing type"
            assert schema["type"] == "object", f"{action_name} must be object type"

    def test_approve_goal_has_required_fields(self) -> None:
        """approve_goal action has goal_id and goal_name."""
        from src.services.thesys_actions import get_aria_custom_actions

        schema = get_aria_custom_actions()["approve_goal"]
        props = schema["properties"]

        assert "goal_id" in props
        assert "goal_name" in props
        assert "goal_id" in schema.get("required", [])
        assert "goal_name" in schema.get("required", [])

    def test_approve_email_has_required_fields(self) -> None:
        """approve_email action has email_draft_id, recipient, subject."""
        from src.services.thesys_actions import get_aria_custom_actions

        schema = get_aria_custom_actions()["approve_email"]
        props = schema["properties"]

        assert "email_draft_id" in props
        assert "recipient" in props
        assert "subject" in props

    def test_investigate_signal_has_signal_type(self) -> None:
        """investigate_signal includes signal_type field."""
        from src.services.thesys_actions import get_aria_custom_actions

        schema = get_aria_custom_actions()["investigate_signal"]
        props = schema["properties"]

        assert "signal_id" in props
        assert "signal_type" in props

    def test_no_hardcoded_ids_in_schemas(self) -> None:
        """Verify no action schema contains hardcoded ID values."""
        from src.services.thesys_actions import get_aria_custom_actions

        actions = get_aria_custom_actions()

        # Check that schemas don't contain hardcoded UUIDs or IDs
        hardcoded_patterns = [
            "00000000-0000-0000",  # UUID pattern
            "12345",  # Common test ID
            "test-id",
            "example",
        ]

        for action_name, schema in actions.items():
            schema_str = str(schema).lower()
            for pattern in hardcoded_patterns:
                assert pattern not in schema_str, (
                    f"{action_name} contains hardcoded pattern: {pattern}"
                )
