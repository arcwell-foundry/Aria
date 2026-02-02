"""Tests for custom exceptions."""

from src.core.exceptions import GraphitiConnectionError, WorkingMemoryError


def test_graphiti_connection_error_attributes() -> None:
    """Test GraphitiConnectionError has correct attributes."""
    error = GraphitiConnectionError("Connection refused")
    assert error.message == "Failed to connect to Neo4j: Connection refused"
    assert error.code == "GRAPHITI_CONNECTION_ERROR"
    assert error.status_code == 503


def test_working_memory_error_attributes() -> None:
    """Test WorkingMemoryError has correct attributes."""
    error = WorkingMemoryError("Context window exceeded")
    assert error.message == "Memory operation failed: Context window exceeded"
    assert error.code == "WORKING_MEMORY_ERROR"
    assert error.status_code == 400


def test_episodic_memory_error_attributes() -> None:
    """Test EpisodicMemoryError has correct attributes."""
    from src.core.exceptions import EpisodicMemoryError

    error = EpisodicMemoryError("Failed to store episode")
    assert error.message == "Episodic memory operation failed: Failed to store episode"
    assert error.code == "EPISODIC_MEMORY_ERROR"
    assert error.status_code == 500


def test_episode_not_found_error_attributes() -> None:
    """Test EpisodeNotFoundError has correct attributes."""
    from src.core.exceptions import EpisodeNotFoundError

    error = EpisodeNotFoundError("ep-123")
    assert error.message == "Episode with ID 'ep-123' not found"
    assert error.code == "NOT_FOUND"
    assert error.status_code == 404


def test_semantic_memory_error_attributes() -> None:
    """Test SemanticMemoryError has correct attributes."""
    from src.core.exceptions import SemanticMemoryError

    error = SemanticMemoryError("Failed to store fact")
    assert error.message == "Semantic memory operation failed: Failed to store fact"
    assert error.code == "SEMANTIC_MEMORY_ERROR"
    assert error.status_code == 500


def test_fact_not_found_error_attributes() -> None:
    """Test FactNotFoundError has correct attributes."""
    from src.core.exceptions import FactNotFoundError

    error = FactNotFoundError("fact-123")
    assert error.message == "Fact with ID 'fact-123' not found"
    assert error.code == "NOT_FOUND"
    assert error.status_code == 404


def test_prospective_memory_error_initialization() -> None:
    """Test ProspectiveMemoryError initializes correctly."""
    from src.core.exceptions import ProspectiveMemoryError

    error = ProspectiveMemoryError("Test error message")

    assert str(error) == "Prospective memory operation failed: Test error message"
    assert error.code == "PROSPECTIVE_MEMORY_ERROR"
    assert error.status_code == 500


def test_task_not_found_error_initialization() -> None:
    """Test TaskNotFoundError initializes correctly."""
    from src.core.exceptions import TaskNotFoundError

    error = TaskNotFoundError("task-123")

    assert "task-123" in str(error)
    assert error.code == "NOT_FOUND"
    assert error.status_code == 404


def test_digital_twin_error_has_correct_attributes() -> None:
    """Test DigitalTwinError has correct message, code, and status."""
    from src.core.exceptions import DigitalTwinError

    error = DigitalTwinError("Style extraction failed")
    assert error.message == "Digital twin operation failed: Style extraction failed"
    assert error.code == "DIGITAL_TWIN_ERROR"
    assert error.status_code == 500


def test_fingerprint_not_found_error_has_correct_attributes() -> None:
    """Test FingerprintNotFoundError has correct message and details."""
    from src.core.exceptions import FingerprintNotFoundError

    error = FingerprintNotFoundError("fp-123")
    assert "Fingerprint" in error.message
    assert "fp-123" in error.message
    assert error.status_code == 404
    assert error.details["resource"] == "Fingerprint"
    assert error.details["resource_id"] == "fp-123"


def test_audit_log_error_initialization() -> None:
    """Test AuditLogError initializes correctly."""
    from src.core.exceptions import AuditLogError

    error = AuditLogError("Failed to write audit log")

    assert error.message == "Audit log operation failed: Failed to write audit log"
    assert error.code == "AUDIT_LOG_ERROR"
    assert error.status_code == 500


def test_corporate_memory_error() -> None:
    """Test CorporateMemoryError exception."""
    from src.core.exceptions import CorporateMemoryError

    error = CorporateMemoryError("Test error")
    assert str(error) == "Corporate memory operation failed: Test error"
    assert error.code == "CORPORATE_MEMORY_ERROR"
    assert error.status_code == 500


def test_corporate_fact_not_found_error() -> None:
    """Test CorporateFactNotFoundError exception."""
    from src.core.exceptions import CorporateFactNotFoundError

    error = CorporateFactNotFoundError("abc123")
    assert "Corporate fact" in str(error)
    assert error.status_code == 404
