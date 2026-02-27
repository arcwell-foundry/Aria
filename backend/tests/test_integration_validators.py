"""Tests for centralized integration health validators."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.integrations.validators import (
    IntegrationHealth,
    check_integration_health,
    get_user_email_integration,
)

USER_ID = "user-123"


def _mock_row(
    *,
    status: str = "active",
    sync_status: str = "success",
    last_sync_at: str | None = None,
    error_message: str | None = None,
    account_email: str = "user@example.com",
    integration_type: str = "gmail",
) -> dict:
    """Build a mock user_integrations row."""
    return {
        "id": "int-1",
        "user_id": USER_ID,
        "integration_type": integration_type,
        "status": status,
        "sync_status": sync_status,
        "last_sync_at": last_sync_at,
        "error_message": error_message,
        "account_email": account_email,
    }


def _recent_iso() -> str:
    """Return an ISO timestamp from 1 hour ago."""
    return (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()


def _stale_iso() -> str:
    """Return an ISO timestamp from 48 hours ago."""
    return (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()


def _setup_mock_client(rows: list[dict]) -> MagicMock:
    """Wire up SupabaseClient.get_client() to return the given rows."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.data = rows

    # Chain: client.table().select().eq().eq().execute()
    mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = (
        mock_response
    )
    return mock_client


# ---------------------------------------------------------------------------
# check_integration_health
# ---------------------------------------------------------------------------


class TestCheckIntegrationHealth:
    """Tests for the check_integration_health function."""

    @pytest.mark.asyncio
    @patch("src.integrations.validators.SupabaseClient")
    async def test_active_integration(self, mock_supa_cls: MagicMock) -> None:
        """A fully active, recently synced integration returns ACTIVE."""
        row = _mock_row(last_sync_at=_recent_iso())
        mock_supa_cls.get_client.return_value = _setup_mock_client([row])

        result = await check_integration_health(USER_ID, "gmail")

        assert result["healthy"] is True
        assert result["status"] == IntegrationHealth.ACTIVE.value
        assert result["provider"] == "gmail"
        assert result["account_email"] == "user@example.com"

    @pytest.mark.asyncio
    @patch("src.integrations.validators.SupabaseClient")
    async def test_stale_integration(self, mock_supa_cls: MagicMock) -> None:
        """An active integration that hasn't synced recently returns STALE."""
        row = _mock_row(last_sync_at=_stale_iso())
        mock_supa_cls.get_client.return_value = _setup_mock_client([row])

        result = await check_integration_health(USER_ID, "gmail")

        assert result["healthy"] is True  # still usable
        assert result["status"] == IntegrationHealth.STALE.value
        assert "hasn't synced recently" in result["detail"]

    @pytest.mark.asyncio
    @patch("src.integrations.validators.SupabaseClient")
    async def test_disconnected_integration(self, mock_supa_cls: MagicMock) -> None:
        """A row with status != 'active' returns DISCONNECTED."""
        row = _mock_row(status="disconnected")
        mock_supa_cls.get_client.return_value = _setup_mock_client([row])

        result = await check_integration_health(USER_ID, "outlook")

        assert result["healthy"] is False
        assert result["status"] == IntegrationHealth.DISCONNECTED.value
        assert "reconnect" in result["detail"].lower()

    @pytest.mark.asyncio
    @patch("src.integrations.validators.SupabaseClient")
    async def test_not_found_integration(self, mock_supa_cls: MagicMock) -> None:
        """No row at all returns NOT_FOUND."""
        mock_supa_cls.get_client.return_value = _setup_mock_client([])

        result = await check_integration_health(USER_ID, "salesforce")

        assert result["healthy"] is False
        assert result["status"] == IntegrationHealth.NOT_FOUND.value
        assert result["provider"] is None
        assert "connect in Settings" in result["detail"]

    @pytest.mark.asyncio
    @patch("src.integrations.validators.SupabaseClient")
    async def test_error_integration(self, mock_supa_cls: MagicMock) -> None:
        """Active but sync_status=failed returns ERROR."""
        row = _mock_row(
            sync_status="failed",
            error_message="Token expired",
            last_sync_at=_recent_iso(),
        )
        mock_supa_cls.get_client.return_value = _setup_mock_client([row])

        result = await check_integration_health(USER_ID, "gmail")

        assert result["healthy"] is False
        assert result["status"] == IntegrationHealth.ERROR.value
        assert result["error_message"] == "Token expired"
        assert "sync failed" in result["detail"]

    @pytest.mark.asyncio
    @patch("src.integrations.validators.SupabaseClient")
    async def test_pending_status_is_disconnected(self, mock_supa_cls: MagicMock) -> None:
        """A pending integration is treated as DISCONNECTED (not active)."""
        row = _mock_row(status="pending")
        mock_supa_cls.get_client.return_value = _setup_mock_client([row])

        result = await check_integration_health(USER_ID, "gmail")

        assert result["healthy"] is False
        assert result["status"] == IntegrationHealth.DISCONNECTED.value

    @pytest.mark.asyncio
    @patch("src.integrations.validators.SupabaseClient")
    async def test_active_no_sync_time_is_active(self, mock_supa_cls: MagicMock) -> None:
        """Active with no last_sync_at is still considered ACTIVE (newly connected)."""
        row = _mock_row(last_sync_at=None)
        mock_supa_cls.get_client.return_value = _setup_mock_client([row])

        result = await check_integration_health(USER_ID, "gmail")

        assert result["healthy"] is True
        assert result["status"] == IntegrationHealth.ACTIVE.value

    @pytest.mark.asyncio
    @patch("src.integrations.validators.SupabaseClient")
    async def test_custom_stale_hours(self, mock_supa_cls: MagicMock) -> None:
        """Custom max_stale_hours changes the threshold."""
        # 5 hours ago — stale with max_stale_hours=4, active with default 24
        five_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        row = _mock_row(last_sync_at=five_hours_ago)
        mock_supa_cls.get_client.return_value = _setup_mock_client([row])

        result = await check_integration_health(USER_ID, "gmail", max_stale_hours=4)

        assert result["status"] == IntegrationHealth.STALE.value


# ---------------------------------------------------------------------------
# get_user_email_integration
# ---------------------------------------------------------------------------


class TestGetUserEmailIntegration:
    """Tests for the get_user_email_integration convenience function."""

    @pytest.mark.asyncio
    @patch("src.integrations.validators.SupabaseClient")
    async def test_returns_healthy_outlook(self, mock_supa_cls: MagicMock) -> None:
        """Returns the first healthy provider (outlook checked first)."""
        row = _mock_row(integration_type="outlook", last_sync_at=_recent_iso())
        mock_supa_cls.get_client.return_value = _setup_mock_client([row])

        result = await get_user_email_integration(USER_ID)

        assert result["healthy"] is True
        assert result["provider"] == "outlook"

    @pytest.mark.asyncio
    @patch("src.integrations.validators.check_integration_health")
    async def test_falls_back_to_gmail(self, mock_check: MagicMock) -> None:
        """If outlook is not found, returns healthy gmail."""
        async def _side_effect(uid: str, provider: str, **kw: int) -> dict:
            if provider == "outlook":
                return {
                    "healthy": False,
                    "status": IntegrationHealth.NOT_FOUND.value,
                    "provider": None,
                    "account_email": None,
                    "last_sync_at": None,
                    "error_message": None,
                    "detail": "No outlook integration found.",
                }
            return {
                "healthy": True,
                "status": IntegrationHealth.ACTIVE.value,
                "provider": "gmail",
                "account_email": "u@gmail.com",
                "last_sync_at": _recent_iso(),
                "error_message": None,
                "detail": "gmail is connected and working.",
            }

        mock_check.side_effect = _side_effect

        result = await get_user_email_integration(USER_ID)

        assert result["healthy"] is True
        assert result["provider"] == "gmail"

    @pytest.mark.asyncio
    @patch("src.integrations.validators.check_integration_health")
    async def test_returns_disconnected_over_not_found(self, mock_check: MagicMock) -> None:
        """When neither is healthy, prefers returning a disconnected status over not_found."""
        async def _side_effect(uid: str, provider: str, **kw: int) -> dict:
            if provider == "outlook":
                return {
                    "healthy": False,
                    "status": IntegrationHealth.DISCONNECTED.value,
                    "provider": "outlook",
                    "account_email": "u@outlook.com",
                    "last_sync_at": None,
                    "error_message": None,
                    "detail": "outlook is disconnected.",
                }
            return {
                "healthy": False,
                "status": IntegrationHealth.NOT_FOUND.value,
                "provider": None,
                "account_email": None,
                "last_sync_at": None,
                "error_message": None,
                "detail": "No gmail integration found.",
            }

        mock_check.side_effect = _side_effect

        result = await get_user_email_integration(USER_ID)

        assert result["healthy"] is False
        assert result["status"] == IntegrationHealth.DISCONNECTED.value
        assert result["provider"] == "outlook"

    @pytest.mark.asyncio
    @patch("src.integrations.validators.check_integration_health")
    async def test_neither_found(self, mock_check: MagicMock) -> None:
        """When no email integration exists at all."""
        async def _side_effect(uid: str, provider: str, **kw: int) -> dict:
            return {
                "healthy": False,
                "status": IntegrationHealth.NOT_FOUND.value,
                "provider": None,
                "account_email": None,
                "last_sync_at": None,
                "error_message": None,
                "detail": f"No {provider} integration found.",
            }

        mock_check.side_effect = _side_effect

        result = await get_user_email_integration(USER_ID)

        assert result["healthy"] is False
        assert result["status"] == IntegrationHealth.NOT_FOUND.value
        assert "Connect your email" in result["detail"]
