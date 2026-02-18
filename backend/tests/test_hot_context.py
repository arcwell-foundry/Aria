"""Tests for hot context builder.

Validates the HotContextBuilder assembles user context under 3000 tokens,
caches results, handles DB failures gracefully, and truncates correctly.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from src.core.cache import clear_all_caches
from src.memory.hot_context import (
    BUDGET_TOTAL,
    HotContext,
    HotContextBuilder,
    HotContextSection,
)
from src.memory.working import WorkingMemory

# ── Helpers ──────────────────────────────────────────────────────


def _mock_execute(data: Any) -> MagicMock:
    """Build a mock .execute() result."""
    result = MagicMock()
    result.data = data
    return result


def _build_chain(execute_return: Any) -> MagicMock:
    """Build a fluent Supabase query chain ending in .execute()."""
    chain = MagicMock()
    chain.select.return_value = chain
    chain.insert.return_value = chain
    chain.update.return_value = chain
    chain.upsert.return_value = chain
    chain.eq.return_value = chain
    chain.gte.return_value = chain
    chain.lte.return_value = chain
    chain.in_.return_value = chain
    chain.order.return_value = chain
    chain.limit.return_value = chain
    chain.maybe_single.return_value = chain
    chain.single.return_value = chain
    chain.execute.return_value = _mock_execute(execute_return)
    return chain


def _make_working_memory(msg_count: int = 3) -> WorkingMemory:
    """Create a WorkingMemory with sample messages."""
    wm = WorkingMemory(conversation_id="conv-1", user_id="user-1")
    for i in range(msg_count):
        role = "user" if i % 2 == 0 else "assistant"
        wm.add_message(role, f"Message {i} content here")
    return wm


# ── HotContext dataclass tests ───────────────────────────────────


class TestHotContext:
    """Tests for HotContext dataclass."""

    def test_formatted_returns_markdown(self) -> None:
        """Formatted output contains section headers."""
        ctx = HotContext(
            user_id="u1",
            sections=[
                HotContextSection(label="User", content="Name: Alice", tokens=5),
                HotContextSection(label="Goal", content="Close deal", tokens=5),
            ],
            total_tokens=10,
        )
        result = ctx.formatted
        assert "## User" in result
        assert "Name: Alice" in result
        assert "## Goal" in result

    def test_formatted_empty_when_no_sections(self) -> None:
        """Formatted returns empty string with no sections."""
        ctx = HotContext(user_id="u1")
        assert ctx.formatted == ""

    def test_formatted_excludes_empty_content(self) -> None:
        """Sections with empty content are excluded from formatted output."""
        ctx = HotContext(
            user_id="u1",
            sections=[
                HotContextSection(label="User", content="", tokens=0),
                HotContextSection(label="Goal", content="Close deal", tokens=5),
            ],
            total_tokens=5,
        )
        result = ctx.formatted
        assert "## User" not in result
        assert "## Goal" in result

    def test_to_dict_serialization(self) -> None:
        """to_dict produces expected structure."""
        ctx = HotContext(
            user_id="u1",
            sections=[HotContextSection(label="User", content="Alice", tokens=3)],
            total_tokens=3,
            assembled_at_ms=1000,
        )
        d = ctx.to_dict()
        assert d["user_id"] == "u1"
        assert d["total_tokens"] == 3
        assert d["assembled_at_ms"] == 1000
        assert len(d["sections"]) == 1
        assert d["sections"][0]["label"] == "User"


# ── HotContextBuilder build tests ───────────────────────────────


class TestHotContextBuild:
    """Tests for HotContextBuilder.build()."""

    @pytest.fixture(autouse=True)
    def _clear_cache(self) -> None:
        """Clear global cache before each test to prevent cross-test pollution."""
        clear_all_caches()

    @pytest.fixture()
    def mock_db(self) -> MagicMock:
        """Create a mock Supabase client."""
        return MagicMock()

    @pytest.fixture()
    def builder(self, mock_db: MagicMock) -> HotContextBuilder:
        """Create a HotContextBuilder with mocked DB."""
        return HotContextBuilder(db_client=mock_db)

    def _setup_db_tables(
        self,
        mock_db: MagicMock,
        user_profile: Any = None,
        goals: Any = None,
        priorities: Any = None,
        schedule: Any = None,
        salience: Any = None,
        facts: Any = None,
    ) -> None:
        """Configure mock_db.table() to return appropriate chains."""
        table_map: dict[str, MagicMock] = {
            "user_profiles": _build_chain(user_profile),
            "goals": _build_chain(goals or []),
            "prospective_memories": _build_chain(priorities or []),
            "semantic_fact_salience": _build_chain(salience or []),
            "memory_semantic": _build_chain(facts or []),
        }

        # Track call count to prospective_memories to distinguish
        # priorities vs schedule calls
        pm_call_count = 0
        schedule_chain = _build_chain(schedule or [])

        original_table_map = dict(table_map)

        def table_side_effect(name: str) -> MagicMock:
            nonlocal pm_call_count
            if name == "prospective_memories":
                pm_call_count += 1
                if pm_call_count == 1:
                    return original_table_map["prospective_memories"]
                return schedule_chain
            return table_map.get(name, _build_chain([]))

        mock_db.table.side_effect = table_side_effect

    @pytest.mark.asyncio()
    async def test_build_returns_hot_context(
        self, builder: HotContextBuilder, mock_db: MagicMock
    ) -> None:
        """build() returns a HotContext instance."""
        self._setup_db_tables(mock_db)
        result = await builder.build("user-1")
        assert isinstance(result, HotContext)
        assert result.user_id == "user-1"

    @pytest.mark.asyncio()
    async def test_build_fetches_user_identity(
        self, builder: HotContextBuilder, mock_db: MagicMock
    ) -> None:
        """build() includes user identity when profile exists."""
        self._setup_db_tables(
            mock_db,
            user_profile={"full_name": "Alice Smith", "role": "VP Sales", "company_name": "Acme"},
        )
        result = await builder.build("user-1")
        user_sections = [s for s in result.sections if s.label == "User"]
        assert len(user_sections) == 1
        assert "Alice Smith" in user_sections[0].content

    @pytest.mark.asyncio()
    async def test_build_fetches_active_goal(
        self, builder: HotContextBuilder, mock_db: MagicMock
    ) -> None:
        """build() includes active goal from goals table."""
        self._setup_db_tables(
            mock_db,
            goals=[{"id": "g1", "objective": "Close Q4 deals", "status": "active", "context": {}}],
        )
        result = await builder.build("user-1")
        goal_sections = [s for s in result.sections if s.label == "Active Goal"]
        assert len(goal_sections) == 1
        assert "Close Q4 deals" in goal_sections[0].content

    @pytest.mark.asyncio()
    async def test_build_extracts_recent_conversation(
        self, builder: HotContextBuilder, mock_db: MagicMock
    ) -> None:
        """build() includes recent conversation from working memory."""
        self._setup_db_tables(mock_db)
        wm = _make_working_memory(msg_count=6)
        result = await builder.build("user-1", working_memory=wm)
        conv_sections = [s for s in result.sections if s.label == "Recent Conversation"]
        assert len(conv_sections) == 1
        # Should only include last 5 messages
        assert "Message 0" not in conv_sections[0].content
        assert "Message 5" in conv_sections[0].content

    @pytest.mark.asyncio()
    async def test_build_fetches_priorities(
        self, builder: HotContextBuilder, mock_db: MagicMock
    ) -> None:
        """build() includes high/urgent priorities."""
        self._setup_db_tables(
            mock_db,
            priorities=[
                {"description": "Follow up with BioGenix", "priority": "high"},
                {"description": "Prepare Q4 forecast", "priority": "urgent"},
            ],
        )
        result = await builder.build("user-1")
        priority_sections = [s for s in result.sections if s.label == "Top Priorities"]
        assert len(priority_sections) == 1
        assert "BioGenix" in priority_sections[0].content

    @pytest.mark.asyncio()
    async def test_build_fetches_schedule(
        self, builder: HotContextBuilder, mock_db: MagicMock
    ) -> None:
        """build() includes time-triggered schedule items."""
        self._setup_db_tables(
            mock_db,
            schedule=[
                {"description": "Team standup", "trigger_value": "09:00"},
                {"description": "Client call", "trigger_value": "14:00"},
            ],
        )
        result = await builder.build("user-1")
        schedule_sections = [s for s in result.sections if s.label == "Today's Schedule"]
        assert len(schedule_sections) == 1
        assert "Team standup" in schedule_sections[0].content

    @pytest.mark.asyncio()
    async def test_build_fetches_salient_facts(
        self, builder: HotContextBuilder, mock_db: MagicMock
    ) -> None:
        """build() includes high-salience facts."""
        self._setup_db_tables(
            mock_db,
            salience=[{"graphiti_episode_id": "f1", "current_salience": 0.8}],
            facts=[{"id": "f1", "fact": "Acme uses Salesforce CRM", "confidence": 0.9}],
        )
        result = await builder.build("user-1")
        fact_sections = [s for s in result.sections if s.label == "Key Facts"]
        assert len(fact_sections) == 1
        assert "Salesforce" in fact_sections[0].content

    @pytest.mark.asyncio()
    async def test_build_under_3000_tokens(
        self, builder: HotContextBuilder, mock_db: MagicMock
    ) -> None:
        """Total tokens never exceed BUDGET_TOTAL."""
        self._setup_db_tables(
            mock_db,
            user_profile={"full_name": "Alice", "role": "VP", "company_name": "Acme"},
            goals=[{"id": "g1", "objective": "X" * 500, "status": "active", "context": {}}],
            priorities=[{"description": "P" * 400, "priority": "high"}],
        )
        wm = _make_working_memory(msg_count=10)
        result = await builder.build("user-1", working_memory=wm)
        assert result.total_tokens <= BUDGET_TOTAL

    @pytest.mark.asyncio()
    async def test_build_uses_cache(
        self, builder: HotContextBuilder, mock_db: MagicMock
    ) -> None:
        """Second call uses cached result, not DB."""
        self._setup_db_tables(
            mock_db,
            user_profile={"full_name": "Alice", "role": "VP", "company_name": "Acme"},
        )
        first = await builder.build("user-1")
        # Reset call count
        mock_db.table.reset_mock()

        second = await builder.build("user-1")
        assert second.user_id == first.user_id
        # DB should not have been called on second build
        mock_db.table.assert_not_called()

    @pytest.mark.asyncio()
    async def test_build_after_invalidate(
        self, mock_db: MagicMock
    ) -> None:
        """Cache miss after invalidate() forces fresh fetch."""
        builder = HotContextBuilder(db_client=mock_db)
        self._setup_db_tables(
            mock_db,
            user_profile={"full_name": "Alice", "role": "VP", "company_name": "Acme"},
        )
        first = await builder.build("user-1")
        user_sections = [s for s in first.sections if s.label == "User"]
        assert len(user_sections) == 1
        assert "Alice" in user_sections[0].content

        builder.invalidate("user-1")

        # Re-setup DB to return different data
        self._setup_db_tables(
            mock_db,
            user_profile={"full_name": "Bob", "role": "Dir", "company_name": "Beta"},
        )
        result = await builder.build("user-1")
        user_sections = [s for s in result.sections if s.label == "User"]
        assert len(user_sections) == 1
        assert "Bob" in user_sections[0].content

    @pytest.mark.asyncio()
    async def test_build_graceful_on_db_failure(
        self, builder: HotContextBuilder, mock_db: MagicMock
    ) -> None:
        """build() returns partial context when some DB calls fail."""
        # Make all table calls raise
        mock_db.table.side_effect = Exception("DB down")
        result = await builder.build("user-1")
        # Should still return a valid HotContext, just empty
        assert isinstance(result, HotContext)
        assert result.total_tokens == 0

    @pytest.mark.asyncio()
    async def test_build_with_no_working_memory(
        self, builder: HotContextBuilder, mock_db: MagicMock
    ) -> None:
        """build() works without working memory (None)."""
        self._setup_db_tables(mock_db)
        result = await builder.build("user-1", working_memory=None)
        assert isinstance(result, HotContext)
        conv_sections = [s for s in result.sections if s.label == "Recent Conversation"]
        assert len(conv_sections) == 0

    @pytest.mark.asyncio()
    async def test_build_with_preloaded_goal(
        self, builder: HotContextBuilder, mock_db: MagicMock
    ) -> None:
        """build() uses preloaded active_goal instead of querying DB."""
        self._setup_db_tables(mock_db)
        goal = {"id": "g1", "objective": "Win Pfizer deal", "status": "active"}
        result = await builder.build("user-1", active_goal=goal)
        goal_sections = [s for s in result.sections if s.label == "Active Goal"]
        assert len(goal_sections) == 1
        assert "Pfizer" in goal_sections[0].content


# ── Truncation tests ─────────────────────────────────────────────


class TestHotContextTruncation:
    """Tests for token budget enforcement."""

    def test_truncate_short_text_unchanged(self) -> None:
        """Text under budget is returned unchanged."""
        builder = HotContextBuilder(db_client=MagicMock())
        text, tokens = builder._truncate("Hello world", 100)
        assert text == "Hello world"
        assert tokens > 0

    def test_truncate_long_text_fits_budget(self) -> None:
        """Text over budget is truncated to fit."""
        builder = HotContextBuilder(db_client=MagicMock())
        long_text = "word " * 500  # ~500 tokens
        text, tokens = builder._truncate(long_text, 50)
        assert tokens <= 60  # Allow some margin from approximation
        assert text.endswith("...")


# ── Invalidation tests ───────────────────────────────────────────


class TestHotContextInvalidation:
    """Tests for cache invalidation."""

    @pytest.fixture(autouse=True)
    def _clear_cache(self) -> None:
        """Clear global cache before each test."""
        clear_all_caches()

    @pytest.mark.asyncio()
    async def test_invalidate_clears_user_cache(self) -> None:
        """invalidate() removes cached context for specific user."""
        mock_db = MagicMock()
        builder = HotContextBuilder(db_client=mock_db)

        # Setup DB for first build
        mock_db.table.side_effect = lambda name: _build_chain(
            {"full_name": "Alice", "role": "VP", "company_name": "X"}
            if name == "user_profiles"
            else []
        )
        first = await builder.build("user-1")
        assert any(s.label == "User" for s in first.sections)

        # Invalidate and re-setup
        builder.invalidate("user-1")
        mock_db.table.side_effect = lambda name: _build_chain(
            {"full_name": "Bob", "role": "Dir", "company_name": "Y"}
            if name == "user_profiles"
            else []
        )

        result = await builder.build("user-1")
        user_sections = [s for s in result.sections if s.label == "User"]
        assert len(user_sections) == 1
        assert "Bob" in user_sections[0].content
