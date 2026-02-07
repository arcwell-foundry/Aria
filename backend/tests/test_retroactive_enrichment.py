"""Tests for US-923: Retroactive Enrichment Service.

Tests cover:
- Entity overlap detection between existing and new data
- Entity merging with source hierarchy conflict resolution
- Stakeholder map updates
- Health score recalculation
- Significant enrichment flagging for Memory Delta
- Episodic memory recording
- Audit trail logging
- Trigger-specific entry points (email, CRM, document)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.memory.retroactive_enrichment import (
    EnrichmentResult,
    EnrichmentTrigger,
    RetroactiveEnrichmentService,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_supabase() -> MagicMock:
    """Create a mock Supabase client."""
    mock = MagicMock()

    # Default: empty query results
    mock_response = MagicMock()
    mock_response.data = []
    mock.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response
    mock.table.return_value.select.return_value.eq.return_value.gt.return_value.execute.return_value = mock_response
    mock.table.return_value.insert.return_value.execute.return_value = mock_response
    mock.table.return_value.update.return_value.eq.return_value.execute.return_value = mock_response
    return mock


@pytest.fixture
def service(mock_supabase: MagicMock) -> RetroactiveEnrichmentService:
    """Create a RetroactiveEnrichmentService with mocked DB."""
    with patch("src.memory.retroactive_enrichment.SupabaseClient") as mock_cls:
        mock_cls.get_client.return_value = mock_supabase
        svc = RetroactiveEnrichmentService()
    return svc


# ---------------------------------------------------------------------------
# EnrichmentTrigger enum
# ---------------------------------------------------------------------------


def test_enrichment_trigger_enum_values() -> None:
    """EnrichmentTrigger has expected trigger types."""
    assert EnrichmentTrigger.EMAIL_ARCHIVE.value == "email_archive"
    assert EnrichmentTrigger.CRM_SYNC.value == "crm_sync"
    assert EnrichmentTrigger.DOCUMENT_BATCH.value == "document_batch"


# ---------------------------------------------------------------------------
# EnrichmentResult model
# ---------------------------------------------------------------------------


def test_enrichment_result_initialization() -> None:
    """EnrichmentResult stores enrichment outcome for a single entity."""
    result = EnrichmentResult(
        entity_name="Moderna",
        entity_type="company",
        facts_added=5,
        facts_updated=3,
        relationships_discovered=2,
        confidence_before=0.55,
        confidence_after=0.85,
        significance=0.8,
        trigger="email_archive",
    )
    assert result.entity_name == "Moderna"
    assert result.facts_added == 5
    assert result.significance == 0.8


def test_enrichment_result_is_significant() -> None:
    """EnrichmentResult.is_significant returns True when significance > 0.7."""
    high = EnrichmentResult(
        entity_name="A",
        entity_type="company",
        facts_added=1,
        facts_updated=0,
        relationships_discovered=0,
        confidence_before=0.5,
        confidence_after=0.9,
        significance=0.8,
        trigger="crm_sync",
    )
    low = EnrichmentResult(
        entity_name="B",
        entity_type="contact",
        facts_added=1,
        facts_updated=0,
        relationships_discovered=0,
        confidence_before=0.5,
        confidence_after=0.6,
        significance=0.3,
        trigger="crm_sync",
    )
    assert high.is_significant is True
    assert low.is_significant is False


# ---------------------------------------------------------------------------
# Overlap detection
# ---------------------------------------------------------------------------


def test_find_overlaps_exact_name_match() -> None:
    """Finds overlaps when entity names match exactly (case-insensitive)."""
    service = RetroactiveEnrichmentService.__new__(RetroactiveEnrichmentService)

    existing = [
        {"name": "Moderna", "type": "company", "confidence": 0.55},
        {"name": "Pfizer", "type": "company", "confidence": 0.70},
    ]
    new = [
        {"name": "moderna", "type": "company", "confidence": 0.85},
        {"name": "BioNTech", "type": "company", "confidence": 0.80},
    ]

    overlaps = service._find_overlaps(existing, new)

    assert len(overlaps) == 1
    assert overlaps[0]["name"] == "moderna"
    assert overlaps[0]["existing"]["name"] == "Moderna"
    assert overlaps[0]["new"]["name"] == "moderna"


def test_find_overlaps_no_match() -> None:
    """Returns empty list when there is no overlap."""
    service = RetroactiveEnrichmentService.__new__(RetroactiveEnrichmentService)

    existing = [{"name": "Moderna", "type": "company"}]
    new = [{"name": "BioNTech", "type": "company"}]

    overlaps = service._find_overlaps(existing, new)
    assert overlaps == []


def test_find_overlaps_multiple_matches() -> None:
    """Finds multiple overlapping entities."""
    service = RetroactiveEnrichmentService.__new__(RetroactiveEnrichmentService)

    existing = [
        {"name": "Moderna", "type": "company"},
        {"name": "John Doe", "type": "contact"},
        {"name": "Pfizer", "type": "company"},
    ]
    new = [
        {"name": "moderna", "type": "company"},
        {"name": "john doe", "type": "contact"},
    ]

    overlaps = service._find_overlaps(existing, new)
    assert len(overlaps) == 2


def test_find_overlaps_empty_name_ignored() -> None:
    """Entities with empty names are ignored during overlap detection."""
    service = RetroactiveEnrichmentService.__new__(RetroactiveEnrichmentService)

    existing = [{"name": "", "type": "company"}]
    new = [{"name": "", "type": "company"}]

    overlaps = service._find_overlaps(existing, new)
    assert overlaps == []


# ---------------------------------------------------------------------------
# Entity enrichment (merge logic)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enrich_entity_merges_new_facts(
    service: RetroactiveEnrichmentService,
    mock_supabase: MagicMock,
) -> None:
    """Enriching an entity inserts new facts into memory_semantic."""
    overlap: dict[str, Any] = {
        "name": "Moderna",
        "existing": {
            "name": "Moderna",
            "type": "company",
            "facts": ["CRM record for Moderna"],
            "confidence": 0.55,
            "source": "crm",
        },
        "new": {
            "name": "Moderna",
            "type": "company",
            "facts": [
                "47 email threads with Moderna stakeholders",
                "3 key stakeholders identified: Jane Smith, Bob Lee, Alice Wong",
            ],
            "confidence": 0.80,
            "source": "email_archive",
            "relationships": [
                {"contact": "Jane Smith", "role": "decision_maker"},
                {"contact": "Bob Lee", "role": "champion"},
            ],
        },
    }

    result = await service._enrich_entity(
        user_id="user-123",
        overlap=overlap,
        trigger=EnrichmentTrigger.EMAIL_ARCHIVE,
    )

    assert result is not None
    assert result.entity_name == "Moderna"
    assert result.facts_added >= 2
    # Verify insert was called on memory_semantic
    mock_supabase.table.assert_any_call("memory_semantic")


@pytest.mark.asyncio
async def test_enrich_entity_respects_source_hierarchy(
    service: RetroactiveEnrichmentService,
) -> None:
    """New data from lower-confidence source does not supersede higher-confidence existing facts."""
    overlap: dict[str, Any] = {
        "name": "Moderna",
        "existing": {
            "name": "Moderna",
            "type": "company",
            "facts": ["Moderna is a biotech company"],
            "confidence": 0.95,
            "source": "user_stated",
        },
        "new": {
            "name": "Moderna",
            "type": "company",
            "facts": ["Moderna is a pharmaceutical company"],
            "confidence": 0.70,
            "source": "enrichment_website",
            "relationships": [],
        },
    }

    result = await service._enrich_entity(
        user_id="user-123",
        overlap=overlap,
        trigger=EnrichmentTrigger.CRM_SYNC,
    )

    # Should not supersede the user_stated fact
    assert result is not None
    assert result.facts_updated == 0


@pytest.mark.asyncio
async def test_enrich_entity_supersedes_lower_confidence(
    service: RetroactiveEnrichmentService,
    mock_supabase: MagicMock,
) -> None:
    """Higher-confidence new data supersedes lower-confidence existing facts."""
    # Set up existing fact in mock
    existing_fact = {
        "id": "fact-old-1",
        "user_id": "user-123",
        "fact": "Moderna has 1 known contact",
        "confidence": 0.55,
        "source": "inferred",
        "metadata": {"category": "contact", "entity_name": "Moderna"},
    }
    mock_response = MagicMock()
    mock_response.data = [existing_fact]
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        mock_response
    )

    overlap: dict[str, Any] = {
        "name": "Moderna",
        "existing": {
            "name": "Moderna",
            "type": "company",
            "facts": ["Moderna has 1 known contact"],
            "confidence": 0.55,
            "source": "inferred",
        },
        "new": {
            "name": "Moderna",
            "type": "company",
            "facts": ["Moderna has 3 key stakeholders across leadership"],
            "confidence": 0.80,
            "source": "email_archive",
            "relationships": [],
        },
    }

    result = await service._enrich_entity(
        user_id="user-123",
        overlap=overlap,
        trigger=EnrichmentTrigger.EMAIL_ARCHIVE,
    )

    assert result is not None
    assert result.facts_updated >= 1


# ---------------------------------------------------------------------------
# Significance calculation
# ---------------------------------------------------------------------------


def test_calculate_significance_high_for_many_new_facts() -> None:
    """Significance is high when many new facts and relationships are discovered."""
    service = RetroactiveEnrichmentService.__new__(RetroactiveEnrichmentService)

    significance = service._calculate_significance(
        facts_added=5,
        facts_updated=3,
        relationships_discovered=2,
        confidence_delta=0.30,
    )

    assert significance > 0.7


def test_calculate_significance_low_for_minor_updates() -> None:
    """Significance is low for minor updates with little new information."""
    service = RetroactiveEnrichmentService.__new__(RetroactiveEnrichmentService)

    significance = service._calculate_significance(
        facts_added=0,
        facts_updated=1,
        relationships_discovered=0,
        confidence_delta=0.05,
    )

    assert significance < 0.5


def test_calculate_significance_bounded_0_to_1() -> None:
    """Significance score is always between 0.0 and 1.0."""
    service = RetroactiveEnrichmentService.__new__(RetroactiveEnrichmentService)

    # Extreme high
    high = service._calculate_significance(
        facts_added=100,
        facts_updated=100,
        relationships_discovered=50,
        confidence_delta=1.0,
    )
    assert 0.0 <= high <= 1.0

    # Extreme low
    low = service._calculate_significance(
        facts_added=0,
        facts_updated=0,
        relationships_discovered=0,
        confidence_delta=0.0,
    )
    assert 0.0 <= low <= 1.0


# ---------------------------------------------------------------------------
# Full enrichment pipeline (enrich_from_new_data)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enrich_from_new_data_returns_counts(
    service: RetroactiveEnrichmentService,
) -> None:
    """enrich_from_new_data returns enriched and significant counts."""
    # Mock _get_existing_entities to return known entities
    with (
        patch.object(
            service,
            "_get_existing_entities",
            new_callable=AsyncMock,
            return_value=[
                {"name": "Moderna", "type": "company", "confidence": 0.55},
            ],
        ),
        patch.object(
            service,
            "_enrich_entity",
            new_callable=AsyncMock,
            return_value=EnrichmentResult(
                entity_name="Moderna",
                entity_type="company",
                facts_added=5,
                facts_updated=2,
                relationships_discovered=3,
                confidence_before=0.55,
                confidence_after=0.85,
                significance=0.8,
                trigger="email_archive",
            ),
        ),
        patch.object(service, "_update_stakeholder_maps", new_callable=AsyncMock),
        patch.object(service, "_recalculate_health_scores", new_callable=AsyncMock),
        patch.object(service, "_flag_for_briefing", new_callable=AsyncMock),
        patch.object(service, "_record_episodic", new_callable=AsyncMock),
    ):
        result = await service.enrich_from_new_data(
            user_id="user-123",
            trigger=EnrichmentTrigger.EMAIL_ARCHIVE,
            new_entities=[
                {"name": "moderna", "type": "company", "confidence": 0.85},
            ],
        )

    assert result["enriched"] == 1
    assert result["significant"] == 1


@pytest.mark.asyncio
async def test_enrich_from_new_data_no_overlaps(
    service: RetroactiveEnrichmentService,
) -> None:
    """When no overlaps exist, returns zero enrichments."""
    with (
        patch.object(
            service,
            "_get_existing_entities",
            new_callable=AsyncMock,
            return_value=[
                {"name": "Pfizer", "type": "company"},
            ],
        ),
        patch.object(service, "_record_episodic", new_callable=AsyncMock),
    ):
        result = await service.enrich_from_new_data(
            user_id="user-123",
            trigger=EnrichmentTrigger.CRM_SYNC,
            new_entities=[
                {"name": "BioNTech", "type": "company"},
            ],
        )

    assert result["enriched"] == 0
    assert result["significant"] == 0


@pytest.mark.asyncio
async def test_enrich_from_new_data_calls_stakeholder_update(
    service: RetroactiveEnrichmentService,
) -> None:
    """Pipeline calls _update_stakeholder_maps with enriched results."""
    mock_result = EnrichmentResult(
        entity_name="Moderna",
        entity_type="company",
        facts_added=2,
        facts_updated=1,
        relationships_discovered=2,
        confidence_before=0.55,
        confidence_after=0.80,
        significance=0.6,
        trigger="email_archive",
    )

    with (
        patch.object(
            service,
            "_get_existing_entities",
            new_callable=AsyncMock,
            return_value=[{"name": "Moderna", "type": "company"}],
        ),
        patch.object(
            service,
            "_enrich_entity",
            new_callable=AsyncMock,
            return_value=mock_result,
        ),
        patch.object(
            service, "_update_stakeholder_maps", new_callable=AsyncMock
        ) as mock_stakeholders,
        patch.object(service, "_recalculate_health_scores", new_callable=AsyncMock),
        patch.object(service, "_flag_for_briefing", new_callable=AsyncMock),
        patch.object(service, "_record_episodic", new_callable=AsyncMock),
    ):
        await service.enrich_from_new_data(
            user_id="user-123",
            trigger=EnrichmentTrigger.EMAIL_ARCHIVE,
            new_entities=[{"name": "moderna", "type": "company"}],
        )

    mock_stakeholders.assert_awaited_once_with("user-123", [mock_result])


@pytest.mark.asyncio
async def test_enrich_from_new_data_calls_health_score_recalculation(
    service: RetroactiveEnrichmentService,
) -> None:
    """Pipeline calls _recalculate_health_scores with enriched results."""
    mock_result = EnrichmentResult(
        entity_name="Moderna",
        entity_type="company",
        facts_added=3,
        facts_updated=0,
        relationships_discovered=1,
        confidence_before=0.55,
        confidence_after=0.75,
        significance=0.6,
        trigger="crm_sync",
    )

    with (
        patch.object(
            service,
            "_get_existing_entities",
            new_callable=AsyncMock,
            return_value=[{"name": "Moderna", "type": "company"}],
        ),
        patch.object(
            service,
            "_enrich_entity",
            new_callable=AsyncMock,
            return_value=mock_result,
        ),
        patch.object(service, "_update_stakeholder_maps", new_callable=AsyncMock),
        patch.object(service, "_recalculate_health_scores", new_callable=AsyncMock) as mock_health,
        patch.object(service, "_flag_for_briefing", new_callable=AsyncMock),
        patch.object(service, "_record_episodic", new_callable=AsyncMock),
    ):
        await service.enrich_from_new_data(
            user_id="user-123",
            trigger=EnrichmentTrigger.CRM_SYNC,
            new_entities=[{"name": "moderna", "type": "company"}],
        )

    mock_health.assert_awaited_once_with("user-123", [mock_result])


@pytest.mark.asyncio
async def test_enrich_from_new_data_flags_significant_for_briefing(
    service: RetroactiveEnrichmentService,
) -> None:
    """Significant enrichments (significance > 0.7) are flagged for briefing."""
    significant_result = EnrichmentResult(
        entity_name="Moderna",
        entity_type="company",
        facts_added=10,
        facts_updated=5,
        relationships_discovered=3,
        confidence_before=0.40,
        confidence_after=0.90,
        significance=0.9,
        trigger="email_archive",
    )

    with (
        patch.object(
            service,
            "_get_existing_entities",
            new_callable=AsyncMock,
            return_value=[{"name": "Moderna", "type": "company"}],
        ),
        patch.object(
            service,
            "_enrich_entity",
            new_callable=AsyncMock,
            return_value=significant_result,
        ),
        patch.object(service, "_update_stakeholder_maps", new_callable=AsyncMock),
        patch.object(service, "_recalculate_health_scores", new_callable=AsyncMock),
        patch.object(service, "_flag_for_briefing", new_callable=AsyncMock) as mock_flag,
        patch.object(service, "_record_episodic", new_callable=AsyncMock),
    ):
        await service.enrich_from_new_data(
            user_id="user-123",
            trigger=EnrichmentTrigger.EMAIL_ARCHIVE,
            new_entities=[{"name": "moderna", "type": "company"}],
        )

    mock_flag.assert_awaited_once()
    flagged = mock_flag.call_args[0]
    assert flagged[0] == "user-123"
    assert len(flagged[1]) == 1
    assert flagged[1][0].significance > 0.7


@pytest.mark.asyncio
async def test_enrich_from_new_data_records_episodic_memory(
    service: RetroactiveEnrichmentService,
) -> None:
    """Each enrichment is recorded as episodic memory."""
    mock_result = EnrichmentResult(
        entity_name="Moderna",
        entity_type="company",
        facts_added=2,
        facts_updated=1,
        relationships_discovered=0,
        confidence_before=0.55,
        confidence_after=0.75,
        significance=0.5,
        trigger="document_batch",
    )

    with (
        patch.object(
            service,
            "_get_existing_entities",
            new_callable=AsyncMock,
            return_value=[{"name": "Moderna", "type": "company"}],
        ),
        patch.object(
            service,
            "_enrich_entity",
            new_callable=AsyncMock,
            return_value=mock_result,
        ),
        patch.object(service, "_update_stakeholder_maps", new_callable=AsyncMock),
        patch.object(service, "_recalculate_health_scores", new_callable=AsyncMock),
        patch.object(service, "_record_episodic", new_callable=AsyncMock) as mock_episodic,
    ):
        await service.enrich_from_new_data(
            user_id="user-123",
            trigger=EnrichmentTrigger.DOCUMENT_BATCH,
            new_entities=[{"name": "moderna", "type": "company"}],
        )

    mock_episodic.assert_awaited_once_with("user-123", mock_result)


@pytest.mark.asyncio
async def test_enrich_from_new_data_skips_none_results(
    service: RetroactiveEnrichmentService,
) -> None:
    """If _enrich_entity returns None for an overlap, it is skipped."""
    with (
        patch.object(
            service,
            "_get_existing_entities",
            new_callable=AsyncMock,
            return_value=[{"name": "Moderna", "type": "company"}],
        ),
        patch.object(
            service,
            "_enrich_entity",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch.object(service, "_update_stakeholder_maps", new_callable=AsyncMock),
        patch.object(service, "_recalculate_health_scores", new_callable=AsyncMock),
        patch.object(service, "_record_episodic", new_callable=AsyncMock) as mock_episodic,
    ):
        result = await service.enrich_from_new_data(
            user_id="user-123",
            trigger=EnrichmentTrigger.EMAIL_ARCHIVE,
            new_entities=[{"name": "moderna", "type": "company"}],
        )

    assert result["enriched"] == 0
    mock_episodic.assert_not_awaited()


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enrich_from_new_data_logs_audit(
    service: RetroactiveEnrichmentService,
) -> None:
    """The enrichment pipeline logs an audit entry."""
    mock_result = EnrichmentResult(
        entity_name="Moderna",
        entity_type="company",
        facts_added=3,
        facts_updated=1,
        relationships_discovered=1,
        confidence_before=0.55,
        confidence_after=0.80,
        significance=0.6,
        trigger="email_archive",
    )

    with (
        patch.object(
            service,
            "_get_existing_entities",
            new_callable=AsyncMock,
            return_value=[{"name": "Moderna", "type": "company"}],
        ),
        patch.object(
            service,
            "_enrich_entity",
            new_callable=AsyncMock,
            return_value=mock_result,
        ),
        patch.object(service, "_update_stakeholder_maps", new_callable=AsyncMock),
        patch.object(service, "_recalculate_health_scores", new_callable=AsyncMock),
        patch.object(service, "_record_episodic", new_callable=AsyncMock),
        patch(
            "src.memory.retroactive_enrichment.log_memory_operation",
            new_callable=AsyncMock,
        ) as mock_audit,
    ):
        await service.enrich_from_new_data(
            user_id="user-123",
            trigger=EnrichmentTrigger.EMAIL_ARCHIVE,
            new_entities=[{"name": "moderna", "type": "company"}],
        )

    mock_audit.assert_awaited_once()
    call_kwargs = mock_audit.call_args[1]
    assert call_kwargs["user_id"] == "user-123"
    assert call_kwargs["metadata"]["action"] == "retroactive_enrichment"
    assert call_kwargs["metadata"]["trigger"] == "email_archive"
    assert call_kwargs["metadata"]["entities_enriched"] == 1


# ---------------------------------------------------------------------------
# get_existing_entities
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_existing_entities_queries_semantic_memory(
    service: RetroactiveEnrichmentService,
    mock_supabase: MagicMock,
) -> None:
    """_get_existing_entities fetches from memory_semantic for the user."""
    mock_response = MagicMock()
    mock_response.data = [
        {"fact": "Moderna is a biotech company", "metadata": {"entity_name": "Moderna"}},
    ]
    mock_supabase.table.return_value.select.return_value.eq.return_value.gt.return_value.execute.return_value = mock_response
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        mock_response
    )

    entities = await service._get_existing_entities("user-123")

    assert len(entities) >= 1
    mock_supabase.table.assert_any_call("memory_semantic")


# ---------------------------------------------------------------------------
# Source confidence helper
# ---------------------------------------------------------------------------


def test_source_confidence_returns_correct_hierarchy() -> None:
    """Source confidence follows CLAUDE.md hierarchy."""
    service = RetroactiveEnrichmentService.__new__(RetroactiveEnrichmentService)

    assert service._source_confidence("user_stated") == 0.95
    assert service._source_confidence("crm") == 0.85
    assert service._source_confidence("document") == 0.80
    assert service._source_confidence("email_archive") == 0.75
    assert service._source_confidence("enrichment_website") == 0.70
    assert service._source_confidence("inferred") == 0.55
    assert service._source_confidence("unknown_source") == 0.50


# ---------------------------------------------------------------------------
# Convenience trigger methods
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enrich_after_email_archive(
    service: RetroactiveEnrichmentService,
) -> None:
    """enrich_after_email_archive delegates to enrich_from_new_data with EMAIL_ARCHIVE trigger."""
    with patch.object(
        service,
        "enrich_from_new_data",
        new_callable=AsyncMock,
        return_value={"enriched": 1, "significant": 0},
    ) as mock_main:
        entities = [{"name": "Moderna", "type": "company"}]
        result = await service.enrich_after_email_archive("user-123", entities)

    mock_main.assert_awaited_once_with(
        user_id="user-123",
        trigger=EnrichmentTrigger.EMAIL_ARCHIVE,
        new_entities=entities,
    )
    assert result["enriched"] == 1


@pytest.mark.asyncio
async def test_enrich_after_crm_sync(
    service: RetroactiveEnrichmentService,
) -> None:
    """enrich_after_crm_sync delegates to enrich_from_new_data with CRM_SYNC trigger."""
    with patch.object(
        service,
        "enrich_from_new_data",
        new_callable=AsyncMock,
        return_value={"enriched": 2, "significant": 1},
    ) as mock_main:
        entities = [
            {"name": "Moderna", "type": "company"},
            {"name": "Pfizer", "type": "company"},
        ]
        result = await service.enrich_after_crm_sync("user-123", entities)

    mock_main.assert_awaited_once_with(
        user_id="user-123",
        trigger=EnrichmentTrigger.CRM_SYNC,
        new_entities=entities,
    )
    assert result["enriched"] == 2


@pytest.mark.asyncio
async def test_enrich_after_document_batch(
    service: RetroactiveEnrichmentService,
) -> None:
    """enrich_after_document_batch delegates to enrich_from_new_data with DOCUMENT_BATCH trigger."""
    with patch.object(
        service,
        "enrich_from_new_data",
        new_callable=AsyncMock,
        return_value={"enriched": 0, "significant": 0},
    ) as mock_main:
        result = await service.enrich_after_document_batch("user-123", [])

    mock_main.assert_awaited_once_with(
        user_id="user-123",
        trigger=EnrichmentTrigger.DOCUMENT_BATCH,
        new_entities=[],
    )
    assert result["enriched"] == 0
