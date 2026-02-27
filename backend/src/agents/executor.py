"""Executor agent module for ARIA.

Browser automation fallback for tasks where no API exists.
Uses Playwright for headless browser automation, learns from
success via Procedural Memory, and integrates with the existing
DCT/trace/orchestration infrastructure.
"""

import asyncio
import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from src.agents.base import AgentResult, BaseAgent
from src.core.task_types import TaskType

if TYPE_CHECKING:
    from src.core.llm import LLMClient
    from src.core.persona import PersonaBuilder
    from src.memory.cold_retrieval import ColdMemoryRetriever
    from src.memory.hot_context import HotContextBuilder

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Safety constants
# ---------------------------------------------------------------------------

MAX_SESSION_DURATION_SECONDS = 300  # 5 minutes
MAX_STEPS_PER_SESSION = 20
MAX_SCREENSHOTS_PER_SESSION = 5
PROCEDURAL_MIN_SUCCESS_RATE = 0.6


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class BrowserStepType(str, Enum):
    """Types of browser actions the executor can perform."""

    NAVIGATE = "navigate"
    CLICK = "click"
    TYPE_TEXT = "type_text"
    SELECT = "select"
    WAIT = "wait"
    SCREENSHOT = "screenshot"
    SCROLL = "scroll"
    EXTRACT = "extract"


@dataclass
class BrowserStep:
    """A single browser automation step."""

    step_type: BrowserStepType
    selector: str = ""
    value: str = ""
    description: str = ""
    timeout_ms: int = 5000
    wait_after_ms: int = 500

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "step_type": self.step_type.value,
            "selector": self.selector,
            "value": self.value,
            "description": self.description,
            "timeout_ms": self.timeout_ms,
            "wait_after_ms": self.wait_after_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BrowserStep":
        """Deserialize from dictionary."""
        return cls(
            step_type=BrowserStepType(data["step_type"]),
            selector=data.get("selector", ""),
            value=data.get("value", ""),
            description=data.get("description", ""),
            timeout_ms=data.get("timeout_ms", 5000),
            wait_after_ms=data.get("wait_after_ms", 500),
        )


@dataclass
class BrowserStepResult:
    """Result of executing a single browser step."""

    step_index: int
    success: bool
    screenshot_b64: str | None = None
    extracted_data: dict[str, Any] | None = None
    error: str | None = None
    elapsed_ms: int = 0


@dataclass
class BrowserResult:
    """Result of a complete browser automation session."""

    success: bool
    steps_executed: int
    steps_total: int
    step_results: list[BrowserStepResult] = field(default_factory=list)
    final_url: str = ""
    extracted_data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    total_elapsed_ms: int = 0
    workflow_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "success": self.success,
            "steps_executed": self.steps_executed,
            "steps_total": self.steps_total,
            "final_url": self.final_url,
            "extracted_data": self.extracted_data,
            "error": self.error,
            "total_elapsed_ms": self.total_elapsed_ms,
            "workflow_id": self.workflow_id,
            "screenshots": self.screenshots,
        }

    @property
    def screenshots(self) -> list[str]:
        """Extract all non-None screenshots from step results."""
        return [sr.screenshot_b64 for sr in self.step_results if sr.screenshot_b64 is not None]


# ---------------------------------------------------------------------------
# Browser backend abstraction
# ---------------------------------------------------------------------------


@runtime_checkable
class BrowserBackend(Protocol):
    """Protocol for browser automation backends."""

    async def start_session(self, url: str) -> None:
        """Navigate to the initial URL and start a browser session."""
        ...

    async def execute_step(self, step: BrowserStep) -> BrowserStepResult:
        """Execute a single browser step."""
        ...

    async def take_screenshot(self) -> str:
        """Capture a screenshot and return base64-encoded JPEG."""
        ...

    async def get_current_url(self) -> str:
        """Return the current page URL."""
        ...

    async def close(self) -> None:
        """Close the browser session."""
        ...


class PlaywrightBackend:
    """Concrete browser backend using Playwright.

    Launches headless Chromium at 1280x720. Screenshot capture returns
    base64 JPEG via Playwright's built-in screenshot method. Browser
    import is lazy (same pattern as web_intel.py).
    """

    def __init__(self) -> None:
        self._playwright: Any = None
        self._browser: Any = None
        self._page: Any = None

    async def start_session(self, url: str) -> None:
        """Launch browser and navigate to initial URL."""
        try:
            from playwright.async_api import async_playwright
        except ImportError as e:
            raise RuntimeError(
                "Playwright is not installed. Run: pip install playwright && playwright install chromium"
            ) from e

        self._playwright = await async_playwright().__aenter__()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
        )
        self._page = await self._browser.new_page(
            viewport={"width": 1280, "height": 720},
        )
        await self._page.goto(url, wait_until="domcontentloaded", timeout=30000)

    async def execute_step(self, step: BrowserStep) -> BrowserStepResult:
        """Execute a single browser automation step."""
        if self._page is None:
            return BrowserStepResult(
                step_index=0,
                success=False,
                error="Browser session not started",
            )

        start = time.perf_counter()
        try:
            await self._dispatch_step(step)

            if step.wait_after_ms > 0:
                await asyncio.sleep(step.wait_after_ms / 1000)

            elapsed = int((time.perf_counter() - start) * 1000)

            extracted = None
            if step.step_type == BrowserStepType.EXTRACT and step.selector:
                content = await self._page.text_content(
                    step.selector,
                    timeout=step.timeout_ms,
                )
                extracted = {"text": content or ""}

            return BrowserStepResult(
                step_index=0,
                success=True,
                extracted_data=extracted,
                elapsed_ms=elapsed,
            )

        except Exception as e:
            elapsed = int((time.perf_counter() - start) * 1000)
            return BrowserStepResult(
                step_index=0,
                success=False,
                error=str(e),
                elapsed_ms=elapsed,
            )

    async def _dispatch_step(self, step: BrowserStep) -> None:
        """Dispatch a step to the appropriate Playwright method."""
        page = self._page
        timeout = step.timeout_ms

        if step.step_type == BrowserStepType.NAVIGATE:
            await page.goto(step.value, wait_until="domcontentloaded", timeout=timeout)

        elif step.step_type == BrowserStepType.CLICK:
            await page.click(step.selector, timeout=timeout)

        elif step.step_type == BrowserStepType.TYPE_TEXT:
            await page.fill(step.selector, step.value, timeout=timeout)

        elif step.step_type == BrowserStepType.SELECT:
            await page.select_option(step.selector, step.value, timeout=timeout)

        elif step.step_type == BrowserStepType.WAIT:
            if step.selector:
                await page.wait_for_selector(step.selector, timeout=timeout)
            else:
                await asyncio.sleep(step.timeout_ms / 1000)

        elif step.step_type == BrowserStepType.SCREENSHOT:
            pass  # Screenshot is handled separately

        elif step.step_type == BrowserStepType.SCROLL:
            amount = int(step.value) if step.value else 300
            await page.evaluate(f"window.scrollBy(0, {amount})")

        elif step.step_type == BrowserStepType.EXTRACT:
            pass  # Extraction is handled in execute_step

    async def take_screenshot(self) -> str:
        """Capture a screenshot as base64 JPEG."""
        if self._page is None:
            return ""
        import base64

        screenshot_bytes = await self._page.screenshot(type="jpeg", quality=50)
        return base64.b64encode(screenshot_bytes).decode("utf-8")

    async def get_current_url(self) -> str:
        """Return the current page URL."""
        if self._page is None:
            return ""
        return self._page.url

    async def close(self) -> None:
        """Close browser and cleanup Playwright resources."""
        try:
            if self._browser is not None:
                await self._browser.close()
            if self._playwright is not None:
                await self._playwright.__aexit__(None, None, None)
        except Exception as e:
            logger.warning("Error closing browser: %s", e)
        finally:
            self._page = None
            self._browser = None
            self._playwright = None


# ---------------------------------------------------------------------------
# Procedural memory interface
# ---------------------------------------------------------------------------


class ProceduralMemory(Protocol):
    """Protocol for procedural memory storage."""

    async def find_workflow(
        self,
        task_description: str,
        url: str,
    ) -> dict[str, Any] | None:
        """Find a stored workflow matching the task and URL.

        Returns dict with 'steps' (list of step dicts), 'success_rate' (float),
        and 'workflow_id' (str), or None if no match.
        """
        ...

    async def store_workflow(
        self,
        task_description: str,
        url: str,
        steps: list[dict[str, Any]],
    ) -> str:
        """Store a successful workflow. Returns workflow_id."""
        ...

    async def record_outcome(
        self,
        workflow_id: str,
        success: bool,
    ) -> None:
        """Record success/failure for a replayed workflow."""
        ...


# ---------------------------------------------------------------------------
# Fallback system prompt
# ---------------------------------------------------------------------------

_FALLBACK_SYSTEM_PROMPT = """\
You are ARIA's Executor — a browser automation specialist. Your job is to plan \
precise browser steps to accomplish a task on a given URL.

SAFETY RULES (ABSOLUTE — NEVER VIOLATE):
- NEVER enter passwords or authentication credentials.
- NEVER interact with login/auth forms.
- NEVER interact with payment forms or enter financial data.
- NEVER download or execute files.
- NEVER navigate away from the approved URL domain.

You must return a JSON array of browser steps. Each step is an object with:
{
  "step_type": "navigate" | "click" | "type_text" | "select" | "wait" | "screenshot" | "scroll" | "extract",
  "selector": "CSS selector (if applicable)",
  "value": "text to type, URL to navigate, scroll amount, etc.",
  "description": "human-readable description of what this step does",
  "timeout_ms": 5000,
  "wait_after_ms": 500
}

Return ONLY the JSON array, no other text."""


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class ExecutorAgent(BaseAgent):
    """Browser automation fallback agent for ARIA.

    Automates web browser tasks when no API exists. Uses Playwright for
    headless browser control, learns from successful workflows via
    Procedural Memory, and enforces strict safety constraints.

    Extends BaseAgent directly (not SkillAwareAgent) because browser
    automation doesn't participate in the skills system.
    """

    name = "Executor"
    description = "Browser automation fallback for tasks without API access"
    agent_id = "executor"

    def __init__(
        self,
        llm_client: "LLMClient",
        user_id: str,
        persona_builder: "PersonaBuilder | None" = None,
        hot_context_builder: "HotContextBuilder | None" = None,
        cold_retriever: "ColdMemoryRetriever | None" = None,
        browser_backend: "BrowserBackend | None" = None,
        procedural_memory: "ProceduralMemory | None" = None,
    ) -> None:
        self._browser_backend = browser_backend
        self._procedural_memory = procedural_memory
        super().__init__(
            llm_client=llm_client,
            user_id=user_id,
            persona_builder=persona_builder,
            hot_context_builder=hot_context_builder,
            cold_retriever=cold_retriever,
        )

    def _register_tools(self) -> dict[str, Callable[..., Any]]:
        """Register browser automation tool."""
        return {"browser_navigate": self.execute_browser_task}

    def validate_input(self, task: dict[str, Any]) -> bool:
        """Validate task has required fields for browser automation.

        Requires:
        - task_description: non-empty string
        - url: string starting with http:// or https://
        - url_approved: True (user pre-approved the URL)
        """
        task_description = task.get("task_description")
        if not task_description or not isinstance(task_description, str):
            return False

        url = task.get("url")
        if not url or not isinstance(url, str):
            return False
        if not url.startswith(("http://", "https://")):
            return False

        return bool(task.get("url_approved"))

    async def execute(self, task: dict[str, Any]) -> AgentResult:
        """Execute browser automation via the standard agent interface.

        Validates DCT if present, then delegates to execute_browser_task.

        Args:
            task: Task dict with task_description, url, url_approved, and
                  optional steps and dct.

        Returns:
            AgentResult wrapping the BrowserResult.
        """
        # Validate DCT if provided
        dct = task.get("dct")
        if dct is not None:
            if hasattr(dct, "is_valid") and not dct.is_valid():
                return AgentResult(
                    success=False,
                    data=None,
                    error="DCT is expired or invalid",
                )
            if hasattr(dct, "can_perform") and not dct.can_perform("browser_navigate"):
                return AgentResult(
                    success=False,
                    data=None,
                    error="DCT does not permit browser_navigate",
                )

        try:
            result = await self.execute_browser_task(
                task_description=task["task_description"],
                url=task["url"],
                steps=task.get("steps"),
            )
            return AgentResult(
                success=result.success,
                data=result.to_dict(),
                error=result.error,
            )
        except Exception as e:
            logger.error("Executor agent failed: %s", e)
            return AgentResult(
                success=False,
                data=None,
                error=str(e),
            )

    async def execute_browser_task(
        self,
        task_description: str,
        url: str,
        steps: list[dict[str, Any]] | None = None,
    ) -> BrowserResult:
        """Core browser automation method.

        Flow:
        1. Try procedural replay (if matching workflow found with success_rate >= 0.6)
        2. Plan steps via LLM (or use provided steps)
        3. Execute steps with 5-minute timeout
        4. Store successful workflow in Procedural Memory

        Args:
            task_description: What to accomplish.
            url: The approved URL to automate.
            steps: Optional pre-planned steps (skip LLM planning).

        Returns:
            BrowserResult with execution details.
        """
        start_time = time.perf_counter()

        # 1. Try procedural replay
        replay_steps = await self._try_procedural_replay(task_description, url)
        is_replay = False
        if replay_steps is not None:
            browser_steps = replay_steps
            is_replay = True
        elif steps is not None:
            # Use provided steps
            browser_steps = [BrowserStep.from_dict(s) for s in steps]
        else:
            # 2. Plan steps via LLM
            browser_steps = await self._plan_steps(task_description, url)

        if not browser_steps:
            return BrowserResult(
                success=False,
                steps_executed=0,
                steps_total=0,
                error="No browser steps planned",
                total_elapsed_ms=int((time.perf_counter() - start_time) * 1000),
            )

        # Cap steps
        if len(browser_steps) > MAX_STEPS_PER_SESSION:
            browser_steps = browser_steps[:MAX_STEPS_PER_SESSION]

        # 3. Execute with timeout
        try:
            result = await asyncio.wait_for(
                self._execute_steps(url, browser_steps),
                timeout=MAX_SESSION_DURATION_SECONDS,
            )
        except TimeoutError:
            result = BrowserResult(
                success=False,
                steps_executed=0,
                steps_total=len(browser_steps),
                error=f"Session timed out after {MAX_SESSION_DURATION_SECONDS}s",
            )

        result.total_elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        # 4. Store on success / record outcome
        if result.success:
            workflow_id = await self._store_workflow(
                task_description,
                url,
                browser_steps,
            )
            result.workflow_id = workflow_id

        if is_replay:
            await self._record_procedural_outcome(task_description, result.success)

        return result

    async def _try_procedural_replay(
        self,
        task_description: str,
        url: str,
    ) -> list[BrowserStep] | None:
        """Try to find and replay a stored workflow.

        Returns list of BrowserSteps if a matching workflow with
        success_rate >= PROCEDURAL_MIN_SUCCESS_RATE is found.
        """
        if self._procedural_memory is None:
            return None

        try:
            workflow = await self._procedural_memory.find_workflow(
                task_description,
                url,
            )
            if workflow is None:
                return None

            success_rate = workflow.get("success_rate", 0.0)
            if success_rate < PROCEDURAL_MIN_SUCCESS_RATE:
                logger.info(
                    "Procedural workflow found but success_rate %.2f < %.2f threshold",
                    success_rate,
                    PROCEDURAL_MIN_SUCCESS_RATE,
                )
                return None

            raw_steps = workflow.get("steps", [])
            return [BrowserStep.from_dict(s) for s in raw_steps]

        except Exception as e:
            logger.warning("Procedural memory lookup failed: %s", e)
            return None

    async def _plan_steps(
        self,
        task_description: str,
        url: str,
    ) -> list[BrowserStep]:
        """Use LLM to plan browser automation steps.

        Args:
            task_description: What to accomplish.
            url: The target URL.

        Returns:
            List of BrowserSteps, or empty list on failure.
        """
        try:
            system_prompt = await self._build_executor_prompt()

            user_message = (
                f"## Browser Automation Task\n\n"
                f"**URL:** {url}\n"
                f"**Task:** {task_description}\n\n"
                f"Plan the exact browser steps needed to accomplish this task. "
                f"Return ONLY a JSON array of step objects."
            )

            response = await self.llm.generate_response(
                messages=[{"role": "user", "content": user_message}],
                system_prompt=system_prompt,
                user_id=self.user_id,
                task=TaskType.OPERATOR_ACTION,
                agent_id="executor",
            )

            return self._parse_steps_response(response.text)

        except Exception as e:
            logger.warning("LLM step planning failed: %s", e)
            return []

    async def _build_executor_prompt(self) -> str:
        """Build system prompt using PersonaBuilder or fallback."""
        task_desc = (
            "Plan precise browser automation steps for a web task. "
            "You are a browser automation specialist. "
            "NEVER interact with login forms, payment forms, or enter passwords."
        )

        persona_prompt = await self._get_persona_system_prompt(
            task_description=task_desc,
            output_format="json",
        )

        if persona_prompt is not None:
            return persona_prompt

        return _FALLBACK_SYSTEM_PROMPT

    @staticmethod
    def _parse_steps_response(text: str) -> list[BrowserStep]:
        """Parse LLM response into list of BrowserSteps."""
        try:
            data = _extract_json_from_text(text)
        except (ValueError, json.JSONDecodeError) as e:
            logger.warning("Could not parse step planning response: %s", e)
            return []

        if not isinstance(data, list):
            logger.warning("LLM returned non-array for step planning")
            return []

        steps: list[BrowserStep] = []
        for item in data:
            try:
                steps.append(BrowserStep.from_dict(item))
            except (KeyError, ValueError) as e:
                logger.warning("Skipping invalid step: %s", e)
                continue

        return steps

    async def _execute_steps(
        self,
        url: str,
        steps: list[BrowserStep],
    ) -> BrowserResult:
        """Execute browser steps sequentially.

        Creates a backend, navigates to the URL, executes each step,
        captures screenshots on failures (up to MAX_SCREENSHOTS_PER_SESSION),
        and fails fast on the first error.

        Args:
            url: The starting URL.
            steps: The browser steps to execute.

        Returns:
            BrowserResult with execution details.
        """
        backend = self._browser_backend or PlaywrightBackend()
        step_results: list[BrowserStepResult] = []
        screenshot_count = 0
        extracted_data: dict[str, Any] = {}

        try:
            await backend.start_session(url)

            for i, step in enumerate(steps):
                result = await backend.execute_step(step)
                result.step_index = i
                step_results.append(result)

                if not result.success:
                    # Screenshot on failure
                    if screenshot_count < MAX_SCREENSHOTS_PER_SESSION:
                        try:
                            screenshot = await backend.take_screenshot()
                            result.screenshot_b64 = screenshot
                            screenshot_count += 1
                        except Exception:
                            pass
                    # Fail fast
                    final_url = await backend.get_current_url()
                    return BrowserResult(
                        success=False,
                        steps_executed=i + 1,
                        steps_total=len(steps),
                        step_results=step_results,
                        final_url=final_url,
                        extracted_data=extracted_data,
                        error=f"Step {i} failed: {result.error}",
                    )

                # Collect extracted data
                if result.extracted_data:
                    extracted_data.update(result.extracted_data)

                # Screenshot on explicit screenshot step
                if (
                    step.step_type == BrowserStepType.SCREENSHOT
                    and screenshot_count < MAX_SCREENSHOTS_PER_SESSION
                ):
                    try:
                        screenshot = await backend.take_screenshot()
                        result.screenshot_b64 = screenshot
                        screenshot_count += 1
                    except Exception:
                        pass

            final_url = await backend.get_current_url()
            return BrowserResult(
                success=True,
                steps_executed=len(steps),
                steps_total=len(steps),
                step_results=step_results,
                final_url=final_url,
                extracted_data=extracted_data,
            )

        except Exception as e:
            return BrowserResult(
                success=False,
                steps_executed=len(step_results),
                steps_total=len(steps),
                step_results=step_results,
                error=str(e),
            )

        finally:
            await backend.close()

    async def _store_workflow(
        self,
        task_description: str,
        url: str,
        steps: list[BrowserStep],
    ) -> str | None:
        """Store a successful workflow in Procedural Memory.

        Returns workflow_id on success, None if no procedural memory
        is configured or storage fails.
        """
        if self._procedural_memory is None:
            return None

        try:
            step_dicts = [s.to_dict() for s in steps]
            workflow_id = await self._procedural_memory.store_workflow(
                task_description,
                url,
                step_dicts,
            )
            logger.info("Stored successful workflow: %s", workflow_id)
            return workflow_id
        except Exception as e:
            logger.warning("Failed to store workflow: %s", e)
            return None

    async def _record_procedural_outcome(
        self,
        task_description: str,
        success: bool,
    ) -> None:
        """Record success/failure for a replayed workflow."""
        if self._procedural_memory is None:
            return

        try:
            # Re-lookup to get workflow_id
            workflow = await self._procedural_memory.find_workflow(
                task_description,
                "",
            )
            if workflow and "workflow_id" in workflow:
                await self._procedural_memory.record_outcome(
                    workflow["workflow_id"],
                    success,
                )
        except Exception as e:
            logger.warning("Failed to record procedural outcome: %s", e)


# ---------------------------------------------------------------------------
# JSON extraction helper (same pattern as verifier.py)
# ---------------------------------------------------------------------------


def _extract_json_from_text(text: str) -> Any:
    """Extract JSON from text that may be wrapped in markdown code fences."""
    text_stripped = text.strip()

    # Strategy 1: Direct parse
    try:
        return json.loads(text_stripped)
    except json.JSONDecodeError:
        pass

    # Strategy 2: Code fence extraction
    fence_pattern = r"```(?:json)?\s*\n?(.*?)\n?\s*```"
    fence_match = re.search(fence_pattern, text_stripped, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Strategy 3: Find outermost brackets/braces
    for open_char, close_char in [("[", "]"), ("{", "}")]:
        start = text_stripped.find(open_char)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(text_stripped)):
            if text_stripped[i] == open_char:
                depth += 1
            elif text_stripped[i] == close_char:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text_stripped[start : i + 1])
                    except json.JSONDecodeError:
                        break

    raise ValueError(f"Could not extract valid JSON from text: {text_stripped[:200]}...")
