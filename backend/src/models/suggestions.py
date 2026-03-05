"""Pydantic models for suggestions API."""

from pydantic import BaseModel


class SuggestionChip(BaseModel):
    """A single suggestion chip with display text and action."""

    text: str  # Short display text for the chip
    action: str  # Full message to send when clicked


class SuggestionsResponse(BaseModel):
    """Response containing context-aware suggestion chips."""

    suggestions: list[SuggestionChip]
