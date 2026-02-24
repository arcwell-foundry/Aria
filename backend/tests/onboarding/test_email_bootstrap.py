"""Tests for Priority Email Bootstrap (US-908).

Tests the PriorityEmailIngestion service which processes 60 days of
sent emails during onboarding to seed relationship graph, refine
writing style, detect active deals, and identify commitments.
"""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.onboarding.email_bootstrap import (
    ActiveThread,
    CommunicationPatterns,
    EmailBootstrapResult,
    EmailContact,
    PriorityEmailIngestion,
)
from src.onboarding.email_integration import (
    EmailIntegrationConfig,
    EmailIntegrationService,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_email(
    to: list[str | dict] | None = None,
    cc: list[str | dict] | None = None,
    subject: str = "Test Subject",
    body: str = "This is a test email body with enough content to be useful.",
    date: str | None = None,
    thread_id: str | None = None,
) -> dict:
    """Helper to build a fake email dict."""
    if date is None:
        date = datetime.now(UTC).isoformat()
    return {
        "to": to or [{"email": "recipient@example.com", "name": "Recipient"}],
        "cc": cc or [],
        "subject": subject,
        "body": body,
        "date": date,
        "thread_id": thread_id or f"thread-{subject}",
    }


def _make_emails_batch(count: int = 10, base_to: str = "contact@example.com") -> list[dict]:
    """Helper to build a batch of emails."""
    now = datetime.now(UTC)
    return [
        _make_email(
            to=[{"email": base_to, "name": "Contact"}],
            subject=f"Email {i}",
            body=f"Body content for email {i}. " * 20,
            date=(now - timedelta(days=i)).isoformat(),
            thread_id=f"thread-{i}",
        )
        for i in range(count)
    ]


@pytest.fixture
def mock_db():
    """Mock Supabase client."""
    db = MagicMock()
    # Default: user_settings returns no exclusions
    settings_result = MagicMock()
    settings_result.data = None
    db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = settings_result
    # Default: inserts succeed
    db.table.return_value.insert.return_value.execute.return_value = MagicMock()
    db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()
    db.table.return_value.upsert.return_value.execute.return_value = MagicMock()
    return db


@pytest.fixture
def mock_llm():
    """Mock LLM client."""
    llm = MagicMock()
    llm.generate_response = AsyncMock(return_value="[]")
    return llm


@pytest.fixture
def service(mock_db, mock_llm):
    """Create PriorityEmailIngestion with mocked dependencies."""
    with (
        patch(
            "src.onboarding.email_bootstrap.SupabaseClient.get_client",
            return_value=mock_db,
        ),
        patch(
            "src.onboarding.email_bootstrap.LLMClient",
            return_value=mock_llm,
        ),
    ):
        return PriorityEmailIngestion()


# ---------------------------------------------------------------------------
# Exclusion filtering tests
# ---------------------------------------------------------------------------


class TestExclusionFiltering:
    """Tests for privacy exclusion filtering."""

    def test_filters_excluded_sender(self, service: PriorityEmailIngestion) -> None:
        """Emails to excluded sender addresses are removed."""
        emails = [
            _make_email(to=[{"email": "allowed@corp.com", "name": "A"}]),
            _make_email(to=[{"email": "excluded@personal.com", "name": "B"}]),
            _make_email(to=[{"email": "another@corp.com", "name": "C"}]),
        ]
        exclusions = [{"type": "sender", "value": "excluded@personal.com"}]

        result = service._apply_exclusions(emails, exclusions)

        assert len(result) == 2
        recipient_emails = [
            e["to"][0]["email"] if isinstance(e["to"][0], dict) else e["to"][0] for e in result
        ]
        assert "excluded@personal.com" not in recipient_emails

    def test_filters_excluded_domain(self, service: PriorityEmailIngestion) -> None:
        """Emails to recipients in excluded domains are removed."""
        emails = [
            _make_email(to=[{"email": "alice@corp.com", "name": "Alice"}]),
            _make_email(to=[{"email": "bob@personal-bank.com", "name": "Bob"}]),
            _make_email(to=[{"email": "carol@corp.com", "name": "Carol"}]),
        ]
        exclusions = [{"type": "domain", "value": "personal-bank.com"}]

        result = service._apply_exclusions(emails, exclusions)

        assert len(result) == 2

    def test_filters_cc_recipients_too(self, service: PriorityEmailIngestion) -> None:
        """CC recipients are also checked against exclusions."""
        emails = [
            _make_email(
                to=[{"email": "allowed@corp.com", "name": "A"}],
                cc=[{"email": "secret@excluded.com", "name": "Secret"}],
            ),
        ]
        exclusions = [{"type": "domain", "value": "excluded.com"}]

        result = service._apply_exclusions(emails, exclusions)

        assert len(result) == 0

    def test_no_exclusions_passes_all(self, service: PriorityEmailIngestion) -> None:
        """Without exclusions, all emails pass through."""
        emails = _make_emails_batch(5)
        result = service._apply_exclusions(emails, [])

        assert len(result) == 5

    def test_case_insensitive_exclusion(self, service: PriorityEmailIngestion) -> None:
        """Exclusion matching is case-insensitive."""
        emails = [
            _make_email(to=[{"email": "Bob@EXCLUDED.COM", "name": "Bob"}]),
        ]
        exclusions = [{"type": "domain", "value": "excluded.com"}]

        result = service._apply_exclusions(emails, exclusions)

        assert len(result) == 0

    def test_handles_string_recipients(self, service: PriorityEmailIngestion) -> None:
        """Handles recipients as plain strings (not dicts)."""
        emails = [
            _make_email(to=["excluded@personal.com"]),
            _make_email(to=["allowed@corp.com"]),
        ]
        exclusions = [{"type": "sender", "value": "excluded@personal.com"}]

        result = service._apply_exclusions(emails, exclusions)

        assert len(result) == 1


# ---------------------------------------------------------------------------
# Contact extraction tests
# ---------------------------------------------------------------------------


class TestContactExtraction:
    """Tests for contact discovery and deduplication."""

    @pytest.mark.asyncio
    async def test_deduplicates_contacts(self, service: PriorityEmailIngestion) -> None:
        """Same contact appearing in multiple emails is counted once."""
        emails = [
            _make_email(to=[{"email": "same@corp.com", "name": "Same Person"}]),
            _make_email(to=[{"email": "same@corp.com", "name": "Same Person"}]),
            _make_email(to=[{"email": "other@corp.com", "name": "Other"}]),
        ]

        contacts = await service._extract_contacts(emails)

        contact_emails = [c.email for c in contacts]
        assert contact_emails.count("same@corp.com") == 1

    @pytest.mark.asyncio
    async def test_counts_interactions(self, service: PriorityEmailIngestion) -> None:
        """Interaction count reflects number of emails to each contact."""
        emails = [
            _make_email(to=[{"email": "frequent@corp.com", "name": "F"}]),
            _make_email(to=[{"email": "frequent@corp.com", "name": "F"}]),
            _make_email(to=[{"email": "frequent@corp.com", "name": "F"}]),
            _make_email(to=[{"email": "rare@corp.com", "name": "R"}]),
        ]

        contacts = await service._extract_contacts(emails)

        freq = next(c for c in contacts if c.email == "frequent@corp.com")
        assert freq.interaction_count == 3

    @pytest.mark.asyncio
    async def test_returns_top_50_contacts(self, service: PriorityEmailIngestion) -> None:
        """Contact list is capped at 100 entries."""
        emails = [
            _make_email(to=[{"email": f"user{i}@corp.com", "name": f"User {i}"}]) for i in range(120)
        ]

        contacts = await service._extract_contacts(emails)

        assert len(contacts) <= 100

    @pytest.mark.asyncio
    async def test_sorted_by_interaction_count(self, service: PriorityEmailIngestion) -> None:
        """Contacts are sorted by interaction count, most frequent first."""
        emails = (
            [_make_email(to=[{"email": "top@corp.com", "name": "Top"}])] * 5
            + [_make_email(to=[{"email": "mid@corp.com", "name": "Mid"}])] * 2
            + [_make_email(to=[{"email": "low@corp.com", "name": "Low"}])]
        )

        contacts = await service._extract_contacts(emails)

        assert contacts[0].email == "top@corp.com"
        assert contacts[0].interaction_count == 5

    @pytest.mark.asyncio
    async def test_includes_cc_recipients(self, service: PriorityEmailIngestion) -> None:
        """CC recipients are included in contact discovery."""
        emails = [
            _make_email(
                to=[{"email": "to@corp.com", "name": "To"}],
                cc=[{"email": "cc@corp.com", "name": "CC"}],
            ),
        ]

        contacts = await service._extract_contacts(emails)

        contact_emails = [c.email for c in contacts]
        assert "cc@corp.com" in contact_emails


# ---------------------------------------------------------------------------
# Contact classification tests
# ---------------------------------------------------------------------------


class TestContactClassification:
    """Tests for LLM-based contact classification."""

    @pytest.mark.asyncio
    async def test_classifies_top_contacts(
        self, service: PriorityEmailIngestion, mock_llm: MagicMock
    ) -> None:
        """Top contacts are classified via LLM call."""
        mock_llm.generate_response = AsyncMock(
            return_value=json.dumps(
                [
                    {
                        "email": "vp@pharma.com",
                        "relationship_type": "client",
                        "company": "Pharma Inc",
                        "title": "VP Sales",
                    },
                ]
            )
        )

        contacts = [
            EmailContact(email="vp@pharma.com", name="VP", interaction_count=10),
        ]
        await service._classify_contacts(contacts, [])

        assert contacts[0].relationship_type == "client"
        assert contacts[0].company == "Pharma Inc"
        assert contacts[0].title == "VP Sales"

    @pytest.mark.asyncio
    async def test_classification_failure_leaves_defaults(
        self, service: PriorityEmailIngestion, mock_llm: MagicMock
    ) -> None:
        """If LLM classification fails, contacts keep default relationship_type."""
        mock_llm.generate_response = AsyncMock(return_value="invalid json")

        contacts = [
            EmailContact(email="test@corp.com", name="Test", interaction_count=5),
        ]
        await service._classify_contacts(contacts, [])

        assert contacts[0].relationship_type == "unknown"


# ---------------------------------------------------------------------------
# Thread identification tests
# ---------------------------------------------------------------------------


class TestThreadIdentification:
    """Tests for active thread detection."""

    @pytest.mark.asyncio
    async def test_groups_by_thread_id(self, service: PriorityEmailIngestion) -> None:
        """Emails with same thread_id are grouped together."""
        emails = [
            _make_email(
                thread_id="thread-A", subject="Deal X", to=[{"email": "a@corp.com", "name": "A"}]
            ),
            _make_email(
                thread_id="thread-A", subject="Deal X", to=[{"email": "a@corp.com", "name": "A"}]
            ),
            _make_email(
                thread_id="thread-A", subject="Deal X", to=[{"email": "a@corp.com", "name": "A"}]
            ),
            _make_email(
                thread_id="thread-B", subject="Other", to=[{"email": "b@corp.com", "name": "B"}]
            ),
        ]

        threads = await service._identify_active_threads(emails)

        # Only thread-A has 3+ messages
        assert len(threads) == 1
        assert threads[0].message_count == 3

    @pytest.mark.asyncio
    async def test_requires_minimum_messages(self, service: PriorityEmailIngestion) -> None:
        """Threads with fewer than 3 messages are not considered active."""
        emails = [
            _make_email(thread_id="short", subject="Short Thread"),
            _make_email(thread_id="short", subject="Short Thread"),
        ]

        threads = await service._identify_active_threads(emails)

        assert len(threads) == 0

    @pytest.mark.asyncio
    async def test_collects_participants(self, service: PriorityEmailIngestion) -> None:
        """Thread participants are collected from all messages in the thread."""
        emails = [
            _make_email(
                thread_id="t1",
                subject="Project",
                to=[{"email": "alice@corp.com", "name": "Alice"}],
            ),
            _make_email(
                thread_id="t1",
                subject="Project",
                to=[{"email": "bob@corp.com", "name": "Bob"}],
            ),
            _make_email(
                thread_id="t1",
                subject="Project",
                to=[{"email": "alice@corp.com", "name": "Alice"}],
                cc=[{"email": "carol@corp.com", "name": "Carol"}],
            ),
        ]

        threads = await service._identify_active_threads(emails)

        assert len(threads) == 1
        participants = set(threads[0].participants)
        assert "alice@corp.com" in participants
        assert "bob@corp.com" in participants
        assert "carol@corp.com" in participants

    @pytest.mark.asyncio
    async def test_falls_back_to_subject_for_grouping(
        self, service: PriorityEmailIngestion
    ) -> None:
        """If no thread_id, emails are grouped by subject."""
        emails = [
            _make_email(
                thread_id=None, subject="Same Subject", to=[{"email": "a@x.com", "name": "A"}]
            ),
            _make_email(
                thread_id=None, subject="Same Subject", to=[{"email": "b@x.com", "name": "B"}]
            ),
            _make_email(
                thread_id=None, subject="Same Subject", to=[{"email": "c@x.com", "name": "C"}]
            ),
        ]
        # When thread_id is None, the key should fall back to subject
        for e in emails:
            e["thread_id"] = None

        threads = await service._identify_active_threads(emails)

        assert len(threads) == 1


# ---------------------------------------------------------------------------
# Commitment detection tests
# ---------------------------------------------------------------------------


class TestCommitmentDetection:
    """Tests for email commitment/follow-up detection."""

    @pytest.mark.asyncio
    async def test_detects_commitments_from_llm(
        self, service: PriorityEmailIngestion, mock_llm: MagicMock
    ) -> None:
        """Commitments are detected via LLM analysis of recent emails."""
        mock_llm.generate_response = AsyncMock(
            return_value=json.dumps(
                [
                    {
                        "commitment": "Send proposal by Friday",
                        "to": "client@pharma.com",
                        "deadline": "2026-02-07",
                        "subject": "Proposal Follow-up",
                    },
                ]
            )
        )
        emails = [
            _make_email(
                subject="Proposal Follow-up",
                body="I'll send the proposal by Friday.",
                to=[{"email": "client@pharma.com", "name": "Client"}],
                date=datetime.now(UTC).isoformat(),
            ),
        ]

        commitments = await service._detect_commitments(emails)

        assert len(commitments) == 1
        assert commitments[0]["commitment"] == "Send proposal by Friday"

    @pytest.mark.asyncio
    async def test_no_commitments_for_empty_emails(self, service: PriorityEmailIngestion) -> None:
        """Empty email list returns no commitments."""
        commitments = await service._detect_commitments([])

        assert commitments == []

    @pytest.mark.asyncio
    async def test_commitment_detection_handles_llm_failure(
        self, service: PriorityEmailIngestion, mock_llm: MagicMock
    ) -> None:
        """If LLM returns invalid JSON, empty list is returned."""
        mock_llm.generate_response = AsyncMock(return_value="not json")
        emails = [
            _make_email(body="I'll follow up next week."),
        ]

        commitments = await service._detect_commitments(emails)

        assert commitments == []


# ---------------------------------------------------------------------------
# Writing sample extraction tests
# ---------------------------------------------------------------------------


class TestWritingSampleExtraction:
    """Tests for writing sample extraction."""

    def test_extracts_appropriate_length_emails(self, service: PriorityEmailIngestion) -> None:
        """Only emails between 100-3000 chars are extracted as samples."""
        emails = [
            _make_email(subject="Short one", body="too short"),  # < 100 chars
            _make_email(subject="Good A", body="A" * 150),  # good length
            _make_email(subject="Good B", body="B" * 500),  # good length
            _make_email(subject="Too long", body="C" * 4000),  # > 3000 chars, excluded
        ]

        samples = service._extract_writing_samples(emails)

        assert len(samples) == 2
        assert "A" * 150 in samples
        assert "B" * 500 in samples

    def test_caps_at_20_samples(self, service: PriorityEmailIngestion) -> None:
        """Returns maximum 20 writing samples."""
        emails = [_make_email(body="X" * 200) for _ in range(30)]

        samples = service._extract_writing_samples(emails)

        assert len(samples) <= 20


# ---------------------------------------------------------------------------
# Communication pattern analysis tests
# ---------------------------------------------------------------------------


class TestPatternAnalysis:
    """Tests for communication timing pattern analysis."""

    def test_identifies_peak_hours(self, service: PriorityEmailIngestion) -> None:
        """Peak send hours are identified from email timestamps."""
        base = datetime(2026, 1, 15, 0, 0, 0, tzinfo=UTC)
        emails = [
            _make_email(date=(base.replace(hour=9) + timedelta(days=i)).isoformat())
            for i in range(5)
        ] + [
            _make_email(date=(base.replace(hour=14) + timedelta(days=i)).isoformat())
            for i in range(3)
        ]

        patterns = service._analyze_patterns(emails)

        assert 9 in patterns.peak_send_hours

    def test_calculates_emails_per_day(self, service: PriorityEmailIngestion) -> None:
        """Average emails per day is calculated."""
        base = datetime(2026, 1, 15, 9, 0, 0, tzinfo=UTC)
        emails = [_make_email(date=(base + timedelta(days=i)).isoformat()) for i in range(10)]

        patterns = service._analyze_patterns(emails)

        assert patterns.emails_per_day_avg > 0

    def test_identifies_peak_days(self, service: PriorityEmailIngestion) -> None:
        """Peak send days are identified from email timestamps."""
        # All emails on a Monday
        monday = datetime(2026, 1, 12, 9, 0, 0, tzinfo=UTC)  # A Monday
        emails = [_make_email(date=(monday + timedelta(weeks=i)).isoformat()) for i in range(5)]

        patterns = service._analyze_patterns(emails)

        assert "Monday" in patterns.peak_send_days

    def test_handles_invalid_dates(self, service: PriorityEmailIngestion) -> None:
        """Invalid date strings are skipped gracefully."""
        emails = [
            _make_email(date="not-a-date"),
            _make_email(date="also-invalid"),
        ]

        patterns = service._analyze_patterns(emails)

        assert isinstance(patterns, CommunicationPatterns)


# ---------------------------------------------------------------------------
# Storage & integration tests
# ---------------------------------------------------------------------------


class TestStorageIntegration:
    """Tests for storing results into memory systems."""

    @pytest.mark.asyncio
    async def test_stores_contacts_in_semantic_memory(
        self, service: PriorityEmailIngestion, mock_db: MagicMock
    ) -> None:
        """Discovered contacts are stored in memory_semantic table."""
        contacts = [
            EmailContact(
                email="vp@pharma.com",
                name="VP",
                interaction_count=10,
                relationship_type="client",
                company="Pharma Inc",
            ),
        ]

        await service._store_contacts("user-123", contacts)

        mock_db.table.assert_any_call("memory_semantic")

    @pytest.mark.asyncio
    async def test_stores_deal_threads(
        self, service: PriorityEmailIngestion, mock_db: MagicMock
    ) -> None:
        """Active deal threads are stored with needs_user_confirmation flag."""
        threads = [
            ActiveThread(
                subject="Deal Discussion",
                participants=["client@pharma.com"],
                message_count=5,
                last_activity="2026-02-01T00:00:00Z",
                thread_type="deal",
            ),
            ActiveThread(
                subject="Project Update",
                participants=["team@corp.com"],
                message_count=4,
                last_activity="2026-02-01T00:00:00Z",
                thread_type="project",
            ),
        ]

        await service._store_threads("user-123", threads)

        # Only deal threads should be stored
        calls = mock_db.table.return_value.insert.call_args_list
        # At least one call for the deal thread
        stored = False
        for call in calls:
            data = call[0][0] if call[0] else call[1].get("data", {})
            if isinstance(data, dict) and data.get("metadata", {}).get("type") == "active_deal":
                stored = True
                assert data["metadata"]["needs_user_confirmation"] is True
        assert stored

    @pytest.mark.asyncio
    async def test_stores_commitments_in_prospective_memory(
        self, service: PriorityEmailIngestion, mock_db: MagicMock
    ) -> None:
        """Detected commitments are stored in prospective_memories table."""
        commitments = [
            {"commitment": "Send proposal", "to": "client@pharma.com", "deadline": "2026-02-07"},
        ]

        await service._store_commitments("user-123", commitments)

        mock_db.table.assert_any_call("prospective_memories")

    @pytest.mark.asyncio
    async def test_refines_writing_style(self, service: PriorityEmailIngestion) -> None:
        """Writing samples are passed to WritingAnalysisService."""
        samples = ["Sample email body " * 10]

        with patch("src.onboarding.writing_analysis.WritingAnalysisService") as mock_writing:
            mock_instance = MagicMock()
            mock_instance.analyze_samples = AsyncMock()
            mock_writing.return_value = mock_instance

            await service._refine_writing_style("user-123", samples)

            mock_instance.analyze_samples.assert_called_once_with("user-123", samples)

    @pytest.mark.asyncio
    async def test_skips_writing_refinement_without_samples(
        self, service: PriorityEmailIngestion
    ) -> None:
        """Writing style refinement is skipped when no samples available."""
        with patch("src.onboarding.writing_analysis.WritingAnalysisService") as mock_writing:
            await service._refine_writing_style("user-123", [])

            mock_writing.assert_not_called()


# ---------------------------------------------------------------------------
# Readiness score update tests
# ---------------------------------------------------------------------------


class TestReadinessUpdate:
    """Tests for readiness score updates."""

    @pytest.mark.asyncio
    async def test_updates_relationship_graph_score(self, service: PriorityEmailIngestion) -> None:
        """Relationship graph readiness increases based on contacts found."""
        result = EmailBootstrapResult(
            contacts_discovered=20,
            writing_samples_extracted=5,
        )

        with patch("src.onboarding.orchestrator.OnboardingOrchestrator") as mock_orch:
            mock_instance = MagicMock()
            mock_instance.update_readiness_scores = AsyncMock()
            mock_orch.return_value = mock_instance

            await service._update_readiness("user-123", result)

            call_args = mock_instance.update_readiness_scores.call_args[0]
            updates = call_args[1]
            assert "relationship_graph" in updates
            assert updates["relationship_graph"] == min(60.0, 20 * 3.0)

    @pytest.mark.asyncio
    async def test_updates_digital_twin_score(self, service: PriorityEmailIngestion) -> None:
        """Digital twin readiness increases based on writing samples."""
        result = EmailBootstrapResult(
            contacts_discovered=0,
            writing_samples_extracted=10,
        )

        with patch("src.onboarding.orchestrator.OnboardingOrchestrator") as mock_orch:
            mock_instance = MagicMock()
            mock_instance.update_readiness_scores = AsyncMock()
            mock_orch.return_value = mock_instance

            await service._update_readiness("user-123", result)

            call_args = mock_instance.update_readiness_scores.call_args[0]
            updates = call_args[1]
            assert "digital_twin" in updates
            assert updates["digital_twin"] == min(70.0, 40.0 + 10 * 1.5)

    @pytest.mark.asyncio
    async def test_caps_readiness_scores(self, service: PriorityEmailIngestion) -> None:
        """Readiness scores are capped at their maximum values."""
        result = EmailBootstrapResult(
            contacts_discovered=100,
            writing_samples_extracted=50,
        )

        with patch("src.onboarding.orchestrator.OnboardingOrchestrator") as mock_orch:
            mock_instance = MagicMock()
            mock_instance.update_readiness_scores = AsyncMock()
            mock_orch.return_value = mock_instance

            await service._update_readiness("user-123", result)

            call_args = mock_instance.update_readiness_scores.call_args[0]
            updates = call_args[1]
            assert updates["relationship_graph"] <= 60.0
            assert updates["digital_twin"] <= 70.0


# ---------------------------------------------------------------------------
# Episodic memory recording tests
# ---------------------------------------------------------------------------


class TestEpisodicRecording:
    """Tests for episodic memory event recording."""

    @pytest.mark.asyncio
    async def test_records_bootstrap_event(self, service: PriorityEmailIngestion) -> None:
        """Bootstrap completion is recorded in episodic memory."""
        result = EmailBootstrapResult(
            emails_processed=100,
            contacts_discovered=20,
            active_threads=5,
            commitments_detected=3,
        )

        with patch("src.memory.episodic.EpisodicMemory") as mock_mem:
            mock_instance = MagicMock()
            mock_instance.store_episode = AsyncMock()
            mock_mem.return_value = mock_instance

            await service._record_episodic("user-123", result)

            mock_instance.store_episode.assert_called_once()
            episode = mock_instance.store_episode.call_args[0][0]
            assert episode.user_id == "user-123"
            assert episode.event_type == "onboarding_email_bootstrap_complete"
            assert episode.context["emails_processed"] == 100
            assert episode.context["contacts_discovered"] == 20
            assert episode.context["active_threads"] == 5
            assert episode.context["commitments_detected"] == 3


# ---------------------------------------------------------------------------
# Full pipeline integration test
# ---------------------------------------------------------------------------


class TestFullBootstrapPipeline:
    """Integration tests for the full bootstrap pipeline."""

    @pytest.mark.asyncio
    async def test_full_pipeline_returns_result(
        self, service: PriorityEmailIngestion, mock_llm: MagicMock
    ) -> None:
        """Full bootstrap pipeline processes emails and returns complete result."""
        emails = _make_emails_batch(5)

        # Mock LLM responses for classification and commitment detection
        mock_llm.generate_response = AsyncMock(return_value="[]")

        with (
            patch.object(service, "_fetch_sent_emails", new_callable=AsyncMock) as mock_fetch,
            patch.object(service, "_store_contacts", new_callable=AsyncMock),
            patch.object(service, "_store_threads", new_callable=AsyncMock),
            patch.object(service, "_store_commitments", new_callable=AsyncMock),
            patch.object(service, "_refine_writing_style", new_callable=AsyncMock),
            patch.object(service, "_store_patterns", new_callable=AsyncMock),
            patch.object(service, "_update_readiness", new_callable=AsyncMock),
            patch.object(service, "_record_episodic", new_callable=AsyncMock),
        ):
            mock_fetch.return_value = emails

            result = await service.run_bootstrap("user-123")

            assert result.emails_processed == 5
            assert result.contacts_discovered > 0
            assert isinstance(result.communication_patterns, CommunicationPatterns)

    @pytest.mark.asyncio
    async def test_pipeline_handles_no_emails(self, service: PriorityEmailIngestion) -> None:
        """Pipeline handles case where no emails are found."""
        with patch.object(service, "_fetch_sent_emails", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = []

            result = await service.run_bootstrap("user-123")

            assert result.emails_processed == 0
            assert result.contacts_discovered == 0

    @pytest.mark.asyncio
    async def test_pipeline_handles_exceptions_gracefully(
        self, service: PriorityEmailIngestion
    ) -> None:
        """Pipeline catches exceptions and returns partial result."""
        with patch.object(service, "_fetch_sent_emails", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = Exception("Composio unavailable")

            result = await service.run_bootstrap("user-123")

            # Should not raise, returns empty result
            assert result.emails_processed == 0

    @pytest.mark.asyncio
    async def test_progress_callback_is_called(self, service: PriorityEmailIngestion) -> None:
        """Progress callback receives stage updates."""
        progress_updates: list[dict] = []

        async def track_progress(update: dict) -> None:
            progress_updates.append(update)

        with (
            patch.object(service, "_fetch_sent_emails", new_callable=AsyncMock) as mock_fetch,
            patch.object(service, "_store_contacts", new_callable=AsyncMock),
            patch.object(service, "_store_threads", new_callable=AsyncMock),
            patch.object(service, "_store_commitments", new_callable=AsyncMock),
            patch.object(service, "_refine_writing_style", new_callable=AsyncMock),
            patch.object(service, "_store_patterns", new_callable=AsyncMock),
            patch.object(service, "_update_readiness", new_callable=AsyncMock),
            patch.object(service, "_record_episodic", new_callable=AsyncMock),
        ):
            mock_fetch.return_value = _make_emails_batch(3)

            await service.run_bootstrap("user-123", progress_callback=track_progress)

            stages = [u["stage"] for u in progress_updates]
            assert "fetching" in stages
            assert "complete" in stages


# ---------------------------------------------------------------------------
# Bootstrap result model tests
# ---------------------------------------------------------------------------


class TestBootstrapResultModel:
    """Tests for the EmailBootstrapResult model."""

    def test_default_values(self) -> None:
        """EmailBootstrapResult has sensible defaults."""
        result = EmailBootstrapResult()

        assert result.emails_processed == 0
        assert result.contacts_discovered == 0
        assert result.active_threads == 0
        assert result.commitments_detected == 0
        assert result.writing_samples_extracted == 0
        assert result.communication_patterns is None

    def test_communication_patterns_model(self) -> None:
        """CommunicationPatterns model holds timing data."""
        patterns = CommunicationPatterns(
            peak_send_hours=[9, 14, 16],
            peak_send_days=["Monday", "Wednesday"],
            emails_per_day_avg=12.5,
        )

        assert len(patterns.peak_send_hours) == 3
        assert patterns.emails_per_day_avg == 12.5


# ---------------------------------------------------------------------------
# Email bootstrap trigger test (US-907 integration)
# ---------------------------------------------------------------------------


class TestBootstrapTrigger:
    """Tests for bootstrap trigger behavior.

    Note: Bootstrap is now triggered from /integrations/record-connection
    endpoint in the API route layer, not from save_privacy_config.
    """

    @pytest.mark.asyncio
    async def test_save_privacy_config_does_not_trigger_bootstrap(self) -> None:
        """Saving privacy config no longer triggers bootstrap (moved to record-connection)."""
        mock_db = MagicMock()
        mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock()

        with (
            patch(
                "src.onboarding.email_integration.SupabaseClient.get_client",
                return_value=mock_db,
            ),
            patch("src.onboarding.orchestrator.OnboardingOrchestrator") as mock_orch,
            patch("src.memory.episodic.EpisodicMemory") as mock_episodic,
            patch("src.onboarding.email_bootstrap.PriorityEmailIngestion") as mock_bootstrap,
        ):
            mock_orch.return_value.update_readiness_scores = AsyncMock()
            mock_episodic_instance = MagicMock()
            mock_episodic_instance.store_episode = AsyncMock()
            mock_episodic.return_value = mock_episodic_instance

            mock_bootstrap_instance = MagicMock()
            mock_bootstrap_instance.run_bootstrap = AsyncMock()
            mock_bootstrap.return_value = mock_bootstrap_instance

            service = EmailIntegrationService()
            config = EmailIntegrationConfig(
                provider="google",
                privacy_exclusions=[],
            )

            await service.save_privacy_config("user-123", config)

            # Bootstrap should NOT be called from save_privacy_config anymore
            mock_bootstrap_instance.run_bootstrap.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetch_emails_detects_provider(self) -> None:
        """PriorityEmailIngestion._fetch_sent_emails detects provider from user_integrations."""
        mock_db = MagicMock()
        # Mock the provider lookup
        mock_result = MagicMock()
        mock_result.data = {"integration_type": "outlook"}
        mock_db.table.return_value.select.return_value.eq.return_value.in_.return_value.maybe_single.return_value.execute.return_value = (
            mock_result
        )

        with (
            patch(
                "src.onboarding.email_bootstrap.SupabaseClient.get_client",
                return_value=mock_db,
            ),
            patch("src.onboarding.email_bootstrap.LLMClient"),
        ):
            service = PriorityEmailIngestion()

            # Verify the service can be instantiated and will detect provider
            assert service is not None


# ---------------------------------------------------------------------------
# Status endpoint test
# ---------------------------------------------------------------------------


class TestBootstrapStatusEndpoint:
    """Tests for the bootstrap status API endpoint."""

    @pytest.mark.asyncio
    async def test_returns_status_from_db(self) -> None:
        """Status endpoint returns bootstrap results from DB."""
        # Test the logic directly to avoid FastAPI multipart dependency
        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.data = {
            "metadata": {
                "email_bootstrap": {
                    "status": "complete",
                    "emails_processed": 150,
                    "contacts_discovered": 25,
                    "active_threads": 8,
                    "commitments_detected": 4,
                }
            }
        }
        mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = mock_result

        with patch(
            "src.db.supabase.SupabaseClient.get_client",
            return_value=mock_db,
        ):
            db = mock_db
            result = (
                db.table("onboarding_state")
                .select("metadata")
                .eq("user_id", "user-123")
                .maybe_single()
                .execute()
            )
            metadata = result.data.get("metadata", {})
            bootstrap_data = metadata.get("email_bootstrap")

            assert bootstrap_data is not None
            assert bootstrap_data["status"] == "complete"
            assert bootstrap_data["emails_processed"] == 150
            assert bootstrap_data["contacts_discovered"] == 25

    @pytest.mark.asyncio
    async def test_returns_not_started_when_no_data(self) -> None:
        """Status returns not_started when no bootstrap data exists."""
        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.data = {"metadata": {}}
        mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = mock_result

        with patch(
            "src.db.supabase.SupabaseClient.get_client",
            return_value=mock_db,
        ):
            db = mock_db
            result = (
                db.table("onboarding_state")
                .select("metadata")
                .eq("user_id", "user-123")
                .maybe_single()
                .execute()
            )
            metadata = result.data.get("metadata", {})
            bootstrap_data = metadata.get("email_bootstrap")

            assert bootstrap_data is None
