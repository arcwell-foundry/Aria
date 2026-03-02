"""Tests for ThesysService."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestThesysServiceInit:
    @patch("src.services.thesys_service.settings")
    def test_disabled_when_not_configured(self, mock_settings: MagicMock) -> None:
        mock_settings.thesys_configured = False
        from src.services.thesys_service import ThesysService

        svc = ThesysService()
        assert svc.is_available is False

    @patch("src.services.thesys_service.settings")
    def test_enabled_when_configured(self, mock_settings: MagicMock) -> None:
        mock_settings.thesys_configured = True
        mock_settings.THESYS_API_KEY = MagicMock()
        mock_settings.THESYS_API_KEY.get_secret_value.return_value = "test-key"
        mock_settings.THESYS_BASE_URL = "https://api.thesys.dev/v1/visualize"
        from src.services.thesys_service import ThesysService

        svc = ThesysService()
        assert svc._enabled is True


class TestVisualize:
    @pytest.mark.asyncio
    @patch("src.services.thesys_service.settings")
    async def test_returns_raw_when_disabled(self, mock_settings: MagicMock) -> None:
        mock_settings.thesys_configured = False
        from src.services.thesys_service import ThesysService

        svc = ThesysService()
        result = await svc.visualize("Hello", "system")
        assert result == "Hello"

    @pytest.mark.asyncio
    @patch("src.services.thesys_service.settings")
    async def test_returns_c1_on_success(self, mock_settings: MagicMock) -> None:
        mock_settings.thesys_configured = True
        mock_settings.THESYS_API_KEY = MagicMock()
        mock_settings.THESYS_API_KEY.get_secret_value.return_value = "k"
        mock_settings.THESYS_BASE_URL = "https://api.thesys.dev/v1/visualize"
        mock_settings.THESYS_MODEL = "c1/test"
        mock_settings.THESYS_TIMEOUT = 10.0

        from src.services.thesys_service import ThesysService

        svc = ThesysService()
        svc._enabled = True

        # Mock the internal _call_c1 method
        svc._call_c1 = AsyncMock(return_value="<div>Rich</div>")

        with patch("src.services.thesys_service.thesys_circuit_breaker") as mock_cb:
            mock_cb.check.return_value = None
            mock_cb.record_success.return_value = None
            result = await svc.visualize("Hello", "system")

        assert result == "<div>Rich</div>"

    @pytest.mark.asyncio
    @patch("src.services.thesys_service.settings")
    async def test_returns_raw_on_failure(self, mock_settings: MagicMock) -> None:
        mock_settings.thesys_configured = True
        mock_settings.THESYS_API_KEY = MagicMock()
        mock_settings.THESYS_API_KEY.get_secret_value.return_value = "k"
        mock_settings.THESYS_BASE_URL = "https://api.thesys.dev/v1/visualize"
        mock_settings.THESYS_MODEL = "c1/test"
        mock_settings.THESYS_TIMEOUT = 10.0

        from src.services.thesys_service import ThesysService

        svc = ThesysService()
        svc._enabled = True

        # Mock _call_c1 to raise
        svc._call_c1 = AsyncMock(side_effect=Exception("API down"))

        with patch("src.services.thesys_service.thesys_circuit_breaker") as mock_cb:
            mock_cb.check.return_value = None
            mock_cb.record_failure.return_value = None
            result = await svc.visualize("Hello", "system")

        assert result == "Hello"


class TestIsAvailable:
    @patch("src.services.thesys_service.settings")
    def test_unavailable_when_circuit_open(self, mock_settings: MagicMock) -> None:
        mock_settings.thesys_configured = True
        mock_settings.THESYS_API_KEY = MagicMock()
        mock_settings.THESYS_API_KEY.get_secret_value.return_value = "k"
        mock_settings.THESYS_BASE_URL = "https://api.thesys.dev/v1/visualize"
        from src.core.resilience import CircuitBreakerOpen
        from src.services.thesys_service import ThesysService

        svc = ThesysService()
        svc._enabled = True

        with patch("src.services.thesys_service.thesys_circuit_breaker") as mock_cb:
            mock_cb.check.side_effect = CircuitBreakerOpen("thesys_c1")
            assert svc.is_available is False

    @patch("src.services.thesys_service.settings")
    def test_available_when_enabled_and_circuit_closed(self, mock_settings: MagicMock) -> None:
        mock_settings.thesys_configured = True
        mock_settings.THESYS_API_KEY = MagicMock()
        mock_settings.THESYS_API_KEY.get_secret_value.return_value = "k"
        mock_settings.THESYS_BASE_URL = "https://api.thesys.dev/v1/visualize"
        from src.services.thesys_service import ThesysService

        svc = ThesysService()
        svc._enabled = True

        with patch("src.services.thesys_service.thesys_circuit_breaker") as mock_cb:
            mock_cb.check.return_value = None
            assert svc.is_available is True
