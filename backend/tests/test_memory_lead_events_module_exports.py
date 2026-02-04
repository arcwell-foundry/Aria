# File: backend/tests/test_memory_lead_events_module_exports.py

def test_lead_memory_events_module_exports():
    """Test that lead memory events are exported from memory module."""
    from src.memory import (
        Direction,
        EventType,
        LeadEvent,
        LeadEventService,
    )
    from src.memory.lead_memory_events import (
        Direction as DirectDirection,
        EventType as DirectEventType,
        LeadEvent as DirectLeadEvent,
        LeadEventService as DirectLeadEventService,
    )

    assert EventType is DirectEventType
    assert Direction is DirectDirection
    assert LeadEvent is DirectLeadEvent
    assert LeadEventService is DirectLeadEventService

def test_event_type_enum_values():
    """Test EventType enum has correct values."""
    from src.memory import EventType

    assert EventType.EMAIL_SENT.value == "email_sent"
    assert EventType.EMAIL_RECEIVED.value == "email_received"
    assert EventType.MEETING.value == "meeting"
    assert EventType.CALL.value == "call"
    assert EventType.NOTE.value == "note"
    assert EventType.SIGNAL.value == "signal"

def test_direction_enum_values():
    """Test Direction enum has correct values."""
    from src.memory import Direction

    assert Direction.INBOUND.value == "inbound"
    assert Direction.OUTBOUND.value == "outbound"
