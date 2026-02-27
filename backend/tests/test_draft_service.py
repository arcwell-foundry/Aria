"""Tests for the DraftService email draft generation service."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.exceptions import EmailDraftError, EmailSendError, NotFoundError
from src.models.email_draft import EmailDraftPurpose, EmailDraftTone


@pytest.fixture
def mock_draft_data() -> dict[str, Any]:
    """Create mock draft data as returned from database."""
    return {
        "id": "draft-123",
        "user_id": "user-456",
        "recipient_email": "client@example.com",
        "recipient_name": "John Doe",
        "subject": "Follow-up on our meeting",
        "body": "Hi John,\n\nThank you for your time today...",
        "purpose": "follow_up",
        "tone": "friendly",
        "context": {"user_context": "Discussed Q4 pipeline"},
        "lead_memory_id": None,
        "style_match_score": 0.85,
        "status": "draft",
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
    }


@pytest.fixture
def mock_lead_context() -> dict[str, Any]:
    """Create mock lead memory context."""
    return {
        "id": "lead-789",
        "user_id": "user-456",
        "company_name": "Acme Pharma",
        "lifecycle_stage": "qualified",
        "contact_name": "Jane Smith",
    }


@pytest.mark.asyncio
async def test_create_draft_generates_email_via_llm(
    mock_draft_data: dict[str, Any],
) -> None:
    """Test that create_draft generates email content via LLM and stores it."""
    from src.services.draft_service import DraftService

    with (
        patch("src.services.draft_service.LLMClient") as mock_llm_class,
        patch("src.services.draft_service.DigitalTwin") as mock_twin_class,
        patch("src.services.draft_service.SupabaseClient") as mock_db_class,
    ):
        # Setup LLM mock
        mock_llm = AsyncMock()
        mock_llm.generate_response = AsyncMock(
            return_value='{"subject": "Follow-up on our meeting", "body": "Hi John,\\n\\nThank you..."}'
        )
        mock_llm_class.return_value = mock_llm

        # Setup DigitalTwin mock
        mock_twin = AsyncMock()
        mock_twin.get_style_guidelines = AsyncMock(return_value="Use friendly tone.")
        mock_twin.score_style_match = AsyncMock(return_value=0.85)
        mock_twin_class.return_value = mock_twin

        # Setup database mock
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_insert = MagicMock()
        mock_insert.execute.return_value = MagicMock(data=[mock_draft_data])
        mock_table.insert.return_value = mock_insert
        mock_client.table.return_value = mock_table
        mock_db_class.get_client.return_value = mock_client

        service = DraftService()
        result = await service.create_draft(
            user_id="user-456",
            recipient_email="client@example.com",
            purpose=EmailDraftPurpose.FOLLOW_UP,
            tone=EmailDraftTone.FRIENDLY,
            recipient_name="John Doe",
            context="Discussed Q4 pipeline",
        )

        # Verify LLM was called
        mock_llm.generate_response.assert_called_once()
        call_kwargs = mock_llm.generate_response.call_args.kwargs
        assert "temperature" in call_kwargs
        assert call_kwargs["temperature"] == 0.7

        # Verify style guidelines were fetched
        mock_twin.get_style_guidelines.assert_called_once_with("user-456")

        # Verify style match was scored
        mock_twin.score_style_match.assert_called_once()

        # Verify draft was stored
        mock_table.insert.assert_called_once()
        insert_data = mock_table.insert.call_args.args[0]
        assert insert_data["user_id"] == "user-456"
        assert insert_data["recipient_email"] == "client@example.com"
        assert insert_data["status"] == "draft"

        # Verify result
        assert result["id"] == "draft-123"
        assert result["subject"] == "Follow-up on our meeting"


@pytest.mark.asyncio
async def test_create_draft_handles_non_json_llm_response(
    mock_draft_data: dict[str, Any],
) -> None:
    """Test that create_draft handles LLM response that isn't valid JSON."""
    from src.services.draft_service import DraftService

    with (
        patch("src.services.draft_service.LLMClient") as mock_llm_class,
        patch("src.services.draft_service.DigitalTwin") as mock_twin_class,
        patch("src.services.draft_service.SupabaseClient") as mock_db_class,
    ):
        mock_llm = AsyncMock()
        # Return plain text instead of JSON
        mock_llm.generate_response = AsyncMock(
            return_value="Hi John,\n\nThank you for your time today. I wanted to follow up..."
        )
        mock_llm_class.return_value = mock_llm

        mock_twin = AsyncMock()
        mock_twin.get_style_guidelines = AsyncMock(return_value="Use friendly tone.")
        mock_twin.score_style_match = AsyncMock(return_value=0.80)
        mock_twin_class.return_value = mock_twin

        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_insert = MagicMock()
        mock_draft_data["subject"] = "Test Subject"
        mock_insert.execute.return_value = MagicMock(data=[mock_draft_data])
        mock_table.insert.return_value = mock_insert
        mock_client.table.return_value = mock_table
        mock_db_class.get_client.return_value = mock_client

        service = DraftService()
        result = await service.create_draft(
            user_id="user-456",
            recipient_email="client@example.com",
            purpose=EmailDraftPurpose.FOLLOW_UP,
            subject_hint="Test Subject",
        )

        # Should still succeed, using the raw response as body
        assert result is not None
        insert_data = mock_table.insert.call_args.args[0]
        assert "Hi John" in insert_data["body"]


@pytest.mark.asyncio
async def test_create_draft_with_lead_memory_id(
    mock_draft_data: dict[str, Any],
    mock_lead_context: dict[str, Any],
) -> None:
    """Test that create_draft pulls context from lead memory when provided."""
    from src.services.draft_service import DraftService

    with (
        patch("src.services.draft_service.LLMClient") as mock_llm_class,
        patch("src.services.draft_service.DigitalTwin") as mock_twin_class,
        patch("src.services.draft_service.SupabaseClient") as mock_db_class,
    ):
        mock_llm = AsyncMock()
        mock_llm.generate_response = AsyncMock(
            return_value='{"subject": "Acme Pharma Partnership", "body": "Dear Jane..."}'
        )
        mock_llm_class.return_value = mock_llm

        mock_twin = AsyncMock()
        mock_twin.get_style_guidelines = AsyncMock(return_value="Use formal tone.")
        mock_twin.score_style_match = AsyncMock(return_value=0.90)
        mock_twin_class.return_value = mock_twin

        mock_client = MagicMock()

        # Mock for lead_memories table
        mock_lead_select = MagicMock()
        mock_lead_eq1 = MagicMock()
        mock_lead_eq2 = MagicMock()
        mock_lead_single = MagicMock()
        mock_lead_single.execute.return_value = MagicMock(data=mock_lead_context)
        mock_lead_eq2.single.return_value = mock_lead_single
        mock_lead_eq1.eq.return_value = mock_lead_eq2
        mock_lead_select.eq.return_value = mock_lead_eq1

        # Mock for email_drafts table
        mock_draft_insert = MagicMock()
        mock_draft_data["lead_memory_id"] = "lead-789"
        mock_draft_insert.execute.return_value = MagicMock(data=[mock_draft_data])

        def table_router(name: str) -> MagicMock:
            if name == "lead_memories":
                mock = MagicMock()
                mock.select.return_value = mock_lead_select
                return mock
            else:  # email_drafts
                mock = MagicMock()
                mock.insert.return_value = mock_draft_insert
                return mock

        mock_client.table = table_router
        mock_db_class.get_client.return_value = mock_client

        service = DraftService()
        result = await service.create_draft(
            user_id="user-456",
            recipient_email="jane@acme.com",
            purpose=EmailDraftPurpose.PROPOSAL,
            tone=EmailDraftTone.FORMAL,
            lead_memory_id="lead-789",
        )

        # Verify LLM prompt included lead context
        call_args = mock_llm.generate_response.call_args
        prompt_content = call_args.kwargs["messages"][0]["content"]
        assert "Acme Pharma" in prompt_content or "qualified" in prompt_content

        assert result["lead_memory_id"] == "lead-789"


@pytest.mark.asyncio
async def test_create_draft_raises_error_on_db_failure() -> None:
    """Test that create_draft raises EmailDraftError on database failure."""
    from src.services.draft_service import DraftService

    with (
        patch("src.services.draft_service.LLMClient") as mock_llm_class,
        patch("src.services.draft_service.DigitalTwin") as mock_twin_class,
        patch("src.services.draft_service.SupabaseClient") as mock_db_class,
    ):
        mock_llm = AsyncMock()
        mock_llm.generate_response = AsyncMock(
            return_value='{"subject": "Test", "body": "Test body"}'
        )
        mock_llm_class.return_value = mock_llm

        mock_twin = AsyncMock()
        mock_twin.get_style_guidelines = AsyncMock(return_value="")
        mock_twin.score_style_match = AsyncMock(return_value=0.5)
        mock_twin_class.return_value = mock_twin

        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_insert = MagicMock()
        mock_insert.execute.return_value = MagicMock(data=[])  # Empty result
        mock_table.insert.return_value = mock_insert
        mock_client.table.return_value = mock_table
        mock_db_class.get_client.return_value = mock_client

        service = DraftService()
        with pytest.raises(EmailDraftError):
            await service.create_draft(
                user_id="user-456",
                recipient_email="client@example.com",
                purpose=EmailDraftPurpose.INTRO,
            )


@pytest.mark.asyncio
async def test_get_draft_returns_draft_by_id(
    mock_draft_data: dict[str, Any],
) -> None:
    """Test that get_draft returns a draft by ID."""
    from src.services.draft_service import DraftService

    with (
        patch("src.services.draft_service.LLMClient"),
        patch("src.services.draft_service.DigitalTwin"),
        patch("src.services.draft_service.SupabaseClient") as mock_db_class,
    ):
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_eq1 = MagicMock()
        mock_eq2 = MagicMock()
        mock_single = MagicMock()
        mock_single.execute.return_value = MagicMock(data=mock_draft_data)
        mock_eq2.single.return_value = mock_single
        mock_eq1.eq.return_value = mock_eq2
        mock_select.eq.return_value = mock_eq1
        mock_table.select.return_value = mock_select
        mock_client.table.return_value = mock_table
        mock_db_class.get_client.return_value = mock_client

        service = DraftService()
        result = await service.get_draft("user-456", "draft-123")

        assert result is not None
        assert result["id"] == "draft-123"
        assert result["user_id"] == "user-456"


@pytest.mark.asyncio
async def test_get_draft_returns_none_if_not_found() -> None:
    """Test that get_draft returns None when draft doesn't exist."""
    from src.services.draft_service import DraftService

    with (
        patch("src.services.draft_service.LLMClient"),
        patch("src.services.draft_service.DigitalTwin"),
        patch("src.services.draft_service.SupabaseClient") as mock_db_class,
    ):
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_eq1 = MagicMock()
        mock_eq2 = MagicMock()
        mock_single = MagicMock()
        mock_single.execute.return_value = MagicMock(data=None)
        mock_eq2.single.return_value = mock_single
        mock_eq1.eq.return_value = mock_eq2
        mock_select.eq.return_value = mock_eq1
        mock_table.select.return_value = mock_select
        mock_client.table.return_value = mock_table
        mock_db_class.get_client.return_value = mock_client

        service = DraftService()
        result = await service.get_draft("user-456", "nonexistent")

        assert result is None


@pytest.mark.asyncio
async def test_list_drafts_returns_user_drafts(
    mock_draft_data: dict[str, Any],
) -> None:
    """Test that list_drafts returns drafts for a user."""
    from src.services.draft_service import DraftService

    with (
        patch("src.services.draft_service.LLMClient"),
        patch("src.services.draft_service.DigitalTwin"),
        patch("src.services.draft_service.SupabaseClient") as mock_db_class,
    ):
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_eq = MagicMock()
        mock_order = MagicMock()
        mock_limit = MagicMock()
        mock_limit.execute.return_value = MagicMock(data=[mock_draft_data])
        mock_order.limit.return_value = mock_limit
        mock_eq.order.return_value = mock_order
        mock_select.eq.return_value = mock_eq
        mock_table.select.return_value = mock_select
        mock_client.table.return_value = mock_table
        mock_db_class.get_client.return_value = mock_client

        service = DraftService()
        result = await service.list_drafts("user-456")

        assert len(result) == 1
        assert result[0]["id"] == "draft-123"


@pytest.mark.asyncio
async def test_list_drafts_filters_by_status(
    mock_draft_data: dict[str, Any],
) -> None:
    """Test that list_drafts can filter by status."""
    from src.services.draft_service import DraftService

    with (
        patch("src.services.draft_service.LLMClient"),
        patch("src.services.draft_service.DigitalTwin"),
        patch("src.services.draft_service.SupabaseClient") as mock_db_class,
    ):
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_eq1 = MagicMock()
        mock_eq2 = MagicMock()  # For status filter
        mock_order = MagicMock()
        mock_limit = MagicMock()
        mock_limit.execute.return_value = MagicMock(data=[mock_draft_data])
        mock_order.limit.return_value = mock_limit
        mock_eq2.order.return_value = mock_order
        mock_eq1.eq.return_value = mock_eq2
        mock_select.eq.return_value = mock_eq1
        mock_table.select.return_value = mock_select
        mock_client.table.return_value = mock_table
        mock_db_class.get_client.return_value = mock_client

        service = DraftService()
        result = await service.list_drafts("user-456", status="draft")

        assert len(result) == 1
        # Verify that eq was called for status
        mock_eq1.eq.assert_called_once_with("status", "draft")


@pytest.mark.asyncio
async def test_update_draft_updates_fields(
    mock_draft_data: dict[str, Any],
) -> None:
    """Test that update_draft updates specified fields."""
    from src.services.draft_service import DraftService

    with (
        patch("src.services.draft_service.LLMClient"),
        patch("src.services.draft_service.DigitalTwin"),
        patch("src.services.draft_service.SupabaseClient") as mock_db_class,
    ):
        updated_data = {**mock_draft_data, "subject": "Updated Subject"}

        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_update = MagicMock()
        mock_eq1 = MagicMock()
        mock_eq2 = MagicMock()
        mock_eq2.execute.return_value = MagicMock(data=[updated_data])
        mock_eq1.eq.return_value = mock_eq2
        mock_update.eq.return_value = mock_eq1
        mock_table.update.return_value = mock_update
        mock_client.table.return_value = mock_table
        mock_db_class.get_client.return_value = mock_client

        service = DraftService()
        result = await service.update_draft(
            "user-456",
            "draft-123",
            {"subject": "Updated Subject"},
        )

        assert result["subject"] == "Updated Subject"
        mock_table.update.assert_called_once_with({"subject": "Updated Subject"})


@pytest.mark.asyncio
async def test_update_draft_raises_not_found_error() -> None:
    """Test that update_draft raises NotFoundError when draft doesn't exist."""
    from src.services.draft_service import DraftService

    with (
        patch("src.services.draft_service.LLMClient"),
        patch("src.services.draft_service.DigitalTwin"),
        patch("src.services.draft_service.SupabaseClient") as mock_db_class,
    ):
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_update = MagicMock()
        mock_eq1 = MagicMock()
        mock_eq2 = MagicMock()
        mock_eq2.execute.return_value = MagicMock(data=[])
        mock_eq1.eq.return_value = mock_eq2
        mock_update.eq.return_value = mock_eq1
        mock_table.update.return_value = mock_update
        mock_client.table.return_value = mock_table
        mock_db_class.get_client.return_value = mock_client

        service = DraftService()
        with pytest.raises(NotFoundError):
            await service.update_draft(
                "user-456",
                "nonexistent",
                {"subject": "New Subject"},
            )


@pytest.mark.asyncio
async def test_delete_draft_removes_draft() -> None:
    """Test that delete_draft removes the draft."""
    from src.services.draft_service import DraftService

    with (
        patch("src.services.draft_service.LLMClient"),
        patch("src.services.draft_service.DigitalTwin"),
        patch("src.services.draft_service.SupabaseClient") as mock_db_class,
    ):
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_delete = MagicMock()
        mock_eq1 = MagicMock()
        mock_eq2 = MagicMock()
        mock_eq2.execute.return_value = MagicMock(data=[])
        mock_eq1.eq.return_value = mock_eq2
        mock_delete.eq.return_value = mock_eq1
        mock_table.delete.return_value = mock_delete
        mock_client.table.return_value = mock_table
        mock_db_class.get_client.return_value = mock_client

        service = DraftService()
        result = await service.delete_draft("user-456", "draft-123")

        assert result is True
        mock_table.delete.assert_called_once()


@pytest.mark.asyncio
async def test_delete_draft_returns_false_on_error() -> None:
    """Test that delete_draft returns False on error."""
    from src.services.draft_service import DraftService

    with (
        patch("src.services.draft_service.LLMClient"),
        patch("src.services.draft_service.DigitalTwin"),
        patch("src.services.draft_service.SupabaseClient") as mock_db_class,
    ):
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_delete = MagicMock()
        mock_delete.eq.side_effect = Exception("DB Error")
        mock_table.delete.return_value = mock_delete
        mock_client.table.return_value = mock_table
        mock_db_class.get_client.return_value = mock_client

        service = DraftService()
        result = await service.delete_draft("user-456", "draft-123")

        assert result is False


@pytest.mark.asyncio
async def test_regenerate_draft_regenerates_with_new_params(
    mock_draft_data: dict[str, Any],
) -> None:
    """Test that regenerate_draft regenerates the draft with new parameters."""
    from src.services.draft_service import DraftService

    with (
        patch("src.services.draft_service.LLMClient") as mock_llm_class,
        patch("src.services.draft_service.DigitalTwin") as mock_twin_class,
        patch("src.services.draft_service.SupabaseClient") as mock_db_class,
    ):
        mock_llm = AsyncMock()
        mock_llm.generate_response = AsyncMock(
            return_value='{"subject": "Urgent: Follow-up needed", "body": "Dear John..."}'
        )
        mock_llm_class.return_value = mock_llm

        mock_twin = AsyncMock()
        mock_twin.get_style_guidelines = AsyncMock(return_value="Be direct.")
        mock_twin.score_style_match = AsyncMock(return_value=0.92)
        mock_twin_class.return_value = mock_twin

        mock_client = MagicMock()

        def create_table_mock(name: str) -> MagicMock:
            mock_table = MagicMock()

            if name == "email_drafts":
                # For get_draft (select)
                mock_select = MagicMock()
                mock_eq1 = MagicMock()
                mock_eq2 = MagicMock()
                mock_single = MagicMock()
                mock_single.execute.return_value = MagicMock(data=mock_draft_data)
                mock_eq2.single.return_value = mock_single
                mock_eq1.eq.return_value = mock_eq2
                mock_select.eq.return_value = mock_eq1
                mock_table.select.return_value = mock_select

                # For update_draft (update)
                regenerated_data = {
                    **mock_draft_data,
                    "subject": "Urgent: Follow-up needed",
                    "body": "Dear John...",
                    "tone": "urgent",
                    "style_match_score": 0.92,
                }
                mock_update = MagicMock()
                mock_update_eq1 = MagicMock()
                mock_update_eq2 = MagicMock()
                mock_update_eq2.execute.return_value = MagicMock(data=[regenerated_data])
                mock_update_eq1.eq.return_value = mock_update_eq2
                mock_update.eq.return_value = mock_update_eq1
                mock_table.update.return_value = mock_update

            elif name == "lead_memories":
                mock_select = MagicMock()
                mock_eq1 = MagicMock()
                mock_eq2 = MagicMock()
                mock_single = MagicMock()
                mock_single.execute.return_value = MagicMock(data=None)
                mock_eq2.single.return_value = mock_single
                mock_eq1.eq.return_value = mock_eq2
                mock_select.eq.return_value = mock_eq1
                mock_table.select.return_value = mock_select

            return mock_table

        mock_client.table = create_table_mock
        mock_db_class.get_client.return_value = mock_client

        service = DraftService()
        result = await service.regenerate_draft(
            "user-456",
            "draft-123",
            tone=EmailDraftTone.URGENT,
            additional_context="Client is waiting for response",
        )

        # Verify LLM was called with higher temperature for variation
        call_kwargs = mock_llm.generate_response.call_args.kwargs
        assert call_kwargs["temperature"] == 0.8

        # Verify result has updated tone
        assert result["tone"] == "urgent"
        assert result["style_match_score"] == 0.92


@pytest.mark.asyncio
async def test_regenerate_draft_raises_not_found_error() -> None:
    """Test that regenerate_draft raises NotFoundError for missing draft."""
    from src.services.draft_service import DraftService

    with (
        patch("src.services.draft_service.LLMClient"),
        patch("src.services.draft_service.DigitalTwin"),
        patch("src.services.draft_service.SupabaseClient") as mock_db_class,
    ):
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_eq1 = MagicMock()
        mock_eq2 = MagicMock()
        mock_single = MagicMock()
        mock_single.execute.return_value = MagicMock(data=None)
        mock_eq2.single.return_value = mock_single
        mock_eq1.eq.return_value = mock_eq2
        mock_select.eq.return_value = mock_eq1
        mock_table.select.return_value = mock_select
        mock_client.table.return_value = mock_table
        mock_db_class.get_client.return_value = mock_client

        service = DraftService()
        with pytest.raises(NotFoundError):
            await service.regenerate_draft("user-456", "nonexistent")


def test_build_generation_prompt_includes_all_elements() -> None:
    """Test that _build_generation_prompt includes all necessary elements."""
    from src.services.draft_service import DraftService

    with (
        patch("src.services.draft_service.LLMClient"),
        patch("src.services.draft_service.DigitalTwin"),
    ):
        service = DraftService()

        prompt = service._build_generation_prompt(
            recipient_email="client@example.com",
            recipient_name="John Doe",
            purpose=EmailDraftPurpose.PROPOSAL,
            tone=EmailDraftTone.FORMAL,
            subject_hint="Partnership proposal",
            context="We discussed expanding collaboration",
            lead_context={"company_name": "Acme Corp", "lifecycle_stage": "negotiation"},
            style_guidelines="Use formal language. Avoid contractions.",
        )

        assert "John Doe" in prompt
        assert "proposal" in prompt.lower()
        assert "formal" in prompt.lower()
        assert "Partnership proposal" in prompt
        assert "expanding collaboration" in prompt
        assert "Acme Corp" in prompt
        assert "negotiation" in prompt
        assert "Use formal language" in prompt


def test_build_generation_prompt_handles_minimal_input() -> None:
    """Test that _build_generation_prompt works with minimal input."""
    from src.services.draft_service import DraftService

    with (
        patch("src.services.draft_service.LLMClient"),
        patch("src.services.draft_service.DigitalTwin"),
    ):
        service = DraftService()

        prompt = service._build_generation_prompt(
            recipient_email="client@example.com",
            recipient_name=None,
            purpose=EmailDraftPurpose.CHECK_IN,
            tone=EmailDraftTone.FRIENDLY,
            subject_hint=None,
            context=None,
            lead_context=None,
            style_guidelines="Default style",
        )

        assert "client@example.com" in prompt
        assert "check-in" in prompt.lower() or "check in" in prompt.lower()


def test_get_draft_service_returns_singleton() -> None:
    """Test that get_draft_service returns the same instance."""
    from src.services.draft_service import get_draft_service

    with (
        patch("src.services.draft_service.LLMClient"),
        patch("src.services.draft_service.DigitalTwin"),
    ):
        # Reset singleton for test
        import src.services.draft_service as module

        module._draft_service = None

        service1 = get_draft_service()
        service2 = get_draft_service()

        assert service1 is service2

        # Clean up
        module._draft_service = None


@pytest.mark.asyncio
async def test_update_draft_with_no_changes_returns_existing(
    mock_draft_data: dict[str, Any],
) -> None:
    """Test that update_draft with empty updates returns existing draft."""
    from src.services.draft_service import DraftService

    with (
        patch("src.services.draft_service.LLMClient"),
        patch("src.services.draft_service.DigitalTwin"),
        patch("src.services.draft_service.SupabaseClient") as mock_db_class,
    ):
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_eq1 = MagicMock()
        mock_eq2 = MagicMock()
        mock_single = MagicMock()
        mock_single.execute.return_value = MagicMock(data=mock_draft_data)
        mock_eq2.single.return_value = mock_single
        mock_eq1.eq.return_value = mock_eq2
        mock_select.eq.return_value = mock_eq1
        mock_table.select.return_value = mock_select
        mock_client.table.return_value = mock_table
        mock_db_class.get_client.return_value = mock_client

        service = DraftService()
        result = await service.update_draft(
            "user-456",
            "draft-123",
            {"subject": None, "body": None},  # All None values
        )

        # Should return existing draft without calling update
        assert result["id"] == "draft-123"
        mock_table.update.assert_not_called()


@pytest.mark.asyncio
async def test_send_draft_via_gmail(
    mock_draft_data: dict[str, Any],
) -> None:
    """Test send_draft sends via Gmail integration."""
    from src.services.draft_service import DraftService

    with (
        patch("src.services.draft_service.LLMClient"),
        patch("src.services.draft_service.DigitalTwin"),
        patch("src.services.draft_service.SupabaseClient") as mock_db_class,
        patch("src.services.draft_service.get_oauth_client") as mock_oauth_getter,
    ):
        mock_client = MagicMock()

        def create_table_mock(name: str) -> MagicMock:
            mock_table = MagicMock()

            if name == "email_drafts":
                # For get_draft (select)
                mock_select = MagicMock()
                mock_eq1 = MagicMock()
                mock_eq2 = MagicMock()
                mock_single = MagicMock()
                mock_single.execute.return_value = MagicMock(data=mock_draft_data)
                mock_eq2.single.return_value = mock_single
                mock_eq1.eq.return_value = mock_eq2
                mock_select.eq.return_value = mock_eq1
                mock_table.select.return_value = mock_select

                # For update_draft (update)
                sent_data = {
                    **mock_draft_data,
                    "status": "sent",
                    "sent_at": "2026-02-03T10:00:00+00:00",
                }
                mock_update = MagicMock()
                mock_update_eq1 = MagicMock()
                mock_update_eq2 = MagicMock()
                mock_update_eq2.execute.return_value = MagicMock(data=[sent_data])
                mock_update_eq1.eq.return_value = mock_update_eq2
                mock_update.eq.return_value = mock_update_eq1
                mock_table.update.return_value = mock_update

            elif name == "user_integrations":
                # Chain: select().eq(user_id).eq(integration_type).eq(status).maybe_single().execute()
                mock_select = MagicMock()
                mock_eq1 = MagicMock()
                mock_eq2 = MagicMock()
                mock_eq3 = MagicMock()
                mock_maybe_single = MagicMock()
                mock_maybe_single.execute.return_value = MagicMock(
                    data={
                        "id": "int-123",
                        "composio_connection_id": "conn-456",
                        "integration_type": "gmail",
                        "status": "active",
                    }
                )
                mock_eq3.maybe_single.return_value = mock_maybe_single
                mock_eq2.eq.return_value = mock_eq3
                mock_eq1.eq.return_value = mock_eq2
                mock_select.eq.return_value = mock_eq1
                mock_table.select.return_value = mock_select

            return mock_table

        mock_client.table = create_table_mock
        mock_db_class.get_client.return_value = mock_client

        mock_oauth = AsyncMock()
        mock_oauth.execute_action = AsyncMock(return_value={"success": True})
        mock_oauth_getter.return_value = mock_oauth

        service = DraftService()
        result = await service.send_draft("user-456", "draft-123")

        assert result["status"] == "sent"
        mock_oauth.execute_action.assert_called_once_with(
            connection_id="conn-456",
            action="gmail_send_email",
            params={
                "to": mock_draft_data["recipient_email"],
                "subject": mock_draft_data["subject"],
                "body": mock_draft_data["body"],
            },
        )


@pytest.mark.asyncio
async def test_send_draft_via_outlook(
    mock_draft_data: dict[str, Any],
) -> None:
    """Test send_draft sends via Outlook integration when Gmail not available."""
    from src.services.draft_service import DraftService

    with (
        patch("src.services.draft_service.LLMClient"),
        patch("src.services.draft_service.DigitalTwin"),
        patch("src.services.draft_service.SupabaseClient") as mock_db_class,
        patch("src.services.draft_service.get_oauth_client") as mock_oauth_getter,
    ):
        mock_client = MagicMock()
        gmail_call_count = 0

        def create_table_mock(name: str) -> MagicMock:
            nonlocal gmail_call_count
            mock_table = MagicMock()

            if name == "email_drafts":
                mock_select = MagicMock()
                mock_eq1 = MagicMock()
                mock_eq2 = MagicMock()
                mock_single = MagicMock()
                mock_single.execute.return_value = MagicMock(data=mock_draft_data)
                mock_eq2.single.return_value = mock_single
                mock_eq1.eq.return_value = mock_eq2
                mock_select.eq.return_value = mock_eq1
                mock_table.select.return_value = mock_select

                sent_data = {**mock_draft_data, "status": "sent"}
                mock_update = MagicMock()
                mock_update_eq1 = MagicMock()
                mock_update_eq2 = MagicMock()
                mock_update_eq2.execute.return_value = MagicMock(data=[sent_data])
                mock_update_eq1.eq.return_value = mock_update_eq2
                mock_update.eq.return_value = mock_update_eq1
                mock_table.update.return_value = mock_update

            elif name == "user_integrations":
                # Chain: select().eq(user_id).eq(integration_type).eq(status).maybe_single().execute()
                mock_select = MagicMock()
                mock_eq1 = MagicMock()

                def eq_router(field: str, value: str) -> MagicMock:
                    nonlocal gmail_call_count
                    mock_eq2 = MagicMock()
                    mock_eq3 = MagicMock()
                    mock_maybe_single = MagicMock()
                    if value == "gmail":
                        gmail_call_count += 1
                        # Gmail not found
                        mock_maybe_single.execute.return_value = MagicMock(data=None)
                    else:
                        # Outlook found
                        mock_maybe_single.execute.return_value = MagicMock(
                            data={
                                "id": "int-123",
                                "composio_connection_id": "conn-789",
                                "integration_type": "outlook",
                                "status": "active",
                            }
                        )
                    mock_eq3.maybe_single.return_value = mock_maybe_single
                    mock_eq2.eq.return_value = mock_eq3
                    return mock_eq2

                mock_eq1.eq = eq_router
                mock_select.eq.return_value = mock_eq1
                mock_table.select.return_value = mock_select

            return mock_table

        mock_client.table = create_table_mock
        mock_db_class.get_client.return_value = mock_client

        mock_oauth = AsyncMock()
        mock_oauth.execute_action = AsyncMock(return_value={"success": True})
        mock_oauth_getter.return_value = mock_oauth

        service = DraftService()
        result = await service.send_draft("user-456", "draft-123")

        assert result["status"] == "sent"
        mock_oauth.execute_action.assert_called_once()
        call_args = mock_oauth.execute_action.call_args
        assert call_args.kwargs["action"] == "outlook_send_email"
        assert call_args.kwargs["connection_id"] == "conn-789"


@pytest.mark.asyncio
async def test_send_draft_fails_without_integration(
    mock_draft_data: dict[str, Any],
) -> None:
    """Test send_draft fails when no email integration."""
    from src.services.draft_service import DraftService

    with (
        patch("src.services.draft_service.LLMClient"),
        patch("src.services.draft_service.DigitalTwin"),
        patch("src.services.draft_service.SupabaseClient") as mock_db_class,
    ):
        mock_client = MagicMock()

        def create_table_mock(name: str) -> MagicMock:
            mock_table = MagicMock()

            if name == "email_drafts":
                mock_select = MagicMock()
                mock_eq1 = MagicMock()
                mock_eq2 = MagicMock()
                mock_single = MagicMock()
                mock_single.execute.return_value = MagicMock(data=mock_draft_data)
                mock_eq2.single.return_value = mock_single
                mock_eq1.eq.return_value = mock_eq2
                mock_select.eq.return_value = mock_eq1
                mock_table.select.return_value = mock_select

            elif name == "user_integrations":
                mock_select = MagicMock()
                mock_eq1 = MagicMock()
                mock_eq2 = MagicMock()
                mock_maybe_single = MagicMock()
                # No integration found
                mock_maybe_single.execute.return_value = MagicMock(data=None)
                mock_eq2.maybe_single.return_value = mock_maybe_single
                mock_eq1.eq.return_value = mock_eq2
                mock_select.eq.return_value = mock_eq1
                mock_table.select.return_value = mock_select

            return mock_table

        mock_client.table = create_table_mock
        mock_db_class.get_client.return_value = mock_client

        service = DraftService()
        with pytest.raises(EmailSendError) as exc_info:
            await service.send_draft("user-456", "draft-123")
        assert "integration" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_send_draft_fails_for_already_sent(
    mock_draft_data: dict[str, Any],
) -> None:
    """Test send_draft fails when draft is already sent."""
    from src.services.draft_service import DraftService

    with (
        patch("src.services.draft_service.LLMClient"),
        patch("src.services.draft_service.DigitalTwin"),
        patch("src.services.draft_service.SupabaseClient") as mock_db_class,
    ):
        mock_client = MagicMock()
        sent_draft_data = {**mock_draft_data, "status": "sent"}

        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_eq1 = MagicMock()
        mock_eq2 = MagicMock()
        mock_single = MagicMock()
        mock_single.execute.return_value = MagicMock(data=sent_draft_data)
        mock_eq2.single.return_value = mock_single
        mock_eq1.eq.return_value = mock_eq2
        mock_select.eq.return_value = mock_eq1
        mock_table.select.return_value = mock_select
        mock_client.table.return_value = mock_table
        mock_db_class.get_client.return_value = mock_client

        service = DraftService()
        with pytest.raises(EmailSendError) as exc_info:
            await service.send_draft("user-456", "draft-123")
        assert "already sent" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_send_draft_fails_for_not_found() -> None:
    """Test send_draft fails when draft doesn't exist."""
    from src.services.draft_service import DraftService

    with (
        patch("src.services.draft_service.LLMClient"),
        patch("src.services.draft_service.DigitalTwin"),
        patch("src.services.draft_service.SupabaseClient") as mock_db_class,
    ):
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_eq1 = MagicMock()
        mock_eq2 = MagicMock()
        mock_single = MagicMock()
        mock_single.execute.return_value = MagicMock(data=None)
        mock_eq2.single.return_value = mock_single
        mock_eq1.eq.return_value = mock_eq2
        mock_select.eq.return_value = mock_eq1
        mock_table.select.return_value = mock_select
        mock_client.table.return_value = mock_table
        mock_db_class.get_client.return_value = mock_client

        service = DraftService()
        with pytest.raises(NotFoundError):
            await service.send_draft("user-456", "nonexistent")
