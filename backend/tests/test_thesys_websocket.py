"""Tests for Thesys C1 WebSocket integration."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestApplyThesysC1:
    @pytest.mark.asyncio
    @patch("src.api.routes.websocket.settings")
    async def test_returns_markdown_when_disabled(self, mock_settings: MagicMock) -> None:
        mock_settings.thesys_configured = False
        from src.api.routes.websocket import _apply_thesys_c1

        content, mode = await _apply_thesys_c1("Hello")
        assert content == "Hello"
        assert mode == "markdown"

    @pytest.mark.asyncio
    @patch("src.api.routes.websocket.settings")
    async def test_returns_markdown_for_non_visualizable(self, mock_settings: MagicMock) -> None:
        mock_settings.thesys_configured = True

        with patch(
            "src.services.thesys_classifier.ThesysRoutingClassifier.classify",
            return_value=(False, None),
        ):
            from src.api.routes.websocket import _apply_thesys_c1

            content, mode = await _apply_thesys_c1("Short reply")
            assert mode == "markdown"

    @pytest.mark.asyncio
    @patch("src.api.routes.websocket.settings")
    async def test_returns_c1_when_service_renders(self, mock_settings: MagicMock) -> None:
        mock_settings.thesys_configured = True

        mock_svc = MagicMock()
        mock_svc.is_available = True
        mock_svc.visualize = AsyncMock(return_value="<div>Rich</div>")

        with (
            patch(
                "src.services.thesys_classifier.ThesysRoutingClassifier.classify",
                return_value=(True, "pipeline_data"),
            ),
            patch(
                "src.services.thesys_service.get_thesys_service",
                return_value=mock_svc,
            ),
        ):
            from src.api.routes.websocket import _apply_thesys_c1

            content, mode = await _apply_thesys_c1("x" * 300 + " pipeline data")
            assert mode == "c1"
            assert content == "<div>Rich</div>"

    @pytest.mark.asyncio
    @patch("src.api.routes.websocket.settings")
    async def test_returns_c1_eligible_when_service_unavailable(self, mock_settings: MagicMock) -> None:
        mock_settings.thesys_configured = True

        mock_svc = MagicMock()
        mock_svc.is_available = False

        with (
            patch(
                "src.services.thesys_classifier.ThesysRoutingClassifier.classify",
                return_value=(True, "pipeline_data"),
            ),
            patch(
                "src.services.thesys_service.get_thesys_service",
                return_value=mock_svc,
            ),
        ):
            from src.api.routes.websocket import _apply_thesys_c1

            content, mode = await _apply_thesys_c1("x" * 300 + " pipeline data")
            assert mode == "c1_eligible"
