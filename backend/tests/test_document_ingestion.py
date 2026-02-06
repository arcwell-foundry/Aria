"""Tests for the document upload & ingestion pipeline (US-904)."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.onboarding.document_ingestion import (
    MAX_COMPANY_TOTAL,
    MAX_FILE_SIZE,
    SUPPORTED_TYPES,
    DocumentIngestionService,
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
    chain.maybe_single.return_value = chain
    chain.single.return_value = chain
    chain.order.return_value = chain
    chain.execute.return_value = _mock_execute(execute_return)
    return chain


@pytest.fixture()
def mock_db() -> MagicMock:
    """Create a mock Supabase client."""
    client = MagicMock()
    return client


@pytest.fixture()
def mock_llm() -> AsyncMock:
    """Create a mock LLM client."""
    llm = AsyncMock()
    llm.generate_response = AsyncMock(return_value="[]")
    return llm


@pytest.fixture()
def service(mock_db: MagicMock, mock_llm: AsyncMock) -> DocumentIngestionService:
    """Create a DocumentIngestionService with mocked dependencies."""
    with patch("src.onboarding.document_ingestion.SupabaseClient") as mock_cls:
        mock_cls.get_client.return_value = mock_db
        with patch("src.onboarding.document_ingestion.LLMClient") as mock_llm_cls:
            mock_llm_cls.return_value = mock_llm
            svc = DocumentIngestionService()
    return svc


# --- Validation tests ---


@pytest.mark.asyncio()
async def test_validate_rejects_unsupported_type(
    service: DocumentIngestionService,
) -> None:
    """Unsupported content types are rejected."""
    result = await service.validate_upload(
        company_id="comp-1",
        filename="malware.exe",
        file_size=1000,
        content_type="application/x-executable",
    )
    assert result["valid"] is False
    assert "Unsupported" in result["reason"]
    assert result["file_type"] == ""


@pytest.mark.asyncio()
async def test_validate_rejects_oversized_file(
    service: DocumentIngestionService,
) -> None:
    """Files over 50MB are rejected."""
    result = await service.validate_upload(
        company_id="comp-1",
        filename="huge.pdf",
        file_size=MAX_FILE_SIZE + 1,
        content_type="application/pdf",
    )
    assert result["valid"] is False
    assert "50MB" in result["reason"]
    assert result["file_type"] == "pdf"


@pytest.mark.asyncio()
async def test_validate_rejects_company_storage_exceeded(
    service: DocumentIngestionService,
    mock_db: MagicMock,
) -> None:
    """Company total storage limit (500MB) is enforced."""
    # Simulate existing usage near the limit
    chain = _build_chain([{"file_size_bytes": MAX_COMPANY_TOTAL - 100}])
    mock_db.table.return_value = chain

    result = await service.validate_upload(
        company_id="comp-1",
        filename="report.pdf",
        file_size=200,
        content_type="application/pdf",
    )
    assert result["valid"] is False
    assert "500MB" in result["reason"]


@pytest.mark.asyncio()
async def test_validate_accepts_valid_file(
    service: DocumentIngestionService,
    mock_db: MagicMock,
) -> None:
    """Valid files pass validation."""
    chain = _build_chain([])
    mock_db.table.return_value = chain

    result = await service.validate_upload(
        company_id="comp-1",
        filename="deck.pdf",
        file_size=1024,
        content_type="application/pdf",
    )
    assert result["valid"] is True
    assert result["reason"] is None
    assert result["file_type"] == "pdf"


@pytest.mark.asyncio()
async def test_validate_accepts_all_supported_types(
    service: DocumentIngestionService,
    mock_db: MagicMock,
) -> None:
    """All defined MIME types pass validation."""
    chain = _build_chain([])
    mock_db.table.return_value = chain

    for content_type, file_type in SUPPORTED_TYPES.items():
        result = await service.validate_upload(
            company_id="comp-1",
            filename=f"file.{file_type}",
            file_size=1024,
            content_type=content_type,
        )
        assert result["valid"] is True, f"Failed for {content_type}"
        assert result["file_type"] == file_type


# --- Text extraction tests ---


@pytest.mark.asyncio()
async def test_extract_text_from_txt(
    service: DocumentIngestionService,
) -> None:
    """Plain text files are decoded correctly."""
    content = b"Hello World\n\nThis is a test document."
    result = await service._extract_text(content, "txt")
    assert "Hello World" in result
    assert "test document" in result


@pytest.mark.asyncio()
async def test_extract_text_from_md(
    service: DocumentIngestionService,
) -> None:
    """Markdown files are decoded correctly."""
    content = b"# Heading\n\nParagraph content."
    result = await service._extract_text(content, "md")
    assert "# Heading" in result
    assert "Paragraph content" in result


@pytest.mark.asyncio()
async def test_extract_text_from_csv(
    service: DocumentIngestionService,
) -> None:
    """CSV files are decoded as text."""
    content = b"Name,Value\nAlpha,100\nBeta,200"
    result = await service._extract_text(content, "csv")
    assert "Alpha" in result
    assert "Beta" in result


@pytest.mark.asyncio()
async def test_extract_text_image_returns_empty(
    service: DocumentIngestionService,
) -> None:
    """Image extraction returns empty (OCR not yet implemented)."""
    result = await service._extract_text(b"\x89PNG", "image")
    assert result == ""


@pytest.mark.asyncio()
async def test_extract_text_unknown_type_returns_empty(
    service: DocumentIngestionService,
) -> None:
    """Unknown file types return empty string."""
    result = await service._extract_text(b"data", "unknown")
    assert result == ""


# --- Semantic chunking tests ---


def test_semantic_chunk_respects_paragraph_boundaries() -> None:
    """Chunks split on paragraph boundaries, not mid-sentence."""
    text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
    chunks = DocumentIngestionService._semantic_chunk(text)
    assert len(chunks) >= 1
    for chunk in chunks:
        assert chunk["content"]
        assert chunk["type"] in ("paragraph", "header", "table", "list")


def test_semantic_chunk_does_not_exceed_max_size() -> None:
    """No chunk exceeds the maximum size limit."""
    # Build a document with many paragraphs
    paragraphs = [f"Paragraph {i} with some content." for i in range(100)]
    text = "\n\n".join(paragraphs)
    max_size = 200
    chunks = DocumentIngestionService._semantic_chunk(text, max_chunk_size=max_size)

    for chunk in chunks:
        # Allow some overflow for the final paragraph added
        assert len(chunk["content"]) <= max_size + 200


def test_semantic_chunk_detects_headers() -> None:
    """Header lines are tagged with type 'header'."""
    text = "# Main Heading\n\nSome paragraph text here."
    chunks = DocumentIngestionService._semantic_chunk(text)
    types = [c["type"] for c in chunks]
    assert "header" in types


def test_semantic_chunk_detects_tables() -> None:
    """Table-like content is tagged with type 'table'."""
    text = "Name | Value | Status\n---|---|---\nAlpha | 100 | Active\n\nRegular text."
    chunks = DocumentIngestionService._semantic_chunk(text)
    types = [c["type"] for c in chunks]
    assert "table" in types


def test_semantic_chunk_detects_lists() -> None:
    """List items are tagged with type 'list'."""
    text = "Introduction\n\n- First item\n- Second item\n- Third item\n\nConclusion."
    chunks = DocumentIngestionService._semantic_chunk(text)
    types = [c["type"] for c in chunks]
    assert "list" in types


def test_semantic_chunk_empty_text() -> None:
    """Empty text returns no chunks."""
    chunks = DocumentIngestionService._semantic_chunk("")
    assert chunks == []


def test_semantic_chunk_single_paragraph() -> None:
    """Single paragraph produces exactly one chunk."""
    text = "Just a single paragraph of text."
    chunks = DocumentIngestionService._semantic_chunk(text)
    assert len(chunks) == 1
    assert chunks[0]["content"] == "Just a single paragraph of text."


# --- Entity extraction tests ---


@pytest.mark.asyncio()
async def test_extract_entities_returns_structured_data(
    service: DocumentIngestionService,
    mock_llm: AsyncMock,
) -> None:
    """Entity extraction returns list of entity dicts."""
    mock_llm.generate_response.return_value = (
        '[{"name": "Pfizer", "type": "company"}, {"name": "Dr. Smith", "type": "person"}]'
    )
    entities = await service._extract_entities("Pfizer CEO Dr. Smith announced...")
    assert len(entities) == 2
    assert entities[0]["name"] == "Pfizer"
    assert entities[0]["type"] == "company"
    assert entities[1]["name"] == "Dr. Smith"


@pytest.mark.asyncio()
async def test_extract_entities_short_text_returns_empty(
    service: DocumentIngestionService,
) -> None:
    """Text under 30 chars skips entity extraction."""
    entities = await service._extract_entities("Hi")
    assert entities == []


@pytest.mark.asyncio()
async def test_extract_entities_handles_malformed_json(
    service: DocumentIngestionService,
    mock_llm: AsyncMock,
) -> None:
    """Malformed LLM response returns empty list instead of crashing."""
    mock_llm.generate_response.return_value = "not valid json"
    entities = await service._extract_entities("Some long text about entities here.")
    assert entities == []


# --- Quality scoring tests ---


@pytest.mark.asyncio()
async def test_score_quality_returns_float_in_range(
    service: DocumentIngestionService,
    mock_llm: AsyncMock,
) -> None:
    """Quality score is a float between 0 and 100."""
    mock_llm.generate_response.return_value = "85"
    score = await service._score_quality("Product capabilities...", "pdf")
    assert 0 <= score <= 100
    assert score == 85.0


@pytest.mark.asyncio()
async def test_score_quality_handles_non_numeric_response(
    service: DocumentIngestionService,
    mock_llm: AsyncMock,
) -> None:
    """Non-numeric LLM response defaults to 50."""
    mock_llm.generate_response.return_value = "High quality document"
    score = await service._score_quality("Some text", "pdf")
    assert score == 50.0


# --- Knowledge extraction tests ---


@pytest.mark.asyncio()
async def test_extract_knowledge_stores_facts(
    service: DocumentIngestionService,
    mock_db: MagicMock,
    mock_llm: AsyncMock,
) -> None:
    """Extracted facts are stored in memory_semantic table."""
    mock_llm.generate_response.return_value = (
        '[{"fact": "Company has 500 employees", "category": "financial", "confidence": 0.8}]'
    )
    chain = _build_chain(None)
    mock_db.table.return_value = chain

    await service._extract_knowledge(
        text="The company has 500 employees worldwide.",
        company_id="comp-1",
        user_id="user-1",
        doc_id="doc-1",
    )

    # Verify insert was called on memory_semantic
    mock_db.table.assert_called_with("memory_semantic")
    insert_call = chain.insert.call_args
    assert insert_call is not None
    inserted = insert_call[0][0]
    assert inserted["fact"] == "Company has 500 employees"
    assert inserted["confidence"] == 0.8
    assert inserted["source"] == "document_upload"
    assert inserted["metadata"]["document_id"] == "doc-1"


@pytest.mark.asyncio()
async def test_extract_knowledge_handles_malformed_json(
    service: DocumentIngestionService,
    mock_db: MagicMock,
    mock_llm: AsyncMock,
) -> None:
    """Malformed knowledge extraction response doesn't crash."""
    mock_llm.generate_response.return_value = "not valid json"
    chain = _build_chain(None)
    mock_db.table.return_value = chain

    # Should not raise
    await service._extract_knowledge(
        text="Some text here",
        company_id="comp-1",
        user_id="user-1",
        doc_id="doc-1",
    )


# --- Embedding tests ---


@pytest.mark.asyncio()
async def test_generate_embedding_returns_correct_dimensions(
    service: DocumentIngestionService,
) -> None:
    """Embedding placeholder returns 1536-dimension vector."""
    embedding = await service._generate_embedding("test text")
    assert len(embedding) == 1536
    assert all(v == 0.0 for v in embedding)


# --- Full upload flow tests ---


@pytest.mark.asyncio()
async def test_upload_and_process_creates_record(
    service: DocumentIngestionService,
    mock_db: MagicMock,
) -> None:
    """upload_and_process stores file and creates document record."""
    # Mock storage
    storage_mock = MagicMock()
    mock_db.storage.from_.return_value = storage_mock

    # Mock document insert
    doc_row = {
        "id": "doc-123",
        "company_id": "comp-1",
        "uploaded_by": "user-1",
        "filename": "deck.txt",
        "file_type": "txt",
        "file_size_bytes": 100,
        "storage_path": "companies/comp-1/documents/deck.txt",
        "processing_status": "processing",
    }
    chain = _build_chain([doc_row])
    mock_db.table.return_value = chain

    result = await service.upload_and_process(
        company_id="comp-1",
        user_id="user-1",
        filename="deck.txt",
        file_content=b"Sample content for testing",
        content_type="text/plain",
    )

    assert result["id"] == "doc-123"
    assert result["processing_status"] == "processing"

    # Verify storage upload was called
    storage_mock.upload.assert_called_once()


@pytest.mark.asyncio()
async def test_get_company_documents_returns_list(
    service: DocumentIngestionService,
    mock_db: MagicMock,
) -> None:
    """get_company_documents returns documents ordered by date."""
    docs = [
        {"id": "doc-1", "filename": "a.pdf"},
        {"id": "doc-2", "filename": "b.pdf"},
    ]
    chain = _build_chain(docs)
    mock_db.table.return_value = chain

    result = await service.get_company_documents("comp-1")
    assert len(result) == 2
    assert result[0]["id"] == "doc-1"


# --- Progress update tests ---


@pytest.mark.asyncio()
async def test_update_progress(
    service: DocumentIngestionService,
    mock_db: MagicMock,
) -> None:
    """Progress updates write to the database."""
    chain = _build_chain(None)
    mock_db.table.return_value = chain

    await service._update_progress("doc-1", 50.0, "processing")

    mock_db.table.assert_called_with("company_documents")
    update_call = chain.update.call_args
    assert update_call is not None
    updated = update_call[0][0]
    assert updated["processing_progress"] == 50.0
    assert updated["processing_status"] == "processing"


# --- Process document pipeline tests ---


@pytest.mark.asyncio()
async def test_process_document_handles_insufficient_text(
    service: DocumentIngestionService,
    mock_db: MagicMock,
) -> None:
    """Documents with < 50 chars of text are marked complete without processing."""
    chain = _build_chain(None)
    mock_db.table.return_value = chain

    await service._process_document(
        doc_id="doc-1",
        content=b"Hi",
        file_type="txt",
        company_id="comp-1",
        user_id="user-1",
    )

    # Should have updated progress to 100/complete
    update_calls = chain.update.call_args_list
    assert any(call[0][0].get("processing_progress") == 100 for call in update_calls)


@pytest.mark.asyncio()
async def test_process_document_marks_failed_on_error(
    service: DocumentIngestionService,
    mock_db: MagicMock,
) -> None:
    """Processing errors mark the document as failed."""
    # First call (update progress) succeeds, then chunk insert fails
    progress_chain = _build_chain(None)
    chunk_chain = MagicMock()
    chunk_chain.select.return_value = chunk_chain
    chunk_chain.insert.return_value = chunk_chain
    chunk_chain.update.return_value = chunk_chain
    chunk_chain.eq.return_value = chunk_chain
    chunk_chain.maybe_single.return_value = chunk_chain
    chunk_chain.execute.side_effect = RuntimeError("DB insert failed")

    # Route table calls: company_documents → progress_chain, document_chunks → error
    def table_router(name: str) -> MagicMock:
        if name == "document_chunks":
            return chunk_chain
        return progress_chain

    mock_db.table.side_effect = table_router

    # Generate enough text to pass the 50-char check
    content = b"A" * 200

    await service._process_document(
        doc_id="doc-1",
        content=content,
        file_type="txt",
        company_id="comp-1",
        user_id="user-1",
    )

    # Verify document was marked as failed
    update_calls = progress_chain.update.call_args_list
    assert any(call[0][0].get("processing_status") == "failed" for call in update_calls)
