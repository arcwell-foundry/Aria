"""Tests for information extraction service."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_extraction_service_extracts_facts() -> None:
    """Test that extraction service extracts facts from conversation."""
    from src.services.extraction import ExtractionService

    with patch("src.services.extraction.LLMClient") as mock_llm_class:
        mock_llm = AsyncMock()
        mock_llm.generate_response = AsyncMock(
            return_value='[{"subject": "John", "predicate": "works_at", "object": "Acme Corp", "confidence": 0.85}]'
        )
        mock_llm_class.return_value = mock_llm

        service = ExtractionService()
        facts = await service.extract_facts(
            conversation=[
                {"role": "user", "content": "I work at Acme Corp now."},
                {"role": "assistant", "content": "Great! Welcome to Acme Corp."},
            ],
            user_id="user-123",
        )

        assert len(facts) == 1
        assert facts[0]["subject"] == "John"
        assert facts[0]["predicate"] == "works_at"


@pytest.mark.asyncio
async def test_extraction_service_handles_no_facts() -> None:
    """Test that extraction service handles conversations with no extractable facts."""
    from src.services.extraction import ExtractionService

    with patch("src.services.extraction.LLMClient") as mock_llm_class:
        mock_llm = AsyncMock()
        mock_llm.generate_response = AsyncMock(return_value="[]")
        mock_llm_class.return_value = mock_llm

        service = ExtractionService()
        facts = await service.extract_facts(
            conversation=[
                {"role": "user", "content": "Hello!"},
                {"role": "assistant", "content": "Hi there!"},
            ],
            user_id="user-123",
        )

        assert facts == []


@pytest.mark.asyncio
async def test_extraction_service_stores_extracted_facts() -> None:
    """Test that extraction service stores facts to semantic memory."""
    from src.services.extraction import ExtractionService

    with (
        patch("src.services.extraction.LLMClient") as mock_llm_class,
        patch("src.services.extraction.SemanticMemory") as mock_semantic_class,
    ):
        mock_llm = AsyncMock()
        mock_llm.generate_response = AsyncMock(
            return_value='[{"subject": "User", "predicate": "prefers", "object": "morning meetings", "confidence": 0.75}]'
        )
        mock_llm_class.return_value = mock_llm

        mock_semantic = AsyncMock()
        mock_semantic.add_fact = AsyncMock(return_value="fact-123")
        mock_semantic_class.return_value = mock_semantic

        service = ExtractionService()
        await service.extract_and_store(
            conversation=[
                {"role": "user", "content": "I prefer morning meetings."},
            ],
            user_id="user-123",
        )

        mock_semantic.add_fact.assert_called_once()


@pytest.mark.asyncio
async def test_extraction_service_handles_invalid_json() -> None:
    """Test that extraction service handles invalid JSON response gracefully."""
    from src.services.extraction import ExtractionService

    with patch("src.services.extraction.LLMClient") as mock_llm_class:
        mock_llm = AsyncMock()
        mock_llm.generate_response = AsyncMock(return_value="not valid json")
        mock_llm_class.return_value = mock_llm

        service = ExtractionService()
        facts = await service.extract_facts(
            conversation=[
                {"role": "user", "content": "Test message"},
            ],
            user_id="user-123",
        )

        assert facts == []


@pytest.mark.asyncio
async def test_extraction_service_returns_stored_fact_ids() -> None:
    """Test that extract_and_store returns the IDs of stored facts."""
    from src.services.extraction import ExtractionService

    with (
        patch("src.services.extraction.LLMClient") as mock_llm_class,
        patch("src.services.extraction.SemanticMemory") as mock_semantic_class,
    ):
        mock_llm = AsyncMock()
        mock_llm.generate_response = AsyncMock(
            return_value='[{"subject": "Alice", "predicate": "manages", "object": "Sales Team", "confidence": 0.9}]'
        )
        mock_llm_class.return_value = mock_llm

        mock_semantic = AsyncMock()
        mock_semantic.add_fact = AsyncMock(return_value="stored-fact-id")
        mock_semantic_class.return_value = mock_semantic

        service = ExtractionService()
        fact_ids = await service.extract_and_store(
            conversation=[
                {"role": "user", "content": "Alice manages the Sales Team."},
            ],
            user_id="user-123",
        )

        assert len(fact_ids) == 1
        assert fact_ids[0] == "stored-fact-id"


@pytest.mark.asyncio
async def test_extraction_service_handles_storage_failure() -> None:
    """Test that extraction service handles storage failures gracefully."""
    from src.services.extraction import ExtractionService

    with (
        patch("src.services.extraction.LLMClient") as mock_llm_class,
        patch("src.services.extraction.SemanticMemory") as mock_semantic_class,
    ):
        mock_llm = AsyncMock()
        mock_llm.generate_response = AsyncMock(
            return_value='[{"subject": "Test", "predicate": "is", "object": "value", "confidence": 0.8}]'
        )
        mock_llm_class.return_value = mock_llm

        mock_semantic = AsyncMock()
        mock_semantic.add_fact = AsyncMock(side_effect=Exception("Storage failed"))
        mock_semantic_class.return_value = mock_semantic

        service = ExtractionService()
        # Should not raise, but return empty list
        fact_ids = await service.extract_and_store(
            conversation=[
                {"role": "user", "content": "Test message."},
            ],
            user_id="user-123",
        )

        assert fact_ids == []


@pytest.mark.asyncio
async def test_extraction_service_uses_default_confidence() -> None:
    """Test that extraction service uses default confidence when not provided."""
    from src.services.extraction import ExtractionService

    with (
        patch("src.services.extraction.LLMClient") as mock_llm_class,
        patch("src.services.extraction.SemanticMemory") as mock_semantic_class,
    ):
        mock_llm = AsyncMock()
        # Response without confidence field
        mock_llm.generate_response = AsyncMock(
            return_value='[{"subject": "Bob", "predicate": "likes", "object": "coffee"}]'
        )
        mock_llm_class.return_value = mock_llm

        mock_semantic = AsyncMock()
        mock_semantic.add_fact = AsyncMock(return_value="fact-456")
        mock_semantic_class.return_value = mock_semantic

        service = ExtractionService()
        await service.extract_and_store(
            conversation=[
                {"role": "user", "content": "Bob likes coffee."},
            ],
            user_id="user-123",
        )

        # Verify add_fact was called and the fact had default confidence
        call_args = mock_semantic.add_fact.call_args
        stored_fact = call_args[0][0]
        assert stored_fact.confidence == 0.75  # Default confidence
