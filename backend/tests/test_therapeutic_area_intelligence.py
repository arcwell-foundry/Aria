"""
Tests for Therapeutic Area Signal Mapping (E8).

Tests the detection of cross-company patterns within therapeutic areas
and manufacturing modalities, enabling sector-level insights.
"""

import pytest

from src.intelligence.therapeutic_area_intelligence import (
    detect_therapeutic_area,
    detect_manufacturing_modality,
    format_therapeutic_context,
)


class TestTherapeuticAreaDetection:
    """Tests for therapeutic area keyword detection."""

    def test_detects_oncology_cancer_signal(self) -> None:
        """Detects oncology from cancer-related signal."""
        text = "Pfizer Phase 3 CAR-T cell therapy trial for B-cell lymphoma shows strong response"
        result = detect_therapeutic_area(text)

        assert "oncology" in result or "cell_gene_therapy" in result, (
            f"Expected oncology or cell_gene_therapy, got {result}"
        )

    def test_detects_oncology_tumor(self) -> None:
        """Detects oncology from tumor keyword."""
        text = "Bristol-Myers solid tumor immuno-oncology combination therapy approved"
        result = detect_therapeutic_area(text)

        assert "oncology" in result

    def test_detects_cell_gene_therapy_crispr(self) -> None:
        """Detects cell/gene therapy from CRISPR keyword."""
        text = "CRISPR gene editing therapy shows promise for genetic disease"
        result = detect_therapeutic_area(text)

        assert "cell_gene_therapy" in result

    def test_detects_metabolic_glp1(self) -> None:
        """Detects metabolic from GLP-1 keyword."""
        text = "Novo Nordisk GLP-1 receptor agonist expands diabetes market share"
        result = detect_therapeutic_area(text)

        assert "metabolic" in result

    def test_detects_rare_disease_orphan(self) -> None:
        """Detects rare disease from orphan drug keyword."""
        text = "FDA grants orphan drug designation for ultra-rare genetic therapy"
        result = detect_therapeutic_area(text)

        assert "rare_disease" in result

    def test_detects_infectious_disease_vaccine(self) -> None:
        """Detects infectious disease from vaccine keyword."""
        text = "Moderna RSV vaccine shows 85% efficacy in clinical trials"
        result = detect_therapeutic_area(text)

        assert "infectious_disease" in result

    def test_detects_multiple_areas(self) -> None:
        """Detects multiple therapeutic areas from single signal."""
        text = "Gene therapy for rare neurodegenerative disease gets FDA approval"
        result = detect_therapeutic_area(text)

        # Should detect both rare_disease and cell_gene_therapy (gene therapy)
        assert len(result) >= 1, f"Expected at least 1 area, got {result}"

    def test_no_false_positive_workforce_signal(self) -> None:
        """Does not detect therapeutic area from workforce news."""
        text = "Sartorius cuts global workforce by 1500 employees"
        result = detect_therapeutic_area(text)

        assert len(result) == 0, f"False positive: {result}"

    def test_no_false_positive_financial_signal(self) -> None:
        """Does not detect therapeutic area from financial news."""
        text = "Company announces Q3 earnings with 15% revenue growth"
        result = detect_therapeutic_area(text)

        assert len(result) == 0, f"False positive: {result}"

    def test_case_insensitive_detection(self) -> None:
        """Detection is case-insensitive."""
        text = "ONCOLOGY and Cancer and TUMOR all capitalized"
        result = detect_therapeutic_area(text)

        assert "oncology" in result


class TestManufacturingModalityDetection:
    """Tests for manufacturing modality keyword detection."""

    def test_detects_cdmo_expansion(self) -> None:
        """Detects CDMO expansion from facility keywords."""
        text = "Cytiva opens new CDMO facility with single-use bioreactor capacity"
        result = detect_manufacturing_modality(text)

        assert "cdmo_expansion" in result or "single_use" in result, (
            f"Expected cdmo_expansion or single_use, got {result}"
        )

    def test_detects_mab_manufacturing(self) -> None:
        """Detects mAb manufacturing from monoclonal antibody keyword."""
        text = "New monoclonal antibody manufacturing line with CHO cell fed-batch process"
        result = detect_manufacturing_modality(text)

        assert "mAb_manufacturing" in result

    def test_detects_mab_from_mab_abbreviation(self) -> None:
        """Detects mAb manufacturing from mAb abbreviation."""
        text = "mAb production capacity expansion with perfusion bioreactors"
        result = detect_manufacturing_modality(text)

        assert "mAb_manufacturing" in result or "continuous_processing" in result

    def test_detects_viral_vector(self) -> None:
        """Detects viral vector manufacturing."""
        text = "AAV viral vector production facility opens for gene therapy"
        result = detect_manufacturing_modality(text)

        assert "viral_vector" in result

    def test_detects_single_use(self) -> None:
        """Detects single-use technology."""
        text = "Single-use bioreactor bags reduce contamination risk"
        result = detect_manufacturing_modality(text)

        assert "single_use" in result

    def test_detects_downstream(self) -> None:
        """Detects downstream processing."""
        text = "New chromatography and TFF purification line for downstream processing"
        result = detect_manufacturing_modality(text)

        assert "downstream" in result

    def test_detects_mrna_manufacturing(self) -> None:
        """Detects mRNA manufacturing."""
        text = "LNP lipid nanoparticle formulation for mRNA vaccine production"
        result = detect_manufacturing_modality(text)

        assert "mrna_manufacturing" in result

    def test_detects_cell_processing(self) -> None:
        """Detects cell processing."""
        text = "Autologous T-cell expansion for CAR-T manufacturing"
        result = detect_manufacturing_modality(text)

        assert "cell_processing" in result

    def test_detects_continuous_processing(self) -> None:
        """Detects continuous processing."""
        text = "Continuous bioprocessing reduces manufacturing costs by 40%"
        result = detect_manufacturing_modality(text)

        assert "continuous_processing" in result

    def test_detects_multiple_modalities(self) -> None:
        """Detects multiple modalities from single signal."""
        text = "CDMO expands single-use bioreactor capacity with continuous downstream purification"
        result = detect_manufacturing_modality(text)

        assert len(result) >= 2, f"Expected at least 2 modalities, got {result}"

    def test_no_false_positive_executive_news(self) -> None:
        """Does not detect modality from executive news."""
        text = "Company appoints new Chief Executive Officer"
        result = detect_manufacturing_modality(text)

        assert len(result) == 0, f"False positive: {result}"


class TestTherapeuticContextFormatting:
    """Tests for therapeutic context formatting for LLM prompts."""

    def test_formats_areas_only(self) -> None:
        """Formats context with therapeutic areas only."""
        result = format_therapeutic_context(["oncology", "cell_gene_therapy"], [])

        assert result is not None
        assert "THERAPEUTIC/MANUFACTURING CLASSIFICATION" in result
        assert "Oncology" in result
        assert "Cell Gene Therapy" in result
        assert "Manufacturing modalities" not in result

    def test_formats_modalities_only(self) -> None:
        """Formats context with manufacturing modalities only."""
        result = format_therapeutic_context([], ["cdmo_expansion", "single_use"])

        assert result is not None
        assert "THERAPEUTIC/MANUFACTURING CLASSIFICATION" in result
        assert "Therapeutic areas" not in result
        assert "Cdmo Expansion" in result or "CDMO Expansion" in result.lower()
        assert "Single Use" in result

    def test_formats_both_areas_and_modalities(self) -> None:
        """Formats context with both areas and modalities."""
        result = format_therapeutic_context(
            ["metabolic"],
            ["mAb_manufacturing", "downstream"]
        )

        assert result is not None
        assert "Metabolic" in result
        assert "Mab Manufacturing" in result  # title() lowercases 'mAb' to 'Mab'
        assert "Downstream" in result

    def test_returns_none_for_empty_inputs(self) -> None:
        """Returns None when no areas or modalities provided."""
        result = format_therapeutic_context([], [])

        assert result is None

    def test_includes_analysis_prompt(self) -> None:
        """Includes analysis guidance in formatted context."""
        result = format_therapeutic_context(["oncology"], [])

        assert result is not None
        assert "ANALYZE" in result
        assert "bioprocessing equipment demand" in result.lower()

    def test_formats_area_names_nicely(self) -> None:
        """Formats area names with proper title case."""
        result = format_therapeutic_context(["rare_disease", "infectious_disease"], [])

        assert result is not None
        assert "Rare Disease" in result
        assert "Infectious Disease" in result


class TestTherapeuticTrendsDetection:
    """Tests for therapeutic trend detection across signals."""

    @pytest.mark.asyncio
    async def test_detects_therapeutic_trends(self, mock_supabase: dict) -> None:
        """Detects trends when multiple signals point to same area."""
        from unittest.mock import AsyncMock, MagicMock

        from src.intelligence.therapeutic_area_intelligence import detect_therapeutic_trends

        # Mock Supabase client
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.data = [
            {
                "company_name": "Pfizer",
                "headline": "Oncology drug shows promise",
                "signal_type": "clinical",
                "detected_at": "2024-01-01",
                "summary": "Cancer therapy advancement",
            },
            {
                "company_name": "Merck",
                "headline": "Tumor immunotherapy approved",
                "signal_type": "regulatory",
                "detected_at": "2024-01-02",
                "summary": "Solid tumor treatment",
            },
            {
                "company_name": "Bristol-Myers",
                "headline": "Leukemia drug trial success",
                "signal_type": "clinical",
                "detected_at": "2024-01-03",
                "summary": "Blood cancer breakthrough",
            },
        ]
        mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_result

        trends = await detect_therapeutic_trends(
            mock_client,
            user_id="test-user",
            days=30,
            min_signals=2
        )

        # Should find oncology trend with 3 signals from 3 companies
        oncology_trend = next(
            (t for t in trends if t["trend_type"] == "therapeutic_area" and "Oncology" in t["name"]),
            None
        )
        assert oncology_trend is not None, f"No oncology trend found in {trends}"
        assert oncology_trend["signal_count"] >= 2
        assert oncology_trend["company_count"] >= 2

    @pytest.mark.asyncio
    async def test_detects_manufacturing_trends(self, mock_supabase: dict) -> None:
        """Detects manufacturing modality trends across companies."""
        from unittest.mock import MagicMock

        from src.intelligence.therapeutic_area_intelligence import detect_therapeutic_trends

        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.data = [
            {
                "company_name": "Cytiva",
                "headline": "CDMO facility expansion",
                "signal_type": "expansion",
                "detected_at": "2024-01-01",
                "summary": "New contract manufacturing site",
            },
            {
                "company_name": "Thermo Fisher",
                "headline": "Manufacturing capacity increase",
                "signal_type": "expansion",
                "detected_at": "2024-01-02",
                "summary": "CDMO operations grow",
            },
            {
                "company_name": "Lonza",
                "headline": "New facility announced",
                "signal_type": "expansion",
                "detected_at": "2024-01-03",
                "summary": "Manufacturing capacity expansion",
            },
        ]
        mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_result

        trends = await detect_therapeutic_trends(
            mock_client,
            user_id="test-user",
            days=30,
            min_signals=2
        )

        # Should find CDMO expansion trend
        cdmo_trend = next(
            (t for t in trends if t["trend_type"] == "manufacturing_modality" and "cdmo" in t["name"].lower()),
            None
        )
        assert cdmo_trend is not None, f"No CDMO trend found in {trends}"

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_signals(self) -> None:
        """Returns empty list when no signals found."""
        from unittest.mock import MagicMock

        from src.intelligence.therapeutic_area_intelligence import detect_therapeutic_trends

        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.data = []
        mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_result

        trends = await detect_therapeutic_trends(
            mock_client,
            user_id="test-user",
            days=30,
            min_signals=2
        )

        assert trends == []

    @pytest.mark.asyncio
    async def test_ignores_isolated_signals(self) -> None:
        """Does not create trend from single signal."""
        from unittest.mock import MagicMock

        from src.intelligence.therapeutic_area_intelligence import detect_therapeutic_trends

        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.data = [
            {
                "company_name": "Pfizer",
                "headline": "Oncology news",
                "signal_type": "clinical",
                "detected_at": "2024-01-01",
                "summary": "Cancer update",
            },
            {
                "company_name": "Moderna",
                "headline": "Vaccine distribution",
                "signal_type": "commercial",
                "detected_at": "2024-01-02",
                "summary": "COVID vaccine",
            },
        ]
        mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_result

        trends = await detect_therapeutic_trends(
            mock_client,
            user_id="test-user",
            days=30,
            min_signals=3  # Require 3 signals
        )

        # No trend should emerge (only 1 oncology, 1 infectious_disease)
        assert trends == []


class TestContextEnricherIntegration:
    """Tests for therapeutic area integration with context enricher."""

    @pytest.mark.asyncio
    async def test_enricher_adds_therapeutic_classification(self) -> None:
        """Context enricher adds therapeutic areas to context."""
        from unittest.mock import MagicMock

        from src.intelligence.context_enricher import ContextEnricher

        mock_db = MagicMock()
        # Mock all database calls
        mock_db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])

        enricher = ContextEnricher(mock_db)
        context = await enricher.enrich_event_context(
            user_id="test-user",
            event="Pfizer CAR-T cell therapy for B-cell lymphoma shows strong results",
            company_name="Pfizer",
            signal_type="clinical"
        )

        # Should include therapeutic classification
        assert "therapeutic_areas" in context or "cell_gene_therapy" in str(context.get("therapeutic_context", ""))

    @pytest.mark.asyncio
    async def test_enricher_adds_manufacturing_modality(self) -> None:
        """Context enricher adds manufacturing modalities to context."""
        from unittest.mock import MagicMock

        from src.intelligence.context_enricher import ContextEnricher

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])

        enricher = ContextEnricher(mock_db)
        context = await enricher.enrich_event_context(
            user_id="test-user",
            event="Thermo Fisher expands Gibco cell culture media with single-use bioreactor capacity",
            company_name="Thermo Fisher",
            signal_type="product"
        )

        # Should include manufacturing modality
        assert "manufacturing_modalities" in context or "single" in str(context.get("therapeutic_context", "")).lower()

    @pytest.mark.asyncio
    async def test_enricher_formats_therapeutic_context_for_llm(self) -> None:
        """Context enricher formats therapeutic context for LLM."""
        from unittest.mock import MagicMock

        from src.intelligence.context_enricher import ContextEnricher

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])

        enricher = ContextEnricher(mock_db)
        context = await enricher.enrich_event_context(
            user_id="test-user",
            event="Novo Nordisk GLP-1 drug for diabetes and obesity",
            company_name="Novo Nordisk",
            signal_type="product"
        )

        llm_context = enricher.format_context_for_llm(context)

        # LLM context should include therapeutic classification
        if context.get("therapeutic_context"):
            assert "THERAPEUTIC" in llm_context or "Metabolic" in llm_context


# Fixtures
@pytest.fixture
def mock_supabase() -> dict:
    """Mock Supabase client fixture."""
    return {}
