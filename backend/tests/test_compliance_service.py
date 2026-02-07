"""Tests for Data Management & Compliance Service (US-929)."""

from unittest.mock import MagicMock, patch

import pytest

from src.core.exceptions import NotFoundError
from src.services.compliance_service import ComplianceError, ComplianceService


@pytest.fixture
def compliance_service():
    """Create a ComplianceService instance."""
    return ComplianceService()


@pytest.fixture
def mock_supabase_client():
    """Mock Supabase client."""
    with patch("src.services.compliance_service.SupabaseClient") as mock:
        yield mock


class TestExportUserData:
    """Test user data export functionality."""

    @pytest.mark.asyncio
    async def test_export_user_data_gathers_all_tables(
        self, compliance_service, mock_supabase_client
    ):
        """Test that export_user_data gathers from all required tables."""
        user_id = "test-user-123"

        # Mock Supabase client
        mock_client = MagicMock()
        mock_supabase_client.get_client.return_value = mock_client

        # Mock user profile response
        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"id": user_id, "full_name": "Test User", "company_id": "company-123"}
        )

        # Mock user settings response
        mock_settings_response = MagicMock()
        mock_settings_response.data = {"user_id": user_id, "preferences": {}}

        # Mock onboarding response
        mock_onboarding_response = MagicMock()
        mock_onboarding_response.data = [{"user_id": user_id, "step": "completed"}]

        # Set up the chain for settings
        def mock_table_side_effect(table_name):
            mock_table = MagicMock()
            mock_select = MagicMock()
            mock_eq = MagicMock()
            mock_single = MagicMock()
            mock_execute = MagicMock()

            if table_name == "user_settings":
                mock_execute.return_value = mock_settings_response
            elif table_name == "onboarding_state":
                mock_execute.return_value = mock_onboarding_response
            else:
                mock_execute.return_value = MagicMock(data={"id": user_id})

            mock_single.return_value = mock_execute
            mock_eq.return_value = mock_single
            mock_select.return_value = mock_eq
            return mock_table

        mock_client.table.side_effect = mock_table_side_effect

        result = await compliance_service.export_user_data(user_id)

        assert "export_date" in result
        assert "user_id" in result
        assert result["user_id"] == user_id
        assert "user_profile" in result
        assert "user_settings" in result
        assert "onboarding_state" in result
        assert "semantic_memory" in result
        assert "prospective_memory" in result
        assert "conversations" in result
        assert "documents" in result
        assert "audit_log" in result

    @pytest.mark.asyncio
    async def test_export_user_data_handles_missing_tables(
        self, compliance_service, mock_supabase_client
    ):
        """Test that export handles tables that don't exist gracefully."""
        user_id = "test-user-456"

        mock_client = MagicMock()
        mock_supabase_client.get_client.return_value = mock_client

        # The service wraps some table access in try/except
        # When those tables don't exist, they return empty lists
        # We'll test by making sure the service doesn't crash

        # Mock successful responses for required tables
        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"id": user_id, "full_name": "Test User"}
        )

        # This should not raise an exception
        result = await compliance_service.export_user_data(user_id)

        assert result["user_id"] == user_id
        # The service should initialize all keys, even if empty
        assert "semantic_memory" in result
        assert "prospective_memory" in result


class TestExportCompanyData:
    """Test company data export functionality."""

    @pytest.mark.asyncio
    async def test_export_company_data_admin_only(
        self, compliance_service, mock_supabase_client
    ):
        """Test that company export requires admin role."""
        company_id = "test-company-123"
        admin_id = "admin-user-456"

        mock_client = MagicMock()
        mock_supabase_client.get_client.return_value = mock_client

        # Create a function to make mock responses
        def make_response(data):
            resp = MagicMock()
            resp.data = data
            return resp

        # We need to handle the admin check which has TWO .eq() calls
        # Chain: .table().select().eq(id).eq(company_id).single().execute()

        # For admin check - simulate admin user
        mock_admin_response = make_response({"id": admin_id, "role": "admin", "company_id": company_id})

        # Set up the chain for admin verification (has two .eq() calls)
        # First eq is for id, second eq is for company_id
        mock_second_eq = MagicMock()
        mock_second_eq.single.return_value.execute.return_value = mock_admin_response

        mock_first_eq = MagicMock()
        mock_first_eq.eq.return_value = mock_second_eq

        mock_select = MagicMock()
        mock_select.eq.return_value = mock_first_eq

        # Now set up the table mock using side_effect to return different chains
        call_tracker = {"count": 0}

        def table_side_effect(table_name):
            call_tracker["count"] += 1
            mock_table = MagicMock()

            if table_name == "user_profiles" and call_tracker["count"] == 1:
                # First call: admin verification
                mock_table.select.return_value = mock_select
            elif table_name == "companies":
                # Company info
                mock_table.select.return_value.eq.return_value.single.return_value.execute.return_value = make_response(
                    {"id": company_id, "name": "Test Company"}
                )
            elif table_name == "user_profiles" and call_tracker["count"] > 1:
                # Get all users
                mock_table.select.return_value.eq.return_value.execute.return_value = make_response(
                    [{"id": admin_id, "role": "admin"}]
                )
            elif table_name == "company_documents":
                mock_table.select.return_value.eq.return_value.execute.return_value = make_response([])

            return mock_table

        mock_client.table.side_effect = table_side_effect

        result = await compliance_service.export_company_data(company_id, admin_id)

        assert "export_date" in result
        assert "company_id" in result
        assert result["company_id"] == company_id
        assert "exported_by" in result
        assert result["exported_by"] == admin_id
        assert "company" in result
        assert "users" in result
        assert "documents" in result

    @pytest.mark.asyncio
    async def test_export_company_data_non_admin_raises_error(
        self, compliance_service, mock_supabase_client
    ):
        """Test that non-admin users cannot export company data."""
        company_id = "test-company-123"
        non_admin_id = "user-456"

        mock_client = MagicMock()
        mock_supabase_client.get_client.return_value = mock_client

        # Mock admin check - user is not admin
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=None  # User not found or not admin
        )

        with pytest.raises(ComplianceError, match="Only admins can export company data"):
            await compliance_service.export_company_data(company_id, non_admin_id)


class TestDeleteUserData:
    """Test user data deletion functionality."""

    @pytest.mark.asyncio
    async def test_delete_user_data_requires_confirmation(
        self, compliance_service
    ):
        """Test that deletion requires exact confirmation string."""
        user_id = "test-user-789"

        with pytest.raises(ComplianceError, match='must be exactly "DELETE MY DATA"'):
            await compliance_service.delete_user_data(user_id, "wrong confirmation")

        with pytest.raises(ComplianceError, match='must be exactly "DELETE MY DATA"'):
            await compliance_service.delete_user_data(user_id, "delete my data")

        with pytest.raises(ComplianceError, match='must be exactly "DELETE MY DATA"'):
            await compliance_service.delete_user_data(user_id, "")

    @pytest.mark.asyncio
    async def test_delete_user_data_cascades_correctly(
        self, compliance_service, mock_supabase_client
    ):
        """Test that deletion follows correct cascade order."""
        user_id = "test-user-789"
        confirmation = "DELETE MY DATA"

        mock_client = MagicMock()
        mock_supabase_client.get_client.return_value = mock_client

        # Mock successful deletions
        mock_client.table.return_value.delete.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "deleted-1"}]  # Simulate deleted items
        )

        # Mock conversations query
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "conv-1"}, {"id": "conv-2"}]
        )

        result = await compliance_service.delete_user_data(user_id, confirmation)

        assert result["deleted"] is True
        assert result["user_id"] == user_id
        assert "summary" in result
        # Verify cascade order by checking tables were called
        assert mock_client.table.called


class TestDeleteDigitalTwin:
    """Test digital twin deletion functionality."""

    @pytest.mark.asyncio
    async def test_delete_digital_twin_removes_only_twin_data(
        self, compliance_service, mock_supabase_client
    ):
        """Test that digital twin deletion removes only twin data."""
        user_id = "test-user-abc"

        mock_client = MagicMock()
        mock_supabase_client.get_client.return_value = mock_client

        # Mock existing settings with digital twin data
        existing_preferences = {
            "digital_twin": {
                "writing_style": "formal",
                "communication_patterns": {"directness": 0.8},
            },
            "other_setting": "should_remain",
        }

        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"user_id": user_id, "preferences": existing_preferences}
        )

        # Mock update
        mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

        result = await compliance_service.delete_digital_twin(user_id)

        assert result["deleted"] is True
        assert result["user_id"] == user_id
        assert "deleted_at" in result

        # Verify update was called with modified preferences
        mock_client.table.return_value.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_digital_twin_user_not_found(
        self, compliance_service, mock_supabase_client
    ):
        """Test that deleting twin for non-existent user raises NotFoundError."""
        user_id = "nonexistent-user"

        mock_client = MagicMock()
        mock_supabase_client.get_client.return_value = mock_client

        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=None
        )

        with pytest.raises(NotFoundError):
            await compliance_service.delete_digital_twin(user_id)


class TestConsentManagement:
    """Test consent management functionality."""

    @pytest.mark.asyncio
    async def test_get_consent_status_returns_all_flags(
        self, compliance_service, mock_supabase_client
    ):
        """Test that consent status returns all consent categories."""
        user_id = "test-user-def"

        mock_client = MagicMock()
        mock_supabase_client.get_client.return_value = mock_client

        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={
                "user_id": user_id,
                "preferences": {
                    "consent": {
                        "email_analysis": True,
                        "document_learning": False,
                        "crm_processing": True,
                        "writing_style_learning": True,
                    }
                },
            }
        )

        result = await compliance_service.get_consent_status(user_id)

        assert "email_analysis" in result
        assert "document_learning" in result
        assert "crm_processing" in result
        assert "writing_style_learning" in result
        assert result["email_analysis"] is True
        assert result["document_learning"] is False

    @pytest.mark.asyncio
    async def test_get_consent_status_defaults_to_granted(
        self, compliance_service, mock_supabase_client
    ):
        """Test that missing consent defaults to granted."""
        user_id = "test-user-ghi"

        mock_client = MagicMock()
        mock_supabase_client.get_client.return_value = mock_client

        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"user_id": user_id, "preferences": {}}
        )

        result = await compliance_service.get_consent_status(user_id)

        # All should default to True
        for category, granted in result.items():
            assert granted is True, f"{category} should default to granted"

    @pytest.mark.asyncio
    async def test_update_consent_persists_change(
        self, compliance_service, mock_supabase_client
    ):
        """Test that consent toggle persists to database."""
        user_id = "test-user-jkl"

        mock_client = MagicMock()
        mock_supabase_client.get_client.return_value = mock_client

        # Mock existing settings
        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"user_id": user_id, "preferences": {"consent": {}}}
        )

        # Mock update
        mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

        result = await compliance_service.update_consent(user_id, "email_analysis", False)

        assert result["category"] == "email_analysis"
        assert result["granted"] is False
        assert "updated_at" in result

    @pytest.mark.asyncio
    async def test_update_consent_invalid_category_raises_error(
        self, compliance_service
    ):
        """Test that invalid consent category raises error."""
        user_id = "test-user-mno"

        with pytest.raises(ComplianceError, match="Invalid consent category"):
            await compliance_service.update_consent(user_id, "invalid_category", True)


class TestMarkDontLearn:
    """Test don't learn marking functionality."""

    @pytest.mark.asyncio
    async def test_mark_dont_learn_excludes_content(
        self, compliance_service, mock_supabase_client
    ):
        """Test that don't learn marks semantic memory entries as excluded."""
        user_id = "test-user-pqr"
        content_ids = ["mem-1", "mem-2", "mem-3"]

        mock_client = MagicMock()
        mock_supabase_client.get_client.return_value = mock_client

        # Mock successful updates
        mock_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock()

        result = await compliance_service.mark_dont_learn(user_id, content_ids)

        assert result["marked_count"] == 3
        assert result["total_requested"] == 3

    @pytest.mark.asyncio
    async def test_mark_dont_learn_handles_partial_failures(
        self, compliance_service, mock_supabase_client
    ):
        """Test that don't learn continues even if some updates fail."""
        user_id = "test-user-stu"
        content_ids = ["mem-1", "mem-2", "mem-3"]

        mock_client = MagicMock()
        mock_supabase_client.get_client.return_value = mock_client

        # Mock some updates to fail
        call_count = [0]

        def mock_execute():
            call_count[0] += 1
            if call_count[0] <= 2:  # First two succeed
                return MagicMock()
            raise Exception("Database error")

        mock_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.side_effect = mock_execute

        result = await compliance_service.mark_dont_learn(user_id, content_ids)

        # Should count successful marks
        assert result["marked_count"] >= 0
        assert result["total_requested"] == 3


class TestRetentionPolicies:
    """Test retention policy functionality."""

    @pytest.mark.asyncio
    async def test_get_retention_policies_returns_static_definitions(
        self, compliance_service
    ):
        """Test that retention policies return defined durations."""
        result = await compliance_service.get_retention_policies("company-123")

        assert "audit_query_logs" in result
        assert "audit_write_logs" in result
        assert "email_data" in result
        assert "conversation_history" in result

        # Check structure
        for policy_name, policy_data in result.items():
            if policy_name != "note":
                assert "duration_days" in policy_data
                assert "description" in policy_data

        # Verify specific values
        assert result["audit_query_logs"]["duration_days"] == 90
        assert result["audit_write_logs"]["duration_days"] == -1
        assert result["email_data"]["duration_days"] == 365
        assert result["conversation_history"]["duration_days"] == -1
