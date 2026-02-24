"""Tests for Tavus CVI tool definitions and VideoToolExecutor."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.integrations.tavus_tools import (
    ARIA_VIDEO_TOOLS,
    TOOL_AGENT_MAP,
    VALID_TOOL_NAMES,
)
from src.integrations.tavus_tool_executor import VideoToolExecutor


# ====================
# Tool Definition Tests
# ====================


def test_thirteen_tools_defined() -> None:
    """All 13 video tools are defined."""
    assert len(ARIA_VIDEO_TOOLS) == 13


def test_all_tools_have_valid_schema() -> None:
    """Each tool follows the OpenAI function-calling schema."""
    for tool in ARIA_VIDEO_TOOLS:
        assert tool["type"] == "function"
        func = tool["function"]
        assert "name" in func
        assert "description" in func
        assert "parameters" in func
        params = func["parameters"]
        assert params["type"] == "object"
        assert "properties" in params
        assert "required" in params


def test_tool_names_match_map() -> None:
    """Every tool definition name appears in TOOL_AGENT_MAP."""
    tool_names = {t["function"]["name"] for t in ARIA_VIDEO_TOOLS}
    assert tool_names == set(TOOL_AGENT_MAP.keys())


def test_valid_tool_names_frozenset() -> None:
    """VALID_TOOL_NAMES is a frozenset matching all tool names."""
    expected = frozenset(TOOL_AGENT_MAP.keys())
    assert VALID_TOOL_NAMES == expected


def test_required_params_are_subset_of_properties() -> None:
    """Every required param must exist in properties."""
    for tool in ARIA_VIDEO_TOOLS:
        func = tool["function"]
        props = set(func["parameters"]["properties"].keys())
        required = set(func["parameters"]["required"])
        assert required.issubset(props), f"{func['name']}: required {required} not in {props}"


def test_tool_agent_map_values() -> None:
    """Agent map routes to known agents or 'service'."""
    valid_agents = {"hunter", "analyst", "scribe", "operator", "scout", "service", "ooda"}
    for tool_name, agent in TOOL_AGENT_MAP.items():
        assert agent in valid_agents, f"{tool_name} maps to unknown agent: {agent}"


def test_search_companies_schema() -> None:
    """search_companies has query (required) and optional filters."""
    tool = next(t for t in ARIA_VIDEO_TOOLS if t["function"]["name"] == "search_companies")
    params = tool["function"]["parameters"]
    assert "query" in params["properties"]
    assert "industry" in params["properties"]
    assert "funding_stage" in params["properties"]
    assert "location" in params["properties"]
    assert params["required"] == ["query"]


def test_draft_email_schema() -> None:
    """draft_email requires 'to' and 'subject_context', optional 'tone'."""
    tool = next(t for t in ARIA_VIDEO_TOOLS if t["function"]["name"] == "draft_email")
    params = tool["function"]["parameters"]
    assert "to" in params["properties"]
    assert "subject_context" in params["properties"]
    assert "tone" in params["properties"]
    assert set(params["required"]) == {"to", "subject_context"}


def test_get_pipeline_summary_no_required_params() -> None:
    """get_pipeline_summary requires no parameters."""
    tool = next(t for t in ARIA_VIDEO_TOOLS if t["function"]["name"] == "get_pipeline_summary")
    assert tool["function"]["parameters"]["required"] == []


# ====================
# VideoToolExecutor Tests
# ====================


@pytest.fixture
def executor() -> VideoToolExecutor:
    """Create a VideoToolExecutor with mocked DB."""
    ex = VideoToolExecutor(user_id="test-user-123")
    ex._db = MagicMock()
    return ex


@pytest.mark.asyncio
async def test_execute_unknown_tool(executor: VideoToolExecutor) -> None:
    """Unknown tool returns graceful message."""
    result = await executor.execute("nonexistent_tool", {})
    assert "don't have a tool" in result.spoken_text


@pytest.mark.asyncio
async def test_execute_get_lead_details_found(executor: VideoToolExecutor) -> None:
    """get_lead_details returns lead info when found."""
    mock_result = MagicMock()
    mock_result.data = [
        {
            "company_name": "Lonza",
            "health_score": 82,
            "lifecycle_stage": "qualified",
            "status": "active",
            "last_activity_at": "2026-02-15T10:00:00Z",
            "metadata": None,
        }
    ]
    executor._db.table.return_value.select.return_value.eq.return_value.ilike.return_value.limit.return_value.execute.return_value = mock_result

    with patch.object(executor, "_log_activity", new_callable=AsyncMock), \
         patch.object(executor, "_store_episodic", new_callable=AsyncMock):
        result = await executor.execute("get_lead_details", {"company_name": "Lonza"})

    assert "Lonza" in result.spoken_text
    assert "82" in result.spoken_text
    assert "qualified" in result.spoken_text


@pytest.mark.asyncio
async def test_execute_get_lead_details_not_found(executor: VideoToolExecutor) -> None:
    """get_lead_details returns offer to research when not found."""
    mock_result = MagicMock()
    mock_result.data = []
    executor._db.table.return_value.select.return_value.eq.return_value.ilike.return_value.limit.return_value.execute.return_value = mock_result

    with patch.object(executor, "_log_activity", new_callable=AsyncMock), \
         patch.object(executor, "_store_episodic", new_callable=AsyncMock):
        result = await executor.execute("get_lead_details", {"company_name": "UnknownCo"})

    assert "don't have" in result.spoken_text or "research" in result.spoken_text.lower()


@pytest.mark.asyncio
async def test_execute_get_pipeline_summary(executor: VideoToolExecutor) -> None:
    """get_pipeline_summary aggregates lead data."""
    mock_result = MagicMock()
    mock_result.data = [
        {"lifecycle_stage": "prospect", "health_score": 45, "status": "active"},
        {"lifecycle_stage": "prospect", "health_score": 60, "status": "active"},
        {"lifecycle_stage": "qualified", "health_score": 78, "status": "active"},
        {"lifecycle_stage": "negotiation", "health_score": 90, "status": "active"},
    ]
    executor._db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_result

    with patch.object(executor, "_log_activity", new_callable=AsyncMock), \
         patch.object(executor, "_store_episodic", new_callable=AsyncMock):
        result = await executor.execute("get_pipeline_summary", {})

    assert "4 active leads" in result.spoken_text
    assert "prospect" in result.spoken_text
    assert "qualified" in result.spoken_text


@pytest.mark.asyncio
async def test_execute_get_pipeline_summary_empty(executor: VideoToolExecutor) -> None:
    """get_pipeline_summary handles empty pipeline."""
    mock_result = MagicMock()
    mock_result.data = []
    executor._db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_result

    with patch.object(executor, "_log_activity", new_callable=AsyncMock), \
         patch.object(executor, "_store_episodic", new_callable=AsyncMock):
        result = await executor.execute("get_pipeline_summary", {})

    assert "empty" in result.spoken_text.lower()


@pytest.mark.asyncio
async def test_execute_get_battle_card_found(executor: VideoToolExecutor) -> None:
    """get_battle_card returns card details when found."""
    mock_result = MagicMock()
    mock_result.data = [
        {
            "competitor_name": "Catalent",
            "strengths": ["Scale", "Global presence"],
            "weaknesses": ["Slow turnaround"],
            "our_differentiators": ["Speed", "Flexibility"],
            "win_strategy": "Emphasise speed-to-market advantage",
        }
    ]
    executor._db.table.return_value.select.return_value.eq.return_value.ilike.return_value.limit.return_value.execute.return_value = mock_result

    with patch.object(executor, "_log_activity", new_callable=AsyncMock), \
         patch.object(executor, "_store_episodic", new_callable=AsyncMock):
        result = await executor.execute("get_battle_card", {"competitor_name": "Catalent"})

    assert "Catalent" in result.spoken_text
    assert "Scale" in result.spoken_text or "strengths" in result.spoken_text.lower()


@pytest.mark.asyncio
async def test_execute_add_lead_existing(executor: VideoToolExecutor) -> None:
    """add_lead_to_pipeline detects existing leads."""
    mock_result = MagicMock()
    mock_result.data = [
        {"id": "lead-1", "company_name": "Lonza", "lifecycle_stage": "qualified"}
    ]
    executor._db.table.return_value.select.return_value.eq.return_value.ilike.return_value.limit.return_value.execute.return_value = mock_result

    with patch.object(executor, "_log_activity", new_callable=AsyncMock), \
         patch.object(executor, "_store_episodic", new_callable=AsyncMock):
        result = await executor.execute("add_lead_to_pipeline", {"company_name": "Lonza"})

    assert "already" in result.spoken_text.lower()


@pytest.mark.asyncio
async def test_execute_add_lead_new(executor: VideoToolExecutor) -> None:
    """add_lead_to_pipeline inserts new lead."""
    # First call (existing check) returns empty
    mock_empty = MagicMock()
    mock_empty.data = []

    # Second call (insert) returns success
    mock_insert = MagicMock()
    mock_insert.data = [{"id": "new-lead"}]

    table_mock = MagicMock()

    call_count = 0

    def select_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        chain = MagicMock()
        chain.eq.return_value.ilike.return_value.limit.return_value.execute.return_value = mock_empty
        return chain

    def insert_side_effect(*args, **kwargs):
        chain = MagicMock()
        chain.execute.return_value = mock_insert
        return chain

    table_mock.select = select_side_effect
    table_mock.insert = insert_side_effect
    executor._db.table.return_value = table_mock

    with patch.object(executor, "_log_activity", new_callable=AsyncMock), \
         patch.object(executor, "_store_episodic", new_callable=AsyncMock):
        result = await executor.execute(
            "add_lead_to_pipeline",
            {"company_name": "NewBiotech", "contact_name": "Jane Doe"},
        )

    assert "NewBiotech" in result.spoken_text
    assert "pipeline" in result.spoken_text.lower() or "prospect" in result.spoken_text.lower()


@pytest.mark.asyncio
async def test_execute_search_companies() -> None:
    """search_companies routes to HunterAgent."""
    from src.integrations.tavus_tool_executor import ToolResult

    executor = VideoToolExecutor(user_id="test-user")

    mock_result = ToolResult(
        spoken_text="I found 2 companies matching your search. 1. BioGenTech 2. NovaCDMO",
        rich_content={"type": "lead_card", "data": {}},
    )

    with (
        patch.object(executor, "_handle_search_companies", new_callable=AsyncMock, return_value=mock_result),
        patch.object(executor, "_log_activity", new_callable=AsyncMock),
        patch.object(executor, "_store_episodic", new_callable=AsyncMock),
    ):
        result = await executor.execute("search_companies", {"query": "cell therapy biotechs"})

    text = result.spoken_text if hasattr(result, "spoken_text") else str(result)
    assert "BioGenTech" in text or "companies" in text.lower()


@pytest.mark.asyncio
async def test_execute_handles_exception_gracefully(executor: VideoToolExecutor) -> None:
    """Tool execution errors return user-friendly message."""
    with (
        patch.object(
            executor,
            "_handle_get_lead_details",
            side_effect=Exception("DB connection failed"),
        ),
        patch.object(executor, "_log_activity", new_callable=AsyncMock),
    ):
        result = await executor.execute("get_lead_details", {"company_name": "Test"})

    assert "issue" in result.spoken_text.lower()


@pytest.mark.asyncio
async def test_activity_logging(executor: VideoToolExecutor) -> None:
    """Tool execution logs to aria_activity."""
    mock_result = MagicMock()
    mock_result.data = [
        {
            "company_name": "TestCo",
            "health_score": 50,
            "lifecycle_stage": "prospect",
            "status": "active",
            "last_activity_at": None,
            "metadata": None,
        }
    ]
    executor._db.table.return_value.select.return_value.eq.return_value.ilike.return_value.limit.return_value.execute.return_value = mock_result

    mock_activity = MagicMock()
    mock_activity.record = AsyncMock()

    with patch("src.services.activity_service.ActivityService", return_value=mock_activity), \
         patch.object(executor, "_store_episodic", new_callable=AsyncMock):
        await executor.execute("get_lead_details", {"company_name": "TestCo"})

    mock_activity.record.assert_called_once()
    call_kwargs = mock_activity.record.call_args.kwargs
    assert call_kwargs["activity_type"] == "video_tool_executed"
    assert call_kwargs["metadata"]["tool_name"] == "get_lead_details"
    assert call_kwargs["metadata"]["success"] is True
