"""Integration tests for email draft flow."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.email_draft import EmailDraftPurpose, EmailDraftTone


@pytest.mark.integration
class TestEmailDraftIntegration:
    """Integration tests for the full email draft flow."""

    @pytest.fixture
    def mock_db_client(self) -> MagicMock:
        """Create mock database client."""
        return MagicMock()

    @pytest.fixture
    def mock_llm_client(self) -> AsyncMock:
        """Create mock LLM client."""
        mock = AsyncMock()
        mock.generate_response = AsyncMock(
            return_value='{"subject": "Test Subject", "body": "Test body content"}'
        )
        return mock

    @pytest.fixture
    def mock_digital_twin(self) -> AsyncMock:
        """Create mock Digital Twin."""
        mock = AsyncMock()
        mock.get_style_guidelines = AsyncMock(return_value="Write professionally and concisely.")
        mock.score_style_match = AsyncMock(return_value=0.85)
        return mock

    @pytest.mark.asyncio
    async def test_full_draft_lifecycle(
        self,
        mock_db_client: MagicMock,
        mock_llm_client: AsyncMock,
        mock_digital_twin: AsyncMock,
    ) -> None:
        """Test complete draft lifecycle: create -> update -> regenerate -> send."""
        from src.services.draft_service import DraftService

        draft_id = "lifecycle-draft-123"
        user_id = "integration-test-user"
        now = datetime.now(UTC)

        # Setup draft data that will be returned from DB
        created_draft = {
            "id": draft_id,
            "user_id": user_id,
            "recipient_email": "recipient@example.com",
            "recipient_name": None,
            "subject": "Test Subject",
            "body": "Test body content",
            "purpose": "intro",
            "tone": "friendly",
            "context": {"user_context": None, "lead_context": None},
            "lead_memory_id": None,
            "style_match_score": 0.85,
            "status": "draft",
            "sent_at": None,
            "error_message": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        with (
            patch("src.services.draft_service.SupabaseClient") as mock_db_class,
            patch("src.services.draft_service.LLMClient") as mock_llm_class,
            patch("src.services.draft_service.DigitalTwin") as mock_twin_class,
            patch("src.services.draft_service.get_oauth_client") as mock_oauth_getter,
        ):
            mock_db_class.get_client.return_value = mock_db_client
            mock_llm_class.return_value = mock_llm_client
            mock_twin_class.return_value = mock_digital_twin

            # 1. CREATE DRAFT
            mock_db_client.table.return_value.insert.return_value.execute.return_value = (
                MagicMock(data=[created_draft])
            )

            service = DraftService()
            result = await service.create_draft(
                user_id=user_id,
                recipient_email="recipient@example.com",
                purpose=EmailDraftPurpose.INTRO,
                tone=EmailDraftTone.FRIENDLY,
            )

            assert result["id"] == draft_id
            assert result["status"] == "draft"
            assert result["subject"] == "Test Subject"

            # Verify Digital Twin was used for style matching
            mock_digital_twin.get_style_guidelines.assert_called_once_with(user_id)
            mock_digital_twin.score_style_match.assert_called_once()

            # 2. UPDATE DRAFT
            updated_draft = created_draft.copy()
            updated_draft["subject"] = "Updated Subject"
            mock_db_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[updated_draft]
            )

            result = await service.update_draft(
                user_id=user_id,
                draft_id=draft_id,
                updates={"subject": "Updated Subject"},
            )

            assert result["subject"] == "Updated Subject"

            # 3. REGENERATE DRAFT
            # Setup mock to return the draft for get_draft
            mock_db_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data=updated_draft
            )

            # New LLM response for regeneration
            mock_llm_client.generate_response = AsyncMock(
                return_value='{"subject": "Regenerated Subject", "body": "Regenerated body content"}'
            )

            regenerated_draft = updated_draft.copy()
            regenerated_draft["subject"] = "Regenerated Subject"
            regenerated_draft["body"] = "Regenerated body content"
            regenerated_draft["tone"] = "urgent"
            mock_db_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[regenerated_draft]
            )

            result = await service.regenerate_draft(
                user_id=user_id,
                draft_id=draft_id,
                tone=EmailDraftTone.URGENT,
            )

            assert result["tone"] == "urgent"

            # 4. SEND DRAFT
            # Setup integration mock
            mock_db_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data=regenerated_draft
            )
            mock_db_client.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
                data={
                    "id": "integration-123",
                    "composio_connection_id": "conn-456",
                    "integration_type": "gmail",
                }
            )

            sent_draft = regenerated_draft.copy()
            sent_draft["status"] = "sent"
            sent_draft["sent_at"] = now.isoformat()
            mock_db_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[sent_draft]
            )

            mock_oauth = AsyncMock()
            mock_oauth.execute_action = AsyncMock(return_value={"success": True})
            mock_oauth_getter.return_value = mock_oauth

            result = await service.send_draft(user_id=user_id, draft_id=draft_id)

            assert result["status"] == "sent"
            mock_oauth.execute_action.assert_called_once()

    @pytest.mark.asyncio
    async def test_draft_with_lead_context(
        self,
        mock_db_client: MagicMock,
        mock_llm_client: AsyncMock,
        mock_digital_twin: AsyncMock,
    ) -> None:
        """Test draft creation with lead memory context enrichment."""
        from src.services.draft_service import DraftService

        user_id = "integration-test-user"
        lead_memory_id = "lead-456"
        now = datetime.now(UTC)

        # Setup lead context that will be fetched
        lead_context = {
            "id": lead_memory_id,
            "company_name": "Acme Corp",
            "lifecycle_stage": "opportunity",
            "status": "active",
        }

        # LLM response includes lead context
        mock_llm_client.generate_response = AsyncMock(
            return_value='{"subject": "Following up - Acme Corp", "body": "Hi John, I wanted to follow up on our conversation about Acme Corp..."}'
        )
        mock_digital_twin.score_style_match = AsyncMock(return_value=0.90)

        created_draft = {
            "id": "lead-draft-123",
            "user_id": user_id,
            "recipient_email": "john@acme.com",
            "recipient_name": "John Smith",
            "subject": "Following up - Acme Corp",
            "body": "Hi John, I wanted to follow up on our conversation about Acme Corp...",
            "purpose": "follow_up",
            "tone": "friendly",
            "context": {"user_context": None, "lead_context": lead_context},
            "lead_memory_id": lead_memory_id,
            "style_match_score": 0.90,
            "status": "draft",
            "sent_at": None,
            "error_message": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        with (
            patch("src.services.draft_service.SupabaseClient") as mock_db_class,
            patch("src.services.draft_service.LLMClient") as mock_llm_class,
            patch("src.services.draft_service.DigitalTwin") as mock_twin_class,
        ):
            mock_db_class.get_client.return_value = mock_db_client
            mock_llm_class.return_value = mock_llm_client
            mock_twin_class.return_value = mock_digital_twin

            # Mock lead_memories table query
            mock_db_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data=lead_context
            )

            # Mock insert
            mock_db_client.table.return_value.insert.return_value.execute.return_value = (
                MagicMock(data=[created_draft])
            )

            service = DraftService()
            result = await service.create_draft(
                user_id=user_id,
                recipient_email="john@acme.com",
                recipient_name="John Smith",
                purpose=EmailDraftPurpose.FOLLOW_UP,
                lead_memory_id=lead_memory_id,
            )

            assert result["lead_memory_id"] == lead_memory_id
            assert "Acme" in result["subject"]
            assert result["style_match_score"] == 0.90

    @pytest.mark.asyncio
    async def test_draft_creation_without_lead_context(
        self,
        mock_db_client: MagicMock,
        mock_llm_client: AsyncMock,
        mock_digital_twin: AsyncMock,
    ) -> None:
        """Test draft creation without lead memory context."""
        from src.services.draft_service import DraftService

        user_id = "test-user"
        now = datetime.now(UTC)

        created_draft = {
            "id": "simple-draft-123",
            "user_id": user_id,
            "recipient_email": "contact@example.com",
            "recipient_name": None,
            "subject": "Test Subject",
            "body": "Test body content",
            "purpose": "intro",
            "tone": "formal",
            "context": {"user_context": None, "lead_context": None},
            "lead_memory_id": None,
            "style_match_score": 0.85,
            "status": "draft",
            "sent_at": None,
            "error_message": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        with (
            patch("src.services.draft_service.SupabaseClient") as mock_db_class,
            patch("src.services.draft_service.LLMClient") as mock_llm_class,
            patch("src.services.draft_service.DigitalTwin") as mock_twin_class,
        ):
            mock_db_class.get_client.return_value = mock_db_client
            mock_llm_class.return_value = mock_llm_client
            mock_twin_class.return_value = mock_digital_twin

            mock_db_client.table.return_value.insert.return_value.execute.return_value = (
                MagicMock(data=[created_draft])
            )

            service = DraftService()
            result = await service.create_draft(
                user_id=user_id,
                recipient_email="contact@example.com",
                purpose=EmailDraftPurpose.INTRO,
                tone=EmailDraftTone.FORMAL,
            )

            assert result["id"] == "simple-draft-123"
            assert result["lead_memory_id"] is None
            assert result["tone"] == "formal"

    @pytest.mark.asyncio
    async def test_send_draft_with_outlook_integration(
        self,
        mock_db_client: MagicMock,
    ) -> None:
        """Test sending draft via Outlook integration."""
        from src.services.draft_service import DraftService

        user_id = "test-user"
        draft_id = "outlook-draft-123"
        now = datetime.now(UTC)

        existing_draft = {
            "id": draft_id,
            "user_id": user_id,
            "recipient_email": "recipient@example.com",
            "recipient_name": "Test Recipient",
            "subject": "Test Subject",
            "body": "Test body",
            "purpose": "intro",
            "tone": "friendly",
            "context": {},
            "lead_memory_id": None,
            "style_match_score": 0.85,
            "status": "draft",
            "sent_at": None,
            "error_message": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        with (
            patch("src.services.draft_service.SupabaseClient") as mock_db_class,
            patch("src.services.draft_service.LLMClient"),
            patch("src.services.draft_service.DigitalTwin"),
            patch("src.services.draft_service.get_oauth_client") as mock_oauth_getter,
        ):
            mock_db_class.get_client.return_value = mock_db_client

            # Mock get_draft
            mock_db_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data=existing_draft
            )

            # Mock outlook integration (not gmail)
            mock_db_client.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
                data={
                    "id": "outlook-int-123",
                    "composio_connection_id": "outlook-conn-456",
                    "integration_type": "outlook",
                }
            )

            sent_draft = existing_draft.copy()
            sent_draft["status"] = "sent"
            sent_draft["sent_at"] = now.isoformat()
            mock_db_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[sent_draft]
            )

            mock_oauth = AsyncMock()
            mock_oauth.execute_action = AsyncMock(return_value={"success": True})
            mock_oauth_getter.return_value = mock_oauth

            service = DraftService()
            result = await service.send_draft(user_id=user_id, draft_id=draft_id)

            assert result["status"] == "sent"
            # Verify Outlook action was used
            mock_oauth.execute_action.assert_called_once()
            call_args = mock_oauth.execute_action.call_args
            assert call_args.kwargs["action"] == "outlook_send_email"

    @pytest.mark.asyncio
    async def test_send_draft_without_email_integration(
        self,
        mock_db_client: MagicMock,
    ) -> None:
        """Test sending draft fails gracefully without email integration."""
        from src.core.exceptions import EmailSendError
        from src.services.draft_service import DraftService

        user_id = "test-user"
        draft_id = "no-int-draft-123"
        now = datetime.now(UTC)

        existing_draft = {
            "id": draft_id,
            "user_id": user_id,
            "recipient_email": "recipient@example.com",
            "recipient_name": None,
            "subject": "Test Subject",
            "body": "Test body",
            "purpose": "intro",
            "tone": "friendly",
            "context": {},
            "lead_memory_id": None,
            "style_match_score": 0.85,
            "status": "draft",
            "sent_at": None,
            "error_message": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        with (
            patch("src.services.draft_service.SupabaseClient") as mock_db_class,
            patch("src.services.draft_service.LLMClient"),
            patch("src.services.draft_service.DigitalTwin"),
        ):
            mock_db_class.get_client.return_value = mock_db_client

            # Mock get_draft
            mock_db_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data=existing_draft
            )

            # No email integration found
            mock_db_client.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
                data=None
            )

            service = DraftService()

            with pytest.raises(EmailSendError) as exc_info:
                await service.send_draft(user_id=user_id, draft_id=draft_id)

            assert "No email integration connected" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_regenerate_preserves_original_context(
        self,
        mock_db_client: MagicMock,
        mock_llm_client: AsyncMock,
        mock_digital_twin: AsyncMock,
    ) -> None:
        """Test that regeneration preserves and extends original context."""
        from src.services.draft_service import DraftService

        user_id = "test-user"
        draft_id = "regen-draft-123"
        now = datetime.now(UTC)

        original_draft = {
            "id": draft_id,
            "user_id": user_id,
            "recipient_email": "recipient@example.com",
            "recipient_name": "Test Recipient",
            "subject": "Original Subject",
            "body": "Original body",
            "purpose": "follow_up",
            "tone": "friendly",
            "context": {"user_context": "Original context info", "lead_context": None},
            "lead_memory_id": None,
            "style_match_score": 0.80,
            "status": "draft",
            "sent_at": None,
            "error_message": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        regenerated_draft = original_draft.copy()
        regenerated_draft["subject"] = "New Regenerated Subject"
        regenerated_draft["body"] = "New regenerated body with additional context"
        regenerated_draft["tone"] = "urgent"
        regenerated_draft["style_match_score"] = 0.88

        with (
            patch("src.services.draft_service.SupabaseClient") as mock_db_class,
            patch("src.services.draft_service.LLMClient") as mock_llm_class,
            patch("src.services.draft_service.DigitalTwin") as mock_twin_class,
        ):
            mock_db_class.get_client.return_value = mock_db_client
            mock_llm_class.return_value = mock_llm_client
            mock_twin_class.return_value = mock_digital_twin

            # Mock get_draft
            mock_db_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data=original_draft
            )

            # Mock update
            mock_db_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[regenerated_draft]
            )

            mock_llm_client.generate_response = AsyncMock(
                return_value='{"subject": "New Regenerated Subject", "body": "New regenerated body with additional context"}'
            )
            mock_digital_twin.score_style_match = AsyncMock(return_value=0.88)

            service = DraftService()
            result = await service.regenerate_draft(
                user_id=user_id,
                draft_id=draft_id,
                tone=EmailDraftTone.URGENT,
                additional_context="Please emphasize urgency",
            )

            assert result["tone"] == "urgent"
            assert result["style_match_score"] == 0.88

            # Verify LLM was called with the prompt
            mock_llm_client.generate_response.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_drafts_with_status_filter(
        self,
        mock_db_client: MagicMock,
    ) -> None:
        """Test listing drafts with status filter."""
        from src.services.draft_service import DraftService

        user_id = "test-user"
        now = datetime.now(UTC)

        drafts_data = [
            {
                "id": "draft-1",
                "user_id": user_id,
                "recipient_email": "a@example.com",
                "subject": "Subject 1",
                "status": "draft",
                "created_at": now.isoformat(),
            },
            {
                "id": "draft-2",
                "user_id": user_id,
                "recipient_email": "b@example.com",
                "subject": "Subject 2",
                "status": "draft",
                "created_at": now.isoformat(),
            },
        ]

        with (
            patch("src.services.draft_service.SupabaseClient") as mock_db_class,
            patch("src.services.draft_service.LLMClient"),
            patch("src.services.draft_service.DigitalTwin"),
        ):
            mock_db_class.get_client.return_value = mock_db_client

            mock_db_client.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                data=drafts_data
            )

            service = DraftService()
            result = await service.list_drafts(user_id=user_id, limit=10, status="draft")

            assert len(result) == 2
            assert all(d["status"] == "draft" for d in result)

    @pytest.mark.asyncio
    async def test_delete_draft(
        self,
        mock_db_client: MagicMock,
    ) -> None:
        """Test deleting a draft."""
        from src.services.draft_service import DraftService

        user_id = "test-user"
        draft_id = "delete-draft-123"

        with (
            patch("src.services.draft_service.SupabaseClient") as mock_db_class,
            patch("src.services.draft_service.LLMClient"),
            patch("src.services.draft_service.DigitalTwin"),
        ):
            mock_db_class.get_client.return_value = mock_db_client

            mock_db_client.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock()

            service = DraftService()
            result = await service.delete_draft(user_id=user_id, draft_id=draft_id)

            assert result is True
