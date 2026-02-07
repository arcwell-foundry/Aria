"""Tests for Team & Company Administration Service (US-927)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from src.services.team_service import TeamService
from src.core.exceptions import ARIAException, NotFoundError, ValidationError


@pytest.fixture
def team_service():
    """Create a TeamService instance."""
    return TeamService()


@pytest.fixture
def mock_supabase():
    """Mock Supabase client."""
    with patch("src.services.team_service.SupabaseClient") as mock:
        yield mock


class TestTeamServiceInvite:
    """Test suite for team invite functionality."""

    @pytest.mark.asyncio
    async def test_team_invite_sends_email(self, team_service):
        """Test that team invite sends an email."""
        with patch("src.services.email_service.EmailService") as mock_email_service:
            mock_email_instance = MagicMock()
            mock_email_instance.send_team_invite = AsyncMock(return_value="email_id")
            mock_email_service.return_value = mock_email_instance

            # Mock Supabase operations
            mock_client = MagicMock()

            # Mock checking for existing invite (none found)
            mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[]
            )

            # Mock invite creation
            mock_invite = {
                "id": "invite-123",
                "company_id": "company-123",
                "email": "newuser@example.com",
                "role": "user",
                "token": "test_token",
                "status": "pending",
                "expires_at": (datetime.now() + timedelta(days=7)).isoformat(),
            }
            mock_client.table.return_value.insert.return_value.execute.return_value = MagicMock(
                data=[mock_invite]
            )

            # Mock _check_escalation_trigger
            team_service._check_escalation_trigger = AsyncMock(return_value=False)

            team_service._client = mock_client

            result = await team_service.invite_member(
                company_id="company-123",
                invited_by="user-123",
                email="newuser@example.com",
                role="user",
            )

            # Verify email was sent
            mock_email_instance.send_team_invite.assert_called_once()
            call_args = mock_email_instance.send_team_invite.call_args
            assert call_args.kwargs["to"] == "newuser@example.com"
            assert "inviter_name" in call_args.kwargs
            assert "company_name" in call_args.kwargs
            assert "invite_url" in call_args.kwargs

    @pytest.mark.asyncio
    async def test_team_invite_email_failure_logs_warning(self, team_service):
        """Test that email sending failures are logged but don't break invite creation."""
        with patch("src.services.email_service.EmailService") as mock_email_service:
            mock_email_instance = MagicMock()
            mock_email_instance.send_team_invite = AsyncMock(
                side_effect=Exception("Email service down")
            )
            mock_email_service.return_value = mock_email_instance

            # Mock Supabase operations
            mock_client = MagicMock()
            mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[]
            )
            mock_invite = {
                "id": "invite-123",
                "company_id": "company-123",
                "email": "newuser@example.com",
                "role": "user",
                "token": "test_token",
                "status": "pending",
                "expires_at": (datetime.now() + timedelta(days=7)).isoformat(),
            }
            mock_client.table.return_value.insert.return_value.execute.return_value = MagicMock(
                data=[mock_invite]
            )
            team_service._check_escalation_trigger = AsyncMock(return_value=False)
            team_service._client = mock_client

            # Should not raise even if email fails
            result = await team_service.invite_member(
                company_id="company-123",
                invited_by="user-123",
                email="newuser@example.com",
                role="user",
            )

            # Invite should still be created
            assert result["email"] == "newuser@example.com"

    @pytest.mark.asyncio
    async def test_team_invite_generates_correct_url(self, team_service):
        """Test that team invite generates the correct invite URL."""
        with patch("src.services.email_service.EmailService") as mock_email_service:
            mock_email_instance = MagicMock()
            mock_email_instance.send_team_invite = AsyncMock(return_value="email_id")
            mock_email_service.return_value = mock_email_instance

            # Capture the actual token that will be generated
            generated_token = None

            def capture_token(*args, **kwargs):
                nonlocal generated_token
                # The token is generated when invite_data is created
                # We'll capture it from the kwargs
                return MagicMock(data=[{
                    "id": "invite-123",
                    "company_id": "company-123",
                    "email": "newuser@example.com",
                    "role": "user",
                    "token": "generated_token",
                    "status": "pending",
                    "expires_at": (datetime.now() + timedelta(days=7)).isoformat(),
                }])

            mock_client = MagicMock()
            mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[]
            )

            # Set up insert to capture and return invite with token
            original_execute = MagicMock()

            def side_effect_execute():
                # Get the invite_data that was passed to insert
                call_args = mock_client.table.return_value.insert.call_args
                if call_args and call_args[0]:
                    invite_data = call_args[0][0]
                    generated_token = invite_data.get("token", "")
                    return MagicMock(data=[{
                        "id": "invite-123",
                        "company_id": "company-123",
                        "email": "newuser@example.com",
                        "role": "user",
                        "token": generated_token,
                        "status": "pending",
                        "expires_at": (datetime.now() + timedelta(days=7)).isoformat(),
                    }])
                return MagicMock(data=[])

            mock_client.table.return_value.insert.return_value.execute = MagicMock(side_effect=side_effect_execute)
            team_service._check_escalation_trigger = AsyncMock(return_value=False)
            team_service._client = mock_client

            await team_service.invite_member(
                company_id="company-123",
                invited_by="user-123",
                email="newuser@example.com",
                role="user",
            )

            call_args = mock_email_instance.send_team_invite.call_args
            invite_url = call_args.kwargs.get("invite_url", "")
            # Verify URL structure rather than specific token
            assert "accept-invite" in invite_url
            assert "token=" in invite_url
            assert invite_url.startswith("http://localhost:3000/")


class TestTeamServiceList:
    """Test suite for team listing functionality."""

    @pytest.mark.asyncio
    async def test_list_team(self, team_service):
        """Test listing team members."""
        mock_client = MagicMock()

        mock_profiles = [
            {
                "id": "user-1",
                "full_name": "User One",
                "role": "admin",
                "is_active": True,
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
            },
            {
                "id": "user-2",
                "full_name": "User Two",
                "role": "user",
                "is_active": True,
                "created_at": "2024-01-02T00:00:00Z",
                "updated_at": "2024-01-02T00:00:00Z",
            },
        ]

        mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
            data=mock_profiles
        )

        # Mock auth admin
        mock_user_data_1 = MagicMock()
        mock_user_data_1.user.email = "user1@example.com"
        mock_user_data_2 = MagicMock()
        mock_user_data_2.user.email = "user2@example.com"

        mock_auth_admin = MagicMock()
        mock_auth_admin.get_user_by_id.side_effect = [
            mock_user_data_1,
            mock_user_data_2,
        ]

        mock_client.auth.admin = mock_auth_admin
        team_service._client = mock_client

        result = await team_service.list_team("company-123")

        assert len(result) == 2
        assert result[0]["full_name"] == "User One"
        assert result[0]["email"] == "user1@example.com"
        assert result[0]["role"] == "admin"
        assert result[1]["full_name"] == "User Two"
        assert result[1]["email"] == "user2@example.com"
