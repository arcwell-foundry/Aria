"""Tests for US-912: Knowledge Gap Detection & Prospective Memory Generation."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.onboarding.gap_detector import (
    GapAnalysisResult,
    KnowledgeGap,
    KnowledgeGapDetector,
)


# --- Fixtures ---


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
    chain.eq.return_value = chain
    chain.maybe_single.return_value = chain
    chain.single.return_value = chain
    chain.execute.return_value = _mock_execute(execute_return)
    return chain


@pytest.fixture()
def mock_db() -> MagicMock:
    """Create a mock Supabase client."""
    return MagicMock()


@pytest.fixture()
def detector(mock_db: MagicMock) -> KnowledgeGapDetector:
    """Create a KnowledgeGapDetector with mocked DB."""
    with patch("src.onboarding.gap_detector.SupabaseClient") as mock_cls:
        mock_cls.get_client.return_value = mock_db
        det = KnowledgeGapDetector()
    return det


# --- Corporate Memory gap detection ---


@pytest.mark.asyncio()
async def test_corporate_gaps_detected_when_no_leadership(
    detector: KnowledgeGapDetector,
) -> None:
    """Corporate memory gap flagged when no leadership info in facts."""
    facts: list[dict[str, Any]] = [
        {
            "fact": "Acme makes widgets",
            "confidence": 0.9,
            "source": "enrichment",
            "metadata": {"category": "product"},
        },
    ]
    gaps = await detector._analyze_corporate_memory(facts, None)

    leadership_gaps = [g for g in gaps if g.subdomain == "leadership"]
    assert len(leadership_gaps) == 1
    assert leadership_gaps[0].priority == "high"
    assert leadership_gaps[0].fill_strategy == "agent_research"
    assert leadership_gaps[0].suggested_agent == "analyst"


@pytest.mark.asyncio()
async def test_corporate_gaps_detected_when_no_products(
    detector: KnowledgeGapDetector,
) -> None:
    """Corporate memory gap flagged when no product info in facts."""
    facts: list[dict[str, Any]] = [
        {"fact": "CEO is Jane Doe", "confidence": 0.9, "source": "enrichment", "metadata": {}},
    ]
    gaps = await detector._analyze_corporate_memory(facts, None)

    product_gaps = [g for g in gaps if g.subdomain == "products"]
    assert len(product_gaps) == 1
    assert product_gaps[0].priority == "high"


@pytest.mark.asyncio()
async def test_corporate_gaps_detected_when_no_competitors(
    detector: KnowledgeGapDetector,
) -> None:
    """Corporate memory gap flagged when no competitor info."""
    facts: list[dict[str, Any]] = [
        {
            "fact": "Sells drug therapy for cancer",
            "confidence": 0.8,
            "source": "web",
            "metadata": {},
        },
    ]
    gaps = await detector._analyze_corporate_memory(facts, None)

    competitor_gaps = [g for g in gaps if g.subdomain == "competitors"]
    assert len(competitor_gaps) == 1
    assert competitor_gaps[0].suggested_agent == "scout"


@pytest.mark.asyncio()
async def test_no_corporate_gap_when_keyword_present(
    detector: KnowledgeGapDetector,
) -> None:
    """No leadership gap when leadership keywords appear in facts."""
    facts: list[dict[str, Any]] = [
        {
            "fact": "CEO John Smith leads the company",
            "confidence": 0.9,
            "source": "web",
            "metadata": {},
        },
        {
            "fact": "Main product is the XR-200 therapy platform",
            "confidence": 0.85,
            "source": "web",
            "metadata": {},
        },
        {
            "fact": "Competitor BioGenX is in same space",
            "confidence": 0.7,
            "source": "web",
            "metadata": {},
        },
        {
            "fact": "Pricing model is value-based at $50k/year",
            "confidence": 0.7,
            "source": "web",
            "metadata": {},
        },
        {
            "fact": "Partnership with Roche announced",
            "confidence": 0.8,
            "source": "news",
            "metadata": {},
        },
        {"fact": "FDA approved in 2024", "confidence": 0.9, "source": "web", "metadata": {}},
        {"fact": "Series C funding of $100M", "confidence": 0.8, "source": "news", "metadata": {}},
    ]
    gaps = await detector._analyze_corporate_memory(facts, None)

    assert len(gaps) == 0


@pytest.mark.asyncio()
async def test_corporate_gap_pricing_uses_user_prompt(
    detector: KnowledgeGapDetector,
) -> None:
    """Pricing gap uses user_prompt strategy (no agent can find it)."""
    facts: list[dict[str, Any]] = [
        {
            "fact": "CEO leads, product ships, competitor known, partner signed, certified iso, revenue growing",
            "confidence": 0.9,
            "source": "web",
            "metadata": {},
        },
    ]
    gaps = await detector._analyze_corporate_memory(facts, None)

    pricing_gaps = [g for g in gaps if g.subdomain == "pricing"]
    assert len(pricing_gaps) == 1
    assert pricing_gaps[0].fill_strategy == "user_prompt"
    assert pricing_gaps[0].suggested_agent is None


@pytest.mark.asyncio()
async def test_corporate_gap_detected_by_category_metadata(
    detector: KnowledgeGapDetector,
) -> None:
    """Facts with category metadata satisfy domain requirements."""
    facts: list[dict[str, Any]] = [
        {
            "fact": "Some fact without keywords",
            "confidence": 0.9,
            "source": "web",
            "metadata": {"category": "leadership"},
        },
    ]
    gaps = await detector._analyze_corporate_memory(facts, None)

    leadership_gaps = [g for g in gaps if g.subdomain == "leadership"]
    assert len(leadership_gaps) == 0


# --- Digital Twin gap detection ---


@pytest.mark.asyncio()
async def test_digital_twin_gap_when_writing_style_missing(
    detector: KnowledgeGapDetector,
) -> None:
    """Digital twin gap flagged when writing style is missing."""
    settings: dict[str, Any] = {"preferences": {"digital_twin": {}}}
    facts: list[dict[str, Any]] = []

    gaps = await detector._analyze_digital_twin(settings, facts)

    ws_gaps = [g for g in gaps if g.subdomain == "writing_style"]
    assert len(ws_gaps) == 1
    assert ws_gaps[0].priority == "high"
    assert ws_gaps[0].fill_strategy == "user_prompt"
    assert ws_gaps[0].suggested_prompt is not None


@pytest.mark.asyncio()
async def test_digital_twin_gap_when_writing_style_low_confidence(
    detector: KnowledgeGapDetector,
) -> None:
    """Digital twin gap flagged when writing style confidence < 0.5."""
    settings: dict[str, Any] = {
        "preferences": {
            "digital_twin": {
                "writing_style": {"confidence": 0.3},
            }
        }
    }

    gaps = await detector._analyze_digital_twin(settings, [])

    ws_gaps = [g for g in gaps if g.subdomain == "writing_style"]
    assert len(ws_gaps) == 1


@pytest.mark.asyncio()
async def test_no_digital_twin_writing_gap_when_high_confidence(
    detector: KnowledgeGapDetector,
) -> None:
    """No writing style gap when confidence >= 0.5."""
    settings: dict[str, Any] = {
        "preferences": {
            "digital_twin": {
                "writing_style": {"confidence": 0.8},
                "communication_patterns": {"peak_send_hours": [9, 10, 14]},
                "scheduling_preferences": {"morning_focus": True},
            }
        }
    }

    gaps = await detector._analyze_digital_twin(settings, [])

    assert len(gaps) == 0


@pytest.mark.asyncio()
async def test_digital_twin_gap_when_no_communication_patterns(
    detector: KnowledgeGapDetector,
) -> None:
    """Digital twin gap when communication patterns missing."""
    settings: dict[str, Any] = {
        "preferences": {
            "digital_twin": {
                "writing_style": {"confidence": 0.8},
            }
        }
    }

    gaps = await detector._analyze_digital_twin(settings, [])

    comm_gaps = [g for g in gaps if g.subdomain == "communication_patterns"]
    assert len(comm_gaps) == 1
    assert comm_gaps[0].fill_strategy == "integration_sync"


@pytest.mark.asyncio()
async def test_digital_twin_gap_when_no_scheduling(
    detector: KnowledgeGapDetector,
) -> None:
    """Digital twin gap when scheduling preferences missing."""
    settings: dict[str, Any] = {
        "preferences": {
            "digital_twin": {
                "writing_style": {"confidence": 0.8},
                "communication_patterns": {"peak_send_hours": [9]},
            }
        }
    }

    gaps = await detector._analyze_digital_twin(settings, [])

    sched_gaps = [g for g in gaps if g.subdomain == "scheduling"]
    assert len(sched_gaps) == 1
    assert sched_gaps[0].priority == "low"


@pytest.mark.asyncio()
async def test_digital_twin_gap_when_settings_none(
    detector: KnowledgeGapDetector,
) -> None:
    """All digital twin gaps detected when settings is None."""
    gaps = await detector._analyze_digital_twin(None, [])

    assert len(gaps) == 3  # writing_style, communication_patterns, scheduling
    subdomains = {g.subdomain for g in gaps}
    assert subdomains == {"writing_style", "communication_patterns", "scheduling"}


# --- Competitive Intelligence gap detection ---


@pytest.mark.asyncio()
async def test_competitive_intel_gap_when_few_competitor_facts(
    detector: KnowledgeGapDetector,
) -> None:
    """Competitive intel gap when < 3 competitor data points."""
    facts: list[dict[str, Any]] = [
        {
            "fact": "BioGenX is a competitor",
            "confidence": 0.7,
            "source": "web",
            "metadata": {"category": "competitive"},
        },
    ]

    gaps = await detector._analyze_competitive_intel(facts, None)

    profile_gaps = [g for g in gaps if g.subdomain == "competitor_profiles"]
    assert len(profile_gaps) == 1
    assert profile_gaps[0].fill_strategy == "agent_research"
    assert profile_gaps[0].suggested_agent == "analyst"


@pytest.mark.asyncio()
async def test_competitive_intel_gap_when_no_differentiation(
    detector: KnowledgeGapDetector,
) -> None:
    """Competitive intel gap when no differentiation data."""
    facts: list[dict[str, Any]] = [
        {
            "fact": "competitor A exists",
            "confidence": 0.7,
            "source": "web",
            "metadata": {"category": "competitive"},
        },
        {
            "fact": "competitor B exists",
            "confidence": 0.7,
            "source": "web",
            "metadata": {"category": "competitive"},
        },
        {
            "fact": "competitor C exists",
            "confidence": 0.7,
            "source": "web",
            "metadata": {"category": "competitive"},
        },
    ]

    gaps = await detector._analyze_competitive_intel(facts, None)

    diff_gaps = [g for g in gaps if g.subdomain == "differentiation"]
    assert len(diff_gaps) == 1
    assert diff_gaps[0].fill_strategy == "user_prompt"
    assert diff_gaps[0].suggested_prompt is not None


@pytest.mark.asyncio()
async def test_no_competitive_gap_when_sufficient_data(
    detector: KnowledgeGapDetector,
) -> None:
    """No competitive gaps when enough competitors and differentiation data."""
    facts: list[dict[str, Any]] = [
        {
            "fact": "competitor A in space",
            "confidence": 0.7,
            "source": "web",
            "metadata": {"category": "competitive"},
        },
        {
            "fact": "competitor B in space",
            "confidence": 0.7,
            "source": "web",
            "metadata": {"category": "competitive"},
        },
        {
            "fact": "competitor C in space",
            "confidence": 0.7,
            "source": "web",
            "metadata": {"category": "competitive"},
        },
        {
            "fact": "Our key differentiation is speed",
            "confidence": 0.8,
            "source": "user",
            "metadata": {},
        },
    ]

    gaps = await detector._analyze_competitive_intel(facts, None)

    assert len(gaps) == 0


# --- Integration gap detection ---


def test_integration_gap_when_no_crm(
    detector: KnowledgeGapDetector,
) -> None:
    """Integration gap when no CRM connected."""
    integrations: list[dict[str, Any]] = [
        {"integration_type": "google", "created_at": "2026-01-01"},
    ]

    gaps = detector._analyze_integrations(integrations)

    crm_gaps = [g for g in gaps if g.subdomain == "crm"]
    assert len(crm_gaps) == 1
    assert crm_gaps[0].priority == "high"


def test_integration_gap_when_no_calendar(
    detector: KnowledgeGapDetector,
) -> None:
    """Integration gap when no calendar connected."""
    integrations: list[dict[str, Any]] = [
        {"integration_type": "salesforce", "created_at": "2026-01-01"},
    ]

    gaps = detector._analyze_integrations(integrations)

    cal_gaps = [g for g in gaps if g.subdomain == "calendar"]
    assert len(cal_gaps) == 1
    assert cal_gaps[0].fill_strategy == "integration_sync"


def test_integration_gap_when_no_email(
    detector: KnowledgeGapDetector,
) -> None:
    """Integration gap when no email connected."""
    integrations: list[dict[str, Any]] = []

    gaps = detector._analyze_integrations(integrations)

    email_gaps = [g for g in gaps if g.subdomain == "email"]
    assert len(email_gaps) == 1
    assert email_gaps[0].priority == "high"


def test_no_integration_gap_when_all_connected(
    detector: KnowledgeGapDetector,
) -> None:
    """No integration gaps when CRM, calendar, email, Slack all connected."""
    integrations: list[dict[str, Any]] = [
        {"integration_type": "salesforce", "created_at": "2026-01-01"},
        {"integration_type": "googlecalendar", "created_at": "2026-01-01"},
        {"integration_type": "google", "created_at": "2026-01-01"},
        {"integration_type": "slack", "created_at": "2026-01-01"},
    ]

    gaps = detector._analyze_integrations(integrations)

    assert len(gaps) == 0


def test_integration_gap_slack_is_medium_priority(
    detector: KnowledgeGapDetector,
) -> None:
    """Slack gap is medium priority, not high."""
    integrations: list[dict[str, Any]] = [
        {"integration_type": "salesforce", "created_at": "2026-01-01"},
        {"integration_type": "googlecalendar", "created_at": "2026-01-01"},
        {"integration_type": "google", "created_at": "2026-01-01"},
    ]

    gaps = detector._analyze_integrations(integrations)

    assert len(gaps) == 1
    assert gaps[0].subdomain == "slack"
    assert gaps[0].priority == "medium"


# --- Completeness scoring ---


def test_completeness_100_when_no_gaps(
    detector: KnowledgeGapDetector,
) -> None:
    """Domain completeness is 100 when no gaps found."""
    assert detector._domain_completeness([]) == 100.0


def test_completeness_decreases_with_high_gap(
    detector: KnowledgeGapDetector,
) -> None:
    """High priority gap reduces completeness by 15."""
    gaps = [
        KnowledgeGap(
            domain="corporate_memory",
            subdomain="leadership",
            description="No leadership info",
            priority="high",
            fill_strategy="agent_research",
        ),
    ]
    score = detector._domain_completeness(gaps)
    assert score == 85.0


def test_completeness_decreases_with_critical_gap(
    detector: KnowledgeGapDetector,
) -> None:
    """Critical priority gap reduces completeness by 25."""
    gaps = [
        KnowledgeGap(
            domain="test",
            subdomain="test",
            description="Critical gap",
            priority="critical",
            fill_strategy="agent_research",
        ),
    ]
    score = detector._domain_completeness(gaps)
    assert score == 75.0


def test_completeness_floors_at_zero(
    detector: KnowledgeGapDetector,
) -> None:
    """Completeness doesn't go below 0."""
    gaps = [
        KnowledgeGap(
            domain="test",
            subdomain=f"sub{i}",
            description=f"Critical gap {i}",
            priority="critical",
            fill_strategy="agent_research",
        )
        for i in range(5)
    ]
    score = detector._domain_completeness(gaps)
    assert score == 0.0


def test_completeness_multiple_priorities(
    detector: KnowledgeGapDetector,
) -> None:
    """Completeness penalty accumulates across priorities."""
    gaps = [
        KnowledgeGap(
            domain="t", subdomain="a", description="high", priority="high", fill_strategy="x"
        ),
        KnowledgeGap(
            domain="t", subdomain="b", description="medium", priority="medium", fill_strategy="x"
        ),
        KnowledgeGap(
            domain="t", subdomain="c", description="low", priority="low", fill_strategy="x"
        ),
    ]
    # 100 - 15 - 8 - 3 = 74
    score = detector._domain_completeness(gaps)
    assert score == 74.0


# --- Prospective Memory entry creation ---


@pytest.mark.asyncio()
async def test_prospective_entries_created_for_each_gap(
    detector: KnowledgeGapDetector,
    mock_db: MagicMock,
) -> None:
    """A Prospective Memory entry is created for each knowledge gap."""
    gaps = [
        KnowledgeGap(
            domain="corporate_memory",
            subdomain="leadership",
            description="No leadership info",
            priority="high",
            fill_strategy="agent_research",
            suggested_agent="analyst",
        ),
        KnowledgeGap(
            domain="digital_twin",
            subdomain="writing_style",
            description="Writing style missing",
            priority="high",
            fill_strategy="user_prompt",
            suggested_prompt="Could you share some emails?",
        ),
    ]

    insert_chain = _build_chain([{"id": "entry-1"}])
    mock_db.table.return_value = insert_chain

    await detector._create_prospective_entries("user-123", gaps)

    # Should insert twice (once per gap)
    assert insert_chain.insert.call_count == 2

    # Check first insert payload
    first_call = insert_chain.insert.call_args_list[0][0][0]
    assert first_call["user_id"] == "user-123"
    assert first_call["status"] == "pending"
    assert first_call["metadata"]["type"] == "knowledge_gap"
    assert first_call["metadata"]["domain"] == "corporate_memory"
    assert first_call["metadata"]["subdomain"] == "leadership"
    assert first_call["metadata"]["priority"] == "high"
    assert first_call["metadata"]["fill_strategy"] == "agent_research"
    assert first_call["metadata"]["suggested_agent"] == "analyst"


@pytest.mark.asyncio()
async def test_prospective_entry_contains_suggested_prompt(
    detector: KnowledgeGapDetector,
    mock_db: MagicMock,
) -> None:
    """Prospective entry preserves suggested_prompt for user-facing gaps."""
    gaps = [
        KnowledgeGap(
            domain="digital_twin",
            subdomain="writing_style",
            description="Writing style missing",
            priority="high",
            fill_strategy="user_prompt",
            suggested_prompt="Could you share some recent emails?",
        ),
    ]

    insert_chain = _build_chain([{"id": "entry-1"}])
    mock_db.table.return_value = insert_chain

    await detector._create_prospective_entries("user-123", gaps)

    payload = insert_chain.insert.call_args_list[0][0][0]
    assert payload["metadata"]["suggested_prompt"] == "Could you share some recent emails?"


@pytest.mark.asyncio()
async def test_prospective_entry_creation_failure_does_not_raise(
    detector: KnowledgeGapDetector,
    mock_db: MagicMock,
) -> None:
    """Failed prospective entry creation logs warning but doesn't raise."""
    gaps = [
        KnowledgeGap(
            domain="test",
            subdomain="test",
            description="test",
            priority="low",
            fill_strategy="user_prompt",
        ),
    ]

    chain = MagicMock()
    chain.table.return_value = chain
    chain.insert.side_effect = Exception("DB error")
    mock_db.table.return_value = chain

    # Should not raise
    await detector._create_prospective_entries("user-123", gaps)


# --- Gap report storage ---


@pytest.mark.asyncio()
async def test_gap_report_stored_in_onboarding_metadata(
    detector: KnowledgeGapDetector,
    mock_db: MagicMock,
) -> None:
    """Gap report is stored in onboarding_state metadata."""
    result = GapAnalysisResult(
        gaps=[],
        total_gaps=5,
        critical_gaps=1,
        domains_analyzed=4,
        completeness_by_domain={
            "corporate_memory": 70.0,
            "digital_twin": 85.0,
            "competitive_intel": 55.0,
            "integrations": 100.0,
        },
    )

    update_chain = _build_chain([{"id": "state-1"}])
    mock_db.table.return_value = update_chain

    await detector._store_gap_report("user-123", result)

    update_chain.update.assert_called_once()
    call_args = update_chain.update.call_args[0][0]
    gap_data = call_args["metadata"]["gap_analysis"]
    assert gap_data["total_gaps"] == 5
    assert gap_data["critical_gaps"] == 1
    assert gap_data["completeness"]["corporate_memory"] == 70.0


# --- Full detect_gaps integration ---


@pytest.mark.asyncio()
async def test_detect_gaps_returns_all_domains(
    detector: KnowledgeGapDetector,
    mock_db: MagicMock,
) -> None:
    """Full detect_gaps analyzes all 4 domains and returns results."""
    # Mock all data fetchers to return empty/minimal data
    semantic_chain = _build_chain([])  # no facts
    settings_chain = _build_chain(None)  # no settings
    integrations_chain = _build_chain([])  # no integrations
    onboarding_chain = _build_chain(None)  # no onboarding state
    profile_chain = _build_chain(None)  # no profile

    # For prospective entries (multiple inserts)
    insert_chain = _build_chain([{"id": "entry"}])
    # For gap report storage
    update_chain = _build_chain([{"id": "state"}])

    # Table calls in order: semantic, settings, integrations, onboarding, profiles,
    # then N inserts for prospective entries, then update for gap report
    mock_db.table.return_value = _build_chain([])
    mock_db.table.side_effect = None

    # Patch individual data fetchers for cleaner control
    with (
        patch.object(detector, "_get_semantic_facts", new_callable=AsyncMock, return_value=[]),
        patch.object(detector, "_get_user_settings", new_callable=AsyncMock, return_value=None),
        patch.object(detector, "_get_integrations", new_callable=AsyncMock, return_value=[]),
        patch.object(detector, "_get_onboarding_state", new_callable=AsyncMock, return_value=None),
        patch.object(
            detector, "_get_company_classification", new_callable=AsyncMock, return_value=None
        ),
        patch.object(detector, "_create_prospective_entries", new_callable=AsyncMock),
        patch.object(detector, "_store_gap_report", new_callable=AsyncMock),
        patch("src.onboarding.gap_detector.EpisodicMemory") as mock_episodic_cls,
    ):
        mock_episodic = MagicMock()
        mock_episodic.store_episode = AsyncMock(return_value="ep-1")
        mock_episodic_cls.return_value = mock_episodic

        result = await detector.detect_gaps("user-123")

    assert isinstance(result, GapAnalysisResult)
    assert result.domains_analyzed == 4
    assert result.total_gaps > 0
    assert "corporate_memory" in result.completeness_by_domain
    assert "digital_twin" in result.completeness_by_domain
    assert "competitive_intel" in result.completeness_by_domain
    assert "integrations" in result.completeness_by_domain


@pytest.mark.asyncio()
async def test_detect_gaps_creates_prospective_entries(
    detector: KnowledgeGapDetector,
    mock_db: MagicMock,
) -> None:
    """detect_gaps calls _create_prospective_entries with all gaps."""
    with (
        patch.object(detector, "_get_semantic_facts", new_callable=AsyncMock, return_value=[]),
        patch.object(detector, "_get_user_settings", new_callable=AsyncMock, return_value=None),
        patch.object(detector, "_get_integrations", new_callable=AsyncMock, return_value=[]),
        patch.object(detector, "_get_onboarding_state", new_callable=AsyncMock, return_value=None),
        patch.object(
            detector, "_get_company_classification", new_callable=AsyncMock, return_value=None
        ),
        patch.object(
            detector, "_create_prospective_entries", new_callable=AsyncMock
        ) as mock_create,
        patch.object(detector, "_store_gap_report", new_callable=AsyncMock),
        patch("src.onboarding.gap_detector.EpisodicMemory") as mock_episodic_cls,
    ):
        mock_episodic = MagicMock()
        mock_episodic.store_episode = AsyncMock(return_value="ep-1")
        mock_episodic_cls.return_value = mock_episodic

        result = await detector.detect_gaps("user-123")

    mock_create.assert_called_once_with("user-123", result.gaps)


@pytest.mark.asyncio()
async def test_detect_gaps_stores_gap_report(
    detector: KnowledgeGapDetector,
    mock_db: MagicMock,
) -> None:
    """detect_gaps stores gap report in onboarding metadata."""
    with (
        patch.object(detector, "_get_semantic_facts", new_callable=AsyncMock, return_value=[]),
        patch.object(detector, "_get_user_settings", new_callable=AsyncMock, return_value=None),
        patch.object(detector, "_get_integrations", new_callable=AsyncMock, return_value=[]),
        patch.object(detector, "_get_onboarding_state", new_callable=AsyncMock, return_value=None),
        patch.object(
            detector, "_get_company_classification", new_callable=AsyncMock, return_value=None
        ),
        patch.object(detector, "_create_prospective_entries", new_callable=AsyncMock),
        patch.object(detector, "_store_gap_report", new_callable=AsyncMock) as mock_store,
        patch("src.onboarding.gap_detector.EpisodicMemory") as mock_episodic_cls,
    ):
        mock_episodic = MagicMock()
        mock_episodic.store_episode = AsyncMock(return_value="ep-1")
        mock_episodic_cls.return_value = mock_episodic

        result = await detector.detect_gaps("user-123")

    mock_store.assert_called_once_with("user-123", result)


@pytest.mark.asyncio()
async def test_detect_gaps_records_episodic_event(
    detector: KnowledgeGapDetector,
    mock_db: MagicMock,
) -> None:
    """detect_gaps records the analysis in episodic memory."""
    with (
        patch.object(detector, "_get_semantic_facts", new_callable=AsyncMock, return_value=[]),
        patch.object(detector, "_get_user_settings", new_callable=AsyncMock, return_value=None),
        patch.object(detector, "_get_integrations", new_callable=AsyncMock, return_value=[]),
        patch.object(detector, "_get_onboarding_state", new_callable=AsyncMock, return_value=None),
        patch.object(
            detector, "_get_company_classification", new_callable=AsyncMock, return_value=None
        ),
        patch.object(detector, "_create_prospective_entries", new_callable=AsyncMock),
        patch.object(detector, "_store_gap_report", new_callable=AsyncMock),
        patch("src.onboarding.gap_detector.EpisodicMemory") as mock_episodic_cls,
    ):
        mock_episodic = MagicMock()
        mock_episodic.store_episode = AsyncMock(return_value="ep-1")
        mock_episodic_cls.return_value = mock_episodic

        await detector.detect_gaps("user-123")

    mock_episodic.store_episode.assert_called_once()
    episode_arg = mock_episodic.store_episode.call_args[0][0]
    assert episode_arg.user_id == "user-123"
    assert episode_arg.event_type == "knowledge_gap_analysis"


@pytest.mark.asyncio()
async def test_detect_gaps_episodic_failure_does_not_raise(
    detector: KnowledgeGapDetector,
    mock_db: MagicMock,
) -> None:
    """Episodic memory failure is logged but does not fail gap detection."""
    with (
        patch.object(detector, "_get_semantic_facts", new_callable=AsyncMock, return_value=[]),
        patch.object(detector, "_get_user_settings", new_callable=AsyncMock, return_value=None),
        patch.object(detector, "_get_integrations", new_callable=AsyncMock, return_value=[]),
        patch.object(detector, "_get_onboarding_state", new_callable=AsyncMock, return_value=None),
        patch.object(
            detector, "_get_company_classification", new_callable=AsyncMock, return_value=None
        ),
        patch.object(detector, "_create_prospective_entries", new_callable=AsyncMock),
        patch.object(detector, "_store_gap_report", new_callable=AsyncMock),
        patch("src.onboarding.gap_detector.EpisodicMemory") as mock_episodic_cls,
    ):
        mock_episodic = MagicMock()
        mock_episodic.store_episode = AsyncMock(side_effect=Exception("Graphiti down"))
        mock_episodic_cls.return_value = mock_episodic

        # Should not raise
        result = await detector.detect_gaps("user-123")

    assert result.domains_analyzed == 4


@pytest.mark.asyncio()
async def test_detect_gaps_critical_gap_count(
    detector: KnowledgeGapDetector,
    mock_db: MagicMock,
) -> None:
    """critical_gaps count only includes gaps with priority 'critical'."""
    with (
        patch.object(detector, "_get_semantic_facts", new_callable=AsyncMock, return_value=[]),
        patch.object(detector, "_get_user_settings", new_callable=AsyncMock, return_value=None),
        patch.object(detector, "_get_integrations", new_callable=AsyncMock, return_value=[]),
        patch.object(detector, "_get_onboarding_state", new_callable=AsyncMock, return_value=None),
        patch.object(
            detector, "_get_company_classification", new_callable=AsyncMock, return_value=None
        ),
        patch.object(detector, "_create_prospective_entries", new_callable=AsyncMock),
        patch.object(detector, "_store_gap_report", new_callable=AsyncMock),
        patch("src.onboarding.gap_detector.EpisodicMemory") as mock_episodic_cls,
    ):
        mock_episodic = MagicMock()
        mock_episodic.store_episode = AsyncMock(return_value="ep-1")
        mock_episodic_cls.return_value = mock_episodic

        result = await detector.detect_gaps("user-123")

    # None of the built-in gaps are "critical" — they're high/medium/low
    assert result.critical_gaps == 0
    assert result.total_gaps > 0


# --- Data fetcher tests ---


@pytest.mark.asyncio()
async def test_get_semantic_facts_queries_correct_table(
    detector: KnowledgeGapDetector,
    mock_db: MagicMock,
) -> None:
    """_get_semantic_facts queries memory_semantic filtered by user_id."""
    chain = _build_chain(
        [
            {"fact": "test", "confidence": 0.9, "source": "web", "metadata": {}},
        ]
    )
    mock_db.table.return_value = chain

    facts = await detector._get_semantic_facts("user-123")

    mock_db.table.assert_called_with("memory_semantic")
    chain.eq.assert_called_with("user_id", "user-123")
    assert len(facts) == 1


@pytest.mark.asyncio()
async def test_get_integrations_queries_correct_table(
    detector: KnowledgeGapDetector,
    mock_db: MagicMock,
) -> None:
    """_get_integrations queries user_integrations filtered by user_id."""
    chain = _build_chain(
        [
            {"integration_type": "salesforce", "created_at": "2026-01-01"},
        ]
    )
    mock_db.table.return_value = chain

    integrations = await detector._get_integrations("user-123")

    mock_db.table.assert_called_with("user_integrations")
    assert len(integrations) == 1


# --- KnowledgeGap model ---


def test_knowledge_gap_model_defaults() -> None:
    """KnowledgeGap has correct defaults."""
    gap = KnowledgeGap(
        domain="test",
        subdomain="sub",
        description="desc",
        priority="high",
        fill_strategy="user_prompt",
    )
    assert gap.suggested_agent is None
    assert gap.suggested_prompt is None
    assert gap.estimated_effort == "low"


def test_gap_analysis_result_defaults() -> None:
    """GapAnalysisResult has correct defaults."""
    result = GapAnalysisResult()
    assert result.gaps == []
    assert result.total_gaps == 0
    assert result.critical_gaps == 0
    assert result.domains_analyzed == 0
    assert result.completeness_by_domain == {}
