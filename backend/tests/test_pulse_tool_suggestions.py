"""Tests for tool suggestion pulse generation."""

# Set required env vars BEFORE any src imports trigger config validation
import os

os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key")

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.intelligence_pulse import IntelligencePulseEngine


@pytest.fixture
def pulse_engine():
    db = MagicMock()
    llm = MagicMock()
    notif = MagicMock()
    return IntelligencePulseEngine(db, llm, notif)


@pytest.mark.asyncio
async def test_generates_pulse_for_unmet_capability(pulse_engine):
    """Should generate pulse when capability demand is high and toolkit not connected."""
    # Mock capability_demand query
    demand_mock = MagicMock()
    demand_mock.select.return_value.eq.return_value.eq.return_value.gte.return_value.execute.return_value = MagicMock(
        data=[{
            "capability_name": "crm_read",
            "times_needed": 5,
            "avg_quality_achieved": 0.6,
            "suggestion_threshold_reached": False,
        }]
    )
    pulse_engine._db.table.return_value = demand_mock

    with (
        patch.object(pulse_engine, "_lookup_composio_app", new_callable=AsyncMock, return_value="SALESFORCE"),
        patch.object(pulse_engine, "_is_toolkit_connected", new_callable=AsyncMock, return_value=False),
    ):
        pulses = await pulse_engine.generate_tool_suggestion_pulses("user-1")
        assert len(pulses) == 1
        assert pulses[0]["type"] == "tool_suggestion"
        assert "SALESFORCE" in pulses[0]["title"] or "Salesforce" in pulses[0]["title"]


@pytest.mark.asyncio
async def test_skips_connected_toolkit(pulse_engine):
    """Should skip suggestions for already-connected toolkits."""
    demand_mock = MagicMock()
    demand_mock.select.return_value.eq.return_value.eq.return_value.gte.return_value.execute.return_value = MagicMock(
        data=[{"capability_name": "email_read", "times_needed": 10, "avg_quality_achieved": 0.5, "suggestion_threshold_reached": False}]
    )
    pulse_engine._db.table.return_value = demand_mock

    with (
        patch.object(pulse_engine, "_lookup_composio_app", new_callable=AsyncMock, return_value="GMAIL"),
        patch.object(pulse_engine, "_is_toolkit_connected", new_callable=AsyncMock, return_value=True),
    ):
        pulses = await pulse_engine.generate_tool_suggestion_pulses("user-1")
        assert len(pulses) == 0


@pytest.mark.asyncio
async def test_no_pulses_when_no_demand(pulse_engine):
    """Should return empty list when no capability demand."""
    demand_mock = MagicMock()
    demand_mock.select.return_value.eq.return_value.eq.return_value.gte.return_value.execute.return_value = MagicMock(data=[])
    pulse_engine._db.table.return_value = demand_mock

    pulses = await pulse_engine.generate_tool_suggestion_pulses("user-1")
    assert pulses == []


@pytest.mark.asyncio
async def test_skips_when_no_composio_app(pulse_engine):
    """Should skip capabilities with no matching Composio app."""
    demand_mock = MagicMock()
    demand_mock.select.return_value.eq.return_value.eq.return_value.gte.return_value.execute.return_value = MagicMock(
        data=[{"capability_name": "custom_tool", "times_needed": 5, "avg_quality_achieved": 0.3, "suggestion_threshold_reached": False}]
    )
    pulse_engine._db.table.return_value = demand_mock

    with patch.object(pulse_engine, "_lookup_composio_app", new_callable=AsyncMock, return_value=None):
        pulses = await pulse_engine.generate_tool_suggestion_pulses("user-1")
        assert len(pulses) == 0
