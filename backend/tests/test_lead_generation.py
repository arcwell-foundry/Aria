"""Tests for LeadGenerationService (US-939)."""

from datetime import UTC, datetime
from unittest.mock import ANY, AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.lead_generation import LeadGenerationService
from src.models.lead_generation import (
    ICPDefinition,
    LeadScoreBreakdown,
    OutreachRequest,
    PipelineStage,
    ReviewStatus,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_icp_data() -> ICPDefinition:
    """Create a sample ICPDefinition for tests."""
    return ICPDefinition(
        industry=["Biotechnology"],
        company_size={"min": 100, "max": 500},
        modalities=["small_molecule"],
        therapeutic_areas=["oncology"],
        geographies=["North America"],
        signals=["funding"],
        exclusions=["competitor.com"],
    )


def _make_icp_row(
    user_id: str,
    icp_id: str | None = None,
    version: int = 1,
) -> dict:
    """Return a fake database row for lead_icp_profiles."""
    now = datetime.now(UTC).isoformat()
    return {
        "id": icp_id or str(uuid4()),
        "user_id": user_id,
        "icp_data": _make_icp_data().model_dump(),
        "version": version,
        "created_at": now,
        "updated_at": now,
    }


def _make_discovered_lead_row(
    user_id: str,
    lead_id: str | None = None,
    icp_id: str | None = None,
    review_status: str = "pending",
    lead_memory_id: str | None = None,
) -> dict:
    """Return a fake database row for discovered_leads."""
    now = datetime.now(UTC).isoformat()
    breakdown = {
        "overall_score": 72,
        "factors": [
            {"name": "ICP Fit", "score": 80, "weight": 0.40, "explanation": "Industry match"},
            {
                "name": "Timing Signals",
                "score": 60,
                "weight": 0.25,
                "explanation": "Funding: Series C",
            },
            {
                "name": "Relationship Proximity",
                "score": 70,
                "weight": 0.20,
                "explanation": "2 contacts",
            },
            {
                "name": "Engagement Signals",
                "score": 55,
                "weight": 0.15,
                "explanation": "5/9 fields",
            },
        ],
    }
    return {
        "id": lead_id or str(uuid4()),
        "user_id": user_id,
        "icp_id": icp_id or str(uuid4()),
        "company_name": "GenTech Bio",
        "company_data": {"name": "GenTech Bio", "domain": "gentechbio.com"},
        "contacts": [{"name": "Sarah Johnson", "title": "CEO"}],
        "fit_score": 72,
        "score_breakdown": breakdown,
        "signals": ["funding:Series C"],
        "review_status": review_status,
        "reviewed_at": None,
        "source": "hunter_pro",
        "lead_memory_id": lead_memory_id,
        "created_at": now,
        "updated_at": now,
    }


def _supabase_chain_mock(return_data: list | dict | None = None) -> MagicMock:
    """Build a mock that supports chained Supabase query methods.

    The mock supports arbitrary chains of .table().select().eq().order()
    etc., and terminates with .execute() returning an object whose
    `.data` attribute equals *return_data*.
    """
    execute_result = MagicMock()
    execute_result.data = return_data

    chain = MagicMock()
    chain.execute.return_value = execute_result

    # Every intermediate method returns the same chain object so that
    # arbitrary .select().eq().eq().order().maybe_single() chains work.
    for method_name in (
        "table",
        "select",
        "eq",
        "order",
        "maybe_single",
        "insert",
        "update",
        "upsert",
        "delete",
    ):
        getattr(chain, method_name).return_value = chain

    return chain


# ---------------------------------------------------------------------------
# ICP Management
# ---------------------------------------------------------------------------


class TestICPManagement:
    """Test ICP save and get operations."""

    @pytest.mark.asyncio
    async def test_save_icp_creates_new_record(self):
        """save_icp should insert a new ICP when none exists."""
        user_id = str(uuid4())
        icp_data = _make_icp_data()

        # First call (select) returns None -> no existing ICP
        select_chain = _supabase_chain_mock(return_data=None)
        # Second call (insert) returns the new row
        new_row = _make_icp_row(user_id, version=1)
        insert_chain = _supabase_chain_mock(return_data=[new_row])

        # The service calls _get_client() once, so we need a single mock
        # whose .table() calls alternate behavior.  Simpler: use side_effect
        # on .execute() to return different results for sequential calls.
        client = MagicMock()
        call_counter = {"n": 0}

        def _table_router(_table_name: str) -> MagicMock:
            call_counter["n"] += 1
            if call_counter["n"] == 1:
                return select_chain
            return insert_chain

        client.table.side_effect = _table_router

        service = LeadGenerationService()
        with patch.object(service, "_get_client", return_value=client):
            result = await service.save_icp(user_id, icp_data)

        assert result.version == 1
        assert result.user_id == user_id

    @pytest.mark.asyncio
    async def test_save_icp_updates_existing_record(self):
        """save_icp should increment version when ICP already exists."""
        user_id = str(uuid4())
        icp_id = str(uuid4())
        icp_data = _make_icp_data()

        existing_row = _make_icp_row(user_id, icp_id=icp_id, version=2)
        updated_row = _make_icp_row(user_id, icp_id=icp_id, version=3)

        select_chain = _supabase_chain_mock(return_data=existing_row)
        update_chain = _supabase_chain_mock(return_data=[updated_row])

        client = MagicMock()
        call_counter = {"n": 0}

        def _table_router(_name: str) -> MagicMock:
            call_counter["n"] += 1
            if call_counter["n"] == 1:
                return select_chain
            return update_chain

        client.table.side_effect = _table_router

        service = LeadGenerationService()
        with patch.object(service, "_get_client", return_value=client):
            result = await service.save_icp(user_id, icp_data)

        assert result.version == 3

    @pytest.mark.asyncio
    async def test_get_icp_returns_none_when_not_found(self):
        """get_icp should return None when no ICP exists."""
        user_id = str(uuid4())
        client = _supabase_chain_mock(return_data=None)

        service = LeadGenerationService()
        with patch.object(service, "_get_client", return_value=client):
            result = await service.get_icp(user_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_icp_returns_icp_when_found(self):
        """get_icp should return ICPResponse when ICP exists."""
        user_id = str(uuid4())
        row = _make_icp_row(user_id)
        client = _supabase_chain_mock(return_data=row)

        service = LeadGenerationService()
        with patch.object(service, "_get_client", return_value=client):
            result = await service.get_icp(user_id)

        assert result is not None
        assert result.user_id == user_id
        assert result.icp_data.industry == ["Biotechnology"]


# ---------------------------------------------------------------------------
# Lead Discovery
# ---------------------------------------------------------------------------


class TestLeadDiscovery:
    """Test lead discovery via Hunter agent."""

    @pytest.mark.asyncio
    async def test_discover_leads_calls_hunter_agent(self):
        """discover_leads should invoke Hunter agent with ICP data."""
        user_id = str(uuid4())
        icp_id = str(uuid4())
        icp_row = _make_icp_row(user_id, icp_id=icp_id)

        # Supabase returns ICP row for the fetch, then accepts inserts
        client = _supabase_chain_mock(return_data=icp_row)

        # Mock the HunterAgent
        mock_agent_result = MagicMock()
        mock_agent_result.success = True
        mock_agent_result.data = []  # No leads to simplify

        service = LeadGenerationService()
        with (
            patch.object(service, "_get_client", return_value=client),
            patch("src.core.lead_generation.LLMClient"),
            patch("src.core.lead_generation.HunterAgent") as mock_hunter_cls,
        ):
            mock_hunter = AsyncMock()
            mock_hunter.execute.return_value = mock_agent_result
            mock_hunter_cls.return_value = mock_hunter

            await service.discover_leads(user_id, icp_id, target_count=5)

            mock_hunter.execute.assert_called_once()
            call_args = mock_hunter.execute.call_args[0][0]
            assert "icp" in call_args
            assert call_args["target_count"] == 5

    @pytest.mark.asyncio
    async def test_discover_leads_stores_results(self):
        """discover_leads should store discovered leads in database."""
        user_id = str(uuid4())
        icp_id = str(uuid4())
        icp_row = _make_icp_row(user_id, icp_id=icp_id)

        client = _supabase_chain_mock(return_data=icp_row)

        hunter_lead = {
            "company": {
                "name": "TestCo",
                "domain": "testco.com",
                "industry": "Biotech",
                "funding_stage": "Series B",
                "technologies": ["Salesforce"],
            },
            "contacts": [{"name": "Alice", "title": "CEO"}],
            "fit_score": 75.0,
            "fit_reasons": ["Industry match"],
            "gaps": [],
            "source": "hunter_pro",
        }

        mock_agent_result = MagicMock()
        mock_agent_result.success = True
        mock_agent_result.data = [hunter_lead]

        service = LeadGenerationService()
        with (
            patch.object(service, "_get_client", return_value=client),
            patch("src.core.lead_generation.LLMClient"),
            patch("src.core.lead_generation.HunterAgent") as mock_hunter_cls,
        ):
            mock_hunter = AsyncMock()
            mock_hunter.execute.return_value = mock_agent_result
            mock_hunter_cls.return_value = mock_hunter

            results = await service.discover_leads(user_id, icp_id, target_count=5)

        assert len(results) == 1
        assert results[0].company_name == "TestCo"
        assert results[0].review_status == ReviewStatus.PENDING
        # Verify insert was called on the discovered_leads table
        client.table.assert_any_call("discovered_leads")

    @pytest.mark.asyncio
    async def test_discover_leads_computes_score_breakdown(self):
        """Each discovered lead should have a 4-factor score breakdown."""
        user_id = str(uuid4())
        icp_id = str(uuid4())
        icp_row = _make_icp_row(user_id, icp_id=icp_id)

        client = _supabase_chain_mock(return_data=icp_row)

        hunter_lead = {
            "company": {
                "name": "ScoreCo",
                "domain": "scoreco.com",
                "funding_stage": "Series A",
                "technologies": ["HubSpot"],
                "revenue": "$5M",
                "founded_year": 2020,
            },
            "contacts": [{"name": "Bob", "title": "CTO"}, {"name": "Eve", "title": "VP Sales"}],
            "fit_score": 80.0,
            "fit_reasons": ["Industry match", "Geo match"],
            "gaps": ["Size mismatch"],
            "source": "hunter_pro",
        }

        mock_agent_result = MagicMock()
        mock_agent_result.success = True
        mock_agent_result.data = [hunter_lead]

        service = LeadGenerationService()
        with (
            patch.object(service, "_get_client", return_value=client),
            patch("src.core.lead_generation.LLMClient"),
            patch("src.core.lead_generation.HunterAgent") as mock_hunter_cls,
        ):
            mock_hunter = AsyncMock()
            mock_hunter.execute.return_value = mock_agent_result
            mock_hunter_cls.return_value = mock_hunter

            results = await service.discover_leads(user_id, icp_id, target_count=5)

        assert len(results) == 1
        breakdown = results[0].score_breakdown
        assert breakdown is not None
        assert len(breakdown.factors) == 4

        factor_names = {f.name for f in breakdown.factors}
        assert factor_names == {
            "ICP Fit",
            "Timing Signals",
            "Relationship Proximity",
            "Engagement Signals",
        }
        assert 0 <= breakdown.overall_score <= 100

    @pytest.mark.asyncio
    async def test_discover_leads_raises_for_missing_icp(self):
        """discover_leads should raise ValueError when ICP not found."""
        user_id = str(uuid4())
        icp_id = str(uuid4())

        client = _supabase_chain_mock(return_data=None)

        service = LeadGenerationService()
        with (
            patch.object(service, "_get_client", return_value=client),
            pytest.raises(ValueError, match="ICP profile not found"),
        ):
            await service.discover_leads(user_id, icp_id, target_count=5)

    @pytest.mark.asyncio
    async def test_discover_leads_returns_empty_on_agent_failure(self):
        """discover_leads should return [] when Hunter agent fails."""
        user_id = str(uuid4())
        icp_id = str(uuid4())
        icp_row = _make_icp_row(user_id, icp_id=icp_id)

        client = _supabase_chain_mock(return_data=icp_row)

        mock_agent_result = MagicMock()
        mock_agent_result.success = False
        mock_agent_result.data = None

        service = LeadGenerationService()
        with (
            patch.object(service, "_get_client", return_value=client),
            patch("src.core.lead_generation.LLMClient"),
            patch("src.core.lead_generation.HunterAgent") as mock_hunter_cls,
        ):
            mock_hunter = AsyncMock()
            mock_hunter.execute.return_value = mock_agent_result
            mock_hunter_cls.return_value = mock_hunter

            results = await service.discover_leads(user_id, icp_id, target_count=5)

        assert results == []


# ---------------------------------------------------------------------------
# Lead Review
# ---------------------------------------------------------------------------


class TestLeadReview:
    """Test lead review actions."""

    @pytest.mark.asyncio
    async def test_review_approve_creates_lead_memory(self):
        """Approving a lead should create a Lead Memory entry."""
        user_id = str(uuid4())
        lead_id = str(uuid4())
        lead_memory_id = str(uuid4())

        existing_row = _make_discovered_lead_row(user_id, lead_id=lead_id)
        updated_row = _make_discovered_lead_row(
            user_id,
            lead_id=lead_id,
            review_status="approved",
            lead_memory_id=lead_memory_id,
        )

        # select returns existing, update returns updated
        select_chain = _supabase_chain_mock(return_data=existing_row)
        update_chain = _supabase_chain_mock(return_data=[updated_row])

        client = MagicMock()
        call_counter = {"n": 0}

        def _table_router(_name: str) -> MagicMock:
            call_counter["n"] += 1
            if call_counter["n"] == 1:
                return select_chain
            return update_chain

        client.table.side_effect = _table_router

        # Mock LeadMemoryService.create
        mock_lead_memory = MagicMock()
        mock_lead_memory.id = lead_memory_id

        service = LeadGenerationService()
        with (
            patch.object(service, "_get_client", return_value=client),
            patch("src.core.lead_generation.LeadMemoryService") as mock_lm_cls,
        ):
            mock_lm_instance = AsyncMock()
            mock_lm_instance.create.return_value = mock_lead_memory
            mock_lm_cls.return_value = mock_lm_instance

            result = await service.review_lead(user_id, lead_id, ReviewStatus.APPROVED)

        assert result is not None
        assert result.review_status == ReviewStatus.APPROVED
        assert result.lead_memory_id == lead_memory_id
        mock_lm_instance.create.assert_called_once_with(
            user_id=user_id,
            company_name=existing_row["company_name"],
            trigger=ANY,
        )

    @pytest.mark.asyncio
    async def test_review_reject_does_not_create_lead_memory(self):
        """Rejecting a lead should NOT create a Lead Memory entry."""
        user_id = str(uuid4())
        lead_id = str(uuid4())

        existing_row = _make_discovered_lead_row(user_id, lead_id=lead_id)
        updated_row = _make_discovered_lead_row(
            user_id,
            lead_id=lead_id,
            review_status="rejected",
        )

        select_chain = _supabase_chain_mock(return_data=existing_row)
        update_chain = _supabase_chain_mock(return_data=[updated_row])

        client = MagicMock()
        call_counter = {"n": 0}

        def _table_router(_name: str) -> MagicMock:
            call_counter["n"] += 1
            if call_counter["n"] == 1:
                return select_chain
            return update_chain

        client.table.side_effect = _table_router

        service = LeadGenerationService()
        with (
            patch.object(service, "_get_client", return_value=client),
            patch("src.core.lead_generation.LeadMemoryService") as mock_lm_cls,
        ):
            mock_lm_instance = AsyncMock()
            mock_lm_cls.return_value = mock_lm_instance

            result = await service.review_lead(user_id, lead_id, ReviewStatus.REJECTED)

        assert result is not None
        assert result.review_status == ReviewStatus.REJECTED
        mock_lm_instance.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_review_save_sets_status(self):
        """Saving a lead should set review_status to saved."""
        user_id = str(uuid4())
        lead_id = str(uuid4())

        existing_row = _make_discovered_lead_row(user_id, lead_id=lead_id)
        updated_row = _make_discovered_lead_row(
            user_id,
            lead_id=lead_id,
            review_status="saved",
        )

        select_chain = _supabase_chain_mock(return_data=existing_row)
        update_chain = _supabase_chain_mock(return_data=[updated_row])

        client = MagicMock()
        call_counter = {"n": 0}

        def _table_router(_name: str) -> MagicMock:
            call_counter["n"] += 1
            if call_counter["n"] == 1:
                return select_chain
            return update_chain

        client.table.side_effect = _table_router

        service = LeadGenerationService()
        with patch.object(service, "_get_client", return_value=client):
            result = await service.review_lead(user_id, lead_id, ReviewStatus.SAVED)

        assert result is not None
        assert result.review_status == ReviewStatus.SAVED

    @pytest.mark.asyncio
    async def test_review_nonexistent_lead_returns_none(self):
        """Reviewing a nonexistent lead should return None."""
        user_id = str(uuid4())
        lead_id = str(uuid4())

        client = _supabase_chain_mock(return_data=None)

        service = LeadGenerationService()
        with patch.object(service, "_get_client", return_value=client):
            result = await service.review_lead(user_id, lead_id, ReviewStatus.APPROVED)

        assert result is None


# ---------------------------------------------------------------------------
# Score Explanation
# ---------------------------------------------------------------------------


class TestScoreExplanation:
    """Test score explanation retrieval."""

    @pytest.mark.asyncio
    async def test_get_score_explanation_returns_breakdown(self):
        """Should return LeadScoreBreakdown with all 4 factors."""
        user_id = str(uuid4())
        lead_id = str(uuid4())

        breakdown_data = {
            "overall_score": 72,
            "factors": [
                {"name": "ICP Fit", "score": 80, "weight": 0.40, "explanation": "Match"},
                {"name": "Timing Signals", "score": 60, "weight": 0.25, "explanation": "Funding"},
                {
                    "name": "Relationship Proximity",
                    "score": 70,
                    "weight": 0.20,
                    "explanation": "2 contacts",
                },
                {"name": "Engagement Signals", "score": 55, "weight": 0.15, "explanation": "5/9"},
            ],
        }

        row_data = {"score_breakdown": breakdown_data}
        client = _supabase_chain_mock(return_data=row_data)

        service = LeadGenerationService()
        with patch.object(service, "_get_client", return_value=client):
            result = await service.get_score_explanation(user_id, lead_id)

        assert result is not None
        assert isinstance(result, LeadScoreBreakdown)
        assert len(result.factors) == 4
        assert result.overall_score == 72

    @pytest.mark.asyncio
    async def test_get_score_explanation_handles_string_json(self):
        """Should handle score_breakdown stored as a JSON string."""
        user_id = str(uuid4())
        lead_id = str(uuid4())

        import json

        breakdown_data = {
            "overall_score": 65,
            "factors": [
                {"name": "ICP Fit", "score": 70, "weight": 0.40, "explanation": "OK"},
                {"name": "Timing Signals", "score": 50, "weight": 0.25, "explanation": "Some"},
                {
                    "name": "Relationship Proximity",
                    "score": 60,
                    "weight": 0.20,
                    "explanation": "1 contact",
                },
                {"name": "Engagement Signals", "score": 55, "weight": 0.15, "explanation": "4/9"},
            ],
        }

        row_data = {"score_breakdown": json.dumps(breakdown_data)}
        client = _supabase_chain_mock(return_data=row_data)

        service = LeadGenerationService()
        with patch.object(service, "_get_client", return_value=client):
            result = await service.get_score_explanation(user_id, lead_id)

        assert result is not None
        assert result.overall_score == 65

    @pytest.mark.asyncio
    async def test_get_score_explanation_nonexistent_returns_none(self):
        """Should return None for nonexistent lead."""
        user_id = str(uuid4())
        lead_id = str(uuid4())

        client = _supabase_chain_mock(return_data=None)

        service = LeadGenerationService()
        with patch.object(service, "_get_client", return_value=client):
            result = await service.get_score_explanation(user_id, lead_id)

        assert result is None


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class TestPipeline:
    """Test pipeline aggregation."""

    @pytest.mark.asyncio
    async def test_get_pipeline_aggregates_by_stage(self):
        """Should aggregate leads by lifecycle stage."""
        user_id = str(uuid4())

        rows = [
            {"lifecycle_stage": "lead", "health_score": 40, "expected_value": 10000},
            {"lifecycle_stage": "lead", "health_score": 70, "expected_value": 20000},
            {"lifecycle_stage": "opportunity", "health_score": 80, "expected_value": 50000},
            {"lifecycle_stage": "account", "health_score": 90, "expected_value": 100000},
        ]

        client = _supabase_chain_mock(return_data=rows)

        service = LeadGenerationService()
        with patch.object(service, "_get_client", return_value=client):
            result = await service.get_pipeline(user_id)

        stage_map = {s.stage: s for s in result.stages}

        # Both leads go to prospect
        assert stage_map[PipelineStage.PROSPECT].count == 2
        assert stage_map[PipelineStage.PROSPECT].total_value == 30000.0

        # Only the lead with health_score >= 60 goes to qualified
        assert stage_map[PipelineStage.QUALIFIED].count == 1
        assert stage_map[PipelineStage.QUALIFIED].total_value == 20000.0

        assert stage_map[PipelineStage.OPPORTUNITY].count == 1
        assert stage_map[PipelineStage.OPPORTUNITY].total_value == 50000.0

        assert stage_map[PipelineStage.CUSTOMER].count == 1
        assert stage_map[PipelineStage.CUSTOMER].total_value == 100000.0

        assert result.total_leads == 5  # 2 prospect + 1 qualified + 1 opp + 1 customer
        assert result.total_pipeline_value == 200000.0

    @pytest.mark.asyncio
    async def test_get_pipeline_empty_returns_zero_counts(self):
        """Should return zero counts when no leads exist."""
        user_id = str(uuid4())

        client = _supabase_chain_mock(return_data=[])

        service = LeadGenerationService()
        with patch.object(service, "_get_client", return_value=client):
            result = await service.get_pipeline(user_id)

        assert result.total_leads == 0
        assert result.total_pipeline_value == 0.0
        for stage_summary in result.stages:
            assert stage_summary.count == 0
            assert stage_summary.total_value == 0.0

    @pytest.mark.asyncio
    async def test_get_pipeline_handles_none_expected_value(self):
        """Should handle None expected_value gracefully."""
        user_id = str(uuid4())

        rows = [
            {"lifecycle_stage": "lead", "health_score": 50, "expected_value": None},
        ]

        client = _supabase_chain_mock(return_data=rows)

        service = LeadGenerationService()
        with patch.object(service, "_get_client", return_value=client):
            result = await service.get_pipeline(user_id)

        stage_map = {s.stage: s for s in result.stages}
        assert stage_map[PipelineStage.PROSPECT].count == 1
        assert stage_map[PipelineStage.PROSPECT].total_value == 0.0


# ---------------------------------------------------------------------------
# Discovered Leads List
# ---------------------------------------------------------------------------


class TestDiscoveredLeadsList:
    """Test listing discovered leads."""

    @pytest.mark.asyncio
    async def test_list_discovered_returns_all(self):
        """Should return all discovered leads when no filter."""
        user_id = str(uuid4())

        rows = [
            _make_discovered_lead_row(user_id, review_status="pending"),
            _make_discovered_lead_row(user_id, review_status="approved"),
        ]

        client = _supabase_chain_mock(return_data=rows)

        service = LeadGenerationService()
        with patch.object(service, "_get_client", return_value=client):
            results = await service.list_discovered(user_id)

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_list_discovered_filters_by_status(self):
        """Should filter by review_status when provided."""
        user_id = str(uuid4())

        rows = [
            _make_discovered_lead_row(user_id, review_status="pending"),
        ]

        client = _supabase_chain_mock(return_data=rows)

        service = LeadGenerationService()
        with patch.object(service, "_get_client", return_value=client):
            results = await service.list_discovered(user_id, status_filter=ReviewStatus.PENDING)

        assert len(results) == 1
        assert results[0].review_status == ReviewStatus.PENDING
        # Verify .eq was called with the status filter value
        client.eq.assert_any_call("review_status", "pending")

    @pytest.mark.asyncio
    async def test_list_discovered_returns_empty_when_no_data(self):
        """Should return empty list when no leads found."""
        user_id = str(uuid4())

        client = _supabase_chain_mock(return_data=None)

        service = LeadGenerationService()
        with patch.object(service, "_get_client", return_value=client):
            results = await service.list_discovered(user_id)

        assert results == []


# ---------------------------------------------------------------------------
# Outreach
# ---------------------------------------------------------------------------


class TestOutreach:
    """Test outreach initiation."""

    @pytest.mark.asyncio
    async def test_initiate_outreach_creates_draft(self):
        """Should create an outreach draft with provided content."""
        user_id = str(uuid4())
        lead_id = str(uuid4())

        # discovered_leads returns a match
        client = _supabase_chain_mock(return_data={"id": lead_id})

        request = OutreachRequest(
            subject="Hello from ARIA",
            message="We would love to connect.",
            tone="professional",
        )

        service = LeadGenerationService()
        with patch.object(service, "_get_client", return_value=client):
            result = await service.initiate_outreach(user_id, lead_id, request)

        assert result is not None
        assert result.lead_id == lead_id
        assert result.draft_subject == "Hello from ARIA"
        assert result.draft_body == "We would love to connect."
        assert result.status == "draft"

    @pytest.mark.asyncio
    async def test_initiate_outreach_nonexistent_lead_returns_none(self):
        """Should return None for nonexistent lead."""
        user_id = str(uuid4())
        lead_id = str(uuid4())

        # Both discovered_leads and lead_memories return None
        client = _supabase_chain_mock(return_data=None)

        request = OutreachRequest(
            subject="Test",
            message="Test message",
        )

        service = LeadGenerationService()
        with patch.object(service, "_get_client", return_value=client):
            result = await service.initiate_outreach(user_id, lead_id, request)

        assert result is None

    @pytest.mark.asyncio
    async def test_initiate_outreach_falls_back_to_lead_memories(self):
        """Should check lead_memories when discovered_leads has no match."""
        user_id = str(uuid4())
        lead_id = str(uuid4())

        # First call to discovered_leads returns None, second to lead_memories returns match
        select_chain_empty = _supabase_chain_mock(return_data=None)
        select_chain_found = _supabase_chain_mock(return_data={"id": lead_id})

        client = MagicMock()
        call_counter = {"n": 0}

        def _table_router(_name: str) -> MagicMock:
            call_counter["n"] += 1
            if call_counter["n"] == 1:
                return select_chain_empty
            return select_chain_found

        client.table.side_effect = _table_router

        request = OutreachRequest(
            subject="Follow up",
            message="Checking in",
        )

        service = LeadGenerationService()
        with patch.object(service, "_get_client", return_value=client):
            result = await service.initiate_outreach(user_id, lead_id, request)

        assert result is not None
        assert result.lead_id == lead_id


# ---------------------------------------------------------------------------
# Score Computation (unit-level)
# ---------------------------------------------------------------------------


class TestScoreComputation:
    """Test the _compute_score_breakdown helper directly."""

    def test_full_signals_company_scores_high(self):
        """Company with all data should score highly."""
        service = LeadGenerationService()
        company = {
            "name": "FullCo",
            "domain": "fullco.com",
            "industry": "Biotech",
            "size": "100-500",
            "geography": "US",
            "website": "https://fullco.com",
            "linkedin_url": "https://linkedin.com/company/fullco",
            "funding_stage": "Series C",
            "revenue": "$50M",
        }
        contacts = [
            {"name": "A"},
            {"name": "B"},
            {"name": "C"},
            {"name": "D"},
        ]

        breakdown = service._compute_score_breakdown(
            fit_score=90,
            company=company,
            contacts=contacts,
            fit_reasons=["Industry match"],
            gaps=[],
        )

        assert breakdown.overall_score > 50
        assert len(breakdown.factors) == 4
        # 4+ contacts -> relationship score = 100
        rel_factor = next(f for f in breakdown.factors if f.name == "Relationship Proximity")
        assert rel_factor.score == 100

    def test_empty_company_scores_low(self):
        """Company with no data should score low."""
        service = LeadGenerationService()
        breakdown = service._compute_score_breakdown(
            fit_score=0,
            company={},
            contacts=[],
            fit_reasons=[],
            gaps=["Everything missing"],
        )

        assert breakdown.overall_score == 0
        for factor in breakdown.factors:
            assert factor.score == 0
