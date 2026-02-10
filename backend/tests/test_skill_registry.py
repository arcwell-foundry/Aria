"""Tests for unified skill registry."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.security.trust_levels import SkillTrustLevel
from src.skills.registry import (
    PerformanceMetrics,
    RankedSkill,
    SkillEntry,
    SkillRegistry,
    SkillType,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(
    *,
    entry_id: str = "native:test",
    name: str = "test_skill",
    description: str = "A test skill",
    skill_type: str = SkillType.NATIVE,
    agent_types: list[str] | None = None,
    trust_level: SkillTrustLevel = SkillTrustLevel.CORE,
    data_classes: list[str] | None = None,
) -> SkillEntry:
    return SkillEntry(
        id=entry_id,
        name=name,
        description=description,
        skill_type=skill_type,
        agent_types=agent_types or [],
        trust_level=trust_level,
        data_classes=data_classes or [],
    )


class _StubCapability:
    """Minimal stand-in for a BaseCapability subclass."""

    capability_name = "company_research"
    agent_types = ["hunter", "analyst"]
    oauth_scopes = ["crm:read"]
    __doc__ = "Research companies via CRM data."

    def __init__(self) -> None:
        pass

    async def can_handle(self, task: dict) -> float:
        if task.get("type") == "company_research":
            return 0.95
        return 0.0

    def get_data_classes_accessed(self) -> list[str]:
        return ["internal", "confidential"]


# ---------------------------------------------------------------------------
# SkillEntry model tests
# ---------------------------------------------------------------------------


class TestSkillEntry:
    """Tests for the SkillEntry dataclass."""

    def test_create_skill_entry(self) -> None:
        entry = _make_entry()
        assert entry.id == "native:test"
        assert entry.name == "test_skill"
        assert entry.skill_type == SkillType.NATIVE

    def test_priority_ordering(self) -> None:
        native = _make_entry(skill_type=SkillType.NATIVE)
        defn = _make_entry(skill_type=SkillType.DEFINITION)
        custom = _make_entry(skill_type=SkillType.CUSTOM)
        external = _make_entry(skill_type=SkillType.EXTERNAL)

        assert native.priority < defn.priority
        assert defn.priority < custom.priority
        assert custom.priority < external.priority

    def test_performance_metrics_default(self) -> None:
        entry = _make_entry()
        assert entry.performance_metrics.success_rate == 0.0
        assert entry.performance_metrics.total_executions == 0

    def test_performance_metrics_custom(self) -> None:
        metrics = PerformanceMetrics(success_rate=0.95, total_executions=100)
        entry = SkillEntry(
            id="x",
            name="x",
            description="x",
            skill_type=SkillType.CUSTOM,
            agent_types=[],
            trust_level=SkillTrustLevel.USER,
            data_classes=[],
            performance_metrics=metrics,
        )
        assert entry.performance_metrics.success_rate == 0.95
        assert entry.performance_metrics.total_executions == 100


class TestRankedSkill:
    """Tests for the RankedSkill dataclass."""

    def test_ranked_skill_creation(self) -> None:
        entry = _make_entry()
        ranked = RankedSkill(entry=entry, relevance=0.85)
        assert ranked.relevance == 0.85
        assert ranked.entry is entry


class TestSkillType:
    """Tests for SkillType constants."""

    def test_skill_type_values(self) -> None:
        assert SkillType.NATIVE == "native"
        assert SkillType.DEFINITION == "definition"
        assert SkillType.CUSTOM == "custom"
        assert SkillType.EXTERNAL == "external"


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


class TestRegisterCapability:
    """Tests for SkillRegistry.register_capability."""

    @patch("src.skills.registry.SupabaseClient")
    @patch("src.skills.index.SupabaseClient")
    def test_register_capability_creates_entry(
        self, mock_idx_sb: MagicMock, mock_reg_sb: MagicMock
    ) -> None:
        mock_idx_sb.get_client.return_value = MagicMock()
        mock_reg_sb.get_client.return_value = MagicMock()

        registry = SkillRegistry()
        cap = _StubCapability()

        # Patch BaseCapability check since _StubCapability isn't a real subclass
        with patch("src.skills.registry.BaseCapability", new=type(cap)):
            registry.register_capability(cap)  # type: ignore[arg-type]

        assert "native:company_research" in registry._entries
        entry = registry._entries["native:company_research"]
        assert entry.skill_type == SkillType.NATIVE
        assert entry.trust_level == SkillTrustLevel.CORE
        assert "hunter" in entry.agent_types
        assert "analyst" in entry.agent_types
        assert "internal" in entry.data_classes

    @patch("src.skills.registry.SupabaseClient")
    @patch("src.skills.index.SupabaseClient")
    def test_register_capability_stores_instance(
        self, mock_idx_sb: MagicMock, mock_reg_sb: MagicMock
    ) -> None:
        mock_idx_sb.get_client.return_value = MagicMock()
        mock_reg_sb.get_client.return_value = MagicMock()

        registry = SkillRegistry()
        cap = _StubCapability()

        with patch("src.skills.registry.BaseCapability", new=type(cap)):
            registry.register_capability(cap)  # type: ignore[arg-type]

        assert registry._capability_instances["native:company_research"] is cap


class TestRegisterDefinition:
    """Tests for SkillRegistry.register_definition."""

    @patch("src.skills.registry.SupabaseClient")
    @patch("src.skills.index.SupabaseClient")
    def test_register_definition_creates_entry(
        self, mock_idx_sb: MagicMock, mock_reg_sb: MagicMock
    ) -> None:
        mock_idx_sb.get_client.return_value = MagicMock()
        mock_reg_sb.get_client.return_value = MagicMock()

        registry = SkillRegistry()

        # Create a mock definition
        mock_defn = MagicMock()
        mock_defn.definition.name = "meeting_summarizer"
        mock_defn.definition.description = "Summarize meetings"
        mock_defn.definition.agent_assignment = ["scribe", "analyst"]
        mock_defn.trust_level = SkillTrustLevel.CORE

        registry.register_definition(mock_defn)

        assert "definition:meeting_summarizer" in registry._entries
        entry = registry._entries["definition:meeting_summarizer"]
        assert entry.skill_type == SkillType.DEFINITION
        assert entry.trust_level == SkillTrustLevel.CORE
        assert "scribe" in entry.agent_types


# ---------------------------------------------------------------------------
# Search tests
# ---------------------------------------------------------------------------


class TestSearch:
    """Tests for SkillRegistry.search."""

    @patch("src.skills.registry.SupabaseClient")
    @patch("src.skills.index.SupabaseClient")
    @pytest.mark.asyncio
    async def test_search_matches_by_name(
        self, mock_idx_sb: MagicMock, mock_reg_sb: MagicMock
    ) -> None:
        mock_idx_sb.get_client.return_value = MagicMock()
        mock_client = MagicMock()
        mock_reg_sb.get_client.return_value = mock_client

        # Mock user_profiles query for custom skill search
        mock_query = MagicMock()
        mock_query.select.return_value = mock_query
        mock_query.eq.return_value = mock_query
        mock_query.single.return_value = mock_query
        mock_query.execute.return_value = MagicMock(data=None)
        mock_client.table.return_value = mock_query

        registry = SkillRegistry()
        registry._entries["native:pdf_parser"] = _make_entry(
            entry_id="native:pdf_parser",
            name="pdf_parser",
            description="Parse PDF documents",
        )
        registry._entries["native:email_gen"] = _make_entry(
            entry_id="native:email_gen",
            name="email_generator",
            description="Generate email sequences",
        )

        results = await registry.search("pdf", user_id="user-1")
        names = [r.name for r in results]
        assert "pdf_parser" in names
        assert "email_generator" not in names

    @patch("src.skills.registry.SupabaseClient")
    @patch("src.skills.index.SupabaseClient")
    @pytest.mark.asyncio
    async def test_search_matches_by_description(
        self, mock_idx_sb: MagicMock, mock_reg_sb: MagicMock
    ) -> None:
        mock_idx_sb.get_client.return_value = MagicMock()
        mock_client = MagicMock()
        mock_reg_sb.get_client.return_value = mock_client

        mock_query = MagicMock()
        mock_query.select.return_value = mock_query
        mock_query.eq.return_value = mock_query
        mock_query.single.return_value = mock_query
        mock_query.execute.return_value = MagicMock(data=None)
        mock_client.table.return_value = mock_query

        registry = SkillRegistry()
        registry._entries["def:meeting"] = _make_entry(
            entry_id="def:meeting",
            name="summarizer",
            description="Summarize meeting transcripts into action items",
            skill_type=SkillType.DEFINITION,
        )

        results = await registry.search("meeting", user_id="user-1")
        assert len(results) == 1
        assert results[0].name == "summarizer"

    @patch("src.skills.registry.SupabaseClient")
    @patch("src.skills.index.SupabaseClient")
    @pytest.mark.asyncio
    async def test_search_results_sorted_by_priority(
        self, mock_idx_sb: MagicMock, mock_reg_sb: MagicMock
    ) -> None:
        mock_idx_sb.get_client.return_value = MagicMock()
        mock_client = MagicMock()
        mock_reg_sb.get_client.return_value = mock_client

        mock_query = MagicMock()
        mock_query.select.return_value = mock_query
        mock_query.eq.return_value = mock_query
        mock_query.single.return_value = mock_query
        mock_query.execute.return_value = MagicMock(data=None)
        mock_client.table.return_value = mock_query

        registry = SkillRegistry()
        # Add external first, native second — results should reorder
        registry._entries["ext:pdf"] = _make_entry(
            entry_id="ext:pdf",
            name="pdf_external",
            description="External pdf parser",
            skill_type=SkillType.EXTERNAL,
        )
        registry._entries["nat:pdf"] = _make_entry(
            entry_id="nat:pdf",
            name="pdf_native",
            description="Native pdf parser",
            skill_type=SkillType.NATIVE,
        )

        results = await registry.search("pdf", user_id="user-1")
        assert len(results) == 2
        assert results[0].skill_type == SkillType.NATIVE
        assert results[1].skill_type == SkillType.EXTERNAL


# ---------------------------------------------------------------------------
# get_for_task tests
# ---------------------------------------------------------------------------


class TestGetForTask:
    """Tests for SkillRegistry.get_for_task."""

    @patch("src.skills.registry.SupabaseClient")
    @patch("src.skills.index.SupabaseClient")
    @pytest.mark.asyncio
    async def test_native_capability_uses_can_handle(
        self, mock_idx_sb: MagicMock, mock_reg_sb: MagicMock
    ) -> None:
        mock_idx_sb.get_client.return_value = MagicMock()
        mock_reg_sb.get_client.return_value = MagicMock()

        registry = SkillRegistry()
        cap = _StubCapability()
        entry_id = "native:company_research"

        registry._entries[entry_id] = _make_entry(
            entry_id=entry_id,
            name="company_research",
            description="Research companies via CRM data",
            skill_type=SkillType.NATIVE,
            agent_types=["hunter", "analyst"],
        )
        registry._capability_instances[entry_id] = cap  # type: ignore[assignment]

        task = {"type": "company_research", "company": "Acme Corp"}
        ranked = await registry.get_for_task(task)

        assert len(ranked) == 1
        assert ranked[0].relevance == 0.95
        assert ranked[0].entry.name == "company_research"

    @patch("src.skills.registry.SupabaseClient")
    @patch("src.skills.index.SupabaseClient")
    @pytest.mark.asyncio
    async def test_non_matching_native_excluded(
        self, mock_idx_sb: MagicMock, mock_reg_sb: MagicMock
    ) -> None:
        mock_idx_sb.get_client.return_value = MagicMock()
        mock_reg_sb.get_client.return_value = MagicMock()

        registry = SkillRegistry()
        cap = _StubCapability()
        entry_id = "native:company_research"

        registry._entries[entry_id] = _make_entry(
            entry_id=entry_id,
            name="company_research",
            skill_type=SkillType.NATIVE,
        )
        registry._capability_instances[entry_id] = cap  # type: ignore[assignment]

        task = {"type": "email_generation", "recipient": "john@example.com"}
        ranked = await registry.get_for_task(task)

        assert len(ranked) == 0

    @patch("src.skills.registry.SupabaseClient")
    @patch("src.skills.index.SupabaseClient")
    @pytest.mark.asyncio
    async def test_keyword_heuristic_for_definitions(
        self, mock_idx_sb: MagicMock, mock_reg_sb: MagicMock
    ) -> None:
        mock_idx_sb.get_client.return_value = MagicMock()
        mock_reg_sb.get_client.return_value = MagicMock()

        registry = SkillRegistry()
        registry._entries["def:meeting_summarizer"] = _make_entry(
            entry_id="def:meeting_summarizer",
            name="meeting_summarizer",
            description="Summarize meeting transcripts",
            skill_type=SkillType.DEFINITION,
        )

        task = {"type": "summarize", "description": "Summarize the meeting transcript"}
        ranked = await registry.get_for_task(task)

        assert len(ranked) >= 1
        assert ranked[0].entry.name == "meeting_summarizer"
        assert ranked[0].relevance > 0.0

    @patch("src.skills.registry.SupabaseClient")
    @patch("src.skills.index.SupabaseClient")
    @pytest.mark.asyncio
    async def test_results_sorted_by_relevance_then_priority(
        self, mock_idx_sb: MagicMock, mock_reg_sb: MagicMock
    ) -> None:
        mock_idx_sb.get_client.return_value = MagicMock()
        mock_reg_sb.get_client.return_value = MagicMock()

        registry = SkillRegistry()

        # Native cap with high confidence
        cap = _StubCapability()
        registry._entries["native:company_research"] = _make_entry(
            entry_id="native:company_research",
            name="company_research",
            skill_type=SkillType.NATIVE,
        )
        registry._capability_instances["native:company_research"] = cap  # type: ignore[assignment]

        # External with partial keyword match
        registry._entries["ext:research"] = _make_entry(
            entry_id="ext:research",
            name="web_scraper",
            description="Scrape company websites for research data",
            skill_type=SkillType.EXTERNAL,
        )

        task = {"type": "company_research", "description": "Research a company"}
        ranked = await registry.get_for_task(task)

        # Native should come first (0.95 relevance vs keyword heuristic)
        assert ranked[0].entry.skill_type == SkillType.NATIVE
        assert ranked[0].relevance == 0.95

    @patch("src.skills.registry.SupabaseClient")
    @patch("src.skills.index.SupabaseClient")
    @pytest.mark.asyncio
    async def test_can_handle_failure_returns_zero(
        self, mock_idx_sb: MagicMock, mock_reg_sb: MagicMock
    ) -> None:
        mock_idx_sb.get_client.return_value = MagicMock()
        mock_reg_sb.get_client.return_value = MagicMock()

        registry = SkillRegistry()

        # Capability that throws on can_handle
        class BrokenCap:
            capability_name = "broken"
            agent_types: list[str] = []

            async def can_handle(self, task: dict) -> float:  # noqa: ARG002
                raise RuntimeError("boom")

            def get_data_classes_accessed(self) -> list[str]:
                return []

        entry_id = "native:broken"
        registry._entries[entry_id] = _make_entry(
            entry_id=entry_id, name="broken", skill_type=SkillType.NATIVE
        )
        registry._capability_instances[entry_id] = BrokenCap()  # type: ignore[assignment]

        ranked = await registry.get_for_task({"type": "anything"})
        assert len(ranked) == 0


# ---------------------------------------------------------------------------
# get_for_agent tests
# ---------------------------------------------------------------------------


class TestGetForAgent:
    """Tests for SkillRegistry.get_for_agent."""

    @patch("src.skills.registry.SupabaseClient")
    @patch("src.skills.index.SupabaseClient")
    @pytest.mark.asyncio
    async def test_filters_by_agent_type(
        self, mock_idx_sb: MagicMock, mock_reg_sb: MagicMock
    ) -> None:
        mock_idx_sb.get_client.return_value = MagicMock()
        mock_reg_sb.get_client.return_value = MagicMock()

        registry = SkillRegistry()
        registry._entries["a"] = _make_entry(
            entry_id="a",
            name="hunter_skill",
            agent_types=["hunter"],
        )
        registry._entries["b"] = _make_entry(
            entry_id="b",
            name="analyst_skill",
            agent_types=["analyst"],
        )
        registry._entries["c"] = _make_entry(
            entry_id="c",
            name="shared_skill",
            agent_types=["hunter", "analyst"],
        )

        results = await registry.get_for_agent("hunter")
        names = [e.name for e in results]
        assert "hunter_skill" in names
        assert "shared_skill" in names
        assert "analyst_skill" not in names

    @patch("src.skills.registry.SupabaseClient")
    @patch("src.skills.index.SupabaseClient")
    @pytest.mark.asyncio
    async def test_unknown_agent_returns_empty(
        self, mock_idx_sb: MagicMock, mock_reg_sb: MagicMock
    ) -> None:
        mock_idx_sb.get_client.return_value = MagicMock()
        mock_reg_sb.get_client.return_value = MagicMock()

        registry = SkillRegistry()
        registry._entries["a"] = _make_entry(agent_types=["hunter"])

        results = await registry.get_for_agent("nonexistent_agent")
        assert results == []

    @patch("src.skills.registry.SupabaseClient")
    @patch("src.skills.index.SupabaseClient")
    @pytest.mark.asyncio
    async def test_results_sorted_by_priority(
        self, mock_idx_sb: MagicMock, mock_reg_sb: MagicMock
    ) -> None:
        mock_idx_sb.get_client.return_value = MagicMock()
        mock_reg_sb.get_client.return_value = MagicMock()

        registry = SkillRegistry()
        registry._entries["ext"] = _make_entry(
            entry_id="ext",
            name="ext_skill",
            skill_type=SkillType.EXTERNAL,
            agent_types=["hunter"],
        )
        registry._entries["nat"] = _make_entry(
            entry_id="nat",
            name="nat_skill",
            skill_type=SkillType.NATIVE,
            agent_types=["hunter"],
        )

        results = await registry.get_for_agent("hunter")
        assert results[0].skill_type == SkillType.NATIVE
        assert results[1].skill_type == SkillType.EXTERNAL


# ---------------------------------------------------------------------------
# get_all_available tests
# ---------------------------------------------------------------------------


class TestGetAllAvailable:
    """Tests for SkillRegistry.get_all_available."""

    @patch("src.skills.registry.SupabaseClient")
    @patch("src.skills.index.SupabaseClient")
    @pytest.mark.asyncio
    async def test_returns_all_entries(
        self, mock_idx_sb: MagicMock, mock_reg_sb: MagicMock
    ) -> None:
        mock_idx_sb.get_client.return_value = MagicMock()
        mock_client = MagicMock()
        mock_reg_sb.get_client.return_value = mock_client

        # Mock user_profiles lookup
        mock_query = MagicMock()
        mock_query.select.return_value = mock_query
        mock_query.eq.return_value = mock_query
        mock_query.single.return_value = mock_query
        mock_query.execute.return_value = MagicMock(data=None)
        mock_client.table.return_value = mock_query

        registry = SkillRegistry()
        registry._entries["a"] = _make_entry(entry_id="a", skill_type=SkillType.NATIVE)
        registry._entries["b"] = _make_entry(entry_id="b", skill_type=SkillType.EXTERNAL)

        results = await registry.get_all_available("user-1")
        assert len(results) == 2

    @patch("src.skills.registry.SupabaseClient")
    @patch("src.skills.index.SupabaseClient")
    @pytest.mark.asyncio
    async def test_sorted_by_priority(self, mock_idx_sb: MagicMock, mock_reg_sb: MagicMock) -> None:
        mock_idx_sb.get_client.return_value = MagicMock()
        mock_client = MagicMock()
        mock_reg_sb.get_client.return_value = mock_client

        mock_query = MagicMock()
        mock_query.select.return_value = mock_query
        mock_query.eq.return_value = mock_query
        mock_query.single.return_value = mock_query
        mock_query.execute.return_value = MagicMock(data=None)
        mock_client.table.return_value = mock_query

        registry = SkillRegistry()
        registry._entries["ext"] = _make_entry(entry_id="ext", skill_type=SkillType.EXTERNAL)
        registry._entries["nat"] = _make_entry(entry_id="nat", skill_type=SkillType.NATIVE)
        registry._entries["def"] = _make_entry(entry_id="def", skill_type=SkillType.DEFINITION)

        results = await registry.get_all_available("user-1")
        types = [r.skill_type for r in results]
        assert types == [SkillType.NATIVE, SkillType.DEFINITION, SkillType.EXTERNAL]


# ---------------------------------------------------------------------------
# refresh_external tests
# ---------------------------------------------------------------------------


class TestRefreshExternal:
    """Tests for SkillRegistry.refresh_external."""

    @patch("src.skills.registry.SupabaseClient")
    @patch("src.skills.index.SupabaseClient")
    @pytest.mark.asyncio
    async def test_refresh_replaces_external_entries(
        self, mock_idx_sb: MagicMock, mock_reg_sb: MagicMock
    ) -> None:
        mock_idx_sb.get_client.return_value = MagicMock()
        mock_client = MagicMock()
        mock_reg_sb.get_client.return_value = mock_client

        # Mock empty DB response for _load_external_skills
        mock_query = MagicMock()
        mock_query.select.return_value = mock_query
        mock_query.execute.return_value = MagicMock(data=[])
        mock_client.table.return_value = mock_query

        registry = SkillRegistry()
        # Seed an old external entry
        registry._entries["external:old"] = _make_entry(
            entry_id="external:old",
            skill_type=SkillType.EXTERNAL,
        )
        # Also a native entry that should survive
        registry._entries["native:keep"] = _make_entry(
            entry_id="native:keep",
            skill_type=SkillType.NATIVE,
        )

        with patch.object(
            registry._skill_index, "sync_from_skills_sh", new_callable=AsyncMock, return_value=0
        ):
            await registry.refresh_external()

        # Old external should be removed
        assert "external:old" not in registry._entries
        # Native should remain
        assert "native:keep" in registry._entries


# ---------------------------------------------------------------------------
# Auto-discovery tests
# ---------------------------------------------------------------------------


class TestDiscoverCapabilities:
    """Tests for SkillRegistry._discover_capabilities."""

    @patch("src.skills.registry.SupabaseClient")
    @patch("src.skills.index.SupabaseClient")
    def test_discover_skips_base_class(
        self, mock_idx_sb: MagicMock, mock_reg_sb: MagicMock
    ) -> None:
        """BaseCapability itself should not be registered."""
        mock_idx_sb.get_client.return_value = MagicMock()
        mock_reg_sb.get_client.return_value = MagicMock()

        registry = SkillRegistry()
        registry._discover_capabilities()

        # base.py only contains BaseCapability which should be excluded
        for entry in registry._entries.values():
            assert entry.name != ""

    @patch("src.skills.registry.SupabaseClient")
    @patch("src.skills.index.SupabaseClient")
    def test_discover_handles_missing_directory(
        self, mock_idx_sb: MagicMock, mock_reg_sb: MagicMock
    ) -> None:
        mock_idx_sb.get_client.return_value = MagicMock()
        mock_reg_sb.get_client.return_value = MagicMock()

        registry = SkillRegistry()

        with patch("src.skills.registry._CAPABILITIES_DIR") as mock_dir:
            mock_dir.is_dir.return_value = False
            registry._discover_capabilities()

        # Should not crash, just skip


class TestDiscoverDefinitions:
    """Tests for SkillRegistry._discover_definitions."""

    @patch("src.skills.registry.SupabaseClient")
    @patch("src.skills.index.SupabaseClient")
    def test_discover_handles_missing_directory(
        self, mock_idx_sb: MagicMock, mock_reg_sb: MagicMock
    ) -> None:
        mock_idx_sb.get_client.return_value = MagicMock()
        mock_reg_sb.get_client.return_value = MagicMock()

        registry = SkillRegistry()

        with patch("src.skills.registry._DEFINITIONS_DIR") as mock_dir:
            mock_dir.is_dir.return_value = False
            registry._discover_definitions()

        # Should not crash, just skip


# ---------------------------------------------------------------------------
# Database loading tests
# ---------------------------------------------------------------------------


class TestLoadExternalSkills:
    """Tests for SkillRegistry._load_external_skills."""

    @patch("src.skills.registry.SupabaseClient")
    @patch("src.skills.index.SupabaseClient")
    @pytest.mark.asyncio
    async def test_loads_from_skills_index_table(
        self, mock_idx_sb: MagicMock, mock_reg_sb: MagicMock
    ) -> None:
        mock_idx_sb.get_client.return_value = MagicMock()
        mock_client = MagicMock()
        mock_reg_sb.get_client.return_value = mock_client

        db_rows = [
            {
                "id": "uuid-1",
                "skill_path": "anthropics/skills/pdf",
                "skill_name": "PDF Parser",
                "description": "Parse PDF documents",
                "full_content": None,
                "content_hash": None,
                "author": "anthropic",
                "version": "1.0",
                "tags": ["pdf"],
                "trust_level": "verified",
                "life_sciences_relevant": False,
                "declared_permissions": [],
                "summary_verbosity": "standard",
                "last_synced": None,
                "created_at": "2024-01-01T00:00:00+00:00",
                "updated_at": "2024-01-01T00:00:00+00:00",
            },
        ]

        mock_query = MagicMock()
        mock_query.select.return_value = mock_query
        mock_query.execute.return_value = MagicMock(data=db_rows)
        mock_client.table.return_value = mock_query

        registry = SkillRegistry()
        await registry._load_external_skills()

        assert "external:uuid-1" in registry._entries
        entry = registry._entries["external:uuid-1"]
        assert entry.name == "PDF Parser"
        assert entry.skill_type == SkillType.EXTERNAL
        assert entry.trust_level == SkillTrustLevel.VERIFIED

    @patch("src.skills.registry.SupabaseClient")
    @patch("src.skills.index.SupabaseClient")
    @pytest.mark.asyncio
    async def test_handles_db_error_gracefully(
        self, mock_idx_sb: MagicMock, mock_reg_sb: MagicMock
    ) -> None:
        mock_idx_sb.get_client.return_value = MagicMock()
        mock_client = MagicMock()
        mock_reg_sb.get_client.return_value = mock_client
        mock_client.table.side_effect = Exception("DB connection failed")

        registry = SkillRegistry()
        await registry._load_external_skills()

        # Should not crash, just have no external entries
        ext_count = sum(1 for e in registry._entries.values() if e.skill_type == SkillType.EXTERNAL)
        assert ext_count == 0


class TestLoadCustomSkills:
    """Tests for SkillRegistry._load_custom_skills."""

    @patch("src.skills.registry.SupabaseClient")
    @patch("src.skills.index.SupabaseClient")
    @pytest.mark.asyncio
    async def test_loads_from_custom_skills_table(
        self, mock_idx_sb: MagicMock, mock_reg_sb: MagicMock
    ) -> None:
        mock_idx_sb.get_client.return_value = MagicMock()
        mock_client = MagicMock()
        mock_reg_sb.get_client.return_value = mock_client

        db_rows = [
            {
                "id": "custom-1",
                "tenant_id": "tenant-abc",
                "created_by": "user-1",
                "skill_name": "My Custom Skill",
                "description": "Custom analysis",
                "skill_type": "llm_definition",
                "definition": {"agent_assignment": ["analyst"]},
                "trust_level": "user",
                "performance_metrics": {
                    "success_rate": 0.85,
                    "executions": 42,
                },
                "is_published": True,
                "version": "1.0",
                "created_at": "2024-01-01T00:00:00+00:00",
                "updated_at": "2024-01-01T00:00:00+00:00",
            },
        ]

        mock_query = MagicMock()
        mock_query.select.return_value = mock_query
        mock_query.execute.return_value = MagicMock(data=db_rows)
        mock_client.table.return_value = mock_query

        registry = SkillRegistry()
        await registry._load_custom_skills()

        assert "custom:custom-1" in registry._entries
        entry = registry._entries["custom:custom-1"]
        assert entry.name == "My Custom Skill"
        assert entry.skill_type == SkillType.CUSTOM
        assert entry.trust_level == SkillTrustLevel.USER
        assert "analyst" in entry.agent_types
        assert entry.performance_metrics.success_rate == 0.85
        assert entry.performance_metrics.total_executions == 42


# ---------------------------------------------------------------------------
# Keyword relevance scoring tests
# ---------------------------------------------------------------------------


class TestKeywordRelevance:
    """Tests for SkillRegistry._keyword_relevance."""

    def test_exact_type_match_boosts_score(self) -> None:
        entry = _make_entry(
            name="company_research",
            description="Research companies",
        )
        task = {"type": "company_research"}
        score = SkillRegistry._keyword_relevance(entry, task)
        assert score >= 0.4  # Boost from exact type match

    def test_description_keyword_match(self) -> None:
        entry = _make_entry(
            name="summarizer",
            description="Summarize meeting transcripts",
        )
        task = {"description": "I need to summarize this meeting"}
        score = SkillRegistry._keyword_relevance(entry, task)
        assert score > 0.0

    def test_no_match_returns_zero(self) -> None:
        entry = _make_entry(
            name="pdf_parser",
            description="Parse PDF files",
        )
        task = {"type": "email_generation", "description": "Generate an email"}
        score = SkillRegistry._keyword_relevance(entry, task)
        assert score == 0.0

    def test_empty_task_returns_zero(self) -> None:
        entry = _make_entry(name="anything", description="anything")
        score = SkillRegistry._keyword_relevance(entry, {})
        assert score == 0.0

    def test_multiple_field_matching(self) -> None:
        entry = _make_entry(
            name="clinical_analysis",
            description="Analyze clinical trial data",
        )
        task = {
            "type": "analysis",
            "description": "clinical trial analysis needed",
            "goal": "Analyze trial data",
        }
        score = SkillRegistry._keyword_relevance(entry, task)
        assert score > 0.0


# ---------------------------------------------------------------------------
# Initialize tests
# ---------------------------------------------------------------------------


class TestInitialize:
    """Tests for SkillRegistry.initialize."""

    @patch("src.skills.registry.SupabaseClient")
    @patch("src.skills.index.SupabaseClient")
    @pytest.mark.asyncio
    async def test_initialize_sets_flag(
        self, mock_idx_sb: MagicMock, mock_reg_sb: MagicMock
    ) -> None:
        mock_idx_sb.get_client.return_value = MagicMock()
        mock_client = MagicMock()
        mock_reg_sb.get_client.return_value = mock_client

        # Mock DB responses
        mock_query = MagicMock()
        mock_query.select.return_value = mock_query
        mock_query.execute.return_value = MagicMock(data=[])
        mock_client.table.return_value = mock_query

        registry = SkillRegistry()
        assert registry._initialized is False

        await registry.initialize()
        assert registry._initialized is True

    @patch("src.skills.registry.SupabaseClient")
    @patch("src.skills.index.SupabaseClient")
    @pytest.mark.asyncio
    async def test_initialize_calls_all_discovery_methods(
        self, mock_idx_sb: MagicMock, mock_reg_sb: MagicMock
    ) -> None:
        mock_idx_sb.get_client.return_value = MagicMock()
        mock_reg_sb.get_client.return_value = MagicMock()

        registry = SkillRegistry()

        with (
            patch.object(registry, "_discover_capabilities") as mock_caps,
            patch.object(registry, "_discover_definitions") as mock_defs,
            patch.object(registry, "_load_external_skills", new_callable=AsyncMock) as mock_ext,
            patch.object(registry, "_load_custom_skills", new_callable=AsyncMock) as mock_custom,
        ):
            await registry.initialize()

        mock_caps.assert_called_once()
        mock_defs.assert_called_once()
        mock_ext.assert_called_once()
        mock_custom.assert_called_once()
