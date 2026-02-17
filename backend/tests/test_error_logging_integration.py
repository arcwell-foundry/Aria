"""Tests for structured error logging integration.

Verifies that:
- Unhandled exceptions are recorded in ErrorTracker
- ARIA exceptions are recorded in ErrorTracker
- Internal error details are never exposed in API responses
- Responses include request_id for correlation
"""

from unittest.mock import patch

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from src.core.error_tracker import ErrorTracker


def _create_app_with_error_routes() -> FastAPI:
    """Create a minimal app with exception handlers and routes that raise."""
    from src.core.exceptions import ARIAException

    app = FastAPI()

    router = APIRouter()

    @router.get("/crash")
    async def crash() -> dict:
        raise RuntimeError("secret database connection string leaked")

    @router.get("/aria-error")
    async def aria_error() -> dict:
        raise ARIAException(
            message="Something went wrong",
            code="TEST_ERROR",
            status_code=400,
        )

    @router.get("/ok")
    async def ok() -> dict:
        return {"status": "ok"}

    app.include_router(router)

    # Register the same exception handlers from main.py
    from src.main import (
        aria_exception_handler,
        global_exception_handler,
    )

    app.add_exception_handler(ARIAException, aria_exception_handler)
    app.add_exception_handler(Exception, global_exception_handler)

    return app


@pytest.fixture(autouse=True)
def _reset_tracker() -> None:
    ErrorTracker._instance = None


@pytest.fixture
def client() -> TestClient:
    app = _create_app_with_error_routes()
    return TestClient(app, raise_server_exceptions=False)


class TestUnhandledExceptionRecording:
    """Unhandled exceptions should be recorded in ErrorTracker."""

    def test_unhandled_exception_recorded(self, client: TestClient) -> None:
        response = client.get("/crash")

        assert response.status_code == 500
        tracker = ErrorTracker.get_instance()
        errors = tracker.get_recent_errors(limit=10)
        assert len(errors) >= 1
        latest = errors[0]
        assert latest["service"] == "api"
        assert "RuntimeError" in latest["error_type"]

    def test_does_not_expose_internal_details(self, client: TestClient) -> None:
        response = client.get("/crash")

        data = response.json()
        # Should NOT contain the actual error message
        assert "secret database" not in data.get("detail", "")
        assert "leaked" not in data.get("detail", "")
        # Should have a generic message
        assert data["detail"] == "An internal server error occurred"

    def test_includes_request_id(self, client: TestClient) -> None:
        response = client.get("/crash")

        data = response.json()
        assert "request_id" in data
        assert len(data["request_id"]) > 0


class TestARIAExceptionRecording:
    """ARIA exceptions should be recorded in ErrorTracker."""

    def test_aria_exception_recorded(self, client: TestClient) -> None:
        response = client.get("/aria-error")

        assert response.status_code == 400
        tracker = ErrorTracker.get_instance()
        errors = tracker.get_recent_errors(limit=10)
        assert len(errors) >= 1
        latest = errors[0]
        assert latest["service"] == "api"
        assert latest["error_type"] == "TEST_ERROR"

    def test_aria_exception_returns_user_message(self, client: TestClient) -> None:
        response = client.get("/aria-error")

        data = response.json()
        assert data["detail"] == "Something went wrong"
        assert data["code"] == "TEST_ERROR"


class TestSuccessfulRequestsNotTracked:
    """Successful requests should NOT add errors to tracker."""

    def test_success_not_recorded(self, client: TestClient) -> None:
        response = client.get("/ok")

        assert response.status_code == 200
        tracker = ErrorTracker.get_instance()
        errors = tracker.get_recent_errors(limit=10)
        assert len(errors) == 0
