"""Tests for Profile Page Service (US-921)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.exceptions import ARIAException, NotFoundError
from src.services.profile_service import ProfileService


@pytest.fixture
def profile_service():
    """Create a ProfileService instance."""
    return ProfileService()


@pytest.fixture
def mock_supabase():
    """Mock Supabase client."""
    with patch("src.services.profile_service.SupabaseClient") as mock:
        yield mock


@pytest.fixture
def sample_user_profile():
    """Sample user profile data from DB."""
    return {
        "id": "user-123",
        "full_name": "Jane Doe",
        "title": "VP Sales",
        "department": "Commercial",
        "linkedin_url": "https://linkedin.com/in/janedoe",
        "avatar_url": "https://example.com/avatar.png",
        "company_id": "company-456",
        "role": "user",
        "communication_preferences": {"briefing_time": "08:00"},
        "privacy_exclusions": ["competitor-data"],
        "default_tone": "friendly",
        "tracked_competitors": ["Acme", "Globex"],
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-15T00:00:00Z",
    }


@pytest.fixture
def sample_company():
    """Sample company data from DB."""
    return {
        "id": "company-456",
        "name": "BioPharm Inc",
        "domain": "biopharm.com",
        "website": "https://biopharm.com",
        "industry": "Life Sciences",
        "sub_vertical": "CDMO",
        "description": "Contract development and manufacturing organization",
        "key_products": ["mRNA Synthesis", "Viral Vectors"],
        "settings": {},
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-10T00:00:00Z",
    }


@pytest.fixture
def sample_integrations():
    """Sample integrations list from DB."""
    return [
        {
            "id": "int-1",
            "integration_type": "gmail",
            "display_name": "jane@biopharm.com",
            "status": "active",
            "last_sync_at": "2024-01-15T00:00:00Z",
            "sync_status": "success",
        },
        {
            "id": "int-2",
            "integration_type": "salesforce",
            "display_name": "BioPharm CRM",
            "status": "active",
            "last_sync_at": "2024-01-14T00:00:00Z",
            "sync_status": "success",
        },
    ]


@pytest.fixture
def sample_preferences():
    """Sample user preferences from DB."""
    return {
        "id": "pref-1",
        "user_id": "user-123",
        "briefing_time": "08:00",
        "meeting_brief_lead_hours": 24,
        "notification_email": True,
        "notification_in_app": True,
        "default_tone": "friendly",
        "tracked_competitors": ["Acme", "Globex"],
        "timezone": "America/New_York",
    }


class TestGetFullProfile:
    """Test suite for get_full_profile - merged view of all profile data."""

    @pytest.mark.asyncio
    async def test_returns_merged_user_company_integrations(
        self,
        profile_service,
        mock_supabase,
        sample_user_profile,
        sample_company,
        sample_integrations,
    ):
        """GET /profile returns user details + company + integrations merged."""
        mock_supabase.get_user_by_id = AsyncMock(return_value=sample_user_profile)

        # Mock company query
        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_eq = MagicMock()
        mock_single = MagicMock()
        mock_execute = MagicMock()
        mock_execute.return_value = MagicMock(data=sample_company)
        mock_single.execute = mock_execute
        mock_eq.single.return_value = mock_single
        mock_select.eq.return_value = mock_eq
        mock_table.select.return_value = mock_select
        mock_supabase.get_client.return_value.table.return_value = mock_table

        # Mock integrations query
        mock_int_table = MagicMock()
        mock_int_select = MagicMock()
        mock_int_eq = MagicMock()
        mock_int_execute = MagicMock()
        mock_int_execute.return_value = MagicMock(data=sample_integrations)
        mock_int_eq.execute = mock_int_execute
        mock_int_select.eq.return_value = mock_int_eq
        mock_int_table.select.return_value = mock_int_select

        # table() should return different mocks per table name
        def table_router(name):
            if name == "companies":
                return mock_table
            if name == "user_integrations":
                return mock_int_table
            return MagicMock()

        mock_supabase.get_client.return_value.table.side_effect = table_router

        result = await profile_service.get_full_profile("user-123")

        assert result["user"]["id"] == "user-123"
        assert result["user"]["full_name"] == "Jane Doe"
        assert result["user"]["title"] == "VP Sales"
        assert result["user"]["department"] == "Commercial"
        assert result["user"]["linkedin_url"] == "https://linkedin.com/in/janedoe"
        assert result["user"]["default_tone"] == "friendly"
        assert result["user"]["tracked_competitors"] == ["Acme", "Globex"]

        assert result["company"]["id"] == "company-456"
        assert result["company"]["name"] == "BioPharm Inc"
        assert result["company"]["industry"] == "Life Sciences"
        assert result["company"]["key_products"] == ["mRNA Synthesis", "Viral Vectors"]

        assert len(result["integrations"]) == 2
        assert result["integrations"][0]["integration_type"] == "gmail"

    @pytest.mark.asyncio
    async def test_returns_null_company_when_no_company(
        self, profile_service, mock_supabase, sample_user_profile
    ):
        """Profile with no company returns company: null."""
        profile_no_company = {**sample_user_profile, "company_id": None}
        mock_supabase.get_user_by_id = AsyncMock(return_value=profile_no_company)

        # Mock integrations (empty)
        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_eq = MagicMock()
        mock_eq.execute.return_value = MagicMock(data=[])
        mock_select.eq.return_value = mock_eq
        mock_table.select.return_value = mock_select
        mock_supabase.get_client.return_value.table.return_value = mock_table

        result = await profile_service.get_full_profile("user-123")

        assert result["user"]["id"] == "user-123"
        assert result["company"] is None

    @pytest.mark.asyncio
    async def test_raises_not_found_for_missing_user(self, profile_service, mock_supabase):
        """Profile for non-existent user raises NotFoundError."""
        mock_supabase.get_user_by_id = AsyncMock(side_effect=NotFoundError("User", "user-999"))

        with pytest.raises(NotFoundError):
            await profile_service.get_full_profile("user-999")


class TestUpdateUserDetails:
    """Test suite for update_user_details."""

    @pytest.mark.asyncio
    async def test_updates_user_profile_fields(self, profile_service, mock_supabase):
        """PUT /profile/user updates name, title, department, etc."""
        # Mock SupabaseClient.get_user_by_id for US-922 diff detection
        old_user_data = {
            "id": "user-123",
            "full_name": "John Doe",
            "title": "Sales Director",
            "department": "Commercial",
        }
        mock_supabase.get_user_by_id = AsyncMock(return_value=old_user_data)

        mock_table = MagicMock()
        mock_update = MagicMock()
        mock_eq = MagicMock()
        updated_data = {
            "id": "user-123",
            "full_name": "Jane Smith",
            "title": "SVP Sales",
            "department": "Commercial",
        }
        mock_eq.execute.return_value = MagicMock(data=[updated_data])
        mock_update.eq.return_value = mock_eq
        mock_table.update.return_value = mock_update
        mock_supabase.get_client.return_value.table.return_value = mock_table

        result = await profile_service.update_user_details(
            user_id="user-123",
            data={
                "full_name": "Jane Smith",
                "title": "SVP Sales",
            },
        )

        assert result["full_name"] == "Jane Smith"
        assert result["title"] == "SVP Sales"
        assert result["merge_pending"] is True
        mock_table.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_update_returns_current_profile(
        self, profile_service, mock_supabase, sample_user_profile
    ):
        """Empty update data should return current profile without DB write."""
        mock_supabase.get_user_by_id = AsyncMock(return_value=sample_user_profile)

        # Mock for integrations/company
        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_eq = MagicMock()
        mock_eq.execute.return_value = MagicMock(data=[])
        mock_eq.single.return_value = MagicMock(
            execute=MagicMock(return_value=MagicMock(data=None))
        )
        mock_select.eq.return_value = mock_eq
        mock_table.select.return_value = mock_select
        mock_supabase.get_client.return_value.table.return_value = mock_table

        await profile_service.update_user_details(
            user_id="user-123",
            data={},
        )

        # Should not call update
        mock_table.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_fires_profile_updated_event(self, profile_service, mock_supabase):
        """Profile update logs a security event for audit trail."""
        # Mock SupabaseClient.get_user_by_id for US-922 diff detection
        old_user_data = {"id": "user-123", "full_name": "Old Name"}
        mock_supabase.get_user_by_id = AsyncMock(return_value=old_user_data)

        mock_table = MagicMock()
        mock_update = MagicMock()
        mock_eq = MagicMock()
        mock_eq.execute.return_value = MagicMock(data=[{"id": "user-123", "full_name": "Updated"}])
        mock_update.eq.return_value = mock_eq
        mock_table.update.return_value = mock_update

        # Mock audit log insert
        mock_audit_table = MagicMock()
        mock_audit_insert = MagicMock()
        mock_audit_insert.execute.return_value = MagicMock(data=[{}])
        mock_audit_table.insert.return_value = mock_audit_insert

        def table_router(name):
            if name == "security_audit_log":
                return mock_audit_table
            return mock_table

        mock_supabase.get_client.return_value.table.side_effect = table_router

        await profile_service.update_user_details(
            user_id="user-123",
            data={"full_name": "Updated"},
        )

        mock_audit_table.insert.assert_called_once()
        call_data = mock_audit_table.insert.call_args[0][0]
        assert call_data["event_type"] == "profile_updated"
        assert call_data["user_id"] == "user-123"

    @pytest.mark.asyncio
    async def test_rejects_disallowed_fields(self, profile_service, mock_supabase):
        """Cannot update role or id through profile update."""
        # Mock SupabaseClient.get_user_by_id for US-922 diff detection
        old_user_data = {"id": "user-123", "full_name": "Old Name"}
        mock_supabase.get_user_by_id = AsyncMock(return_value=old_user_data)

        mock_table = MagicMock()
        mock_update = MagicMock()
        mock_eq = MagicMock()
        mock_eq.execute.return_value = MagicMock(data=[{"id": "user-123", "full_name": "Jane"}])
        mock_update.eq.return_value = mock_eq
        mock_table.update.return_value = mock_update

        # Mock audit table
        mock_audit = MagicMock()
        mock_audit.insert.return_value = MagicMock(
            execute=MagicMock(return_value=MagicMock(data=[{}]))
        )

        def table_router(name):
            if name == "security_audit_log":
                return mock_audit
            return mock_table

        mock_supabase.get_client.return_value.table.side_effect = table_router

        await profile_service.update_user_details(
            user_id="user-123",
            data={"full_name": "Jane", "role": "admin", "id": "hacker"},
        )

        # The update call should NOT include role or id
        update_call = mock_table.update.call_args[0][0]
        assert "role" not in update_call
        assert "id" not in update_call
        assert "full_name" in update_call


class TestUpdateCompanyDetails:
    """Test suite for update_company_details - admin only."""

    @pytest.mark.asyncio
    async def test_admin_can_update_company(self, profile_service, mock_supabase):
        """Admin users can update company details."""
        # Mock getting user profile to verify admin role
        mock_supabase.get_user_by_id = AsyncMock(
            return_value={"id": "user-123", "company_id": "company-456", "role": "admin"}
        )

        mock_table = MagicMock()
        mock_update = MagicMock()
        mock_eq = MagicMock()
        updated_company = {
            "id": "company-456",
            "name": "BioPharm Inc",
            "industry": "Biotech",
        }
        mock_eq.execute.return_value = MagicMock(data=[updated_company])
        mock_update.eq.return_value = mock_eq
        mock_table.update.return_value = mock_update

        # Mock audit table
        mock_audit = MagicMock()
        mock_audit.insert.return_value = MagicMock(
            execute=MagicMock(return_value=MagicMock(data=[{}]))
        )

        def table_router(name):
            if name == "security_audit_log":
                return mock_audit
            return mock_table

        mock_supabase.get_client.return_value.table.side_effect = table_router

        result = await profile_service.update_company_details(
            user_id="user-123",
            data={"industry": "Biotech"},
        )

        assert result["industry"] == "Biotech"

    @pytest.mark.asyncio
    async def test_non_admin_cannot_update_company(self, profile_service, mock_supabase):
        """Non-admin users get 403 when updating company details."""
        mock_supabase.get_user_by_id = AsyncMock(
            return_value={"id": "user-123", "company_id": "company-456", "role": "user"}
        )

        with pytest.raises(ARIAException) as exc_info:
            await profile_service.update_company_details(
                user_id="user-123",
                data={"industry": "Biotech"},
            )

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_user_without_company_cannot_update(self, profile_service, mock_supabase):
        """User with no company gets 400."""
        mock_supabase.get_user_by_id = AsyncMock(
            return_value={"id": "user-123", "company_id": None, "role": "admin"}
        )

        with pytest.raises(ARIAException) as exc_info:
            await profile_service.update_company_details(
                user_id="user-123",
                data={"industry": "Biotech"},
            )

        assert exc_info.value.status_code == 400


class TestListDocuments:
    """Test suite for list_documents."""

    @pytest.mark.asyncio
    async def test_lists_both_company_and_user_documents(self, profile_service, mock_supabase):
        """Returns both company and user documents separated by category."""
        mock_supabase.get_user_by_id = AsyncMock(
            return_value={"id": "user-123", "company_id": "company-456", "role": "user"}
        )

        company_docs = [
            {"id": "doc-1", "filename": "deck.pdf", "uploaded_by": "user-123"},
            {"id": "doc-2", "filename": "brochure.pdf", "uploaded_by": "user-other"},
        ]
        user_docs = [
            {"id": "doc-3", "filename": "writing_sample.docx", "user_id": "user-123"},
        ]

        mock_company_table = MagicMock()
        mock_company_select = MagicMock()
        mock_company_eq = MagicMock()
        mock_company_order = MagicMock()
        mock_company_order.execute.return_value = MagicMock(data=company_docs)
        mock_company_eq.order.return_value = mock_company_order
        mock_company_select.eq.return_value = mock_company_eq
        mock_company_table.select.return_value = mock_company_select

        mock_user_table = MagicMock()
        mock_user_select = MagicMock()
        mock_user_eq = MagicMock()
        mock_user_order = MagicMock()
        mock_user_order.execute.return_value = MagicMock(data=user_docs)
        mock_user_eq.order.return_value = mock_user_order
        mock_user_select.eq.return_value = mock_user_eq
        mock_user_table.select.return_value = mock_user_select

        def table_router(name):
            if name == "company_documents":
                return mock_company_table
            if name == "user_documents":
                return mock_user_table
            return MagicMock()

        mock_supabase.get_client.return_value.table.side_effect = table_router

        result = await profile_service.list_documents("user-123")

        assert len(result["company_documents"]) == 2
        assert len(result["user_documents"]) == 1
        assert result["company_documents"][0]["filename"] == "deck.pdf"
        assert result["user_documents"][0]["filename"] == "writing_sample.docx"

    @pytest.mark.asyncio
    async def test_user_without_company_gets_empty_company_docs(
        self, profile_service, mock_supabase
    ):
        """User with no company gets empty company_documents list."""
        mock_supabase.get_user_by_id = AsyncMock(
            return_value={"id": "user-123", "company_id": None, "role": "user"}
        )

        mock_user_table = MagicMock()
        mock_user_select = MagicMock()
        mock_user_eq = MagicMock()
        mock_user_order = MagicMock()
        mock_user_order.execute.return_value = MagicMock(data=[])
        mock_user_eq.order.return_value = mock_user_order
        mock_user_select.eq.return_value = mock_user_eq
        mock_user_table.select.return_value = mock_user_select

        mock_supabase.get_client.return_value.table.return_value = mock_user_table

        result = await profile_service.list_documents("user-123")

        assert result["company_documents"] == []
        assert result["user_documents"] == []


class TestUpdatePreferences:
    """Test suite for update_preferences."""

    @pytest.mark.asyncio
    async def test_updates_communication_preferences(self, profile_service, mock_supabase):
        """Updates notification and communication preferences."""
        mock_table = MagicMock()
        mock_update = MagicMock()
        mock_eq = MagicMock()
        updated = {
            "id": "user-123",
            "communication_preferences": {"briefing_time": "09:00"},
            "default_tone": "formal",
            "tracked_competitors": ["Acme"],
        }
        mock_eq.execute.return_value = MagicMock(data=[updated])
        mock_update.eq.return_value = mock_eq
        mock_table.update.return_value = mock_update

        # Mock audit
        mock_audit = MagicMock()
        mock_audit.insert.return_value = MagicMock(
            execute=MagicMock(return_value=MagicMock(data=[{}]))
        )

        def table_router(name):
            if name == "security_audit_log":
                return mock_audit
            return mock_table

        mock_supabase.get_client.return_value.table.side_effect = table_router

        result = await profile_service.update_preferences(
            user_id="user-123",
            data={
                "communication_preferences": {"briefing_time": "09:00"},
                "default_tone": "formal",
                "tracked_competitors": ["Acme"],
            },
        )

        assert result["default_tone"] == "formal"
        assert result["tracked_competitors"] == ["Acme"]

    @pytest.mark.asyncio
    async def test_empty_preferences_update_is_noop(
        self, profile_service, mock_supabase, sample_user_profile
    ):
        """Empty preferences update returns current data without DB write."""
        mock_supabase.get_user_by_id = AsyncMock(return_value=sample_user_profile)

        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_eq = MagicMock()
        mock_eq.execute.return_value = MagicMock(data=[])
        mock_eq.single.return_value = MagicMock(
            execute=MagicMock(return_value=MagicMock(data=None))
        )
        mock_select.eq.return_value = mock_eq
        mock_table.select.return_value = mock_select
        mock_supabase.get_client.return_value.table.return_value = mock_table

        await profile_service.update_preferences(
            user_id="user-123",
            data={},
        )

        mock_table.update.assert_not_called()
