"""Base agent module for ARIA.

Provides the abstract base class and common types for all specialized agents.
"""

import inspect
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.core.llm import LLMClient

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

    def __init__(self, llm_client: "LLMClient", user_id: str) -> None:
        """Initialize the agent.

        Args:
            llm_client: LLM client for reasoning and generation.
            user_id: ID of the user this agent is working for.
        """
        self.llm = llm_client
        self.user_id = user_id
        self.status = AgentStatus.IDLE
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

    @abstractmethod
    async def execute(self, task: dict[str, Any]) -> AgentResult:
        """Execute the agent's primary task.

        Args:
            task: Task specification with parameters.

        Returns:
            AgentResult with success status and output data.
        """
        pass
