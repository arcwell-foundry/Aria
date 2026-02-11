"""In-process pub/sub event bus for goal execution events.

Enables SSE endpoints to stream real-time events from background
agent execution. Each subscriber gets an asyncio.Queue that receives
events for a specific goal_id.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


@dataclass
class GoalEvent:
    """Event emitted during goal execution."""

    goal_id: str
    user_id: str
    event_type: str  # progress.update, agent.started, agent.completed, action.pending, action.completed, goal.complete, goal.error, signal.detected
    data: dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "user_id": self.user_id,
            "event_type": self.event_type,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
        }


class EventBus:
    """In-process pub/sub for goal execution events."""

    _instance: ClassVar["EventBus | None"] = None

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[GoalEvent]]] = {}

    @classmethod
    def get_instance(cls) -> "EventBus":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    def subscribe(self, goal_id: str) -> asyncio.Queue[GoalEvent]:
        queue: asyncio.Queue[GoalEvent] = asyncio.Queue()
        if goal_id not in self._subscribers:
            self._subscribers[goal_id] = []
        self._subscribers[goal_id].append(queue)
        return queue

    def unsubscribe(self, goal_id: str, queue: asyncio.Queue[GoalEvent]) -> None:
        if goal_id in self._subscribers:
            try:
                self._subscribers[goal_id].remove(queue)
            except ValueError:
                pass
            if not self._subscribers[goal_id]:
                del self._subscribers[goal_id]

    async def publish(self, event: GoalEvent) -> None:
        subscribers = self._subscribers.get(event.goal_id, [])
        for queue in subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("Event queue full for goal %s", event.goal_id)
