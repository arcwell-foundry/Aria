"""Tests for the Memory Delta Presenter service (US-920)."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.memory.delta_presenter import (
    CorrectionRequest,
    MemoryDelta,
    MemoryDeltaPresenter,
    MemoryFact,
)

# --- Helpers ---


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
    chain.gte.return_value = chain
    chain.in_.return_value = chain
    chain.order.return_value = chain
    chain.limit.return_value = chain
    chain.maybe_single.return_value = chain
    chain.execute.return_value = _mock_execute(execute_return)
    return chain


def _make_fact_row(
    fact_id: str = "fact-1",
    fact: str = "Acme Corp specializes in biotech",
    confidence: float = 0.85,
    source: str = "enrichment_web",
    category: str = "product",
) -> dict[str, Any]:
    """Build a mock memory_semantic row."""
    return {
        "id": fact_id,
        "user_id": "user-123",
        "fact": fact,
        "confidence": confidence,
        "source": source,
        "metadata": {"category": category},
        "created_at": "2026-02-06T14:00:00+00:00",
    }


@pytest.fixture()
def mock_db() -> MagicMock:
    """Create a mock Supabase client."""
    return MagicMock()


@pytest.fixture()
def presenter(mock_db: MagicMock) -> MemoryDeltaPresenter:
    """Create a MemoryDeltaPresenter with mocked DB."""
    with patch("src.memory.delta_presenter.SupabaseClient") as mock_cls:
        mock_cls.get_client.return_value = mock_db
        return MemoryDeltaPresenter()


# --- Confidence calibration ---


class TestConfidenceCalibration:
    """Tests for confidence → language mapping."""

    def test_high_confidence_stated_as_fact(self, presenter: MemoryDeltaPresenter) -> None:
        """95%+ confidence → stated as fact (no prefix)."""
        result = presenter.calibrate_language("Your company specializes in biotech", 0.97)
        assert result == "Your company specializes in biotech"

    def test_conviction_confidence(self, presenter: MemoryDeltaPresenter) -> None:
        """80-94% confidence → 'Based on available data' prefix."""
        result = presenter.calibrate_language("You prefer direct communication", 0.85)
        assert result.startswith("Based on available data, ")
        assert "you prefer direct communication" in result

    def test_hedged_confidence(self, presenter: MemoryDeltaPresenter) -> None:
        """60-79% confidence → 'It appears that' prefix."""
        result = presenter.calibrate_language("Your team focuses on oncology", 0.65)
        assert result.startswith("It appears that ")
        assert "your team focuses on oncology" in result

    def test_uncertain_confidence(self, presenter: MemoryDeltaPresenter) -> None:
        """40-59% confidence → 'I'm not fully certain' prefix."""
        result = presenter.calibrate_language("This may be relevant", 0.45)
        assert result.startswith("I'm not fully certain, but ")
        assert "this may be relevant" in result

    def test_low_confidence_asks_confirmation(self, presenter: MemoryDeltaPresenter) -> None:
        """<40% confidence → asks for confirmation."""
        result = presenter.calibrate_language("You work with Moderna", 0.25)
        assert result.startswith("Can you confirm: ")
        assert result.endswith("?")

    def test_boundary_95_is_stated(self, presenter: MemoryDeltaPresenter) -> None:
        """Exactly 0.95 is treated as stated fact."""
        result = presenter.calibrate_language("This is a fact", 0.95)
        assert result == "This is a fact"

    def test_boundary_80_is_conviction(self, presenter: MemoryDeltaPresenter) -> None:
        """Exactly 0.80 is treated as conviction."""
        result = presenter.calibrate_language("This is likely true", 0.80)
        assert result.startswith("Based on available data, ")

    def test_boundary_60_is_hedged(self, presenter: MemoryDeltaPresenter) -> None:
        """Exactly 0.60 is treated as hedged."""
        result = presenter.calibrate_language("This seems correct", 0.60)
        assert result.startswith("It appears that ")

    def test_boundary_40_is_uncertain(self, presenter: MemoryDeltaPresenter) -> None:
        """Exactly 0.40 is treated as uncertain."""
        result = presenter.calibrate_language("This might be true", 0.40)
        assert result.startswith("I'm not fully certain, but ")

    def test_zero_confidence_asks_confirmation(self, presenter: MemoryDeltaPresenter) -> None:
        """0.0 confidence → asks for confirmation."""
        result = presenter.calibrate_language("Unknown fact", 0.0)
        assert result.startswith("Can you confirm: ")

    def test_empty_fact_returns_empty(self, presenter: MemoryDeltaPresenter) -> None:
        """Empty fact string returns empty string."""
        result = presenter.calibrate_language("", 0.95)
        assert result == ""


# --- Domain grouping ---


class TestDomainGrouping:
    """Tests for domain categorization and grouping."""

    def test_product_maps_to_corporate_memory(self, presenter: MemoryDeltaPresenter) -> None:
        """Product category maps to corporate_memory domain."""
        facts = [_make_fact_row(category="product")]
        grouped = presenter._group_by_domain(facts)
        assert "corporate_memory" in grouped

    def test_competitive_maps_to_competitive(self, presenter: MemoryDeltaPresenter) -> None:
        """Competitive category maps to competitive domain."""
        facts = [_make_fact_row(category="competitive")]
        grouped = presenter._group_by_domain(facts)
        assert "competitive" in grouped

    def test_contact_maps_to_relationship(self, presenter: MemoryDeltaPresenter) -> None:
        """Contact category maps to relationship domain."""
        facts = [_make_fact_row(category="contact")]
        grouped = presenter._group_by_domain(facts)
        assert "relationship" in grouped

    def test_writing_style_maps_to_digital_twin(self, presenter: MemoryDeltaPresenter) -> None:
        """Writing style category maps to digital_twin domain."""
        facts = [_make_fact_row(category="writing_style")]
        grouped = presenter._group_by_domain(facts)
        assert "digital_twin" in grouped

    def test_unknown_category_defaults_to_corporate_memory(
        self, presenter: MemoryDeltaPresenter
    ) -> None:
        """Unknown categories default to corporate_memory."""
        facts = [_make_fact_row(category="something_new")]
        grouped = presenter._group_by_domain(facts)
        assert "corporate_memory" in grouped

    def test_multiple_domains_grouped_separately(self, presenter: MemoryDeltaPresenter) -> None:
        """Facts from different domains are grouped separately."""
        facts = [
            _make_fact_row(fact_id="f1", category="product"),
            _make_fact_row(fact_id="f2", category="competitive"),
            _make_fact_row(fact_id="f3", category="contact"),
        ]
        grouped = presenter._group_by_domain(facts)
        assert len(grouped) == 3
        assert "corporate_memory" in grouped
        assert "competitive" in grouped
        assert "relationship" in grouped

    def test_facts_within_same_domain_grouped_together(
        self, presenter: MemoryDeltaPresenter
    ) -> None:
        """Multiple facts in same domain are in same group."""
        facts = [
            _make_fact_row(fact_id="f1", category="product"),
            _make_fact_row(fact_id="f2", category="pipeline"),
        ]
        grouped = presenter._group_by_domain(facts)
        assert len(grouped) == 1
        assert len(grouped["corporate_memory"]) == 2


# --- Delta generation ---


class TestDeltaGeneration:
    """Tests for full delta generation flow."""

    @pytest.mark.asyncio()
    async def test_generate_delta_returns_grouped_deltas(
        self,
        presenter: MemoryDeltaPresenter,
        mock_db: MagicMock,
    ) -> None:
        """generate_delta returns deltas grouped by domain."""
        facts = [
            _make_fact_row(fact_id="f1", category="product", confidence=0.9),
            _make_fact_row(fact_id="f2", category="competitive", confidence=0.7),
        ]
        query_chain = _build_chain(facts)
        mock_db.table.return_value = query_chain

        deltas = await presenter.generate_delta("user-123")

        assert len(deltas) == 2
        domains = {d.domain for d in deltas}
        assert "corporate_memory" in domains
        assert "competitive" in domains

    @pytest.mark.asyncio()
    async def test_generate_delta_caps_facts_per_domain(
        self,
        presenter: MemoryDeltaPresenter,
        mock_db: MagicMock,
    ) -> None:
        """Each domain is capped at 10 facts."""
        facts = [
            _make_fact_row(fact_id=f"f{i}", category="product", confidence=0.8) for i in range(15)
        ]
        query_chain = _build_chain(facts)
        mock_db.table.return_value = query_chain

        deltas = await presenter.generate_delta("user-123")

        assert len(deltas) == 1
        assert len(deltas[0].facts) == 10

    @pytest.mark.asyncio()
    async def test_generate_delta_empty_returns_empty_list(
        self,
        presenter: MemoryDeltaPresenter,
        mock_db: MagicMock,
    ) -> None:
        """Empty result returns empty delta list."""
        query_chain = _build_chain([])
        mock_db.table.return_value = query_chain

        deltas = await presenter.generate_delta("user-123")

        assert deltas == []

    @pytest.mark.asyncio()
    async def test_generate_delta_includes_calibrated_language(
        self,
        presenter: MemoryDeltaPresenter,
        mock_db: MagicMock,
    ) -> None:
        """Facts include calibrated language based on confidence."""
        facts = [
            _make_fact_row(
                fact="Acme Corp has 500 employees",
                confidence=0.65,
                category="product",
            ),
        ]
        query_chain = _build_chain(facts)
        mock_db.table.return_value = query_chain

        deltas = await presenter.generate_delta("user-123")

        fact = deltas[0].facts[0]
        assert fact.language.startswith("It appears that ")

    @pytest.mark.asyncio()
    async def test_generate_delta_summary_includes_count(
        self,
        presenter: MemoryDeltaPresenter,
        mock_db: MagicMock,
    ) -> None:
        """Domain summary includes fact count."""
        facts = [
            _make_fact_row(fact_id="f1", category="product"),
            _make_fact_row(fact_id="f2", category="pipeline"),
        ]
        query_chain = _build_chain(facts)
        mock_db.table.return_value = query_chain

        deltas = await presenter.generate_delta("user-123")

        assert "2" in deltas[0].summary
        assert "company intelligence" in deltas[0].summary

    @pytest.mark.asyncio()
    async def test_generate_delta_singular_summary(
        self,
        presenter: MemoryDeltaPresenter,
        mock_db: MagicMock,
    ) -> None:
        """Single fact uses singular summary."""
        facts = [_make_fact_row(category="competitive")]
        query_chain = _build_chain(facts)
        mock_db.table.return_value = query_chain

        deltas = await presenter.generate_delta("user-123")

        assert "1 new fact" in deltas[0].summary

    @pytest.mark.asyncio()
    async def test_generate_delta_passes_since_filter(
        self,
        presenter: MemoryDeltaPresenter,
        mock_db: MagicMock,
    ) -> None:
        """since parameter is passed to the database query."""
        query_chain = _build_chain([])
        mock_db.table.return_value = query_chain

        await presenter.generate_delta("user-123", since="2026-02-06T00:00:00Z")

        query_chain.gte.assert_called_once_with("created_at", "2026-02-06T00:00:00Z")

    @pytest.mark.asyncio()
    async def test_generate_delta_db_error_returns_empty(
        self,
        presenter: MemoryDeltaPresenter,
        mock_db: MagicMock,
    ) -> None:
        """Database errors result in empty delta list."""
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.order.return_value = chain
        chain.limit.return_value = chain
        chain.execute.side_effect = Exception("DB connection failed")
        mock_db.table.return_value = chain

        deltas = await presenter.generate_delta("user-123")

        assert deltas == []


# --- Corrections ---


class TestCorrections:
    """Tests for the correction flow."""

    @pytest.mark.asyncio()
    async def test_correction_reduces_original_confidence(
        self,
        presenter: MemoryDeltaPresenter,
        mock_db: MagicMock,
    ) -> None:
        """Correcting a fact reduces the original's confidence."""
        original = _make_fact_row(confidence=0.85)
        select_chain = _build_chain(original)
        update_chain = _build_chain([])
        insert_chain = _build_chain([])

        mock_db.table.side_effect = [select_chain, update_chain, insert_chain]

        with patch("src.memory.delta_presenter.log_memory_operation", new_callable=AsyncMock):
            correction = CorrectionRequest(
                fact_id="fact-1",
                corrected_value="Acme Corp specializes in pharma",
            )
            result = await presenter.apply_correction("user-123", correction)

        assert result["status"] == "corrected"
        # Check update was called on original
        update_chain.update.assert_called_once()
        update_call_args = update_chain.update.call_args[0][0]
        assert update_call_args["confidence"] <= 0.3

    @pytest.mark.asyncio()
    async def test_correction_creates_user_stated_fact(
        self,
        presenter: MemoryDeltaPresenter,
        mock_db: MagicMock,
    ) -> None:
        """Corrections create a new fact with source: user_stated and confidence 0.95."""
        original = _make_fact_row()
        select_chain = _build_chain(original)
        update_chain = _build_chain([])
        insert_chain = _build_chain([])

        mock_db.table.side_effect = [select_chain, update_chain, insert_chain]

        with patch("src.memory.delta_presenter.log_memory_operation", new_callable=AsyncMock):
            correction = CorrectionRequest(
                fact_id="fact-1",
                corrected_value="Corrected fact text",
            )
            result = await presenter.apply_correction("user-123", correction)

        assert result["new_confidence"] == 0.95
        insert_chain.insert.assert_called_once()
        insert_data = insert_chain.insert.call_args[0][0]
        assert insert_data["source"] == "user_stated"
        assert insert_data["confidence"] == 0.95
        assert insert_data["fact"] == "Corrected fact text"

    @pytest.mark.asyncio()
    async def test_correction_preserves_metadata(
        self,
        presenter: MemoryDeltaPresenter,
        mock_db: MagicMock,
    ) -> None:
        """Corrections preserve original metadata and add correction info."""
        original = _make_fact_row()
        select_chain = _build_chain(original)
        update_chain = _build_chain([])
        insert_chain = _build_chain([])

        mock_db.table.side_effect = [select_chain, update_chain, insert_chain]

        with patch("src.memory.delta_presenter.log_memory_operation", new_callable=AsyncMock):
            correction = CorrectionRequest(
                fact_id="fact-1",
                corrected_value="New value",
                correction_type="outdated",
            )
            await presenter.apply_correction("user-123", correction)

        insert_data = insert_chain.insert.call_args[0][0]
        assert insert_data["metadata"]["corrects"] == "fact-1"
        assert insert_data["metadata"]["correction_type"] == "outdated"
        assert insert_data["metadata"]["category"] == "product"

    @pytest.mark.asyncio()
    async def test_correction_not_found(
        self,
        presenter: MemoryDeltaPresenter,
        mock_db: MagicMock,
    ) -> None:
        """Correcting a non-existent fact returns not_found."""
        select_chain = _build_chain(None)
        mock_db.table.return_value = select_chain

        correction = CorrectionRequest(
            fact_id="nonexistent",
            corrected_value="Doesn't matter",
        )
        result = await presenter.apply_correction("user-123", correction)

        assert result["status"] == "not_found"

    @pytest.mark.asyncio()
    async def test_correction_logs_audit(
        self,
        presenter: MemoryDeltaPresenter,
        mock_db: MagicMock,
    ) -> None:
        """Corrections are logged to the audit trail."""
        original = _make_fact_row()
        select_chain = _build_chain(original)
        update_chain = _build_chain([])
        insert_chain = _build_chain([])

        mock_db.table.side_effect = [select_chain, update_chain, insert_chain]

        mock_audit = AsyncMock()
        with patch("src.memory.delta_presenter.log_memory_operation", mock_audit):
            correction = CorrectionRequest(
                fact_id="fact-1",
                corrected_value="Corrected text",
            )
            await presenter.apply_correction("user-123", correction)

        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args[1]
        assert call_kwargs["user_id"] == "user-123"
        assert call_kwargs["metadata"]["action"] == "memory_correction"
        assert call_kwargs["metadata"]["original_fact"] == "Acme Corp specializes in biotech"
        assert call_kwargs["metadata"]["corrected_to"] == "Corrected text"


# --- Pydantic models ---


class TestModels:
    """Tests for Pydantic model validation."""

    def test_memory_fact_defaults(self) -> None:
        """MemoryFact has sensible defaults."""
        fact = MemoryFact(fact="Test", confidence=0.5, source="test")
        assert fact.id == ""
        assert fact.category == "general"
        assert fact.language == ""

    def test_memory_delta_defaults(self) -> None:
        """MemoryDelta has sensible defaults."""
        delta = MemoryDelta(domain="corporate_memory")
        assert delta.facts == []
        assert delta.summary == ""
        assert delta.timestamp is None

    def test_correction_request_defaults(self) -> None:
        """CorrectionRequest defaults correction_type to factual."""
        req = CorrectionRequest(fact_id="f1", corrected_value="new")
        assert req.correction_type == "factual"

    def test_memory_fact_confidence_bounds(self) -> None:
        """MemoryFact confidence must be between 0 and 1."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            MemoryFact(fact="Test", confidence=1.5, source="test")
        with pytest.raises(ValidationError):
            MemoryFact(fact="Test", confidence=-0.1, source="test")


# --- Summary generation ---


class TestSummary:
    """Tests for summary text generation."""

    def test_summary_with_multiple_facts(self, presenter: MemoryDeltaPresenter) -> None:
        """Summary uses plural for multiple facts."""
        facts = [
            MemoryFact(fact="f1", confidence=0.9, source="test"),
            MemoryFact(fact="f2", confidence=0.9, source="test"),
        ]
        summary = presenter._build_summary("corporate_memory", facts)
        assert summary == "Learned 2 new facts about company intelligence"

    def test_summary_with_single_fact(self, presenter: MemoryDeltaPresenter) -> None:
        """Summary uses singular for single fact."""
        facts = [MemoryFact(fact="f1", confidence=0.9, source="test")]
        summary = presenter._build_summary("corporate_memory", facts)
        assert summary == "Learned 1 new fact about company intelligence"

    def test_summary_uses_domain_label(self, presenter: MemoryDeltaPresenter) -> None:
        """Summary uses human-readable domain label."""
        facts = [MemoryFact(fact="f1", confidence=0.9, source="test")]
        summary = presenter._build_summary("competitive", facts)
        assert "competitive landscape" in summary

    def test_summary_unknown_domain_uses_key(self, presenter: MemoryDeltaPresenter) -> None:
        """Unknown domain uses the domain key as label."""
        facts = [MemoryFact(fact="f1", confidence=0.9, source="test")]
        summary = presenter._build_summary("unknown_domain", facts)
        assert "unknown_domain" in summary
