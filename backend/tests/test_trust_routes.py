"""Tests for trust API routes."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.trust import TrustProfile


@pytest.fixture
def mock_trust_service():
    with patch("src.api.routes.trust.get_trust_calibration_service") as mock_fn:
        svc = AsyncMock()
        mock_fn.return_value = svc
        yield svc


@pytest.fixture
def mock_db():
    with patch("src.api.routes.trust.SupabaseClient") as mock_cls:
        client = MagicMock()
        mock_cls.get_client.return_value = client
        yield client


@pytest.fixture
def mock_user():
    user = MagicMock()
    user.id = "user-123"
    return user


class TestGetTrustProfiles:
    @pytest.mark.asyncio
    async def test_returns_profiles_with_computed_fields(
        self, mock_trust_service, mock_user
    ) -> None:
        from src.api.routes.trust import get_trust_profiles

        mock_trust_service.get_all_profiles.return_value = [
            TrustProfile(user_id="user-123", action_category="email_send",
                         trust_score=0.7, successful_actions=20,
                         failed_actions=2, override_count=1),
        ]
        mock_trust_service.can_request_autonomy_upgrade.return_value = True

        # Mock the _get_overrides helper
        with patch("src.api.routes.trust._get_overrides", return_value={}):
            result = await get_trust_profiles(mock_user)

        assert len(result) == 1
        assert result[0]["action_category"] == "email_send"
        assert result[0]["can_request_upgrade"] is True
        assert result[0]["override_mode"] is None
        # trust=0.7 (>0.4) + default risk=0.3 (>=0.3, <0.6) → APPROVE_PLAN
        assert result[0]["approval_level"] == "APPROVE_PLAN"

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_profiles(
        self, mock_trust_service, mock_user
    ) -> None:
        from src.api.routes.trust import get_trust_profiles

        mock_trust_service.get_all_profiles.return_value = []

        with patch("src.api.routes.trust._get_overrides", return_value={}):
            result = await get_trust_profiles(mock_user)

        assert result == []


class TestSetTrustOverride:
    @pytest.mark.asyncio
    async def test_sets_override(self, mock_trust_service, mock_user) -> None:
        from src.api.routes.trust import set_trust_override, SetOverrideRequest

        mock_trust_service.get_trust_profile.return_value = TrustProfile(
            user_id="user-123", action_category="email_send", trust_score=0.7,
            successful_actions=20, failed_actions=2, override_count=1,
        )
        mock_trust_service.can_request_autonomy_upgrade.return_value = False

        with patch("src.api.routes.trust._get_overrides", return_value={}), \
             patch("src.api.routes.trust._save_overrides") as mock_save:
            req = SetOverrideRequest(mode="always_approve")
            result = await set_trust_override("email_send", req, mock_user)

        assert result["override_mode"] == "always_approve"
        mock_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_aria_decides_removes_override(self, mock_trust_service, mock_user) -> None:
        from src.api.routes.trust import set_trust_override, SetOverrideRequest

        mock_trust_service.get_trust_profile.return_value = TrustProfile(
            user_id="user-123", action_category="email_send", trust_score=0.7,
            successful_actions=20, failed_actions=2, override_count=1,
        )
        mock_trust_service.can_request_autonomy_upgrade.return_value = False

        with patch("src.api.routes.trust._get_overrides", return_value={"email_send": "full_auto"}), \
             patch("src.api.routes.trust._save_overrides") as mock_save:
            req = SetOverrideRequest(mode="aria_decides")
            result = await set_trust_override("email_send", req, mock_user)

        assert result["override_mode"] is None
        # Verify the save was called with overrides dict that has email_send removed
        saved_overrides = mock_save.call_args[0][1]
        assert "email_send" not in saved_overrides

    @pytest.mark.asyncio
    async def test_rejects_invalid_mode(self) -> None:
        from src.api.routes.trust import SetOverrideRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SetOverrideRequest(mode="invalid_mode")
