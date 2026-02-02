"""Base agent module for ARIA.

Provides the abstract base class and common types for all specialized agents.
"""

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

    @abstractmethod
    async def execute(self, task: dict[str, Any]) -> AgentResult:
        """Execute the agent's primary task.

        Args:
            task: Task specification with parameters.

        Returns:
            AgentResult with success status and output data.
        """
        pass
