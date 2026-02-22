"""Tests for EmailLeadIntelligence service.

Verifies:
- Personal domain filtering
- Lead matching via company name / sender domain
- LLM signal extraction parsing
- Event recording for matched leads
- Health score recalculation trigger
- Non-blocking error handling
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.email_lead_intelligence import (
    PERSONAL_DOMAINS,
    EmailLeadIntelligence,
)


@pytest.fixture
def service() -> EmailLeadIntelligence:
    return EmailLeadIntelligence()


class TestPersonalDomainFiltering:
    """Emails from personal domains should be skipped entirely."""

    @pytest.mark.asyncio
    async def test_gmail_skipped(self, service: EmailLeadIntelligence) -> None:
        result = await service.process_email_for_leads(
            user_id="user-1",
            email={"sender_email": "john@gmail.com", "subject": "hi", "body": "hello"},
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_protonmail_skipped(self, service: EmailLeadIntelligence) -> None:
        result = await service.process_email_for_leads(
            user_id="user-1",
            email={"sender_email": "john@protonmail.com", "subject": "hi", "body": "hello"},
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_empty_sender_skipped(self, service: EmailLeadIntelligence) -> None:
        result = await service.process_email_for_leads(
            user_id="user-1",
            email={"sender_email": "", "subject": "hi", "body": "hello"},
        )
        assert result == []

    def test_personal_domains_set_is_frozenset(self) -> None:
        assert isinstance(PERSONAL_DOMAINS, frozenset)
        assert "gmail.com" in PERSONAL_DOMAINS


class TestLeadMatching:
    """Sender domain should match against lead_memories company_name."""

    @pytest.mark.asyncio
    async def test_no_match_returns_empty(self, service: EmailLeadIntelligence) -> None:
        mock_response = MagicMock()
        mock_response.data = []

        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.eq.return_value.ilike.return_value.in_.return_value.execute.return_value = mock_response

        with patch("src.services.email_lead_intelligence.SupabaseClient") as mock_sb:
            mock_sb.get_client.return_value = mock_client
            result = await service._match_sender_to_leads("user-1", "unknowncorp.com")

        assert result == []

    @pytest.mark.asyncio
    async def test_match_returns_lead_data(self, service: EmailLeadIntelligence) -> None:
        lead_data = [
            {"id": "lead-1", "company_name": "Savillex", "status": "active", "health_score": 65}
        ]
        mock_response = MagicMock()
        mock_response.data = lead_data

        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.eq.return_value.ilike.return_value.in_.return_value.execute.return_value = mock_response

        with patch("src.services.email_lead_intelligence.SupabaseClient") as mock_sb:
            mock_sb.get_client.return_value = mock_client
            result = await service._match_sender_to_leads("user-1", "savillex.com")

        assert len(result) == 1
        assert result[0]["company_name"] == "Savillex"


class TestSignalExtraction:
    """LLM output should be parsed into structured signals."""

    @pytest.mark.asyncio
    async def test_valid_json_parsed(self, service: EmailLeadIntelligence) -> None:
        llm_output = '[{"category": "competitor_mention", "detail": "Cytiva offering 20% discount", "confidence": 0.85}]'

        with patch.object(service._llm, "generate_response", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = llm_output
            signals = await service._extract_signals("body", "subject", "", "user-1")

        assert len(signals) == 1
        assert signals[0]["category"] == "competitor_mention"
        assert signals[0]["confidence"] == 0.85

    @pytest.mark.asyncio
    async def test_empty_array_returned(self, service: EmailLeadIntelligence) -> None:
        with patch.object(service._llm, "generate_response", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "[]"
            signals = await service._extract_signals("body", "subject", "", "user-1")

        assert signals == []

    @pytest.mark.asyncio
    async def test_low_confidence_filtered(self, service: EmailLeadIntelligence) -> None:
        llm_output = '[{"category": "sentiment_shift", "detail": "maybe slightly warmer", "confidence": 0.4}]'

        with patch.object(service._llm, "generate_response", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = llm_output
            signals = await service._extract_signals("body", "subject", "", "user-1")

        assert signals == []

    @pytest.mark.asyncio
    async def test_malformed_json_returns_empty(self, service: EmailLeadIntelligence) -> None:
        with patch.object(service._llm, "generate_response", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "not json at all"
            signals = await service._extract_signals("body", "subject", "", "user-1")

        assert signals == []

    @pytest.mark.asyncio
    async def test_markdown_fences_stripped(self, service: EmailLeadIntelligence) -> None:
        llm_output = '```json\n[{"category": "budget_signal", "detail": "Q3 budget approved", "confidence": 0.9}]\n```'

        with patch.object(service._llm, "generate_response", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = llm_output
            signals = await service._extract_signals("body", "subject", "", "user-1")

        assert len(signals) == 1
        assert signals[0]["category"] == "budget_signal"

    @pytest.mark.asyncio
    async def test_empty_body_returns_empty(self, service: EmailLeadIntelligence) -> None:
        signals = await service._extract_signals("", "", "", "user-1")
        assert signals == []

    @pytest.mark.asyncio
    async def test_llm_error_returns_empty(self, service: EmailLeadIntelligence) -> None:
        with patch.object(service._llm, "generate_response", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = Exception("API error")
            signals = await service._extract_signals("body", "subject", "", "user-1")

        assert signals == []

    @pytest.mark.asyncio
    async def test_multiple_signals_extracted(self, service: EmailLeadIntelligence) -> None:
        llm_output = """[
            {"category": "competitor_mention", "detail": "Cytiva pricing pressure", "confidence": 0.8},
            {"category": "timeline_shift", "detail": "Q3 deadline moved to Q4", "confidence": 0.75},
            {"category": "budget_signal", "detail": "Budget approved for 2026", "confidence": 0.9}
        ]"""

        with patch.object(service._llm, "generate_response", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = llm_output
            signals = await service._extract_signals("body", "subject", "", "user-1")

        assert len(signals) == 3


class TestEventRecording:
    """Signals should be recorded as lead events with EventType.SIGNAL."""

    @pytest.mark.asyncio
    async def test_signal_recorded_as_event(self, service: EmailLeadIntelligence) -> None:
        lead = {"id": "lead-1", "company_name": "Savillex", "status": "active", "health_score": 65}
        signal = {"category": "competitor_mention", "detail": "Cytiva 20% discount", "confidence": 0.85}

        mock_response = MagicMock()
        mock_response.data = [{"id": "event-1"}]

        mock_client = MagicMock()
        mock_client.table.return_value.insert.return_value.execute.return_value = mock_response

        # Patch SupabaseClient at source — LeadEventService late-imports from src.db.supabase
        with patch("src.db.supabase.SupabaseClient") as mock_sb:
            mock_sb.get_client.return_value = mock_client

            await service._record_signal("user-1", lead, signal)

            # Verify insert was called on lead_memory_events table
            mock_client.table.assert_called_with("lead_memory_events")


class TestFullPipeline:
    """End-to-end test of process_email_for_leads."""

    @pytest.mark.asyncio
    async def test_full_pipeline_with_match(self, service: EmailLeadIntelligence) -> None:
        lead_data = [
            {"id": "lead-1", "company_name": "Savillex", "status": "active", "health_score": 65}
        ]
        signals = [
            {"category": "competitor_mention", "detail": "Cytiva 20% discount", "confidence": 0.85}
        ]

        with (
            patch.object(service, "_match_sender_to_leads", new_callable=AsyncMock) as mock_match,
            patch.object(service, "_extract_signals", new_callable=AsyncMock) as mock_extract,
            patch.object(service, "_record_signal", new_callable=AsyncMock) as mock_record,
            patch.object(service._lead_service, "calculate_health_score", new_callable=AsyncMock),
        ):
            mock_match.return_value = lead_data
            mock_extract.return_value = signals

            result = await service.process_email_for_leads(
                user_id="user-1",
                email={
                    "sender_email": "rob@savillex.com",
                    "subject": "Re: Q3 Pricing",
                    "body": "Cytiva offered us 20% off their standard rates.",
                },
                thread_summary="Discussing pricing for Q3 order.",
            )

        assert len(result) == 1
        assert result[0]["lead_id"] == "lead-1"
        assert result[0]["company"] == "Savillex"
        assert result[0]["signal"]["category"] == "competitor_mention"
        mock_record.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_signals_returns_empty(self, service: EmailLeadIntelligence) -> None:
        lead_data = [
            {"id": "lead-1", "company_name": "Savillex", "status": "active", "health_score": 65}
        ]

        with (
            patch.object(service, "_match_sender_to_leads", new_callable=AsyncMock) as mock_match,
            patch.object(service, "_extract_signals", new_callable=AsyncMock) as mock_extract,
        ):
            mock_match.return_value = lead_data
            mock_extract.return_value = []

            result = await service.process_email_for_leads(
                user_id="user-1",
                email={
                    "sender_email": "rob@savillex.com",
                    "subject": "Thanks",
                    "body": "Thanks for the meeting.",
                },
            )

        assert result == []

    @pytest.mark.asyncio
    async def test_health_recalc_on_deal_signal(self, service: EmailLeadIntelligence) -> None:
        lead_data = [
            {"id": "lead-1", "company_name": "APC", "status": "active", "health_score": 50}
        ]
        signals = [
            {"category": "deal_stage_signal", "detail": "Procurement approved", "confidence": 0.9}
        ]

        with (
            patch.object(service, "_match_sender_to_leads", new_callable=AsyncMock) as mock_match,
            patch.object(service, "_extract_signals", new_callable=AsyncMock) as mock_extract,
            patch.object(service, "_record_signal", new_callable=AsyncMock),
            patch.object(
                service._lead_service, "calculate_health_score", new_callable=AsyncMock,
            ) as mock_health,
        ):
            mock_match.return_value = lead_data
            mock_extract.return_value = signals

            await service.process_email_for_leads(
                user_id="user-1",
                email={
                    "sender_email": "john@apc.com",
                    "subject": "Procurement update",
                    "body": "Our procurement team has approved the purchase.",
                },
            )

        mock_health.assert_called_once_with("user-1", "lead-1")

    @pytest.mark.asyncio
    async def test_match_failure_returns_empty(self, service: EmailLeadIntelligence) -> None:
        with patch.object(service, "_match_sender_to_leads", new_callable=AsyncMock) as mock_match:
            mock_match.side_effect = Exception("DB error")

            result = await service.process_email_for_leads(
                user_id="user-1",
                email={
                    "sender_email": "rob@savillex.com",
                    "subject": "test",
                    "body": "test",
                },
            )

        assert result == []

    @pytest.mark.asyncio
    async def test_body_dict_handled(self, service: EmailLeadIntelligence) -> None:
        """Email body may come as a dict with 'content' key."""
        with (
            patch.object(service, "_match_sender_to_leads", new_callable=AsyncMock) as mock_match,
            patch.object(service, "_extract_signals", new_callable=AsyncMock) as mock_extract,
        ):
            mock_match.return_value = [
                {"id": "lead-1", "company_name": "Test Corp", "status": "active", "health_score": 50}
            ]
            mock_extract.return_value = []

            await service.process_email_for_leads(
                user_id="user-1",
                email={
                    "sender_email": "contact@testcorp.com",
                    "subject": "Update",
                    "body": {"content": "Some email content here"},
                },
            )

        # Verify _extract_signals was called (body dict was handled)
        mock_extract.assert_called_once()
        call_args = mock_extract.call_args
        assert call_args.kwargs.get("body") == "Some email content here" or call_args[0][0] == "Some email content here"
