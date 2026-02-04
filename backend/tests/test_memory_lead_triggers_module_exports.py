"""Test that LeadTriggerService is exported from memory module."""

def test_lead_trigger_service_exported():
    """Test LeadTriggerService is importable from src.memory."""
    from src.memory import LeadTriggerService

    assert LeadTriggerService is not None


def test_lead_trigger_service_has_required_methods():
    """Test LeadTriggerService has all trigger methods."""
    from src.memory import LeadTriggerService

    required_methods = [
        "find_or_create",
        "on_email_approved",
        "on_manual_track",
        "on_crm_import",
        "on_inbound_response",
        "scan_history_for_lead",
    ]

    for method_name in required_methods:
        assert hasattr(LeadTriggerService, method_name), f"Missing method: {method_name}"
