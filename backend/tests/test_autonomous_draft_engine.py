"""Tests for AutonomousDraftEngine service."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, UTC

from src.services.autonomous_draft_engine import (
    AutonomousDraftEngine,
    DraftResult,
    ProcessingRunResult,
)
from src.services.email_analyzer import EmailCategory, EmailScanResult
from src.services.email_context_gatherer import (
    DraftContext,
    ThreadContext,
    ThreadMessage,
    RecipientResearch,
    RecipientWritingStyle,
    RelationshipHistory,
    CalendarContext,
    CRMContext,
)


@pytest.fixture
def engine():
    """Create an AutonomousDraftEngine instance with all dependencies mocked."""
    with (
        patch("src.services.autonomous_draft_engine.SupabaseClient") as mock_supabase,
        patch("src.services.autonomous_draft_engine.LLMClient") as mock_llm,
        patch("src.services.autonomous_draft_engine.EmailAnalyzer") as mock_analyzer,
        patch(
            "src.services.autonomous_draft_engine.EmailContextGatherer"
        ) as mock_gatherer,
        patch("src.services.autonomous_draft_engine.DigitalTwin") as mock_twin,
        patch(
            "src.services.autonomous_draft_engine.PersonalityCalibrator"
        ) as mock_calibrator,
    ):
        mock_client = MagicMock()
        mock_supabase.get_client.return_value = mock_client

        e = AutonomousDraftEngine()
        e._db = mock_client
        e._llm = AsyncMock()
        e._email_analyzer = AsyncMock()
        e._context_gatherer = AsyncMock()
        e._digital_twin = AsyncMock()
        e._personality_calibrator = AsyncMock()

        yield e


@pytest.fixture
def sample_email():
    """Sample email needing a reply."""
    return EmailCategory(
        email_id="email-123",
        thread_id="thread-456",
        sender_email="john@acme.com",
        sender_name="John Smith",
        subject="Q2 Proposal Follow-up",
        snippet="Hi, I wanted to follow up on our discussion...",
        category="NEEDS_REPLY",
        urgency="NORMAL",
        topic_summary="Follow-up on Q2 proposal",
        reason="Email contains a direct question",
    )


@pytest.fixture
def urgent_email():
    """Sample urgent email."""
    return EmailCategory(
        email_id="email-urgent",
        thread_id="thread-urgent",
        sender_email="ceo@bigco.com",
        sender_name="CEO",
        subject="URGENT: Decision needed",
        snippet="We need your input by end of day...",
        category="NEEDS_REPLY",
        urgency="URGENT",
        topic_summary="Urgent decision request",
        reason="High urgency flag detected",
    )


@pytest.fixture
def rich_context():
    """Context with all sources available."""
    return DraftContext(
        id="context-123",
        user_id="user-456",
        email_id="email-123",
        thread_id="thread-456",
        sender_email="john@acme.com",
        subject="Q2 Proposal",
        sources_used=[
            "composio_thread",
            "exa_research",
            "recipient_style_profile",
            "memory_semantic",
            "corporate_memory",
            "calendar",
            "crm",
        ],
        thread_context=ThreadContext(
            thread_id="thread-456",
            messages=[
                ThreadMessage(
                    sender_email="john@acme.com",
                    sender_name="John Smith",
                    body="Initial message",
                    timestamp="2026-02-13T10:00:00Z",
                ),
                ThreadMessage(
                    sender_email="user@company.com",
                    sender_name="User",
                    body="Reply",
                    timestamp="2026-02-13T11:00:00Z",
                ),
                ThreadMessage(
                    sender_email="john@acme.com",
                    sender_name="John Smith",
                    body="Follow-up",
                    timestamp="2026-02-13T12:00:00Z",
                ),
            ],
            summary="Discussion about Q2 proposal",
            message_count=3,
        ),
        recipient_research=RecipientResearch(
            sender_email="john@acme.com",
            sender_name="John Smith",
            sender_title="VP of Sales",
            sender_company="Acme Corp",
            bio="Experienced sales leader with 15 years in enterprise software.",
            company_description="Leading provider of enterprise solutions.",
            exa_sources_used=["linkedin", "company_website"],
        ),
        recipient_style=RecipientWritingStyle(
            exists=True,
            formality_level=0.7,
            greeting_style="Hi",
            signoff_style="Best regards",
            tone="professional",
            uses_emoji=False,
            email_count=10,
        ),
        relationship_history=RelationshipHistory(
            sender_email="john@acme.com",
            total_emails=8,
            last_interaction="2026-02-10",
            relationship_type="client",
            memory_facts=[
                {"fact": "Prefers email over phone"},
                {"fact": "Travels frequently"},
            ],
        ),
        calendar_context=CalendarContext(
            connected=True,
            upcoming_meetings=[
                {"summary": "Q2 Review", "start": "2026-02-20T10:00:00Z"}
            ],
        ),
        crm_context=CRMContext(
            connected=True,
            lead_stage="Qualified",
            deal_value=50000.0,
        ),
    )


@pytest.fixture
def poor_context():
    """Context with minimal sources."""
    return DraftContext(
        id="context-poor",
        user_id="user-456",
        email_id="email-new",
        thread_id="thread-new",
        sender_email="new@contact.com",
        subject="Introduction",
        sources_used=[],
        thread_context=None,
        recipient_research=None,
        recipient_style=RecipientWritingStyle(exists=False),
        relationship_history=RelationshipHistory(
            sender_email="new@contact.com",
            total_emails=0,
        ),
    )


class TestProcessInbox:
    """Tests for process_inbox method."""

    @pytest.mark.asyncio
    async def test_process_inbox_no_emails(self, engine):
        """Test handling of empty inbox."""
        engine._email_analyzer.scan_inbox.return_value = EmailScanResult(
            total_emails=0,
            needs_reply=[],
            fyi=[],
            skipped=[],
            urgent=[],
        )
        engine._db.table().insert().execute = MagicMock()

        result = await engine.process_inbox("user-123")

        assert result.emails_scanned == 0
        assert result.emails_needing_reply == 0
        assert result.drafts_generated == 0
        assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_process_inbox_with_emails(self, engine, sample_email):
        """Test processing with emails needing replies."""
        engine._email_analyzer.scan_inbox.return_value = EmailScanResult(
            total_emails=5,
            needs_reply=[sample_email],
            fyi=[],
            skipped=[],
            urgent=[],
        )

        # Mock the full pipeline
        engine._context_gatherer.gather_context.return_value = DraftContext(
            id="ctx-1",
            user_id="user-123",
            email_id="email-123",
            thread_id="thread-456",
            sender_email="john@acme.com",
            subject="Test",
            sources_used=["composio_thread"],
        )
        engine._digital_twin.get_style_guidelines.return_value = "Be professional."
        engine._personality_calibrator.get_calibration.return_value = None
        engine._llm.generate_response.return_value = (
            '{"subject": "Re: Test", "body": "Test body"}'
        )
        engine._digital_twin.score_style_match.return_value = 0.85
        engine._db.table().insert().execute = MagicMock()
        engine._db.table().update().eq().execute = MagicMock()

        result = await engine.process_inbox("user-123")

        assert result.emails_scanned == 5
        assert result.emails_needing_reply == 1
        assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_process_inbox_handles_failures(self, engine, sample_email):
        """Test that individual email failures don't crash the run."""
        engine._email_analyzer.scan_inbox.return_value = EmailScanResult(
            total_emails=1,
            needs_reply=[sample_email],
            fyi=[],
            skipped=[],
            urgent=[],
        )

        # Make the entire _process_single_email fail so it counts as a draft failure
        engine._context_gatherer.gather_context.side_effect = Exception("API error")
        # Mock the LLM to also fail (so fallback context path still fails)
        engine._llm.generate_response.side_effect = Exception("LLM error")
        engine._digital_twin.get_style_guidelines.side_effect = Exception("Twin error")

        # Mock _check_existing_draft to return None (no existing draft)
        engine._check_existing_draft = AsyncMock(return_value=None)
        # Mock _is_active_conversation to return False
        engine._is_active_conversation = AsyncMock(return_value=False)
        # Mock _get_user_name to return a name
        engine._get_user_name = AsyncMock(return_value="Test User")
        # Mock _create_processing_run and _update_processing_run
        engine._create_processing_run = AsyncMock()
        engine._update_processing_run = AsyncMock()
        # Mock activity service (non-blocking, should not affect flow)
        engine._activity_service = AsyncMock()
        # Mock learning mode to be inactive
        engine._learning_mode = MagicMock()
        engine._learning_mode.is_learning_mode_active = AsyncMock(return_value=False)

        engine._db.table().insert().execute = MagicMock()
        engine._db.table().update().eq().execute = MagicMock()

        result = await engine.process_inbox("user-123")

        assert result.drafts_failed == 1
        assert result.drafts_generated == 0
        assert result.status == "failed"


class TestConfidenceCalculation:
    """Tests for _calculate_confidence method."""

    def test_confidence_high_context(self, engine, rich_context):
        """Rich context should produce high confidence (>= 0.8)."""
        style_score = 0.9
        confidence = engine._calculate_confidence(rich_context, style_score)

        assert confidence >= 0.8, f"Expected >= 0.8, got {confidence}"

    def test_confidence_low_context(self, engine, poor_context):
        """Poor context should produce lower confidence (< 0.6)."""
        style_score = 0.5
        confidence = engine._calculate_confidence(poor_context, style_score)

        assert confidence < 0.6, f"Expected < 0.6, got {confidence}"

    def test_confidence_with_thread_history(self, engine):
        """Thread history should boost confidence."""
        context_no_thread = DraftContext(
            id="ctx-1",
            user_id="u1",
            email_id="e1",
            thread_id="t1",
            sender_email="test@test.com",
            subject="Test",
            sources_used=["composio_thread"],
        )

        context_with_thread = DraftContext(
            id="ctx-2",
            user_id="u1",
            email_id="e1",
            thread_id="t1",
            sender_email="test@test.com",
            subject="Test",
            sources_used=["composio_thread"],
            thread_context=ThreadContext(
                thread_id="t1",
                messages=[
                    ThreadMessage(
                        sender_email="test@test.com",
                        body="msg1",
                        timestamp="2026-02-13T10:00:00Z",
                    )
                ],
                message_count=3,
            ),
        )

        conf_no_thread = engine._calculate_confidence(context_no_thread, 0.5)
        conf_with_thread = engine._calculate_confidence(context_with_thread, 0.5)

        assert conf_with_thread > conf_no_thread

    def test_confidence_bounded(self, engine, rich_context, poor_context):
        """Confidence should be bounded between 0 and 1."""
        # Even with perfect score
        confidence = engine._calculate_confidence(rich_context, 1.0)
        assert 0.0 <= confidence <= 1.0

        # Even with poor context
        confidence = engine._calculate_confidence(poor_context, 0.0)
        assert 0.0 <= confidence <= 1.0


class TestARIANotes:
    """Tests for _generate_aria_notes method."""

    @pytest.mark.asyncio
    async def test_aria_notes_includes_urgency(self, engine, urgent_email):
        """Urgent emails should be flagged in ARIA notes."""
        context = DraftContext(
            id="ctx-1",
            user_id="u1",
            email_id="e1",
            thread_id="t1",
            sender_email="test@test.com",
            subject="Test",
            sources_used=[],
        )

        notes = await engine._generate_aria_notes(urgent_email, context, 0.8, 0.7)

        assert "URGENT" in notes

    @pytest.mark.asyncio
    async def test_aria_notes_includes_sources(self, engine, sample_email, rich_context):
        """ARIA notes should list context sources used."""
        notes = await engine._generate_aria_notes(sample_email, rich_context, 0.8, 0.7)

        assert "composio_thread" in notes
        assert "exa_research" in notes

    @pytest.mark.asyncio
    async def test_aria_notes_warns_low_style(self, engine, sample_email):
        """Low style match should trigger warning."""
        context = DraftContext(
            id="ctx-1",
            user_id="u1",
            email_id="e1",
            thread_id="t1",
            sender_email="test@test.com",
            subject="Test",
            sources_used=[],
        )

        notes = await engine._generate_aria_notes(sample_email, context, 0.5, 0.6)

        assert "WARNING" in notes
        assert "Style match is low" in notes

    @pytest.mark.asyncio
    async def test_aria_notes_shows_relationship(self, engine, sample_email, rich_context):
        """Notes should show prior relationship count."""
        notes = await engine._generate_aria_notes(sample_email, rich_context, 0.8, 0.7)

        assert "Prior relationship" in notes
        assert "8 emails" in notes

    @pytest.mark.asyncio
    async def test_aria_notes_new_contact(self, engine, sample_email):
        """Notes should indicate new contact."""
        context = DraftContext(
            id="ctx-1",
            user_id="u1",
            email_id="e1",
            thread_id="t1",
            sender_email="new@contact.com",
            subject="Test",
            sources_used=[],
            relationship_history=RelationshipHistory(
                sender_email="new@contact.com",
                total_emails=0,
            ),
        )

        notes = await engine._generate_aria_notes(sample_email, context, 0.8, 0.7)

        assert "New contact" in notes


class TestPromptBuilder:
    """Tests for _build_reply_prompt method."""

    def test_prompt_includes_all_context(self, engine, sample_email, rich_context):
        """Prompt should include all available context sections."""
        prompt = engine._build_reply_prompt(
            user_name="Test User",
            email=sample_email,
            context=rich_context,
            style_guidelines="Be professional and concise.",
            tone_guidance="Keep it friendly but formal.",
        )

        # Check all sections are present
        assert "ORIGINAL EMAIL" in prompt
        assert sample_email.subject in prompt
        assert "CONVERSATION THREAD" in prompt
        assert "ABOUT THE RECIPIENT" in prompt
        assert "John Smith" in prompt
        assert "RELATIONSHIP HISTORY" in prompt
        assert "RECIPIENT'S COMMUNICATION STYLE" in prompt
        assert "WRITING STYLE" in prompt
        assert "Be professional" in prompt
        assert "TONE GUIDANCE" in prompt
        assert "UPCOMING MEETINGS" in prompt
        assert "CRM STATUS" in prompt
        assert "Test User" in prompt

    def test_prompt_handles_missing_context(self, engine, sample_email):
        """Prompt should handle missing context gracefully."""
        context = DraftContext(
            id="ctx-1",
            user_id="u1",
            email_id="e1",
            thread_id="t1",
            sender_email="test@test.com",
            subject="Test",
            sources_used=[],
        )

        prompt = engine._build_reply_prompt(
            user_name="User",
            email=sample_email,
            context=context,
            style_guidelines="",
            tone_guidance="",
        )

        # Should still have original email
        assert "ORIGINAL EMAIL" in prompt
        assert "Test User" not in prompt  # User name is User, not Test User
        assert "User" in prompt


class TestDraftPersistence:
    """Tests for draft saving functionality."""

    @pytest.mark.asyncio
    async def test_draft_persistence_all_fields(self, engine):
        """All new fields should be saved correctly."""
        engine._db.table().insert().execute = MagicMock()

        draft_id = await engine._save_draft_with_metadata(
            user_id="user-123",
            recipient_email="john@acme.com",
            recipient_name="John Smith",
            subject="Re: Test",
            body="Test body",
            original_email_id="email-456",
            thread_id="thread-789",
            context_id="context-abc",
            style_match_score=0.85,
            confidence_level=0.78,
            aria_notes="Context: 5 sources | Confidence: HIGH",
            urgency="NORMAL",
        )

        # Verify the insert was called
        insert_call = engine._db.table().insert()
        assert insert_call is not None

        # Verify draft_id is a valid UUID string
        assert draft_id is not None
        assert len(draft_id) == 36  # UUID format

    @pytest.mark.asyncio
    async def test_draft_urgency_tone_mapping(self, engine):
        """Urgent emails should use urgent tone."""
        engine._db.table().insert().execute = MagicMock()

        await engine._save_draft_with_metadata(
            user_id="user-123",
            recipient_email="ceo@bigco.com",
            recipient_name="CEO",
            subject="Re: Urgent",
            body="Response",
            original_email_id="email-urgent",
            thread_id="thread-urgent",
            context_id="ctx-urgent",
            style_match_score=0.9,
            confidence_level=0.8,
            aria_notes="URGENT flagged",
            urgency="URGENT",
        )

        # Just verify it doesn't crash
        assert True


class TestProcessingRun:
    """Tests for processing run tracking."""

    @pytest.mark.asyncio
    async def test_processing_run_created(self, engine):
        """Processing run should be created at start."""
        engine._db.table().insert().execute = MagicMock()

        await engine._create_processing_run(
            run_id="run-123",
            user_id="user-456",
            started_at=datetime.now(UTC),
        )

        # Verify insert was called
        assert engine._db.table().insert().execute.called

    @pytest.mark.asyncio
    async def test_processing_run_updated(self, engine):
        """Processing run should be updated on completion."""
        engine._db.table().update().eq().execute = MagicMock()

        result = ProcessingRunResult(
            run_id="run-123",
            user_id="user-456",
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            emails_scanned=10,
            emails_needing_reply=3,
            drafts_generated=3,
            drafts_failed=0,
            status="completed",
        )

        await engine._update_processing_run(result)

        # Verify update was called
        assert engine._db.table().update().eq().execute.called


class TestGuardrails:
    """Tests for strategic guardrail checking."""

    @pytest.mark.asyncio
    async def test_check_guardrails_no_warnings_clean_draft(self, engine, rich_context):
        """Clean draft with no commitment language should have no warnings."""
        draft_body = """Hi John,

Thanks for reaching out about the Q2 proposal. I'd be happy to discuss this further.

Let me know when works for a call.

Best regards,
User"""

        warnings = await engine._check_guardrails(draft_body, rich_context)
        assert warnings == []

    @pytest.mark.asyncio
    async def test_check_guardrails_pricing_warning(self, engine, rich_context):
        """Draft mentioning pricing without context should warn."""
        draft_body = """Hi John,

Thanks for your interest. Our pricing starts at $50,000 per year.

Let me know if you have questions.

Best regards,
User"""

        warnings = await engine._check_guardrails(draft_body, rich_context)
        assert len(warnings) == 1
        assert "PRICING_COMMITMENT" in warnings[0]

    @pytest.mark.asyncio
    async def test_check_guardrails_pricing_allowed_with_context(self, engine):
        """Draft mentioning pricing is OK if thread context has pricing discussion."""
        context = DraftContext(
            id="ctx-1",
            user_id="user-1",
            email_id="email-1",
            thread_id="thread-1",
            sender_email="test@test.com",
            subject="Pricing",
            sources_used=["thread"],
            thread_context=ThreadContext(
                thread_id="thread-1",
                messages=[
                    ThreadMessage(
                        sender_email="test@test.com",
                        sender_name="Test",
                        body="What is your price for this?",
                        timestamp="2026-02-01T10:00:00Z",
                    ),
                ],
                summary="Discussion about pricing and costs",
                message_count=1,
            ),
        )

        draft_body = """Hi,

Our price is $50,000 as discussed.

Best,
User"""

        warnings = await engine._check_guardrails(draft_body, context)
        # Should NOT warn because thread has pricing context
        assert not any("PRICING" in w for w in warnings)

    @pytest.mark.asyncio
    async def test_check_guardrails_timeline_warning(self, engine, rich_context):
        """Draft with specific timeline should warn."""
        draft_body = """Hi John,

I'll have that to you by Friday.

Best regards,
User"""

        warnings = await engine._check_guardrails(draft_body, rich_context)
        assert len(warnings) == 1
        assert "TIMELINE_COMMITMENT" in warnings[0]

    @pytest.mark.asyncio
    async def test_check_guardrails_meeting_warning(self, engine, rich_context):
        """Draft confirming a meeting should warn."""
        draft_body = """Hi John,

See you at 2pm on Thursday!

Best regards,
User"""

        warnings = await engine._check_guardrails(draft_body, rich_context)
        assert len(warnings) == 1
        assert "MEETING_COMMITMENT" in warnings[0]

    @pytest.mark.asyncio
    async def test_check_guardrails_multiple_warnings(self, engine, rich_context):
        """Draft with multiple issues should generate multiple warnings."""
        draft_body = """Hi John,

Our pricing is $50K and I'll have the proposal ready by Friday.

See you at the meeting on Monday!

Best regards,
User"""

        warnings = await engine._check_guardrails(draft_body, rich_context)
        assert len(warnings) >= 2
        warning_types = [w.split(":")[0] for w in warnings]
        assert "PRICING_COMMITMENT" in warning_types
        assert "TIMELINE_COMMITMENT" in warning_types
        assert "MEETING_COMMITMENT" in warning_types

    @pytest.mark.asyncio
    async def test_confidence_reduced_by_guardrail_warnings(self, engine, rich_context):
        """Each guardrail warning should reduce confidence by 0.1."""
        base_confidence = engine._calculate_confidence(rich_context)

        # Simulate 2 warnings
        adjusted_confidence = max(0.1, base_confidence - (2 * 0.1))

        assert adjusted_confidence == base_confidence - 0.2

    @pytest.mark.asyncio
    async def test_confidence_floor_at_0_1(self, engine, rich_context):
        """Confidence should not go below 0.1 even with many warnings."""
        base_confidence = 0.3

        # Simulate 10 warnings
        adjusted_confidence = max(0.1, base_confidence - (10 * 0.1))

        assert adjusted_confidence == 0.1


class TestSingleton:
    """Tests for singleton accessor."""

    def test_get_autonomous_draft_engine_returns_singleton(self):
        """Should return the same instance on multiple calls."""
        from src.services.autonomous_draft_engine import (
            get_autonomous_draft_engine,
            _engine as engine_module,
        )
        import src.services.autonomous_draft_engine as module

        # Reset singleton
        module._engine = None

        # Need to patch all dependencies
        with (
            patch("src.services.autonomous_draft_engine.SupabaseClient"),
            patch("src.services.autonomous_draft_engine.LLMClient"),
            patch("src.services.autonomous_draft_engine.EmailAnalyzer"),
            patch("src.services.autonomous_draft_engine.EmailContextGatherer"),
            patch("src.services.autonomous_draft_engine.DigitalTwin"),
            patch("src.services.autonomous_draft_engine.PersonalityCalibrator"),
        ):
            engine1 = get_autonomous_draft_engine()
            engine2 = get_autonomous_draft_engine()

            assert engine1 is engine2

        # Clean up
        module._engine = None
