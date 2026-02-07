"""Search API routes for US-931.

This module provides endpoints for:
- Global search across all memory types
- Recent items tracking and retrieval
"""

from typing import Any

from fastapi import APIRouter, Query

from src.api.deps import CurrentUser
from src.services.search_service import SearchService

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/global")
async def global_search(
    current_user: CurrentUser,
    query: str = Query(..., description="Search query string"),
    types: list[str] | None = Query(None, description="Filter by types (e.g., leads,goals)"),
    limit: int = Query(10, ge=1, le=100, description="Maximum results to return"),
) -> list[dict[str, Any]]:
    """Perform global search across all memory types.

    Args:
        current_user: The authenticated user.
        query: The search query string.
        types: Optional list of types to filter by.
        limit: Maximum number of results to return.

    Returns:
        List of search results with type, id, title, snippet, score, and url.
    """
    search_service = SearchService()
    results = await search_service.global_search(
        user_id=current_user.id,
        query=query,
        types=types,
        limit=limit,
    )

    # Convert SearchResult objects to dicts
    return [result.to_dict() for result in results]


@router.get("/recent")
async def get_recent_items(
    current_user: CurrentUser,
    limit: int = Query(10, ge=1, le=50, description="Maximum items to return"),
) -> list[dict[str, Any]]:
    """Get user's recently accessed items.

    Args:
        current_user: The authenticated user.
        limit: Maximum number of items to return.

    Returns:
        List of recent items with type, id, title, url, and accessed_at.
    """
    search_service = SearchService()
    items = await search_service.recent_items(
        user_id=current_user.id,
        limit=limit,
    )

    # Convert RecentItem objects to dicts
    return [item.to_dict() for item in items]
