"""Memory API routes for unified memory querying."""

import logging
from datetime import datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["memory"])


# Response Models
class MemoryQueryResult(BaseModel):
    """A single result from unified memory query.

    Represents a memory item retrieved from any of the four memory types:
    - episodic: Past events, interactions, meetings
    - semantic: Facts with confidence scores
    - procedural: Learned workflows and patterns
    - prospective: Future tasks, reminders, follow-ups
    """

    id: str
    memory_type: Literal["episodic", "semantic", "procedural", "prospective"]
    content: str
    relevance_score: float = Field(..., ge=0.0, le=1.0)
    confidence: float | None = Field(None, ge=0.0, le=1.0)
    timestamp: datetime


class MemoryQueryResponse(BaseModel):
    """Paginated response for memory queries.

    Provides a unified response format for querying across all memory types
    with standard pagination fields.
    """

    items: list[MemoryQueryResult]
    total: int
    page: int
    page_size: int
    has_more: bool
