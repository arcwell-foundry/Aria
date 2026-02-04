"""Tests for prediction API endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from src.api.deps import get_current_user
from src.main import app


@pytest.fixture
def mock_current_user() -> MagicMock:
    """Create mock current user."""
    user = MagicMock()
    user.id = "user-456"
    user.email = "test@example.com"
    return user


@pytest.fixture
def test_client(mock_current_user: MagicMock) -> TestClient:
    """Create test client with mocked authentication."""

    async def override_get_current_user() -> MagicMock:
        return mock_current_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_create_prediction_returns_created(test_client: TestClient) -> None:
    """Test POST /predictions creates and returns prediction."""
    with patch("src.api.routes.predictions._get_service") as mock_service_factory:
        mock_service = MagicMock()
        mock_service.register = AsyncMock(
            return_value={
                "id": "pred-123",
                "prediction_type": "deal_outcome",
                "prediction_text": "Deal will close",
                "confidence": 0.8,
                "status": "pending",
            }
        )
        mock_service_factory.return_value = mock_service

        response = test_client.post(
            "/api/v1/predictions",
            json={
                "prediction_type": "deal_outcome",
                "prediction_text": "Deal will close",
                "confidence": 0.8,
                "expected_resolution_date": "2026-03-01",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["id"] == "pred-123"


def test_list_predictions_returns_list(test_client: TestClient) -> None:
    """Test GET /predictions returns list."""
    with patch("src.api.routes.predictions._get_service") as mock_service_factory:
        mock_service = MagicMock()
        mock_service.list_predictions = AsyncMock(
            return_value=[
                {"id": "pred-1", "status": "pending"},
                {"id": "pred-2", "status": "validated_correct"},
            ]
        )
        mock_service_factory.return_value = mock_service

        response = test_client.get("/api/v1/predictions")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.json()) == 2


def test_get_prediction_returns_prediction(test_client: TestClient) -> None:
    """Test GET /predictions/{id} returns prediction."""
    with patch("src.api.routes.predictions._get_service") as mock_service_factory:
        mock_service = MagicMock()
        mock_service.get_prediction = AsyncMock(
            return_value={"id": "pred-123", "prediction_type": "deal_outcome"}
        )
        mock_service_factory.return_value = mock_service

        response = test_client.get("/api/v1/predictions/pred-123")

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["id"] == "pred-123"


def test_get_prediction_returns_404_when_not_found(test_client: TestClient) -> None:
    """Test GET /predictions/{id} returns 404 when not found."""
    with patch("src.api.routes.predictions._get_service") as mock_service_factory:
        mock_service = MagicMock()
        mock_service.get_prediction = AsyncMock(return_value=None)
        mock_service_factory.return_value = mock_service

        response = test_client.get("/api/v1/predictions/pred-999")

        assert response.status_code == status.HTTP_404_NOT_FOUND


def test_validate_prediction_updates_status(test_client: TestClient) -> None:
    """Test PUT /predictions/{id}/validate updates prediction."""
    with patch("src.api.routes.predictions._get_service") as mock_service_factory:
        mock_service = MagicMock()
        mock_service.validate = AsyncMock(
            return_value={"id": "pred-123", "status": "validated_correct"}
        )
        mock_service_factory.return_value = mock_service

        response = test_client.put(
            "/api/v1/predictions/pred-123/validate",
            json={"is_correct": True, "validation_notes": "Closed as predicted"},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["status"] == "validated_correct"


def test_validate_prediction_returns_404_when_not_found(test_client: TestClient) -> None:
    """Test PUT /predictions/{id}/validate returns 404 when not found."""
    with patch("src.api.routes.predictions._get_service") as mock_service_factory:
        mock_service = MagicMock()
        mock_service.validate = AsyncMock(return_value=None)
        mock_service_factory.return_value = mock_service

        response = test_client.put(
            "/api/v1/predictions/pred-999/validate",
            json={"is_correct": False, "validation_notes": "Not found"},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


def test_get_calibration_returns_stats(test_client: TestClient) -> None:
    """Test GET /predictions/calibration returns calibration stats."""
    with patch("src.api.routes.predictions._get_service") as mock_service_factory:
        mock_service = MagicMock()
        mock_service.get_calibration_stats = AsyncMock(
            return_value=[
                {
                    "prediction_type": "deal_outcome",
                    "confidence_bucket": 0.8,
                    "total_predictions": 100,
                    "correct_predictions": 78,
                    "accuracy": 0.78,
                    "is_calibrated": True,
                }
            ]
        )
        mock_service_factory.return_value = mock_service

        response = test_client.get("/api/v1/predictions/calibration")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.json()) == 1


def test_get_pending_returns_pending_predictions(test_client: TestClient) -> None:
    """Test GET /predictions/pending returns pending predictions."""
    with patch("src.api.routes.predictions._get_service") as mock_service_factory:
        mock_service = MagicMock()
        mock_service.get_pending = AsyncMock(return_value=[{"id": "pred-1", "status": "pending"}])
        mock_service_factory.return_value = mock_service

        response = test_client.get("/api/v1/predictions/pending")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.json()) == 1


def test_get_accuracy_summary_returns_stats(test_client: TestClient) -> None:
    """Test GET /predictions/accuracy returns accuracy summary."""
    with patch("src.api.routes.predictions._get_service") as mock_service_factory:
        mock_service = MagicMock()
        mock_service.get_accuracy_summary = AsyncMock(
            return_value={
                "overall_accuracy": 0.75,
                "total_predictions": 100,
                "correct_predictions": 75,
                "by_type": {"deal_outcome": 0.8, "timing": 0.7},
            }
        )
        mock_service_factory.return_value = mock_service

        response = test_client.get("/api/v1/predictions/accuracy")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["overall_accuracy"] == 0.75
        assert data["total_predictions"] == 100


def test_predictions_require_auth() -> None:
    """Test that prediction endpoints require authentication."""
    client = TestClient(app)

    response = client.get("/api/v1/predictions")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    response = client.post("/api/v1/predictions", json={})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    response = client.get("/api/v1/predictions/pred-123")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_list_predictions_with_filters(test_client: TestClient) -> None:
    """Test GET /predictions with status and type filters."""
    with patch("src.api.routes.predictions._get_service") as mock_service_factory:
        mock_service = MagicMock()
        mock_service.list_predictions = AsyncMock(return_value=[])
        mock_service_factory.return_value = mock_service

        response = test_client.get(
            "/api/v1/predictions?status=pending&prediction_type=deal_outcome&limit=10"
        )

        assert response.status_code == status.HTTP_200_OK
        # Verify the service was called with correct parameters
        mock_service.list_predictions.assert_called_once()
