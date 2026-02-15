"""Tests for per-recipient style analysis in email bootstrap."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestEmailBootstrapRecipientProfiles:
    """Tests for recipient profile building during bootstrap."""

    @pytest.mark.asyncio
    async def test_bootstrap_calls_recipient_analysis(self):
        """Bootstrap calls analyze_recipient_samples after fetching emails."""
        from src.onboarding.email_bootstrap import PriorityEmailIngestion

        service = PriorityEmailIngestion.__new__(PriorityEmailIngestion)
        service._db = MagicMock()
        service._llm = AsyncMock()

        emails = [
            {
                "to": ["sarah@team.com"],
                "cc": [],
                "body": "Hey Sarah, quick sync?",
                "date": "2026-02-10T10:00:00Z",
                "subject": "sync",
                "thread_id": "t1",
            },
            {
                "to": ["boss@client.com"],
                "cc": [],
                "body": "Dear Mr. Smith, Following up on our discussion...",
                "date": "2026-02-10T14:00:00Z",
                "subject": "follow up",
                "thread_id": "t2",
            },
        ]

        # Mock all bootstrap methods to isolate recipient analysis
        service._load_exclusions = AsyncMock(return_value=[])
        service._fetch_sent_emails = AsyncMock(return_value=emails)
        service._apply_exclusions = MagicMock(return_value=emails)
        service._extract_contacts = AsyncMock(return_value=[])
        service._identify_active_threads = AsyncMock(return_value=[])
        service._detect_commitments = AsyncMock(return_value=[])
        service._extract_writing_samples = MagicMock(return_value=[])
        service._analyze_patterns = MagicMock(
            return_value=MagicMock(model_dump=MagicMock(return_value={}))
        )
        service._store_contacts = AsyncMock()
        service._store_threads = AsyncMock()
        service._store_commitments = AsyncMock()
        service._refine_writing_style = AsyncMock()
        service._store_patterns = AsyncMock()
        service._build_recipient_profiles = AsyncMock()
        service._store_bootstrap_status = AsyncMock()
        service._update_readiness = AsyncMock()
        service._record_episodic = AsyncMock()
        service._trigger_retroactive_enrichment = AsyncMock()

        with patch("src.services.activity_service.ActivityService", autospec=True):
            result = await service.run_bootstrap("user-123")

        # Verify recipient profile building was called with the emails
        service._build_recipient_profiles.assert_called_once_with("user-123", emails)

    @pytest.mark.asyncio
    async def test_build_recipient_profiles_delegates_to_writing_analysis(self):
        """_build_recipient_profiles calls WritingAnalysisService."""
        from src.onboarding.email_bootstrap import PriorityEmailIngestion

        service = PriorityEmailIngestion.__new__(PriorityEmailIngestion)
        service._db = MagicMock()
        service._llm = AsyncMock()

        emails = [
            {"to": ["a@b.com"], "body": "Hello", "date": "2026-02-10T10:00:00Z", "subject": "hi"},
        ]

        mock_analysis = AsyncMock()
        mock_analysis.analyze_recipient_samples = AsyncMock(return_value=[])

        with patch(
            "src.onboarding.writing_analysis.WritingAnalysisService",
            return_value=mock_analysis,
        ):
            await service._build_recipient_profiles("user-123", emails)

        mock_analysis.analyze_recipient_samples.assert_called_once_with("user-123", emails)

    @pytest.mark.asyncio
    async def test_build_recipient_profiles_handles_failure_gracefully(self):
        """Failure in recipient analysis doesn't crash bootstrap."""
        from src.onboarding.email_bootstrap import PriorityEmailIngestion

        service = PriorityEmailIngestion.__new__(PriorityEmailIngestion)
        service._db = MagicMock()
        service._llm = AsyncMock()

        with patch(
            "src.onboarding.writing_analysis.WritingAnalysisService",
            side_effect=Exception("LLM down"),
        ):
            # Should not raise
            await service._build_recipient_profiles("user-123", [{"to": ["a@b.com"], "body": "hi"}])
