"""Tests for message persistence to the messages table.

Verifies:
- save_message inserts to the messages table with correct fields
- get_conversation_messages reads from the messages table (not working memory)
"""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest


# ============================================================================
# save_message tests
# ============================================================================


class TestSaveMessage:
    """Tests for ConversationService.save_message."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create a mock Supabase client."""
        mock = MagicMock()
        mock.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": "test-msg-id"}]
        )
        return mock

    @pytest.mark.asyncio
    async def test_save_message_inserts_to_messages_table(
        self, mock_db: MagicMock
    ) -> None:
        """save_message should insert a row into the 'messages' table."""
        from src.services.conversations import ConversationService

        service = ConversationService(db_client=mock_db)
        msg_id = await service.save_message(
            conversation_id="conv-123",
            role="user",
            content="Hello ARIA",
        )

        # Should have called table("messages")
        mock_db.table.assert_called_with("messages")
        mock_db.table.return_value.insert.assert_called_once()

        # Verify the inserted row has correct fields
        insert_call = mock_db.table.return_value.insert.call_args
        row: dict[str, Any] = insert_call[0][0]

        assert row["conversation_id"] == "conv-123"
        assert row["role"] == "user"
        assert row["content"] == "Hello ARIA"
        assert row["metadata"] == {}
        assert "id" in row
        assert isinstance(row["id"], str)

        # Return value should be the message ID
        assert msg_id == row["id"]

    @pytest.mark.asyncio
    async def test_save_message_includes_metadata(
        self, mock_db: MagicMock
    ) -> None:
        """save_message should include custom metadata in the row."""
        from src.services.conversations import ConversationService

        service = ConversationService(db_client=mock_db)
        meta = {"skill_plan_id": "plan-abc", "skill_status": "completed"}

        await service.save_message(
            conversation_id="conv-123",
            role="assistant",
            content="Here is the battle card.",
            metadata=meta,
        )

        insert_call = mock_db.table.return_value.insert.call_args
        row: dict[str, Any] = insert_call[0][0]

        assert row["metadata"] == meta
        assert row["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_save_message_generates_uuid(
        self, mock_db: MagicMock
    ) -> None:
        """save_message should generate a UUID for the message ID."""
        import uuid as uuid_mod

        from src.services.conversations import ConversationService

        service = ConversationService(db_client=mock_db)
        msg_id = await service.save_message(
            conversation_id="conv-123",
            role="user",
            content="Test",
        )

        # Verify it's a valid UUID string
        parsed = uuid_mod.UUID(msg_id)
        assert str(parsed) == msg_id

    @pytest.mark.asyncio
    async def test_save_message_defaults_metadata_to_empty_dict(
        self, mock_db: MagicMock
    ) -> None:
        """save_message should default metadata to {} when None is passed."""
        from src.services.conversations import ConversationService

        service = ConversationService(db_client=mock_db)
        await service.save_message(
            conversation_id="conv-123",
            role="user",
            content="Test",
            metadata=None,
        )

        insert_call = mock_db.table.return_value.insert.call_args
        row: dict[str, Any] = insert_call[0][0]
        assert row["metadata"] == {}


# ============================================================================
# get_conversation_messages tests (reads from messages table)
# ============================================================================


class TestGetConversationMessages:
    """Tests for ConversationService.get_conversation_messages reading from messages table."""

    @pytest.fixture
    def mock_db_with_messages(self) -> MagicMock:
        """Create mock DB that returns messages from the messages table."""
        mock = MagicMock()
        now = datetime.now(UTC)

        # Ownership check: conversations table query succeeds
        mock.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"id": "conv-123"}
        )

        # Messages table query returns rows
        messages_data = [
            {
                "id": "msg-1",
                "conversation_id": "conv-123",
                "role": "user",
                "content": "Hello ARIA",
                "metadata": {},
                "created_at": now.isoformat(),
            },
            {
                "id": "msg-2",
                "conversation_id": "conv-123",
                "role": "assistant",
                "content": "Hello! How can I help?",
                "metadata": {},
                "created_at": now.isoformat(),
            },
        ]

        mock.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
            data=messages_data
        )

        return mock

    @pytest.mark.asyncio
    async def test_reads_from_messages_table(
        self, mock_db_with_messages: MagicMock
    ) -> None:
        """get_conversation_messages should query the messages table, not working memory."""
        from src.services.conversations import ConversationService

        service = ConversationService(db_client=mock_db_with_messages)
        messages = await service.get_conversation_messages(
            user_id="user-456",
            conversation_id="conv-123",
        )

        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[0].content == "Hello ARIA"
        assert messages[1].role == "assistant"
        assert messages[1].content == "Hello! How can I help?"

    @pytest.mark.asyncio
    async def test_verifies_ownership_before_querying(
        self,
    ) -> None:
        """get_conversation_messages should check conversation ownership first."""
        from src.core.exceptions import NotFoundError
        from src.services.conversations import ConversationService

        mock_db = MagicMock()
        # Ownership check fails — no matching conversation
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=None
        )

        service = ConversationService(db_client=mock_db)

        with pytest.raises(NotFoundError):
            await service.get_conversation_messages(
                user_id="user-456",
                conversation_id="conv-nonexistent",
            )

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_messages(
        self,
    ) -> None:
        """get_conversation_messages should return [] when no messages exist."""
        from src.services.conversations import ConversationService

        mock_db = MagicMock()
        # Ownership check passes
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"id": "conv-123"}
        )
        # Messages query returns empty
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
            data=[]
        )

        service = ConversationService(db_client=mock_db)
        messages = await service.get_conversation_messages(
            user_id="user-456",
            conversation_id="conv-123",
        )

        assert messages == []

    @pytest.mark.asyncio
    async def test_returns_conversation_message_objects(
        self, mock_db_with_messages: MagicMock
    ) -> None:
        """get_conversation_messages should return ConversationMessage dataclass instances."""
        from src.services.conversations import ConversationMessage, ConversationService

        service = ConversationService(db_client=mock_db_with_messages)
        messages = await service.get_conversation_messages(
            user_id="user-456",
            conversation_id="conv-123",
        )

        for msg in messages:
            assert isinstance(msg, ConversationMessage)
            assert isinstance(msg.id, str)
            assert isinstance(msg.created_at, datetime)

    @pytest.mark.asyncio
    async def test_messages_ordered_chronologically(
        self, mock_db_with_messages: MagicMock
    ) -> None:
        """get_conversation_messages should order by created_at ascending."""
        from src.services.conversations import ConversationService

        service = ConversationService(db_client=mock_db_with_messages)
        await service.get_conversation_messages(
            user_id="user-456",
            conversation_id="conv-123",
        )

        # Verify the order call used desc=False (ascending)
        order_call = mock_db_with_messages.table.return_value.select.return_value.eq.return_value.order
        order_call.assert_called_with("created_at", desc=False)
