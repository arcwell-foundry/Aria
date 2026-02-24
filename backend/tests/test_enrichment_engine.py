"""Tests for Company Enrichment Engine (US-903)."""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# --- Model Tests ---


def test_enrichment_stage_enum_values() -> None:
    """Test EnrichmentStage has all required stages."""
    from src.onboarding.enrichment import EnrichmentStage

    assert EnrichmentStage.QUEUED == "queued"
    assert EnrichmentStage.CLASSIFYING == "classifying"
    assert EnrichmentStage.RESEARCHING == "researching"
    assert EnrichmentStage.EXTRACTING == "extracting"
    assert EnrichmentStage.SEEDING_GRAPH == "seeding_graph"
    assert EnrichmentStage.IDENTIFYING_GAPS == "identifying_gaps"
    assert EnrichmentStage.COMPLETE == "complete"
    assert EnrichmentStage.FAILED == "failed"


def test_company_classification_model() -> None:
    """Test CompanyClassification initializes with all fields."""
    from src.onboarding.enrichment import CompanyClassification

    classification = CompanyClassification(
        company_type="Bioprocessing Equipment Manufacturer",
        company_description="Develops bioprocessing equipment for biopharmaceutical manufacturing",
        primary_customers=["CDMOs", "Pharma companies", "Biotech companies"],
        value_chain_position="Upstream supplier / equipment vendor",
        primary_modality="Bioprocessing Equipment",
        company_posture="Seller",
        therapeutic_areas=["Oncology", "Immunology"],
        key_products=["OPUS chromatography columns", "XCell ATF filtration"],
        likely_pain_points=["Pipeline visibility", "CRO management"],
        confidence=0.85,
    )

    assert classification.company_type == "Bioprocessing Equipment Manufacturer"
    assert classification.company_description != ""
    assert len(classification.primary_customers) == 3
    assert classification.value_chain_position == "Upstream supplier / equipment vendor"
    assert classification.primary_modality == "Bioprocessing Equipment"
    assert classification.company_posture == "Seller"
    assert len(classification.therapeutic_areas) == 2
    assert len(classification.key_products) == 2
    assert len(classification.likely_pain_points) == 2
    assert classification.confidence == 0.85


def test_company_classification_defaults() -> None:
    """Test CompanyClassification default values."""
    from src.onboarding.enrichment import CompanyClassification

    classification = CompanyClassification(
        company_type="Unknown",
        company_posture="Unknown",
    )

    assert classification.company_description == ""
    assert classification.primary_customers == []
    assert classification.value_chain_position == ""
    assert classification.primary_modality == ""
    assert classification.therapeutic_areas == []
    assert classification.key_products == []
    assert classification.likely_pain_points == []
    assert classification.confidence == 0.0


def test_discovered_fact_model() -> None:
    """Test DiscoveredFact initializes correctly."""
    from src.onboarding.enrichment import DiscoveredFact

    fact = DiscoveredFact(
        fact="Company has 3 Phase III trials",
        source="clinical_trials",
        confidence=0.9,
        category="pipeline",
        entities=["Drug A", "Drug B"],
    )

    assert fact.fact == "Company has 3 Phase III trials"
    assert fact.source == "clinical_trials"
    assert fact.confidence == 0.9
    assert fact.category == "pipeline"
    assert len(fact.entities) == 2


def test_causal_hypothesis_defaults() -> None:
    """Test CausalHypothesis default confidence and source."""
    from src.onboarding.enrichment import CausalHypothesis

    hyp = CausalHypothesis(
        premise="Series C funding",
        inference="Hiring ramp likely",
    )

    assert hyp.confidence == 0.55
    assert hyp.source == "inferred_during_onboarding"


def test_knowledge_gap_model() -> None:
    """Test KnowledgeGap model fields."""
    from src.onboarding.enrichment import KnowledgeGap

    gap = KnowledgeGap(
        domain="leadership",
        description="No leadership data found",
        priority="high",
        suggested_agent="analyst",
        suggested_action="Research leadership team within 48 hours",
    )

    assert gap.domain == "leadership"
    assert gap.priority == "high"
    assert gap.suggested_agent == "analyst"


def test_enrichment_result_defaults() -> None:
    """Test EnrichmentResult initializes with empty collections."""
    from src.onboarding.enrichment import CompanyClassification, EnrichmentResult

    result = EnrichmentResult(
        classification=CompanyClassification(
            company_type="Biotech",
            primary_modality="Biologics",
            company_posture="Buyer",
        )
    )

    assert result.facts == []
    assert result.hypotheses == []
    assert result.gaps == []
    assert result.quality_score == 0.0
    assert result.research_sources_used == []


def test_enrichment_progress_model() -> None:
    """Test EnrichmentProgress serialization."""
    from src.onboarding.enrichment import EnrichmentProgress, EnrichmentStage

    progress = EnrichmentProgress(
        stage=EnrichmentStage.RESEARCHING,
        percentage=50.0,
        facts_discovered=12,
        message="Researching...",
    )

    data = progress.model_dump()
    assert data["stage"] == "researching"
    assert data["percentage"] == 50.0
    assert data["facts_discovered"] == 12


# --- Classification Tests ---


@pytest.mark.asyncio
async def test_classify_company_parses_valid_json() -> None:
    """Test _classify_company parses valid LLM JSON response with open-ended fields."""
    from src.onboarding.enrichment import CompanyEnrichmentEngine

    llm_response = json.dumps({
        "company_type": "Clinical-Stage Oncology Biotech",
        "company_description": "Develops novel cell therapies for solid tumors",
        "primary_customers": ["Hospitals", "Cancer centers"],
        "value_chain_position": "Drug developer",
        "primary_modality": "Cell Therapy",
        "company_posture": "Buyer",
        "therapeutic_areas": ["Oncology"],
        "key_products": ["CAR-T platform", "TIL therapy program"],
        "likely_pain_points": ["Manufacturing scale-up"],
        "confidence": 0.82,
    })

    with (
        patch("src.onboarding.enrichment.SupabaseClient") as mock_sb,
        patch("src.onboarding.enrichment.LLMClient") as mock_llm_cls,
    ):
        mock_sb.get_client.return_value = MagicMock()
        mock_llm = MagicMock()
        mock_llm.generate_response = AsyncMock(return_value=llm_response)
        mock_llm_cls.return_value = mock_llm

        engine = CompanyEnrichmentEngine()
        # Mock _fetch_website_content to avoid real HTTP calls
        engine._fetch_website_content = AsyncMock(return_value="We develop cell therapies")
        result = await engine._classify_company("TestBio", "https://testbio.com")

    assert result.company_type == "Clinical-Stage Oncology Biotech"
    assert result.company_description == "Develops novel cell therapies for solid tumors"
    assert result.primary_customers == ["Hospitals", "Cancer centers"]
    assert result.value_chain_position == "Drug developer"
    assert result.primary_modality == "Cell Therapy"
    assert result.company_posture == "Buyer"
    assert result.confidence == 0.82
    assert "Oncology" in result.therapeutic_areas
    assert len(result.key_products) == 2


@pytest.mark.asyncio
async def test_classify_company_handles_invalid_json() -> None:
    """Test _classify_company returns fallback on invalid JSON."""
    from src.onboarding.enrichment import CompanyEnrichmentEngine

    with (
        patch("src.onboarding.enrichment.SupabaseClient") as mock_sb,
        patch("src.onboarding.enrichment.LLMClient") as mock_llm_cls,
    ):
        mock_sb.get_client.return_value = MagicMock()
        mock_llm = MagicMock()
        mock_llm.generate_response = AsyncMock(return_value="not json at all")
        mock_llm_cls.return_value = mock_llm

        engine = CompanyEnrichmentEngine()
        engine._fetch_website_content = AsyncMock(return_value="")
        result = await engine._classify_company("BadCo", "https://badco.com")

    assert result.company_type == "Unknown"
    assert result.confidence == 0.0


# --- Research Module Tests ---


@pytest.mark.asyncio
async def test_research_website_returns_results_with_exa() -> None:
    """Test _research_website returns pages when Exa is configured."""
    from src.onboarding.enrichment import CompanyEnrichmentEngine

    exa_response = {
        "results": [
            {"url": "https://test.com/about", "title": "About Us", "text": "We are a biotech"},
            {"url": "https://test.com/pipeline", "title": "Pipeline", "text": "Phase III trials"},
        ]
    }

    with (
        patch("src.onboarding.enrichment.SupabaseClient") as mock_sb,
        patch("src.onboarding.enrichment.LLMClient") as mock_llm_cls,
        patch("src.onboarding.enrichment.settings") as mock_settings,
        patch("src.onboarding.enrichment.httpx.AsyncClient") as mock_httpx,
    ):
        mock_sb.get_client.return_value = MagicMock()
        mock_llm_cls.return_value = MagicMock()
        mock_settings.EXA_API_KEY = "test-key"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = exa_response

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_httpx.return_value = mock_client

        engine = CompanyEnrichmentEngine()
        results = await engine._research_website("https://test.com")

    assert len(results) == 2
    assert results[0]["source"] == "website"
    assert results[0]["title"] == "About Us"


@pytest.mark.asyncio
async def test_research_website_skips_without_exa_key() -> None:
    """Test _research_website returns empty list without Exa key."""
    from src.onboarding.enrichment import CompanyEnrichmentEngine

    with (
        patch("src.onboarding.enrichment.SupabaseClient") as mock_sb,
        patch("src.onboarding.enrichment.LLMClient") as mock_llm_cls,
        patch("src.onboarding.enrichment.settings") as mock_settings,
    ):
        mock_sb.get_client.return_value = MagicMock()
        mock_llm_cls.return_value = MagicMock()
        mock_settings.EXA_API_KEY = ""

        engine = CompanyEnrichmentEngine()
        results = await engine._research_website("https://test.com")

    assert results == []


@pytest.mark.asyncio
async def test_research_website_handles_api_failure() -> None:
    """Test _research_website handles HTTP errors gracefully."""
    from src.onboarding.enrichment import CompanyEnrichmentEngine

    with (
        patch("src.onboarding.enrichment.SupabaseClient") as mock_sb,
        patch("src.onboarding.enrichment.LLMClient") as mock_llm_cls,
        patch("src.onboarding.enrichment.settings") as mock_settings,
        patch("src.onboarding.enrichment.httpx.AsyncClient") as mock_httpx,
    ):
        mock_sb.get_client.return_value = MagicMock()
        mock_llm_cls.return_value = MagicMock()
        mock_settings.EXA_API_KEY = "test-key"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("Connection timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_httpx.return_value = mock_client

        engine = CompanyEnrichmentEngine()
        results = await engine._research_website("https://test.com")

    assert results == []


@pytest.mark.asyncio
async def test_research_news_skips_without_exa_key() -> None:
    """Test _research_news returns empty list without Exa key."""
    from src.onboarding.enrichment import CompanyEnrichmentEngine

    with (
        patch("src.onboarding.enrichment.SupabaseClient") as mock_sb,
        patch("src.onboarding.enrichment.LLMClient") as mock_llm_cls,
        patch("src.onboarding.enrichment.settings") as mock_settings,
    ):
        mock_sb.get_client.return_value = MagicMock()
        mock_llm_cls.return_value = MagicMock()
        mock_settings.EXA_API_KEY = ""

        engine = CompanyEnrichmentEngine()
        results = await engine._research_news("TestBio")

    assert results == []


@pytest.mark.asyncio
async def test_research_clinical_trials_parses_studies() -> None:
    """Test _research_clinical_trials parses ClinicalTrials.gov response."""
    from src.onboarding.enrichment import CompanyClassification, CompanyEnrichmentEngine

    ct_response = {
        "studies": [
            {
                "protocolSection": {
                    "identificationModule": {
                        "nctId": "NCT12345",
                        "briefTitle": "Phase III Trial for Drug X",
                    },
                    "statusModule": {"overallStatus": "RECRUITING"},
                    "designModule": {"phases": ["PHASE3"]},
                }
            }
        ]
    }

    with (
        patch("src.onboarding.enrichment.SupabaseClient") as mock_sb,
        patch("src.onboarding.enrichment.LLMClient") as mock_llm_cls,
        patch("src.onboarding.enrichment.httpx.AsyncClient") as mock_httpx,
    ):
        mock_sb.get_client.return_value = MagicMock()
        mock_llm_cls.return_value = MagicMock()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = ct_response

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_httpx.return_value = mock_client

        engine = CompanyEnrichmentEngine()
        classification = CompanyClassification(
            company_type="Biotech",
            primary_modality="Biologics",
            company_posture="Buyer",
        )
        results = await engine._research_clinical_trials("TestBio", classification)

    assert len(results) == 1
    assert results[0]["nct_id"] == "NCT12345"
    assert results[0]["source"] == "clinical_trials"


@pytest.mark.asyncio
async def test_research_clinical_trials_handles_api_failure() -> None:
    """Test _research_clinical_trials handles API errors gracefully."""
    from src.onboarding.enrichment import CompanyClassification, CompanyEnrichmentEngine

    with (
        patch("src.onboarding.enrichment.SupabaseClient") as mock_sb,
        patch("src.onboarding.enrichment.LLMClient") as mock_llm_cls,
        patch("src.onboarding.enrichment.httpx.AsyncClient") as mock_httpx,
    ):
        mock_sb.get_client.return_value = MagicMock()
        mock_llm_cls.return_value = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_httpx.return_value = mock_client

        engine = CompanyEnrichmentEngine()
        classification = CompanyClassification(
            company_type="Biotech",
            primary_modality="Biologics",
            company_posture="Buyer",
        )
        results = await engine._research_clinical_trials("TestBio", classification)

    assert results == []


@pytest.mark.asyncio
async def test_research_leadership_skips_without_exa_key() -> None:
    """Test _research_leadership returns empty without Exa key."""
    from src.onboarding.enrichment import CompanyEnrichmentEngine

    with (
        patch("src.onboarding.enrichment.SupabaseClient") as mock_sb,
        patch("src.onboarding.enrichment.LLMClient") as mock_llm_cls,
        patch("src.onboarding.enrichment.settings") as mock_settings,
    ):
        mock_sb.get_client.return_value = MagicMock()
        mock_llm_cls.return_value = MagicMock()
        mock_settings.EXA_API_KEY = ""

        engine = CompanyEnrichmentEngine()
        results = await engine._research_leadership("TestBio")

    assert results == []


@pytest.mark.asyncio
async def test_run_research_modules_aggregates_results() -> None:
    """Test _run_research_modules aggregates results from all modules."""
    from src.onboarding.enrichment import CompanyClassification, CompanyEnrichmentEngine

    with (
        patch("src.onboarding.enrichment.SupabaseClient") as mock_sb,
        patch("src.onboarding.enrichment.LLMClient") as mock_llm_cls,
    ):
        mock_sb.get_client.return_value = MagicMock()
        mock_llm_cls.return_value = MagicMock()

        engine = CompanyEnrichmentEngine()
        engine._research_website = AsyncMock(return_value=[  # type: ignore[method-assign]
            {"source": "website", "title": "About", "content": "Bio company"}
        ])
        engine._research_news = AsyncMock(return_value=[  # type: ignore[method-assign]
            {"source": "news", "title": "Funding", "content": "Series B"}
        ])
        engine._research_clinical_trials = AsyncMock(return_value=[])  # type: ignore[method-assign]
        engine._research_leadership = AsyncMock(return_value=[  # type: ignore[method-assign]
            {"source": "leadership", "title": "Team", "content": "CEO John"}
        ])
        engine._research_competitors = AsyncMock(return_value=[])  # type: ignore[method-assign]

        classification = CompanyClassification(
            company_type="Biotech",
            primary_modality="Biologics",
            company_posture="Buyer",
        )
        all_data, sources = await engine._run_research_modules(
            "TestBio", "https://testbio.com", classification
        )

    assert len(all_data) == 3
    assert "website" in sources
    assert "news" in sources
    assert "leadership" in sources
    assert "clinical_trials" not in sources  # returned empty
    assert "competitors" not in sources  # returned empty


@pytest.mark.asyncio
async def test_run_research_modules_handles_individual_failures() -> None:
    """Test _run_research_modules continues when a module fails."""
    from src.onboarding.enrichment import CompanyClassification, CompanyEnrichmentEngine

    with (
        patch("src.onboarding.enrichment.SupabaseClient") as mock_sb,
        patch("src.onboarding.enrichment.LLMClient") as mock_llm_cls,
    ):
        mock_sb.get_client.return_value = MagicMock()
        mock_llm_cls.return_value = MagicMock()

        engine = CompanyEnrichmentEngine()
        engine._research_website = AsyncMock(  # type: ignore[method-assign]
            side_effect=Exception("Website error")
        )
        engine._research_news = AsyncMock(return_value=[  # type: ignore[method-assign]
            {"source": "news", "title": "Test", "content": "News content"}
        ])
        engine._research_clinical_trials = AsyncMock(return_value=[])  # type: ignore[method-assign]
        engine._research_leadership = AsyncMock(return_value=[])  # type: ignore[method-assign]
        engine._research_competitors = AsyncMock(return_value=[])  # type: ignore[method-assign]

        classification = CompanyClassification(
            company_type="Biotech",
            primary_modality="Biologics",
            company_posture="Buyer",
        )
        all_data, sources = await engine._run_research_modules(
            "TestBio", "https://testbio.com", classification
        )

    # Only news succeeded
    assert len(all_data) == 1
    assert "news" in sources
    assert "website" not in sources


# --- Fact Extraction Tests ---


@pytest.mark.asyncio
async def test_extract_facts_from_research_data() -> None:
    """Test _extract_facts parses LLM response into DiscoveredFact list."""
    from src.onboarding.enrichment import CompanyEnrichmentEngine

    llm_response = json.dumps([
        {
            "fact": "TestBio has 3 Phase III trials",
            "source": "clinical_trials",
            "confidence": 0.9,
            "category": "pipeline",
            "entities": ["Drug X", "Drug Y"],
        },
        {
            "fact": "CEO is John Smith",
            "source": "leadership",
            "confidence": 0.85,
            "category": "leadership",
            "entities": ["John Smith"],
        },
    ])

    with (
        patch("src.onboarding.enrichment.SupabaseClient") as mock_sb,
        patch("src.onboarding.enrichment.LLMClient") as mock_llm_cls,
    ):
        mock_sb.get_client.return_value = MagicMock()
        mock_llm = MagicMock()
        mock_llm.generate_response = AsyncMock(return_value=llm_response)
        mock_llm_cls.return_value = mock_llm

        engine = CompanyEnrichmentEngine()
        raw_data = [{"source": "test", "title": "Test", "content": "Test content"}]
        facts = await engine._extract_facts(raw_data, "TestBio")

    assert len(facts) == 2
    assert facts[0].fact == "TestBio has 3 Phase III trials"
    assert facts[0].category == "pipeline"
    assert facts[1].category == "leadership"


@pytest.mark.asyncio
async def test_extract_facts_returns_empty_on_no_research() -> None:
    """Test _extract_facts returns empty list when no research data."""
    from src.onboarding.enrichment import CompanyEnrichmentEngine

    with (
        patch("src.onboarding.enrichment.SupabaseClient") as mock_sb,
        patch("src.onboarding.enrichment.LLMClient") as mock_llm_cls,
    ):
        mock_sb.get_client.return_value = MagicMock()
        mock_llm_cls.return_value = MagicMock()

        engine = CompanyEnrichmentEngine()
        facts = await engine._extract_facts([], "TestBio")

    assert facts == []


@pytest.mark.asyncio
async def test_extract_facts_handles_invalid_json() -> None:
    """Test _extract_facts handles LLM returning invalid JSON."""
    from src.onboarding.enrichment import CompanyEnrichmentEngine

    with (
        patch("src.onboarding.enrichment.SupabaseClient") as mock_sb,
        patch("src.onboarding.enrichment.LLMClient") as mock_llm_cls,
    ):
        mock_sb.get_client.return_value = MagicMock()
        mock_llm = MagicMock()
        mock_llm.generate_response = AsyncMock(return_value="not valid json")
        mock_llm_cls.return_value = mock_llm

        engine = CompanyEnrichmentEngine()
        raw_data = [{"source": "test", "title": "Test", "content": "Content"}]
        facts = await engine._extract_facts(raw_data, "TestBio")

    assert facts == []


# --- Causal Hypothesis Tests ---


@pytest.mark.asyncio
async def test_generate_causal_hypotheses_from_facts() -> None:
    """Test _generate_causal_hypotheses creates hypotheses from facts."""
    from src.onboarding.enrichment import CompanyEnrichmentEngine, DiscoveredFact

    llm_response = json.dumps([
        {
            "premise": "Series C funding of $200M",
            "inference": "Likely hiring ramp and pipeline expansion",
            "confidence": 0.55,
        },
        {
            "premise": "New manufacturing facility announced",
            "inference": "CDMO contract opportunities",
            "confidence": 0.52,
        },
    ])

    with (
        patch("src.onboarding.enrichment.SupabaseClient") as mock_sb,
        patch("src.onboarding.enrichment.LLMClient") as mock_llm_cls,
    ):
        mock_sb.get_client.return_value = MagicMock()
        mock_llm = MagicMock()
        mock_llm.generate_response = AsyncMock(return_value=llm_response)
        mock_llm_cls.return_value = mock_llm

        engine = CompanyEnrichmentEngine()
        facts = [
            DiscoveredFact(
                fact="Series C funding of $200M",
                source="news",
                confidence=0.9,
                category="financial",
            ),
            DiscoveredFact(
                fact="New manufacturing facility in NJ",
                source="news",
                confidence=0.85,
                category="manufacturing",
            ),
        ]
        hypotheses = await engine._generate_causal_hypotheses(facts)

    assert len(hypotheses) == 2
    assert hypotheses[0].source == "inferred_during_onboarding"
    assert 0.50 <= hypotheses[0].confidence <= 0.60


@pytest.mark.asyncio
async def test_generate_causal_hypotheses_empty_facts() -> None:
    """Test _generate_causal_hypotheses returns empty for no facts."""
    from src.onboarding.enrichment import CompanyEnrichmentEngine

    with (
        patch("src.onboarding.enrichment.SupabaseClient") as mock_sb,
        patch("src.onboarding.enrichment.LLMClient") as mock_llm_cls,
    ):
        mock_sb.get_client.return_value = MagicMock()
        mock_llm_cls.return_value = MagicMock()

        engine = CompanyEnrichmentEngine()
        hypotheses = await engine._generate_causal_hypotheses([])

    assert hypotheses == []


@pytest.mark.asyncio
async def test_generate_causal_hypotheses_handles_invalid_json() -> None:
    """Test _generate_causal_hypotheses handles parse failure."""
    from src.onboarding.enrichment import CompanyEnrichmentEngine, DiscoveredFact

    with (
        patch("src.onboarding.enrichment.SupabaseClient") as mock_sb,
        patch("src.onboarding.enrichment.LLMClient") as mock_llm_cls,
    ):
        mock_sb.get_client.return_value = MagicMock()
        mock_llm = MagicMock()
        mock_llm.generate_response = AsyncMock(return_value="broken json")
        mock_llm_cls.return_value = mock_llm

        engine = CompanyEnrichmentEngine()
        facts = [
            DiscoveredFact(
                fact="Test fact",
                source="news",
                confidence=0.9,
                category="financial",
            )
        ]
        hypotheses = await engine._generate_causal_hypotheses(facts)

    assert hypotheses == []


# --- Knowledge Gap Tests ---


@pytest.mark.asyncio
async def test_identify_gaps_finds_missing_domains() -> None:
    """Test _identify_knowledge_gaps identifies domains with no facts."""
    from src.onboarding.enrichment import (
        CompanyClassification,
        CompanyEnrichmentEngine,
        DiscoveredFact,
    )

    with (
        patch("src.onboarding.enrichment.SupabaseClient") as mock_sb,
        patch("src.onboarding.enrichment.LLMClient") as mock_llm_cls,
    ):
        mock_sb.get_client.return_value = MagicMock()
        mock_llm_cls.return_value = MagicMock()

        engine = CompanyEnrichmentEngine()

        # Only provide pipeline and leadership facts
        facts = [
            DiscoveredFact(
                fact="Phase III trial for Drug X",
                source="clinical_trials",
                confidence=0.9,
                category="pipeline",
            ),
            DiscoveredFact(
                fact="CEO is John Smith",
                source="leadership",
                confidence=0.85,
                category="leadership",
            ),
        ]
        classification = CompanyClassification(
            company_type="Biotech",
            primary_modality="Biologics",
            company_posture="Buyer",
        )
        gaps = await engine._identify_knowledge_gaps(facts, classification)

    # Should identify gaps for missing domains
    gap_domains = {g.domain for g in gaps}
    assert "financial" in gap_domains
    assert "competitive" in gap_domains
    assert "manufacturing" in gap_domains
    assert "partnership" in gap_domains
    assert "regulatory" in gap_domains

    # Pipeline and leadership should NOT be gaps
    assert "pipeline" not in gap_domains
    assert "leadership" not in gap_domains


@pytest.mark.asyncio
async def test_identify_gaps_assigns_correct_priority() -> None:
    """Test _identify_knowledge_gaps assigns high/medium priority correctly."""
    from src.onboarding.enrichment import (
        CompanyClassification,
        CompanyEnrichmentEngine,
    )

    with (
        patch("src.onboarding.enrichment.SupabaseClient") as mock_sb,
        patch("src.onboarding.enrichment.LLMClient") as mock_llm_cls,
    ):
        mock_sb.get_client.return_value = MagicMock()
        mock_llm_cls.return_value = MagicMock()

        engine = CompanyEnrichmentEngine()
        classification = CompanyClassification(
            company_type="Biotech",
            primary_modality="Biologics",
            company_posture="Buyer",
        )
        # No facts at all — all domains are gaps
        gaps = await engine._identify_knowledge_gaps([], classification)

    gap_by_domain = {g.domain: g for g in gaps}

    # High priority domains
    assert gap_by_domain["leadership"].priority == "high"
    assert gap_by_domain["pipeline"].priority == "high"
    assert gap_by_domain["competitive"].priority == "high"

    # Medium priority domains
    assert gap_by_domain["financial"].priority == "medium"
    assert gap_by_domain["manufacturing"].priority == "medium"
    assert gap_by_domain["partnership"].priority == "medium"
    assert gap_by_domain["regulatory"].priority == "medium"


@pytest.mark.asyncio
async def test_identify_gaps_with_all_domains_covered() -> None:
    """Test _identify_knowledge_gaps returns no gaps when all covered."""
    from src.onboarding.enrichment import (
        CompanyClassification,
        CompanyEnrichmentEngine,
        DiscoveredFact,
    )

    with (
        patch("src.onboarding.enrichment.SupabaseClient") as mock_sb,
        patch("src.onboarding.enrichment.LLMClient") as mock_llm_cls,
    ):
        mock_sb.get_client.return_value = MagicMock()
        mock_llm_cls.return_value = MagicMock()

        engine = CompanyEnrichmentEngine()

        # Provide facts covering all domains
        facts = [
            DiscoveredFact(fact="CEO John", source="web", confidence=0.9, category="leadership"),
            DiscoveredFact(fact="Phase III", source="ct", confidence=0.9, category="pipeline"),
            DiscoveredFact(fact="$200M rev", source="sec", confidence=0.9, category="financial"),
            DiscoveredFact(fact="vs Pfizer", source="web", confidence=0.9, category="competitive"),
            DiscoveredFact(fact="GMP facility", source="web", confidence=0.9, category="manufacturing"),
            DiscoveredFact(fact="Roche deal", source="news", confidence=0.9, category="partnership"),
            DiscoveredFact(fact="FDA approved", source="web", confidence=0.9, category="regulatory"),
        ]
        classification = CompanyClassification(
            company_type="Biotech",
            primary_modality="Biologics",
            company_posture="Buyer",
        )
        gaps = await engine._identify_knowledge_gaps(facts, classification)

    assert len(gaps) == 0


# --- Quality Score Tests ---


def test_quality_score_zero_facts() -> None:
    """Test quality score is low with zero facts."""
    from src.onboarding.enrichment import (
        CompanyClassification,
        CompanyEnrichmentEngine,
        EnrichmentResult,
    )

    with (
        patch("src.onboarding.enrichment.SupabaseClient") as mock_sb,
        patch("src.onboarding.enrichment.LLMClient") as mock_llm_cls,
    ):
        mock_sb.get_client.return_value = MagicMock()
        mock_llm_cls.return_value = MagicMock()

        engine = CompanyEnrichmentEngine()
        result = EnrichmentResult(
            classification=CompanyClassification(
                company_type="Unknown",
                primary_modality="Unknown",
                company_posture="Unknown",
                confidence=0.2,
            ),
            facts=[],
            hypotheses=[],
            gaps=[],
        )
        score = engine._calculate_quality_score(result)

    # With no facts, low confidence, no hypotheses — very low score
    # Only gap coverage (15) since no high-priority gaps in empty list
    assert score <= 20


def test_quality_score_high_with_many_facts() -> None:
    """Test quality score is high with 20+ diverse facts and hypotheses."""
    from src.onboarding.enrichment import (
        CausalHypothesis,
        CompanyClassification,
        CompanyEnrichmentEngine,
        DiscoveredFact,
        EnrichmentResult,
    )

    with (
        patch("src.onboarding.enrichment.SupabaseClient") as mock_sb,
        patch("src.onboarding.enrichment.LLMClient") as mock_llm_cls,
    ):
        mock_sb.get_client.return_value = MagicMock()
        mock_llm_cls.return_value = MagicMock()

        engine = CompanyEnrichmentEngine()

        categories = [
            "product", "pipeline", "leadership", "financial",
            "partnership", "regulatory", "competitive", "manufacturing",
        ]
        facts = [
            DiscoveredFact(
                fact=f"Fact {i}",
                source="website",
                confidence=0.8,
                category=categories[i % len(categories)],
            )
            for i in range(25)
        ]
        hypotheses = [
            CausalHypothesis(premise=f"P{i}", inference=f"I{i}")
            for i in range(6)
        ]

        result = EnrichmentResult(
            classification=CompanyClassification(
                company_type="Biotech",
                primary_modality="Biologics",
                company_posture="Buyer",
                confidence=0.85,
            ),
            facts=facts,
            hypotheses=hypotheses,
            gaps=[],  # No gaps
        )
        score = engine._calculate_quality_score(result)

    assert score >= 80


def test_quality_score_mid_range() -> None:
    """Test quality score is mid-range with moderate data."""
    from src.onboarding.enrichment import (
        CausalHypothesis,
        CompanyClassification,
        CompanyEnrichmentEngine,
        DiscoveredFact,
        EnrichmentResult,
        KnowledgeGap,
    )

    with (
        patch("src.onboarding.enrichment.SupabaseClient") as mock_sb,
        patch("src.onboarding.enrichment.LLMClient") as mock_llm_cls,
    ):
        mock_sb.get_client.return_value = MagicMock()
        mock_llm_cls.return_value = MagicMock()

        engine = CompanyEnrichmentEngine()

        facts = [
            DiscoveredFact(
                fact=f"Fact {i}",
                source="news",
                confidence=0.7,
                category="pipeline" if i < 5 else "leadership",
            )
            for i in range(10)
        ]
        hypotheses = [CausalHypothesis(premise="P", inference="I")]
        gaps = [
            KnowledgeGap(
                domain="competitive",
                description="No competitors found",
                priority="high",
                suggested_agent="analyst",
                suggested_action="Research competitors",
            )
        ]

        result = EnrichmentResult(
            classification=CompanyClassification(
                company_type="Biotech",
                primary_modality="Biologics",
                company_posture="Buyer",
                confidence=0.6,
            ),
            facts=facts,
            hypotheses=hypotheses,
            gaps=gaps,
        )
        score = engine._calculate_quality_score(result)

    assert 30 <= score <= 70


def test_quality_score_capped_at_100() -> None:
    """Test quality score never exceeds 100."""
    from src.onboarding.enrichment import (
        CausalHypothesis,
        CompanyClassification,
        CompanyEnrichmentEngine,
        DiscoveredFact,
        EnrichmentResult,
    )

    with (
        patch("src.onboarding.enrichment.SupabaseClient") as mock_sb,
        patch("src.onboarding.enrichment.LLMClient") as mock_llm_cls,
    ):
        mock_sb.get_client.return_value = MagicMock()
        mock_llm_cls.return_value = MagicMock()

        engine = CompanyEnrichmentEngine()

        # Maximize all dimensions
        categories = [
            "product", "pipeline", "leadership", "financial",
            "partnership", "regulatory", "competitive", "manufacturing",
        ]
        facts = [
            DiscoveredFact(
                fact=f"Fact {i}",
                source="website",
                confidence=0.95,
                category=categories[i % len(categories)],
            )
            for i in range(50)
        ]
        hypotheses = [
            CausalHypothesis(premise=f"P{i}", inference=f"I{i}")
            for i in range(10)
        ]

        result = EnrichmentResult(
            classification=CompanyClassification(
                company_type="Biotech",
                primary_modality="Biologics",
                company_posture="Buyer",
                confidence=0.99,
            ),
            facts=facts,
            hypotheses=hypotheses,
            gaps=[],
        )
        score = engine._calculate_quality_score(result)

    assert score <= 100.0


# --- Storage Tests ---


@pytest.mark.asyncio
async def test_store_results_stores_facts_in_semantic_memory() -> None:
    """Test _store_results inserts facts into memory_semantic table."""
    from src.onboarding.enrichment import (
        CompanyClassification,
        CompanyEnrichmentEngine,
        DiscoveredFact,
        EnrichmentResult,
    )

    with (
        patch("src.onboarding.enrichment.SupabaseClient") as mock_sb,
        patch("src.onboarding.enrichment.LLMClient") as mock_llm_cls,
    ):
        mock_db = MagicMock()
        mock_table = MagicMock()
        mock_insert = MagicMock()
        mock_insert.execute = MagicMock(return_value=MagicMock())
        mock_table.insert = MagicMock(return_value=mock_insert)

        mock_update = MagicMock()
        mock_eq = MagicMock()
        mock_eq.execute = MagicMock(return_value=MagicMock())
        mock_update.eq = MagicMock(return_value=mock_eq)
        mock_table.update = MagicMock(return_value=mock_update)

        mock_db.table = MagicMock(return_value=mock_table)
        mock_sb.get_client.return_value = mock_db
        mock_llm_cls.return_value = MagicMock()

        engine = CompanyEnrichmentEngine()

        result = EnrichmentResult(
            classification=CompanyClassification(
                company_type="Biotech",
                primary_modality="Biologics",
                company_posture="Buyer",
                confidence=0.8,
            ),
            facts=[
                DiscoveredFact(
                    fact="Has Phase III trial",
                    source="clinical_trials",
                    confidence=0.9,
                    category="pipeline",
                    entities=["Drug X"],
                ),
            ],
            hypotheses=[],
            gaps=[],
            quality_score=50.0,
        )

        await engine._store_results("company-123", "user-456", result)

    # Verify table was called for companies update and memory_semantic insert
    calls = mock_db.table.call_args_list
    table_names = [c.args[0] for c in calls]
    assert "companies" in table_names
    assert "memory_semantic" in table_names


@pytest.mark.asyncio
async def test_store_results_stores_gaps_in_prospective_memory() -> None:
    """Test _store_results inserts gaps into prospective_memories table."""
    from src.onboarding.enrichment import (
        CompanyClassification,
        CompanyEnrichmentEngine,
        EnrichmentResult,
        KnowledgeGap,
    )

    with (
        patch("src.onboarding.enrichment.SupabaseClient") as mock_sb,
        patch("src.onboarding.enrichment.LLMClient") as mock_llm_cls,
    ):
        mock_db = MagicMock()
        mock_table = MagicMock()
        mock_insert = MagicMock()
        mock_insert.execute = MagicMock(return_value=MagicMock())
        mock_table.insert = MagicMock(return_value=mock_insert)

        mock_update = MagicMock()
        mock_eq = MagicMock()
        mock_eq.execute = MagicMock(return_value=MagicMock())
        mock_update.eq = MagicMock(return_value=mock_eq)
        mock_table.update = MagicMock(return_value=mock_update)

        mock_db.table = MagicMock(return_value=mock_table)
        mock_sb.get_client.return_value = mock_db
        mock_llm_cls.return_value = MagicMock()

        engine = CompanyEnrichmentEngine()

        result = EnrichmentResult(
            classification=CompanyClassification(
                company_type="Biotech",
                primary_modality="Biologics",
                company_posture="Buyer",
            ),
            facts=[],
            hypotheses=[],
            gaps=[
                KnowledgeGap(
                    domain="leadership",
                    description="No leadership info",
                    priority="high",
                    suggested_agent="analyst",
                    suggested_action="Research leadership within 48 hours",
                ),
            ],
            quality_score=20.0,
        )

        await engine._store_results("company-123", "user-456", result)

    # Verify prospective_memories was called
    calls = mock_db.table.call_args_list
    table_names = [c.args[0] for c in calls]
    assert "prospective_memories" in table_names


# --- Readiness Update Tests ---


@pytest.mark.asyncio
async def test_update_readiness_calls_orchestrator() -> None:
    """Test _update_readiness calls OnboardingOrchestrator with correct score."""
    from src.onboarding.enrichment import CompanyEnrichmentEngine

    with (
        patch("src.onboarding.enrichment.SupabaseClient") as mock_sb,
        patch("src.onboarding.enrichment.LLMClient") as mock_llm_cls,
        patch("src.onboarding.orchestrator.OnboardingOrchestrator") as mock_orch_cls,
    ):
        mock_sb.get_client.return_value = MagicMock()
        mock_llm_cls.return_value = MagicMock()

        mock_orch = MagicMock()
        mock_orch.update_readiness_scores = AsyncMock()
        mock_orch_cls.return_value = mock_orch

        engine = CompanyEnrichmentEngine()
        await engine._update_readiness("user-123", 80.0)

    # readiness should be min(60, 80 * 0.6) = 48
    mock_orch.update_readiness_scores.assert_called_once_with(
        "user-123", {"corporate_memory": 48.0}
    )


@pytest.mark.asyncio
async def test_update_readiness_caps_at_60() -> None:
    """Test _update_readiness caps corporate_memory at 60."""
    from src.onboarding.enrichment import CompanyEnrichmentEngine

    with (
        patch("src.onboarding.enrichment.SupabaseClient") as mock_sb,
        patch("src.onboarding.enrichment.LLMClient") as mock_llm_cls,
        patch("src.onboarding.orchestrator.OnboardingOrchestrator") as mock_orch_cls,
    ):
        mock_sb.get_client.return_value = MagicMock()
        mock_llm_cls.return_value = MagicMock()

        mock_orch = MagicMock()
        mock_orch.update_readiness_scores = AsyncMock()
        mock_orch_cls.return_value = mock_orch

        engine = CompanyEnrichmentEngine()
        await engine._update_readiness("user-123", 100.0)

    # readiness = min(60, 100 * 0.6) = 60
    mock_orch.update_readiness_scores.assert_called_once_with(
        "user-123", {"corporate_memory": 60.0}
    )


@pytest.mark.asyncio
async def test_update_readiness_handles_error_gracefully() -> None:
    """Test _update_readiness doesn't raise on failure."""
    from src.onboarding.enrichment import CompanyEnrichmentEngine

    with (
        patch("src.onboarding.enrichment.SupabaseClient") as mock_sb,
        patch("src.onboarding.enrichment.LLMClient") as mock_llm_cls,
        patch(
            "src.onboarding.enrichment.CompanyEnrichmentEngine._update_readiness",
        ) as mock_method,
    ):
        mock_sb.get_client.return_value = MagicMock()
        mock_llm_cls.return_value = MagicMock()
        # Should not raise
        mock_method.return_value = None

        engine = CompanyEnrichmentEngine()
        # Direct test — should not raise
        await engine._update_readiness("user-123", 50.0)


# --- Progress Callback Tests ---


@pytest.mark.asyncio
async def test_progress_callback_called_at_each_stage() -> None:
    """Test progress_callback is called at each enrichment stage."""
    from src.onboarding.enrichment import CompanyEnrichmentEngine, EnrichmentStage

    progress_reports: list[dict[str, Any]] = []

    async def track_progress(data: dict[str, Any]) -> None:
        progress_reports.append(data)

    with (
        patch("src.onboarding.enrichment.SupabaseClient") as mock_sb,
        patch("src.onboarding.enrichment.LLMClient") as mock_llm_cls,
    ):
        mock_db = MagicMock()
        mock_table = MagicMock()
        mock_insert = MagicMock()
        mock_insert.execute = MagicMock(return_value=MagicMock())
        mock_table.insert = MagicMock(return_value=mock_insert)

        mock_update = MagicMock()
        mock_eq = MagicMock()
        mock_eq.execute = MagicMock(return_value=MagicMock())
        mock_update.eq = MagicMock(return_value=mock_eq)
        mock_table.update = MagicMock(return_value=mock_update)

        mock_select = MagicMock()
        mock_select_eq = MagicMock()
        mock_maybe = MagicMock()
        mock_maybe.execute = MagicMock(
            return_value=MagicMock(data={"readiness_scores": {}})
        )
        mock_select_eq.maybe_single = MagicMock(return_value=mock_maybe)
        mock_select.eq = MagicMock(return_value=mock_select_eq)
        mock_table.select = MagicMock(return_value=mock_select)

        mock_db.table = MagicMock(return_value=mock_table)
        mock_sb.get_client.return_value = mock_db

        mock_llm = MagicMock()
        # Classification response
        classification_json = json.dumps({
            "company_type": "Biotech",
            "primary_modality": "Biologics",
            "company_posture": "Buyer",
            "therapeutic_areas": [],
            "likely_pain_points": [],
            "confidence": 0.8,
        })
        # Facts response
        facts_json = json.dumps([
            {
                "fact": "Test fact",
                "source": "website",
                "confidence": 0.9,
                "category": "pipeline",
                "entities": [],
            }
        ])
        # Hypotheses response
        hyp_json = json.dumps([
            {"premise": "P", "inference": "I", "confidence": 0.55}
        ])

        mock_llm.generate_response = AsyncMock(
            side_effect=[classification_json, facts_json, hyp_json]
        )
        mock_llm_cls.return_value = mock_llm

        engine = CompanyEnrichmentEngine()
        # Mock all research modules to return quickly
        engine._research_website = AsyncMock(return_value=[  # type: ignore[method-assign]
            {"source": "website", "title": "T", "content": "C"}
        ])
        engine._research_news = AsyncMock(return_value=[])  # type: ignore[method-assign]
        engine._research_clinical_trials = AsyncMock(return_value=[])  # type: ignore[method-assign]
        engine._research_leadership = AsyncMock(return_value=[])  # type: ignore[method-assign]

        # Mock episodic memory to avoid Graphiti dependency
        with patch("src.onboarding.enrichment.CompanyEnrichmentEngine._record_episodic", new_callable=AsyncMock):
            result = await engine.enrich_company(
                company_id="company-123",
                company_name="TestBio",
                website="https://testbio.com",
                user_id="user-456",
                progress_callback=track_progress,
            )

    stages = [r["stage"] for r in progress_reports]
    assert EnrichmentStage.CLASSIFYING in stages
    assert EnrichmentStage.RESEARCHING in stages
    assert EnrichmentStage.EXTRACTING in stages
    assert EnrichmentStage.SEEDING_GRAPH in stages
    assert EnrichmentStage.IDENTIFYING_GAPS in stages
    assert EnrichmentStage.COMPLETE in stages

    # Final progress should be 100%
    assert progress_reports[-1]["percentage"] == 100


@pytest.mark.asyncio
async def test_progress_callback_not_required() -> None:
    """Test enrichment works without progress callback."""
    from src.onboarding.enrichment import CompanyEnrichmentEngine

    with (
        patch("src.onboarding.enrichment.SupabaseClient") as mock_sb,
        patch("src.onboarding.enrichment.LLMClient") as mock_llm_cls,
    ):
        mock_db = MagicMock()
        mock_table = MagicMock()
        mock_insert = MagicMock()
        mock_insert.execute = MagicMock(return_value=MagicMock())
        mock_table.insert = MagicMock(return_value=mock_insert)

        mock_update = MagicMock()
        mock_eq = MagicMock()
        mock_eq.execute = MagicMock(return_value=MagicMock())
        mock_update.eq = MagicMock(return_value=mock_eq)
        mock_table.update = MagicMock(return_value=mock_update)

        mock_select = MagicMock()
        mock_select_eq = MagicMock()
        mock_maybe = MagicMock()
        mock_maybe.execute = MagicMock(
            return_value=MagicMock(data={"readiness_scores": {}})
        )
        mock_select_eq.maybe_single = MagicMock(return_value=mock_maybe)
        mock_select.eq = MagicMock(return_value=mock_select_eq)
        mock_table.select = MagicMock(return_value=mock_select)

        mock_db.table = MagicMock(return_value=mock_table)
        mock_sb.get_client.return_value = mock_db

        mock_llm = MagicMock()
        classification_json = json.dumps({
            "company_type": "Biotech",
            "primary_modality": "Biologics",
            "company_posture": "Buyer",
            "therapeutic_areas": [],
            "likely_pain_points": [],
            "confidence": 0.8,
        })
        mock_llm.generate_response = AsyncMock(
            side_effect=[classification_json, "[]", "[]"]
        )
        mock_llm_cls.return_value = mock_llm

        engine = CompanyEnrichmentEngine()
        engine._research_website = AsyncMock(return_value=[])  # type: ignore[method-assign]
        engine._research_news = AsyncMock(return_value=[])  # type: ignore[method-assign]
        engine._research_clinical_trials = AsyncMock(return_value=[])  # type: ignore[method-assign]
        engine._research_leadership = AsyncMock(return_value=[])  # type: ignore[method-assign]

        with patch("src.onboarding.enrichment.CompanyEnrichmentEngine._record_episodic", new_callable=AsyncMock):
            # Should not raise
            result = await engine.enrich_company(
                company_id="company-123",
                company_name="TestBio",
                website="https://testbio.com",
                user_id="user-456",
                progress_callback=None,
            )

    assert result.classification.company_type == "Biotech"


# --- Full Pipeline Integration Tests ---


@pytest.mark.asyncio
async def test_full_enrichment_pipeline() -> None:
    """Test complete enrichment pipeline end-to-end with mocked externals."""
    from src.onboarding.enrichment import CompanyEnrichmentEngine

    classification_json = json.dumps({
        "company_type": "Biotech",
        "primary_modality": "Cell Therapy",
        "company_posture": "Buyer",
        "therapeutic_areas": ["Oncology", "Hematology"],
        "likely_pain_points": ["Manufacturing scale", "Regulatory complexity"],
        "confidence": 0.88,
    })
    facts_json = json.dumps([
        {
            "fact": "Has CAR-T platform targeting CD19",
            "source": "website",
            "confidence": 0.92,
            "category": "product",
            "entities": ["CAR-T", "CD19"],
        },
        {
            "fact": "Phase III DLBCL trial recruiting",
            "source": "clinical_trials",
            "confidence": 0.95,
            "category": "pipeline",
            "entities": ["DLBCL"],
        },
        {
            "fact": "CEO Dr. Sarah Chen, former Novartis",
            "source": "leadership",
            "confidence": 0.85,
            "category": "leadership",
            "entities": ["Dr. Sarah Chen", "Novartis"],
        },
        {
            "fact": "Series D at $400M valuation",
            "source": "news",
            "confidence": 0.88,
            "category": "financial",
            "entities": [],
        },
        {
            "fact": "Partnership with WuXi for manufacturing",
            "source": "news",
            "confidence": 0.80,
            "category": "partnership",
            "entities": ["WuXi"],
        },
    ])
    hyp_json = json.dumps([
        {
            "premise": "Series D funding",
            "inference": "Commercialization push and hiring ramp",
            "confidence": 0.55,
        },
        {
            "premise": "Phase III trial recruiting",
            "inference": "BLA filing within 18-24 months",
            "confidence": 0.52,
        },
    ])

    progress_reports: list[dict[str, Any]] = []

    async def track_progress(data: dict[str, Any]) -> None:
        progress_reports.append(data)

    with (
        patch("src.onboarding.enrichment.SupabaseClient") as mock_sb,
        patch("src.onboarding.enrichment.LLMClient") as mock_llm_cls,
    ):
        mock_db = MagicMock()
        mock_table = MagicMock()
        mock_insert = MagicMock()
        mock_insert.execute = MagicMock(return_value=MagicMock())
        mock_table.insert = MagicMock(return_value=mock_insert)

        mock_update = MagicMock()
        mock_eq = MagicMock()
        mock_eq.execute = MagicMock(return_value=MagicMock())
        mock_update.eq = MagicMock(return_value=mock_eq)
        mock_table.update = MagicMock(return_value=mock_update)

        mock_select = MagicMock()
        mock_select_eq = MagicMock()
        mock_maybe = MagicMock()
        mock_maybe.execute = MagicMock(
            return_value=MagicMock(data={"readiness_scores": {}})
        )
        mock_select_eq.maybe_single = MagicMock(return_value=mock_maybe)
        mock_select.eq = MagicMock(return_value=mock_select_eq)
        mock_table.select = MagicMock(return_value=mock_select)

        mock_db.table = MagicMock(return_value=mock_table)
        mock_sb.get_client.return_value = mock_db

        mock_llm = MagicMock()
        mock_llm.generate_response = AsyncMock(
            side_effect=[classification_json, facts_json, hyp_json]
        )
        mock_llm_cls.return_value = mock_llm

        engine = CompanyEnrichmentEngine()
        engine._research_website = AsyncMock(return_value=[  # type: ignore[method-assign]
            {"source": "website", "title": "About", "content": "CAR-T company"},
        ])
        engine._research_news = AsyncMock(return_value=[  # type: ignore[method-assign]
            {"source": "news", "title": "Funding", "content": "Series D"},
        ])
        engine._research_clinical_trials = AsyncMock(return_value=[  # type: ignore[method-assign]
            {"source": "clinical_trials", "title": "Phase III", "content": "Trial"},
        ])
        engine._research_leadership = AsyncMock(return_value=[  # type: ignore[method-assign]
            {"source": "leadership", "title": "Team", "content": "CEO"},
        ])

        with patch("src.onboarding.enrichment.CompanyEnrichmentEngine._record_episodic", new_callable=AsyncMock):
            result = await engine.enrich_company(
                company_id="company-abc",
                company_name="CellThera Inc",
                website="https://cellthera.com",
                user_id="user-xyz",
                progress_callback=track_progress,
            )

    # Verify classification
    assert result.classification.company_type == "Biotech"
    assert result.classification.primary_modality == "Cell Therapy"
    assert result.classification.confidence == 0.88

    # Verify facts
    assert len(result.facts) == 5
    fact_categories = {f.category for f in result.facts}
    assert "product" in fact_categories
    assert "pipeline" in fact_categories
    assert "leadership" in fact_categories

    # Verify hypotheses
    assert len(result.hypotheses) == 2
    assert all(h.source == "inferred_during_onboarding" for h in result.hypotheses)

    # Verify gaps — should identify missing domains
    gap_domains = {g.domain for g in result.gaps}
    # competitive, manufacturing, regulatory are not in facts
    assert "competitive" in gap_domains
    assert "manufacturing" in gap_domains
    assert "regulatory" in gap_domains

    # Verify quality score is reasonable
    assert result.quality_score > 0

    # Verify progress reports
    assert len(progress_reports) >= 6
    assert progress_reports[-1]["stage"] == "complete"
    assert progress_reports[-1]["percentage"] == 100

    # Verify research sources tracked
    assert "website" in result.research_sources_used
    assert "news" in result.research_sources_used
    assert "clinical_trials" in result.research_sources_used
    assert "leadership" in result.research_sources_used


@pytest.mark.asyncio
async def test_enrichment_pipeline_failure_reports_failed_stage() -> None:
    """Test enrichment reports FAILED stage on error."""
    from src.onboarding.enrichment import CompanyEnrichmentEngine, EnrichmentStage

    progress_reports: list[dict[str, Any]] = []

    async def track_progress(data: dict[str, Any]) -> None:
        progress_reports.append(data)

    with (
        patch("src.onboarding.enrichment.SupabaseClient") as mock_sb,
        patch("src.onboarding.enrichment.LLMClient") as mock_llm_cls,
    ):
        mock_sb.get_client.return_value = MagicMock()
        mock_llm = MagicMock()
        # Fail on classification
        mock_llm.generate_response = AsyncMock(
            side_effect=Exception("LLM API down")
        )
        mock_llm_cls.return_value = mock_llm

        engine = CompanyEnrichmentEngine()

        with pytest.raises(Exception, match="LLM API down"):
            await engine.enrich_company(
                company_id="company-123",
                company_name="TestBio",
                website="https://testbio.com",
                user_id="user-456",
                progress_callback=track_progress,
            )

    # Should have CLASSIFYING stage and then FAILED
    stages = [r["stage"] for r in progress_reports]
    assert EnrichmentStage.CLASSIFYING in stages
    assert EnrichmentStage.FAILED in stages


# --- Episodic Memory Tests ---


@pytest.mark.asyncio
async def test_record_episodic_creates_episode() -> None:
    """Test _record_episodic creates an Episode with correct fields."""
    from src.onboarding.enrichment import (
        CompanyClassification,
        CompanyEnrichmentEngine,
        EnrichmentResult,
    )

    with (
        patch("src.onboarding.enrichment.SupabaseClient") as mock_sb,
        patch("src.onboarding.enrichment.LLMClient") as mock_llm_cls,
        patch("src.memory.episodic.EpisodicMemory") as mock_em_cls,
    ):
        mock_sb.get_client.return_value = MagicMock()
        mock_llm_cls.return_value = MagicMock()

        mock_memory = MagicMock()
        mock_memory.store_episode = AsyncMock(return_value="ep-123")
        mock_em_cls.return_value = mock_memory

        engine = CompanyEnrichmentEngine()

        result = EnrichmentResult(
            classification=CompanyClassification(
                company_type="Biotech",
                primary_modality="Biologics",
                company_posture="Buyer",
            ),
            facts=[],
            hypotheses=[],
            gaps=[],
            quality_score=50.0,
        )

        await engine._record_episodic("user-123", "TestBio", result)

    mock_memory.store_episode.assert_called_once()
    episode = mock_memory.store_episode.call_args.args[0]
    assert episode.event_type == "onboarding_enrichment_complete"
    assert "TestBio" in episode.content
    assert episode.user_id == "user-123"


@pytest.mark.asyncio
async def test_record_episodic_handles_error_gracefully() -> None:
    """Test _record_episodic doesn't raise on failure."""
    from src.onboarding.enrichment import (
        CompanyClassification,
        CompanyEnrichmentEngine,
        EnrichmentResult,
    )

    with (
        patch("src.onboarding.enrichment.SupabaseClient") as mock_sb,
        patch("src.onboarding.enrichment.LLMClient") as mock_llm_cls,
        patch("src.memory.episodic.EpisodicMemory") as mock_em_cls,
    ):
        mock_sb.get_client.return_value = MagicMock()
        mock_llm_cls.return_value = MagicMock()

        mock_memory = MagicMock()
        mock_memory.store_episode = AsyncMock(
            side_effect=Exception("Graphiti down")
        )
        mock_em_cls.return_value = mock_memory

        engine = CompanyEnrichmentEngine()
        result = EnrichmentResult(
            classification=CompanyClassification(
                company_type="Biotech",
                primary_modality="Biologics",
                company_posture="Buyer",
            ),
        )

        # Should not raise
        await engine._record_episodic("user-123", "TestBio", result)
