"""Tests for ProfileMergeService (US-922).

Profile Update → Memory Merge Pipeline: detects changes, re-researches
if company changed, merges into memory with conflict resolution, presents
Memory Delta, recalculates readiness, and logs audit trail.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.memory.audit import MemoryOperation, MemoryType
from src.memory.profile_merge import ProfileMergeService


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
    chain.order.return_value = chain
    chain.limit.return_value = chain
    chain.in_.return_value = chain
    chain.maybe_single.return_value = chain
    chain.single.return_value = chain
    chain.execute.return_value = _mock_execute(execute_return)
    return chain


@pytest.fixture()
def mock_db() -> MagicMock:
    """Create a mock Supabase client."""
    return MagicMock()


@pytest.fixture()
def service(mock_db: MagicMock) -> ProfileMergeService:
    """Create a ProfileMergeService with mocked DB."""
    with patch("src.memory.profile_merge.SupabaseClient") as mock_cls:
        mock_cls.get_client.return_value = mock_db
        return ProfileMergeService()


class TestDetectChanges:
    """Tests for diff detection between old and new profile data."""

    def test_no_changes_returns_empty(self, service: ProfileMergeService) -> None:
        old = {"full_name": "Jane", "title": "VP Sales"}
        new = {"full_name": "Jane", "title": "VP Sales"}
        changes = service._detect_changes(old, new)
        assert changes == {}

    def test_detects_field_change(self, service: ProfileMergeService) -> None:
        old = {"full_name": "Jane Smith", "title": "VP Sales"}
        new = {"full_name": "Jane Smith", "title": "SVP Sales"}
        changes = service._detect_changes(old, new)
        assert "title" in changes
        assert changes["title"]["old"] == "VP Sales"
        assert changes["title"]["new"] == "SVP Sales"

    def test_detects_new_field(self, service: ProfileMergeService) -> None:
        old = {"full_name": "Jane"}
        new = {"full_name": "Jane", "department": "Commercial"}
        changes = service._detect_changes(old, new)
        assert "department" in changes
        assert changes["department"]["old"] is None
        assert changes["department"]["new"] == "Commercial"

    def test_detects_removed_field(self, service: ProfileMergeService) -> None:
        old = {"full_name": "Jane", "linkedin_url": "https://linkedin.com/in/jane"}
        new = {"full_name": "Jane", "linkedin_url": None}
        changes = service._detect_changes(old, new)
        assert "linkedin_url" in changes

    def test_detects_list_changes(self, service: ProfileMergeService) -> None:
        old = {"tracked_competitors": ["CompA", "CompB"]}
        new = {"tracked_competitors": ["CompA", "CompC"]}
        changes = service._detect_changes(old, new)
        assert "tracked_competitors" in changes

    def test_ignores_metadata_fields(self, service: ProfileMergeService) -> None:
        old = {"full_name": "Jane", "updated_at": "2026-01-01T00:00:00"}
        new = {"full_name": "Jane", "updated_at": "2026-02-07T12:00:00"}
        changes = service._detect_changes(old, new)
        assert changes == {}


class TestCompanyChanged:
    """Tests for company change detection."""

    def test_company_name_change(self, service: ProfileMergeService) -> None:
        changes = {"name": {"old": "OldCo", "new": "NewCo"}}
        assert service._company_changed(changes) is True

    def test_website_change(self, service: ProfileMergeService) -> None:
        changes = {"website": {"old": "old.com", "new": "new.com"}}
        assert service._company_changed(changes) is True

    def test_industry_change(self, service: ProfileMergeService) -> None:
        changes = {"industry": {"old": "Pharma", "new": "Biotech"}}
        assert service._company_changed(changes) is True

    def test_non_company_change(self, service: ProfileMergeService) -> None:
        changes = {"description": {"old": "Old desc", "new": "New desc"}}
        assert service._company_changed(changes) is False


class TestMergeChanges:
    """Tests for memory merge with conflict resolution."""

    @pytest.mark.asyncio()
    async def test_user_stated_wins_over_existing(
        self,
        service: ProfileMergeService,
        mock_db: MagicMock,
    ) -> None:
        """User-stated profile data supersedes existing lower-confidence facts."""
        # Mock existing fact with web research confidence
        existing_facts = [
            {
                "id": "fact-1",
                "fact": "Jane is VP Sales",
                "confidence": 0.70,
                "source": "enrichment_website",
                "metadata": {"category": "leadership"},
            }
        ]
        select_chain = _build_chain(existing_facts)
        update_chain = _build_chain(None)
        insert_chain = _build_chain([{"id": "fact-2"}])

        mock_db.table.side_effect = [select_chain, update_chain, insert_chain]

        changes = {
            "title": {"old": "VP Sales", "new": "SVP Sales"},
        }

        merged = await service._merge_changes("user-123", changes)

        assert len(merged) >= 1
        # The new fact should be user_stated with high confidence
        user_fact = next((m for m in merged if m.get("source") == "user_stated"), None)
        assert user_fact is not None
        assert user_fact["confidence"] == 0.95

    @pytest.mark.asyncio()
    async def test_creates_new_fact_when_no_conflict(
        self,
        service: ProfileMergeService,
        mock_db: MagicMock,
    ) -> None:
        """New profile data creates a new semantic memory fact."""
        select_chain = _build_chain([])  # No existing facts
        insert_chain = _build_chain([{"id": "fact-new"}])

        mock_db.table.side_effect = [select_chain, insert_chain]

        changes = {
            "department": {"old": None, "new": "Commercial"},
        }

        merged = await service._merge_changes("user-123", changes)

        assert len(merged) == 1
        assert merged[0]["source"] == "user_stated"
        assert merged[0]["confidence"] == 0.95


class TestProcessUpdate:
    """Tests for the full merge pipeline."""

    @pytest.mark.asyncio()
    async def test_no_changes_returns_early(
        self,
        service: ProfileMergeService,
    ) -> None:
        """Identical old and new data returns no_changes status."""
        old_data = {"full_name": "Jane", "title": "VP Sales"}
        new_data = {"full_name": "Jane", "title": "VP Sales"}

        result = await service.process_update("user-123", old_data, new_data)

        assert result["status"] == "no_changes"

    @pytest.mark.asyncio()
    async def test_full_pipeline_with_user_change(
        self,
        service: ProfileMergeService,
        mock_db: MagicMock,
    ) -> None:
        """Title change triggers merge, delta generation, readiness, and audit."""
        old_data = {"full_name": "Jane", "title": "VP Sales"}
        new_data = {"full_name": "Jane", "title": "SVP Sales"}

        # Mock merge: existing facts query, supersede update, new fact insert
        select_chain = _build_chain([])
        insert_chain = _build_chain([{"id": "fact-1"}])

        # Mock delta generation (fetch facts)
        delta_chain = _build_chain([
            {
                "id": "fact-1",
                "fact": "Jane's title is SVP Sales",
                "confidence": 0.95,
                "source": "user_stated",
                "metadata": {"category": "leadership"},
            }
        ])

        # Mock readiness recalculation
        readiness_chain = _build_chain({"readiness_scores": {}})

        # Mock audit insert
        audit_chain = _build_chain([{"id": "audit-1"}])

        mock_db.table.side_effect = [
            select_chain,   # merge: fetch existing facts
            insert_chain,   # merge: insert new fact
            delta_chain,    # delta: fetch facts
            readiness_chain,  # readiness: fetch state
            audit_chain,    # audit: insert
        ]

        with patch.object(service, "_recalculate_readiness", new_callable=AsyncMock):
            result = await service.process_update("user-123", old_data, new_data)

        assert result["status"] == "merged"
        assert result["changes"] == 1

    @pytest.mark.asyncio()
    async def test_company_change_triggers_re_enrichment(
        self,
        service: ProfileMergeService,
        mock_db: MagicMock,
    ) -> None:
        """Company name change triggers re-enrichment."""
        old_data = {"name": "OldCo", "website": "old.com"}
        new_data = {"name": "NewCo", "website": "new.com"}

        # Mock the pipeline
        select_chain = _build_chain([])
        insert_chain = _build_chain([{"id": "fact-1"}])
        delta_chain = _build_chain([])
        readiness_chain = _build_chain({"readiness_scores": {}})
        audit_chain = _build_chain([{"id": "audit-1"}])

        mock_db.table.side_effect = [
            select_chain,  # merge name
            insert_chain,
            select_chain,  # merge website
            insert_chain,
            delta_chain,
            readiness_chain,
            audit_chain,
        ]

        with (
            patch.object(
                service, "_trigger_re_enrichment", new_callable=AsyncMock
            ) as mock_enrich,
            patch.object(service, "_recalculate_readiness", new_callable=AsyncMock),
        ):
            await service.process_update("user-123", old_data, new_data)

        mock_enrich.assert_called_once()


class TestAuditChanges:
    """Tests for audit logging of profile changes."""

    @pytest.mark.asyncio()
    async def test_audit_log_records_before_after(
        self,
        service: ProfileMergeService,
        mock_db: MagicMock,
    ) -> None:
        """Audit log captures before/after values and change metadata."""
        changes = {"title": {"old": "VP Sales", "new": "SVP Sales"}}
        merged = [{"fact": "Title changed", "source": "user_stated"}]

        with patch(
            "src.memory.profile_merge.log_memory_operation",
            new_callable=AsyncMock,
        ) as mock_log:
            await service._audit_changes("user-123", changes, merged)

        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args.kwargs
        assert call_kwargs["user_id"] == "user-123"
        assert call_kwargs["operation"] == MemoryOperation.UPDATE
        assert call_kwargs["memory_type"] == MemoryType.SEMANTIC
        assert "title" in call_kwargs["metadata"]["fields_changed"]
        assert call_kwargs["metadata"]["changes"]["title"]["old"] == "VP Sales"
        assert call_kwargs["metadata"]["changes"]["title"]["new"] == "SVP Sales"


class TestSourceHierarchy:
    """Tests for conflict resolution source hierarchy."""

    def test_source_confidence_ordering(self, service: ProfileMergeService) -> None:
        """Verify source hierarchy: user_stated > CRM > document > web > inferred."""
        assert service._source_confidence("user_stated") == 0.95
        assert service._source_confidence("crm") == 0.85
        assert service._source_confidence("document") == 0.80
        assert service._source_confidence("enrichment_website") == 0.70
        assert service._source_confidence("inferred") == 0.55
        assert service._source_confidence("unknown") == 0.50

    def test_user_stated_always_wins(self, service: ProfileMergeService) -> None:
        """User-stated confidence always outranks other sources."""
        for source in ["crm", "document", "enrichment_website", "inferred"]:
            assert service._source_confidence("user_stated") > service._source_confidence(
                source
            )
