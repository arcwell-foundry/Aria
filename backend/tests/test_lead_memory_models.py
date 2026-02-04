"""Tests for lead memory Pydantic models."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError


class TestContributionTypeEnum:
    """Tests for ContributionType enum."""

    def test_contribution_type_enum_exists(self) -> None:
        """Test that ContributionType enum has all required values."""
        from src.models.lead_memory import ContributionType

        assert hasattr(ContributionType, "EVENT")
        assert ContributionType.EVENT.value == "event"
        assert hasattr(ContributionType, "NOTE")
        assert ContributionType.NOTE.value == "note"
        assert hasattr(ContributionType, "INSIGHT")
        assert ContributionType.INSIGHT.value == "insight"


class TestContributionStatusEnum:
    """Tests for ContributionStatus enum."""

    def test_contribution_status_enum_exists(self) -> None:
        """Test that ContributionStatus enum has all required values."""
        from src.models.lead_memory import ContributionStatus

        assert hasattr(ContributionStatus, "PENDING")
        assert ContributionStatus.PENDING.value == "pending"
        assert hasattr(ContributionStatus, "MERGED")
        assert ContributionStatus.MERGED.value == "merged"
        assert hasattr(ContributionStatus, "REJECTED")
        assert ContributionStatus.REJECTED.value == "rejected"


class TestContributorCreateModel:
    """Tests for ContributorCreate Pydantic model."""

    def test_contributor_create_model(self) -> None:
        """Test that ContributorCreate model validates correctly."""
        from src.models.lead_memory import ContributorCreate

        # Test valid creation
        contributor = ContributorCreate(
            contributor_id="user-123",
            contributor_name="Jane Doe",
            contributor_email="jane@example.com",
        )
        assert contributor.contributor_id == "user-123"
        assert contributor.contributor_name == "Jane Doe"
        assert contributor.contributor_email == "jane@example.com"

    def test_contributor_create_missing_fields(self) -> None:
        """Test that ContributorCreate requires all fields."""
        from src.models.lead_memory import ContributorCreate

        # Missing contributor_id - use type: ignore for intentional invalid test
        with pytest.raises(ValidationError):
            ContributorCreate.model_validate({
                "contributor_name": "Jane Doe",
                "contributor_email": "jane@example.com",
            })

    def test_contributor_create_invalid_email(self) -> None:
        """Test that ContributorCreate rejects invalid email."""
        from src.models.lead_memory import ContributorCreate

        with pytest.raises(ValidationError):
            ContributorCreate(
                contributor_id="user-123",
                contributor_name="Jane Doe",
                contributor_email="not-an-email",
            )


class TestContributorResponseModel:
    """Tests for ContributorResponse Pydantic model."""

    def test_contributor_response_model(self) -> None:
        """Test that ContributorResponse model works correctly."""
        from src.models.lead_memory import ContributorResponse

        contributor = ContributorResponse(
            id="contrib-123",
            lead_memory_id="lead-456",
            name="Jane Doe",
            email="jane@example.com",
            added_at=datetime.now(UTC),
            contribution_count=5,
        )
        assert contributor.id == "contrib-123"
        assert contributor.lead_memory_id == "lead-456"
        assert contributor.name == "Jane Doe"
        assert contributor.email == "jane@example.com"
        assert contributor.contribution_count == 5

    def test_contributor_response_invalid_email(self) -> None:
        """Test that ContributorResponse rejects invalid email."""
        from src.models.lead_memory import ContributorResponse

        with pytest.raises(ValidationError):
            ContributorResponse(
                id="contrib-123",
                lead_memory_id="lead-456",
                name="Jane Doe",
                email="not-an-email",
                added_at=datetime.now(UTC),
                contribution_count=5,
            )


class TestContributionCreateModel:
    """Tests for ContributionCreate Pydantic model."""

    def test_contribution_create_model(self) -> None:
        """Test that ContributionCreate model validates correctly."""
        from src.models.lead_memory import ContributionCreate, ContributionType

        # Test with contribution_type only
        contribution = ContributionCreate(
            contribution_type=ContributionType.EVENT,
            contribution_id=None,
            content=None,
        )
        assert contribution.contribution_type == ContributionType.EVENT
        assert contribution.contribution_id is None
        assert contribution.content is None

        # Test with all fields
        contribution_full = ContributionCreate(
            contribution_type=ContributionType.NOTE,
            contribution_id="note-123",
            content="This is a note contribution",
        )
        assert contribution_full.contribution_type == ContributionType.NOTE
        assert contribution_full.contribution_id == "note-123"
        assert contribution_full.content == "This is a note contribution"


class TestContributionResponseModel:
    """Tests for ContributionResponse Pydantic model."""

    def test_contribution_response_model(self) -> None:
        """Test that ContributionResponse model works correctly."""
        from src.models.lead_memory import (
            ContributionResponse,
            ContributionStatus,
            ContributionType,
        )

        contribution = ContributionResponse(
            id="contrib-123",
            lead_memory_id="lead-456",
            contributor_id="user-789",
            contributor_name="Jane Doe",
            contribution_type=ContributionType.INSIGHT,
            contribution_id="insight-abc",
            content="Competitor mentioned",
            status=ContributionStatus.PENDING,
            created_at=datetime.now(UTC),
            reviewed_at=None,
            reviewed_by=None,
        )
        assert contribution.id == "contrib-123"
        assert contribution.lead_memory_id == "lead-456"
        assert contribution.contributor_id == "user-789"
        assert contribution.contributor_name == "Jane Doe"
        assert contribution.contribution_type == ContributionType.INSIGHT
        assert contribution.status == ContributionStatus.PENDING
        assert contribution.reviewed_at is None
        assert contribution.reviewed_by is None


class TestContributionReviewRequestModel:
    """Tests for ContributionReviewRequest Pydantic model."""

    def test_review_request_valid_actions(self) -> None:
        """Test that ContributionReviewRequest accepts valid actions."""
        from src.models.lead_memory import ContributionReviewRequest

        # Test merge action
        merge_request = ContributionReviewRequest(action="merge")
        assert merge_request.action == "merge"

        # Test reject action
        reject_request = ContributionReviewRequest(action="reject")
        assert reject_request.action == "reject"

    def test_review_request_invalid_action(self) -> None:
        """Test that ContributionReviewRequest rejects invalid actions."""
        from pydantic import ValidationError

        from src.models.lead_memory import ContributionReviewRequest

        # Use model_validate to test invalid actions without type errors
        with pytest.raises(ValidationError):
            ContributionReviewRequest.model_validate({"action": "invalid"})

        with pytest.raises(ValidationError):
            ContributionReviewRequest.model_validate({"action": "approve"})

        with pytest.raises(ValidationError):
            ContributionReviewRequest.model_validate({"action": "delete"})
