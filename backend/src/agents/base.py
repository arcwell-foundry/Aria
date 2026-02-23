"""Base agent module for ARIA.

Provides the abstract base class and common types for all specialized agents.
"""

import asyncio
import inspect
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.core.llm import LLMClient
    from src.core.persona import PersonaBuilder
    from src.mcp_servers.client import MCPToolClient
    from src.memory.cold_retrieval import ColdMemoryRetriever
    from src.memory.hot_context import HotContext, HotContextBuilder
    from src.memory.working import WorkingMemory

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    """Current execution status of an agent."""

    IDLE = "idle"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class AgentResult:
    """Result of an agent execution.

    Captures success/failure status, output data, error information,
    and execution metrics.
    """

    success: bool
    data: Any
    error: str | None = None
    tokens_used: int = 0
    execution_time_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize result to dictionary.

        Returns:
            Dictionary representation suitable for JSON.
        """
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "tokens_used": self.tokens_used,
            "execution_time_ms": self.execution_time_ms,
        }


class BaseAgent(ABC):
    """Abstract base class for all ARIA agents.

    Provides common functionality including tool registration,
    status tracking, and execution lifecycle management.
    """

    name: str
    description: str

    def __init__(
        self,
        llm_client: "LLMClient",
        user_id: str,
        persona_builder: "PersonaBuilder | None" = None,
        hot_context_builder: "HotContextBuilder | None" = None,
        cold_retriever: "ColdMemoryRetriever | None" = None,
        mcp_client: "MCPToolClient | None" = None,
    ) -> None:
        """Initialize the agent.

        Args:
            llm_client: LLM client for reasoning and generation.
            user_id: ID of the user this agent is working for.
            persona_builder: Optional PersonaBuilder for centralized prompt assembly.
            hot_context_builder: Optional builder for always-loaded context.
            cold_retriever: Optional retriever for on-demand deep memory search.
            mcp_client: Optional MCP tool client for calling tools via MCP servers.
        """
        self.llm = llm_client
        self.user_id = user_id
        self.persona_builder = persona_builder
        self._hot_context_builder = hot_context_builder
        self._cold_retriever = cold_retriever
        self._mcp_client = mcp_client
        self._hot_context_cache: HotContext | None = None
        self.status = AgentStatus.IDLE
        self.total_tokens_used = 0
        self.tools: dict[str, Callable[..., Any]] = self._register_tools()

    @abstractmethod
    def _register_tools(self) -> dict[str, Callable[..., Any]]:
        """Register agent-specific tools.

        Returns:
            Dictionary mapping tool names to callable functions.
        """
        pass

    def validate_input(self, task: dict[str, Any]) -> bool:  # noqa: ARG002
        """Validate task input before execution.

        Subclasses can override to add custom validation logic.

        Args:
            task: Task specification to validate.

        Returns:
            True if valid, False otherwise.
        """
        return True

    def format_output(self, data: Any) -> Any:  # noqa: ARG002
        """Format output data before returning.

        Subclasses can override to transform or enrich output.

        Args:
            data: Raw output data from execution.

        Returns:
            Formatted output data.
        """
        return data

    def reset_token_count(self) -> None:
        """Reset the accumulated token usage counter."""
        self.total_tokens_used = 0

    @property
    def is_idle(self) -> bool:
        """Check if agent is idle."""
        return self.status == AgentStatus.IDLE

    @property
    def is_running(self) -> bool:
        """Check if agent is currently running."""
        return self.status == AgentStatus.RUNNING

    @property
    def is_complete(self) -> bool:
        """Check if agent completed successfully."""
        return self.status == AgentStatus.COMPLETE

    @property
    def is_failed(self) -> bool:
        """Check if agent failed."""
        return self.status == AgentStatus.FAILED

    async def _get_persona_system_prompt(
        self,
        task_description: str = "",
        output_format: str = "json",
        include_relationship: bool = False,
        lead_id: str | None = None,
        account_name: str | None = None,
        recipient_name: str | None = None,
    ) -> str | None:
        """Build a persona-based system prompt if PersonaBuilder is available.

        Returns None if no persona_builder is set, allowing the caller
        to fall back to its hardcoded prompt.

        Args:
            task_description: What this agent is currently doing.
            output_format: Expected output format.
            include_relationship: Whether to include relationship context.
            lead_id: Optional lead ID for relationship context.
            account_name: Optional account name for relationship context.
            recipient_name: Optional recipient name for relationship context.

        Returns:
            System prompt string or None.
        """
        if self.persona_builder is None:
            return None

        try:
            from src.core.persona import PersonaRequest

            request = PersonaRequest(
                user_id=self.user_id,
                agent_name=getattr(self, "name", None),
                agent_role_description=getattr(self, "description", None),
                task_description=task_description,
                output_format=output_format,
                include_relationship_context=include_relationship,
                lead_id=lead_id,
                account_name=account_name,
                recipient_name=recipient_name,
            )
            ctx = await self.persona_builder.build(request)
            return ctx.to_system_prompt()
        except Exception as e:
            logger.warning("PersonaBuilder failed, falling back to hardcoded prompt: %s", e)
            return None

    async def _call_tool(self, tool_name: str, **kwargs: Any) -> Any:
        """Call a registered tool with error handling.

        Args:
            tool_name: Name of the tool to call.
            **kwargs: Arguments to pass to the tool.

        Returns:
            Tool execution result.

        Raises:
            ValueError: If tool_name is not registered.
        """
        if tool_name not in self.tools:
            raise ValueError(f"Unknown tool: {tool_name}")

        tool = self.tools[tool_name]

        # Handle both sync and async tools
        if inspect.iscoroutinefunction(tool):
            return await tool(**kwargs)
        else:
            return tool(**kwargs)

    async def _call_tool_with_retry(
        self,
        tool_name: str,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        **kwargs: Any,
    ) -> Any:
        """Call a tool with automatic retry on failure.

        Args:
            tool_name: Name of the tool to call.
            max_retries: Maximum number of retry attempts.
            retry_delay: Delay in seconds between retries.
            **kwargs: Arguments to pass to the tool.

        Returns:
            Tool execution result.

        Raises:
            Exception: If all retries are exhausted.
        """
        last_error: Exception | None = None

        for attempt in range(max_retries):
            try:
                return await self._call_tool(tool_name, **kwargs)
            except Exception as e:
                last_error = e
                logger.warning(
                    f"Tool {tool_name} failed (attempt {attempt + 1}/{max_retries}): {e}"
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)

        # Re-raise the last error after exhausting retries
        if last_error is not None:
            raise last_error
        raise RuntimeError(f"Tool {tool_name} failed with no error captured")

    async def _call_mcp_tool(
        self,
        tool_name: str,
        *,
        dct: Any = None,
        **kwargs: Any,
    ) -> Any:
        """Call a tool via MCP if a client is available, else fall back to ``_call_tool``.

        This is the preferred way for agents to call tools when
        ``USE_MCP_TOOLS`` is enabled.  When ``_mcp_client`` is None the
        call transparently falls back to the agent's locally registered
        tool.

        Args:
            tool_name: Name of the tool to call.
            dct: Optional DelegationCapabilityToken for MCP enforcement.
            **kwargs: Arguments to pass to the tool.

        Returns:
            Tool execution result.
        """
        if self._mcp_client is not None:
            return await self._mcp_client.call_tool(
                tool_name=tool_name,
                arguments=kwargs,
                dct=dct,
                delegatee=getattr(self, "name", "unknown"),
            )
        return await self._call_tool(tool_name, **kwargs)

    async def tracked_api_call(
        self,
        api_type: str,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Execute an external API call with per-user usage tracking.

        Wraps Exa searches, Composio actions, PubMed queries, etc. with
        rate limiting and usage recording. Use this instead of calling
        external APIs directly.

        Args:
            api_type: The API type (exa, composio, pubmed, fda, etc.).
            func: The async function to execute.
            *args: Positional arguments for func.
            **kwargs: Keyword arguments for func.

        Returns:
            The result of func(*args, **kwargs).

        Raises:
            RateLimitExceeded: If the user has exceeded their daily limit.
        """
        try:
            from src.services.usage_tracker import track_and_execute

            return await track_and_execute(
                self.user_id, api_type, func, *args, **kwargs
            )
        except ImportError:
            # Fallback: execute without tracking if module unavailable
            return await func(*args, **kwargs)

    @abstractmethod
    async def execute(self, task: dict[str, Any]) -> AgentResult:
        """Execute the agent's primary task.

        Args:
            task: Task specification with parameters.

        Returns:
            AgentResult with success status and output data.
        """
        pass

    async def get_hot_context(
        self,
        working_memory: "WorkingMemory | None" = None,
    ) -> "HotContext | None":
        """Lazy-load hot context, cached per run.

        Args:
            working_memory: Optional working memory with recent messages.

        Returns:
            HotContext if builder is configured, None otherwise.
        """
        if self._hot_context_builder is None:
            return None
        if self._hot_context_cache is None:
            self._hot_context_cache = await self._hot_context_builder.build(
                self.user_id,
                working_memory=working_memory,
            )
        return self._hot_context_cache

    async def cold_retrieve(
        self,
        query: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """On-demand cold memory retrieval.

        Args:
            query: Natural language search query.
            limit: Maximum results to return.

        Returns:
            List of result dicts, or empty list if no retriever.
        """
        if self._cold_retriever is None:
            return []
        results = await self._cold_retriever.retrieve(
            user_id=self.user_id,
            query=query,
            limit=limit,
        )
        return [r.to_dict() for r in results]

    async def run(self, task: dict[str, Any]) -> AgentResult:
        """Run the agent with full lifecycle management.

        Handles status transitions, input validation, execution,
        error handling, and logging.

        Args:
            task: Task specification with parameters.

        Returns:
            AgentResult with execution outcome.
        """
        start_time = time.perf_counter()
        self._hot_context_cache = None  # Reset per execution
        self.status = AgentStatus.RUNNING

        logger.info(
            f"Agent {self.name} starting execution",
            extra={
                "agent": self.name,
                "user_id": self.user_id,
                "task_keys": list(task.keys()),
            },
        )

        try:
            # Validate input
            if not self.validate_input(task):
                self.status = AgentStatus.FAILED
                return AgentResult(
                    success=False,
                    data=None,
                    error="Input validation failed",
                )

            # Execute the task
            result = await self.execute(task)

            # Format output
            result.data = self.format_output(result.data)

            # Calculate execution time
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            result.execution_time_ms = elapsed_ms

            # Accumulate token usage
            self.total_tokens_used += result.tokens_used

            self.status = AgentStatus.COMPLETE if result.success else AgentStatus.FAILED

            logger.info(
                f"Agent {self.name} execution complete",
                extra={
                    "agent": self.name,
                    "user_id": self.user_id,
                    "success": result.success,
                    "execution_time_ms": elapsed_ms,
                    "tokens_used": result.tokens_used,
                },
            )

            return result

        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            self.status = AgentStatus.FAILED

            logger.error(
                f"Agent {self.name} execution failed: {e}",
                extra={
                    "agent": self.name,
                    "user_id": self.user_id,
                    "error": str(e),
                    "execution_time_ms": elapsed_ms,
                },
            )

            return AgentResult(
                success=False,
                data=None,
                error=str(e),
                execution_time_ms=elapsed_ms,
            )
