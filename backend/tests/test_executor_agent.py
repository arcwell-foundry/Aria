"""Tests for ExecutorAgent module."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# --- Section 1: Class structure ---


def test_executor_agent_has_name_and_description() -> None:
    """Test ExecutorAgent has correct name and description."""
    from src.agents.executor import ExecutorAgent

    assert ExecutorAgent.name == "Executor"
    assert ExecutorAgent.description == "Browser automation fallback for tasks without API access"


def test_executor_agent_has_agent_id() -> None:
    """Test ExecutorAgent has agent_id set."""
    from src.agents.executor import ExecutorAgent

    assert ExecutorAgent.agent_id == "executor"


def test_executor_agent_extends_base_agent() -> None:
    """Test ExecutorAgent extends BaseAgent directly."""
    from src.agents.base import BaseAgent
    from src.agents.executor import ExecutorAgent

    assert issubclass(ExecutorAgent, BaseAgent)


def test_executor_agent_initializes_with_llm_and_user() -> None:
    """Test ExecutorAgent initializes correctly with minimal args."""
    from src.agents.base import AgentStatus
    from src.agents.executor import ExecutorAgent

    mock_llm = MagicMock()
    agent = ExecutorAgent(llm_client=mock_llm, user_id="user-123")

    assert agent.llm == mock_llm
    assert agent.user_id == "user-123"
    assert agent.status == AgentStatus.IDLE


def test_executor_agent_registers_browser_navigate_tool() -> None:
    """Test ExecutorAgent registers a browser_navigate tool."""
    from src.agents.executor import ExecutorAgent

    mock_llm = MagicMock()
    agent = ExecutorAgent(llm_client=mock_llm, user_id="user-123")

    assert "browser_navigate" in agent.tools


def test_executor_agent_accepts_optional_params() -> None:
    """Test ExecutorAgent accepts persona_builder, browser_backend, procedural_memory."""
    from src.agents.executor import ExecutorAgent

    mock_llm = MagicMock()
    mock_persona = MagicMock()
    mock_backend = MagicMock()
    mock_memory = MagicMock()

    agent = ExecutorAgent(
        llm_client=mock_llm,
        user_id="user-123",
        persona_builder=mock_persona,
        browser_backend=mock_backend,
        procedural_memory=mock_memory,
    )

    assert agent.persona_builder == mock_persona
    assert agent._browser_backend == mock_backend
    assert agent._procedural_memory == mock_memory


# --- Section 2: Data models ---


def test_browser_step_roundtrip() -> None:
    """Test BrowserStep serializes and deserializes correctly."""
    from src.agents.executor import BrowserStep, BrowserStepType

    step = BrowserStep(
        step_type=BrowserStepType.CLICK,
        selector="#submit-btn",
        value="",
        description="Click the submit button",
        timeout_ms=3000,
        wait_after_ms=1000,
    )
    d = step.to_dict()
    restored = BrowserStep.from_dict(d)

    assert restored.step_type == BrowserStepType.CLICK
    assert restored.selector == "#submit-btn"
    assert restored.description == "Click the submit button"
    assert restored.timeout_ms == 3000
    assert restored.wait_after_ms == 1000


def test_browser_step_from_dict_defaults() -> None:
    """Test BrowserStep.from_dict uses defaults for missing fields."""
    from src.agents.executor import BrowserStep, BrowserStepType

    step = BrowserStep.from_dict({"step_type": "navigate"})
    assert step.step_type == BrowserStepType.NAVIGATE
    assert step.selector == ""
    assert step.timeout_ms == 5000


def test_browser_result_creation() -> None:
    """Test BrowserResult creates with correct fields."""
    from src.agents.executor import BrowserResult

    result = BrowserResult(
        success=True,
        steps_executed=3,
        steps_total=3,
        final_url="https://example.com/done",
    )
    assert result.success is True
    assert result.steps_executed == 3
    assert result.final_url == "https://example.com/done"


def test_browser_result_screenshots_property() -> None:
    """Test BrowserResult.screenshots extracts non-None screenshots."""
    from src.agents.executor import BrowserResult, BrowserStepResult

    result = BrowserResult(
        success=True,
        steps_executed=3,
        steps_total=3,
        step_results=[
            BrowserStepResult(step_index=0, success=True, screenshot_b64="abc123"),
            BrowserStepResult(step_index=1, success=True, screenshot_b64=None),
            BrowserStepResult(step_index=2, success=True, screenshot_b64="def456"),
        ],
    )
    assert result.screenshots == ["abc123", "def456"]


def test_browser_result_to_dict() -> None:
    """Test BrowserResult serializes to dict."""
    from src.agents.executor import BrowserResult

    result = BrowserResult(
        success=True,
        steps_executed=2,
        steps_total=2,
        final_url="https://example.com",
        extracted_data={"text": "hello"},
        workflow_id="wf-123",
    )
    d = result.to_dict()
    assert d["success"] is True
    assert d["steps_executed"] == 2
    assert d["final_url"] == "https://example.com"
    assert d["extracted_data"] == {"text": "hello"}
    assert d["workflow_id"] == "wf-123"
    assert isinstance(d["screenshots"], list)


def test_browser_step_type_enum_values() -> None:
    """Test BrowserStepType has all expected values."""
    from src.agents.executor import BrowserStepType

    expected = {"navigate", "click", "type_text", "select", "wait", "screenshot", "scroll", "extract"}
    actual = {e.value for e in BrowserStepType}
    assert actual == expected


# --- Section 3: Input validation ---


def test_validate_input_rejects_missing_task_description() -> None:
    """Test validate_input rejects task without task_description."""
    from src.agents.executor import ExecutorAgent

    mock_llm = MagicMock()
    agent = ExecutorAgent(llm_client=mock_llm, user_id="user-123")

    assert agent.validate_input({"url": "https://example.com", "url_approved": True}) is False


def test_validate_input_rejects_missing_url() -> None:
    """Test validate_input rejects task without url."""
    from src.agents.executor import ExecutorAgent

    mock_llm = MagicMock()
    agent = ExecutorAgent(llm_client=mock_llm, user_id="user-123")

    assert agent.validate_input({"task_description": "Do something", "url_approved": True}) is False


def test_validate_input_rejects_missing_url_approved() -> None:
    """Test validate_input rejects task without url_approved."""
    from src.agents.executor import ExecutorAgent

    mock_llm = MagicMock()
    agent = ExecutorAgent(llm_client=mock_llm, user_id="user-123")

    assert agent.validate_input({
        "task_description": "Do something",
        "url": "https://example.com",
    }) is False


def test_validate_input_rejects_non_http_url() -> None:
    """Test validate_input rejects non-http URLs."""
    from src.agents.executor import ExecutorAgent

    mock_llm = MagicMock()
    agent = ExecutorAgent(llm_client=mock_llm, user_id="user-123")

    assert agent.validate_input({
        "task_description": "Do something",
        "url": "ftp://example.com",
        "url_approved": True,
    }) is False


def test_validate_input_accepts_valid_task() -> None:
    """Test validate_input accepts a complete valid task."""
    from src.agents.executor import ExecutorAgent

    mock_llm = MagicMock()
    agent = ExecutorAgent(llm_client=mock_llm, user_id="user-123")

    assert agent.validate_input({
        "task_description": "Download report",
        "url": "https://example.com/report",
        "url_approved": True,
    }) is True


def test_validate_input_accepts_http_url() -> None:
    """Test validate_input accepts http:// URL."""
    from src.agents.executor import ExecutorAgent

    mock_llm = MagicMock()
    agent = ExecutorAgent(llm_client=mock_llm, user_id="user-123")

    assert agent.validate_input({
        "task_description": "Do something",
        "url": "http://example.com",
        "url_approved": True,
    }) is True


# --- Section 4: DCT enforcement ---


@pytest.mark.asyncio
async def test_execute_rejects_expired_dct() -> None:
    """Test execute rejects an expired DCT."""
    from src.agents.executor import ExecutorAgent

    mock_llm = MagicMock()
    agent = ExecutorAgent(llm_client=mock_llm, user_id="user-123")

    mock_dct = MagicMock()
    mock_dct.is_valid.return_value = False

    result = await agent.execute({
        "task_description": "Do something",
        "url": "https://example.com",
        "url_approved": True,
        "dct": mock_dct,
    })

    assert result.success is False
    assert "expired" in (result.error or "").lower() or "invalid" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_execute_rejects_dct_without_browser_navigate() -> None:
    """Test execute rejects DCT that doesn't permit browser_navigate."""
    from src.agents.executor import ExecutorAgent

    mock_llm = MagicMock()
    agent = ExecutorAgent(llm_client=mock_llm, user_id="user-123")

    mock_dct = MagicMock()
    mock_dct.is_valid.return_value = True
    mock_dct.can_perform.return_value = False

    result = await agent.execute({
        "task_description": "Do something",
        "url": "https://example.com",
        "url_approved": True,
        "dct": mock_dct,
    })

    assert result.success is False
    assert "browser_navigate" in (result.error or "").lower()


# --- Section 5: LLM planning ---


@pytest.mark.asyncio
async def test_plan_steps_from_llm_response() -> None:
    """Test _plan_steps parses LLM JSON response into BrowserSteps."""
    from src.agents.executor import BrowserStepType, ExecutorAgent

    mock_llm = MagicMock()
    llm_response = json.dumps([
        {"step_type": "click", "selector": "#btn", "description": "Click button"},
        {"step_type": "type_text", "selector": "#input", "value": "hello", "description": "Type text"},
    ])
    resp = MagicMock()
    resp.text = llm_response
    mock_llm.generate_response = AsyncMock(return_value=resp)

    agent = ExecutorAgent(llm_client=mock_llm, user_id="user-123")
    steps = await agent._plan_steps("Click button and type", "https://example.com")

    assert len(steps) == 2
    assert steps[0].step_type == BrowserStepType.CLICK
    assert steps[0].selector == "#btn"
    assert steps[1].step_type == BrowserStepType.TYPE_TEXT
    assert steps[1].value == "hello"


@pytest.mark.asyncio
async def test_plan_steps_returns_empty_on_llm_failure() -> None:
    """Test _plan_steps returns empty list when LLM fails."""
    from src.agents.executor import ExecutorAgent

    mock_llm = MagicMock()
    mock_llm.generate_response = AsyncMock(side_effect=RuntimeError("API error"))

    agent = ExecutorAgent(llm_client=mock_llm, user_id="user-123")
    steps = await agent._plan_steps("Do something", "https://example.com")

    assert steps == []


@pytest.mark.asyncio
async def test_plan_steps_returns_empty_on_invalid_json() -> None:
    """Test _plan_steps returns empty list on unparseable response."""
    from src.agents.executor import ExecutorAgent

    mock_llm = MagicMock()
    resp = MagicMock()
    resp.text = "This is not JSON at all"
    mock_llm.generate_response = AsyncMock(return_value=resp)

    agent = ExecutorAgent(llm_client=mock_llm, user_id="user-123")
    steps = await agent._plan_steps("Do something", "https://example.com")

    assert steps == []


@pytest.mark.asyncio
async def test_plan_steps_uses_persona_builder() -> None:
    """Test _plan_steps uses PersonaBuilder when available."""
    from src.agents.executor import ExecutorAgent

    mock_llm = MagicMock()
    resp = MagicMock()
    resp.text = json.dumps([{"step_type": "click", "selector": "#btn", "description": "Click"}])
    mock_llm.generate_response = AsyncMock(return_value=resp)

    mock_persona_ctx = MagicMock()
    mock_persona_ctx.to_system_prompt.return_value = "You are ARIA's Executor"
    mock_persona_builder = MagicMock()
    mock_persona_builder.build = AsyncMock(return_value=mock_persona_ctx)

    agent = ExecutorAgent(
        llm_client=mock_llm,
        user_id="user-123",
        persona_builder=mock_persona_builder,
    )
    await agent._plan_steps("Click button", "https://example.com")

    mock_persona_builder.build.assert_called_once()
    call_kwargs = mock_llm.generate_response.call_args.kwargs
    assert call_kwargs["system_prompt"] == "You are ARIA's Executor"


# --- Section 6: Procedural Memory ---


@pytest.mark.asyncio
async def test_procedural_replay_uses_stored_workflow() -> None:
    """Test _try_procedural_replay returns steps from stored workflow."""
    from src.agents.executor import BrowserStepType, ExecutorAgent

    mock_llm = MagicMock()
    mock_memory = AsyncMock()
    mock_memory.find_workflow.return_value = {
        "workflow_id": "wf-001",
        "success_rate": 0.8,
        "steps": [
            {"step_type": "click", "selector": "#go", "description": "Click go"},
        ],
    }

    agent = ExecutorAgent(
        llm_client=mock_llm,
        user_id="user-123",
        procedural_memory=mock_memory,
    )
    steps = await agent._try_procedural_replay("Click go button", "https://example.com")

    assert steps is not None
    assert len(steps) == 1
    assert steps[0].step_type == BrowserStepType.CLICK


@pytest.mark.asyncio
async def test_procedural_replay_skips_low_success_rate() -> None:
    """Test _try_procedural_replay skips workflow with low success_rate."""
    from src.agents.executor import ExecutorAgent

    mock_llm = MagicMock()
    mock_memory = AsyncMock()
    mock_memory.find_workflow.return_value = {
        "workflow_id": "wf-002",
        "success_rate": 0.3,
        "steps": [{"step_type": "click", "selector": "#go", "description": "Click"}],
    }

    agent = ExecutorAgent(
        llm_client=mock_llm,
        user_id="user-123",
        procedural_memory=mock_memory,
    )
    steps = await agent._try_procedural_replay("Click go button", "https://example.com")

    assert steps is None


@pytest.mark.asyncio
async def test_procedural_replay_returns_none_without_memory() -> None:
    """Test _try_procedural_replay returns None when no procedural_memory."""
    from src.agents.executor import ExecutorAgent

    mock_llm = MagicMock()
    agent = ExecutorAgent(llm_client=mock_llm, user_id="user-123")

    steps = await agent._try_procedural_replay("Click go button", "https://example.com")
    assert steps is None


@pytest.mark.asyncio
async def test_store_workflow_on_success() -> None:
    """Test _store_workflow stores steps in procedural memory."""
    from src.agents.executor import BrowserStep, BrowserStepType, ExecutorAgent

    mock_llm = MagicMock()
    mock_memory = AsyncMock()
    mock_memory.store_workflow.return_value = "wf-new"

    agent = ExecutorAgent(
        llm_client=mock_llm,
        user_id="user-123",
        procedural_memory=mock_memory,
    )
    steps = [BrowserStep(step_type=BrowserStepType.CLICK, selector="#btn", description="Click")]
    workflow_id = await agent._store_workflow("Click button", "https://example.com", steps)

    assert workflow_id == "wf-new"
    mock_memory.store_workflow.assert_called_once()


# --- Section 7: Full lifecycle (mock backend) ---


@pytest.mark.asyncio
async def test_full_lifecycle_with_mock_backend() -> None:
    """Test full execute flow with mocked browser backend and LLM planning."""
    from src.agents.executor import BrowserStepResult, ExecutorAgent

    mock_llm = MagicMock()
    llm_response = json.dumps([
        {"step_type": "click", "selector": "#btn", "description": "Click button"},
        {"step_type": "extract", "selector": "#result", "description": "Extract result"},
    ])
    resp = MagicMock()
    resp.text = llm_response
    mock_llm.generate_response = AsyncMock(return_value=resp)

    mock_backend = AsyncMock()
    mock_backend.start_session = AsyncMock()
    mock_backend.execute_step = AsyncMock(
        return_value=BrowserStepResult(step_index=0, success=True),
    )
    mock_backend.get_current_url = AsyncMock(return_value="https://example.com/done")
    mock_backend.take_screenshot = AsyncMock(return_value="screenshot_data")
    mock_backend.close = AsyncMock()

    agent = ExecutorAgent(
        llm_client=mock_llm,
        user_id="user-123",
        browser_backend=mock_backend,
    )

    task = {
        "task_description": "Click button and extract result",
        "url": "https://example.com",
        "url_approved": True,
    }

    result = await agent.execute(task)

    assert result.success is True
    assert result.data is not None
    assert result.data["success"] is True
    assert result.data["steps_executed"] == 2
    mock_backend.start_session.assert_called_once_with("https://example.com")
    mock_backend.close.assert_called_once()


@pytest.mark.asyncio
async def test_execute_fails_on_invalid_input_via_run() -> None:
    """Test run() rejects invalid input through validate_input."""
    from src.agents.executor import ExecutorAgent

    mock_llm = MagicMock()
    agent = ExecutorAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent.run({"url": "https://example.com"})

    assert result.success is False
    assert "validation" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_execute_with_provided_steps() -> None:
    """Test execute uses pre-provided steps instead of LLM planning."""
    from src.agents.executor import BrowserStepResult, ExecutorAgent

    mock_llm = MagicMock()
    # LLM should NOT be called since steps are provided
    mock_llm.generate_response = AsyncMock(side_effect=RuntimeError("Should not be called"))

    mock_backend = AsyncMock()
    mock_backend.start_session = AsyncMock()
    mock_backend.execute_step = AsyncMock(
        return_value=BrowserStepResult(step_index=0, success=True),
    )
    mock_backend.get_current_url = AsyncMock(return_value="https://example.com")
    mock_backend.close = AsyncMock()

    agent = ExecutorAgent(
        llm_client=mock_llm,
        user_id="user-123",
        browser_backend=mock_backend,
    )

    task = {
        "task_description": "Click button",
        "url": "https://example.com",
        "url_approved": True,
        "steps": [{"step_type": "click", "selector": "#btn", "description": "Click"}],
    }

    result = await agent.execute(task)
    assert result.success is True


@pytest.mark.asyncio
async def test_backend_failure_produces_error_result() -> None:
    """Test that a backend step failure produces a failed BrowserResult."""
    from src.agents.executor import BrowserStepResult, ExecutorAgent

    mock_llm = MagicMock()
    resp = MagicMock()
    resp.text = json.dumps([{"step_type": "click", "selector": "#missing", "description": "Click"}])
    mock_llm.generate_response = AsyncMock(return_value=resp)

    mock_backend = AsyncMock()
    mock_backend.start_session = AsyncMock()
    mock_backend.execute_step = AsyncMock(
        return_value=BrowserStepResult(step_index=0, success=False, error="Element not found"),
    )
    mock_backend.get_current_url = AsyncMock(return_value="https://example.com")
    mock_backend.take_screenshot = AsyncMock(return_value="error_screenshot")
    mock_backend.close = AsyncMock()

    agent = ExecutorAgent(
        llm_client=mock_llm,
        user_id="user-123",
        browser_backend=mock_backend,
    )

    task = {
        "task_description": "Click missing element",
        "url": "https://example.com",
        "url_approved": True,
    }

    result = await agent.execute(task)
    assert result.success is False
    assert "failed" in (result.error or "").lower() or "Element not found" in (result.error or "")


# --- Section 8: Module exports ---


def test_executor_exported_from_agents_module() -> None:
    """Test ExecutorAgent is exported from agents module."""
    from src.agents import ExecutorAgent

    assert ExecutorAgent.name == "Executor"


def test_all_includes_executor_exports() -> None:
    """Test __all__ includes ExecutorAgent, BrowserResult, BrowserStep."""
    from src.agents import __all__

    assert "ExecutorAgent" in __all__
    assert "BrowserResult" in __all__
    assert "BrowserStep" in __all__
