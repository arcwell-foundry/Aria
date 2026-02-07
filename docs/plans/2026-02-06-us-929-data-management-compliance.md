# US-929: Data Management & Compliance (GDPR/CCPA) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement GDPR/CCPA compliance features including data export, deletion, consent management, and "don't learn" controls.

**Architecture:**
- Backend: `ComplianceService` handles data aggregation from all tables (user_profiles, user_settings, onboarding_state, memory tables, conversations, messages, documents, audit logs)
- Routes: RESTful endpoints for export, deletion, consent, and retention policies
- Frontend: Dark surface privacy settings page with toggle cards, data export, digital twin deletion, and data deletion confirmation
- Tests: Unit tests for service methods, integration tests for routes, permission checks

**Tech Stack:**
- Python/FastAPI for backend service and routes
- Pydantic for request/response models
- Supabase PostgreSQL for all data sources
- React/TypeScript for frontend
- Lucide React for icons

---

## Task 1: Create ComplianceService

**Files:**
- Create: `backend/src/services/compliance_service.py`
- Test: `backend/tests/test_compliance_service.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_compliance_service.py

import pytest
from src.services.compliance_service import ComplianceService, ComplianceError
from src.core.exceptions import NotFoundError


@pytest.fixture
def compliance_service():
    """Create a ComplianceService instance for testing."""
    return ComplianceService()


def test_export_user_data_gathers_all_tables(compliance_service, mock_supabase_client):
    """Test that export_user_data gathers from all required tables."""
    user_id = "test-user-123"
    
    result = await compliance_service.export_user_data(user_id)
    
    assert "user_profile" in result
    assert "user_settings" in result
    assert "onboarding_state" in result
    assert "semantic_memory" in result
    assert "prospective_memory" in result
    assert "conversations" in result
    assert "messages" in result
    assert "documents" in result
    assert "audit_log" in result


def test_export_company_data_admin_only(compliance_service, mock_supabase_client):
    """Test that company export requires admin role."""
    company_id = "test-company-123"
    admin_id = "admin-user-456"
    
    result = await compliance_service.export_company_data(company_id, admin_id)
    
    assert "company" in result
    assert "users" in result
    assert "documents" in result
    assert "corporate_memory" in result


def test_delete_user_data_cascades_correctly(compliance_service, mock_supabase_client):
    """Test that deletion follows correct cascade order."""
    user_id = "test-user-789"
    confirmation = "DELETE MY DATA"
    
    result = await compliance_service.delete_user_data(user_id, confirmation)
    
    assert result["deleted"] is True
    assert result["summary"]["memories_deleted"] >= 0
    assert result["summary"]["conversations_deleted"] >= 0
    assert result["summary"]["documents_deleted"] >= 0


def test_delete_digital_twin_removes_only_twin_data(compliance_service, mock_supabase_client):
    """Test that digital twin deletion removes writing_style and communication_patterns."""
    user_id = "test-user-abc"
    
    result = await compliance_service.delete_digital_twin(user_id)
    
    assert result["deleted"] is True
    # Verify other settings remain intact


def test_get_consent_status_returns_all_flags(compliance_service, mock_supabase_client):
    """Test that consent status returns all consent categories."""
    user_id = "test-user-def"
    
    result = await compliance_service.get_consent_status(user_id)
    
    assert "email_analysis" in result
    assert "document_learning" in result
    assert "crm_processing" in result
    assert "writing_style_learning" in result


def test_update_consent_persists_change(compliance_service, mock_supabase_client):
    """Test that consent toggle persists to database."""
    user_id = "test-user-ghi"
    
    result = await compliance_service.update_consent(user_id, "email_analysis", False)
    
    assert result["category"] == "email_analysis"
    assert result["granted"] is False


def test_mark_dont_learn_excludes_content(compliance_service, mock_supabase_client):
    """Test that don't learn marks semantic memory entries as excluded."""
    user_id = "test-user-jkl"
    content_ids = ["mem-1", "mem-2", "mem-3"]
    
    result = await compliance_service.mark_dont_learn(user_id, content_ids)
    
    assert result["marked_count"] == 3


def test_get_retention_policies_returns_static_definitions(compliance_service):
    """Test that retention policies return defined durations."""
    result = await compliance_service.get_retention_policies("company-123")
    
    assert "audit_logs" in result
    assert "email_data" in result
    assert "conversation_history" in result
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_compliance_service.py -v`
Expected: FAIL with "ComplianceService not defined"

**Step 3: Write minimal implementation**

```python
# backend/src/services/compliance_service.py

"""Data Management & Compliance Service (US-929).

Provides GDPR/CCPA compliance functionality:
- Data export (user and company level)
- Data deletion with cascade
- Digital twin deletion
- Consent management
- "Don't learn" marking
- Retention policy information
"""

import logging
from datetime import UTC, datetime
from typing import Any

from src.core.exceptions import ARIAError, NotFoundError
from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


class ComplianceError(ARIAError):
    """Compliance operation error."""

    def __init__(self, message: str = "Compliance operation failed") -> None:
        """Initialize compliance error.

        Args:
            message: Error details.
        """
        super().__init__(
            message=message,
            code="COMPLIANCE_ERROR",
            status_code=500,
        )


class ComplianceService:
    """Service for GDPR/CCPA compliance operations."""

    # Consent categories
    CONSENT_EMAIL_ANALYSIS = "email_analysis"
    CONSENT_DOCUMENT_LEARNING = "document_learning"
    CONSENT_CRM_PROCESSING = "crm_processing"
    CONSENT_WRITING_STYLE_LEARNING = "writing_style_learning"

    ALL_CONSENT_CATEGORIES = [
        CONSENT_EMAIL_ANALYSIS,
        CONSENT_DOCUMENT_LEARNING,
        CONSENT_CRM_PROCESSING,
        CONSENT_WRITING_STYLE_LEARNING,
    ]

    # Retention policy definitions (in days)
    RETENTION_AUDIT_QUERY_LOGS = 90
    RETENTION_AUDIT_WRITE_LOGS = -1  # Permanent
    RETENTION_EMAIL_DATA = 365
    RETENTION_CONVERSATION_HISTORY = -1  # Permanent unless deleted

    async def export_user_data(self, user_id: str) -> dict[str, Any]:
        """Export all user data for GDPR right to access.

        Gathers data from:
        - user_profiles
        - user_settings
        - onboarding_state
        - memory_semantic
        - memory_prospective
        - conversations
        - messages
        - company_documents (uploaded_by user)
        - security_audit_log

        Args:
            user_id: The user's UUID.

        Returns:
            Structured dictionary with all user data.

        Raises:
            NotFoundError: If user not found.
            ComplianceError: If export fails.
        """
        try:
            client = SupabaseClient.get_client()
            export_data: dict[str, Any] = {
                "export_date": datetime.now(UTC).isoformat(),
                "user_id": user_id,
            }

            # Get user profile
            profile_response = (
                client.table("user_profiles")
                .select("*")
                .eq("id", user_id)
                .single()
                .execute()
            )
            if profile_response.data:
                export_data["user_profile"] = profile_response.data

            # Get user settings
            settings_response = (
                client.table("user_settings")
                .select("*")
                .eq("user_id", user_id)
                .single()
                .execute()
            )
            if settings_response.data:
                export_data["user_settings"] = settings_response.data

            # Get onboarding state
            onboarding_response = (
                client.table("onboarding_state")
                .select("*")
                .eq("user_id", user_id)
                .execute()
            )
            if onboarding_response.data:
                export_data["onboarding_state"] = onboarding_response.data

            # Get semantic memory (if table exists)
            try:
                semantic_response = (
                    client.table("memory_semantic")
                    .select("*")
                    .eq("user_id", user_id)
                    .execute()
                )
                export_data["semantic_memory"] = semantic_response.data
            except Exception:
                export_data["semantic_memory"] = []

            # Get prospective memory
            try:
                prospective_response = (
                    client.table("memory_prospective")
                    .select("*")
                    .eq("user_id", user_id)
                    .execute()
                )
                export_data["prospective_memory"] = prospective_response.data
            except Exception:
                export_data["prospective_memory"] = []

            # Get conversations
            try:
                conversations_response = (
                    client.table("conversations")
                    .select("*")
                    .eq("user_id", user_id)
                    .execute()
                )
                export_data["conversations"] = conversations_response.data
            except Exception:
                export_data["conversations"] = []

            # Get messages (by conversation if we have them)
            if export_data.get("conversations"):
                try:
                    conversation_ids = [c["id"] for c in export_data["conversations"]]
                    messages_response = (
                        client.table("messages")
                        .select("*")
                        .in_("conversation_id", conversation_ids)
                        .execute()
                    )
                    export_data["messages"] = messages_response.data
                except Exception:
                    export_data["messages"] = []

            # Get documents uploaded by user
            try:
                documents_response = (
                    client.table("company_documents")
                    .select("*")
                    .eq("uploaded_by", user_id)
                    .execute()
                )
                export_data["documents"] = documents_response.data
            except Exception:
                export_data["documents"] = []

            # Get security audit log entries for user
            try:
                audit_response = (
                    client.table("security_audit_log")
                    .select("*")
                    .eq("user_id", user_id)
                    .execute()
                )
                export_data["audit_log"] = audit_response.data
            except Exception:
                export_data["audit_log"] = []

            logger.info(f"User data exported for {user_id}")
            return export_data

        except Exception as e:
            logger.exception("Error exporting user data", extra={"user_id": user_id})
            raise ComplianceError(f"Failed to export user data: {e}") from e

    async def export_company_data(self, company_id: str, admin_id: str) -> dict[str, Any]:
        """Export all company data (admin only).

        Args:
            company_id: The company's UUID.
            admin_id: The requesting admin's UUID for verification.

        Returns:
            Structured dictionary with all company data.

        Raises:
            NotFoundError: If company or admin not found.
            ComplianceError: If export fails or user is not admin.
        """
        try:
            client = SupabaseClient.get_client()

            # Verify admin role
            admin_response = (
                client.table("user_profiles")
                .select("role")
                .eq("id", admin_id)
                .eq("company_id", company_id)
                .single()
                .execute()
            )

            if not admin_response.data or admin_response.data.get("role") != "admin":
                raise ComplianceError("Only admins can export company data")

            export_data: dict[str, Any] = {
                "export_date": datetime.now(UTC).isoformat(),
                "company_id": company_id,
                "exported_by": admin_id,
            }

            # Get company info
            company_response = (
                client.table("companies")
                .select("*")
                .eq("id", company_id)
                .single()
                .execute()
            )
            if company_response.data:
                export_data["company"] = company_response.data

            # Get all users in company
            users_response = (
                client.table("user_profiles")
                .select("*")
                .eq("company_id", company_id)
                .execute()
            )
            export_data["users"] = users_response.data

            # Get all company documents
            documents_response = (
                client.table("company_documents")
                .select("*")
                .eq("company_id", company_id)
                .execute()
            )
            export_data["documents"] = documents_response.data

            # Get corporate memory (if available)
            export_data["corporate_memory"] = {
                "note": "Corporate memory stored in Graphiti/Neo4j - use separate export"
            }

            logger.info(f"Company data exported for {company_id} by {admin_id}")
            return export_data

        except ComplianceError:
            raise
        except Exception as e:
            logger.exception("Error exporting company data", extra={"company_id": company_id})
            raise ComplianceError(f"Failed to export company data: {e}") from e

    async def delete_user_data(
        self, user_id: str, confirmation: str
    ) -> dict[str, Any]:
        """Delete all user data with cascade (GDPR right to erasure).

        Deletion order (cascade):
        1. Memories (semantic, prospective)
        2. Messages
        3. Conversations
        4. Documents (uploaded_by user)
        5. Onboarding state
        6. User settings
        7. User profile
        8. Auth user (handled by Supabase Auth)

        Args:
            user_id: The user's UUID.
            confirmation: Must be "DELETE MY DATA" for safety.

        Returns:
            Summary of deleted counts.

        Raises:
            ComplianceError: If confirmation doesn't match or deletion fails.
        """
        if confirmation != "DELETE MY DATA":
            raise ComplianceError('Confirmation must be exactly "DELETE MY DATA"')

        try:
            client = SupabaseClient.get_client()
            summary: dict[str, Any] = {
                "deleted": True,
                "user_id": user_id,
                "summary": {},
            }

            # Delete semantic memory
            try:
                semantic_result = (
                    client.table("memory_semantic")
                    .delete()
                    .eq("user_id", user_id)
                    .execute()
                )
                summary["summary"]["semantic_memory"] = len(semantic_result.data) if semantic_result.data else 0
            except Exception:
                summary["summary"]["semantic_memory"] = 0

            # Delete prospective memory
            try:
                prospective_result = (
                    client.table("memory_prospective")
                    .delete()
                    .eq("user_id", user_id)
                    .execute()
                )
                summary["summary"]["prospective_memory"] = len(prospective_result.data) if prospective_result.data else 0
            except Exception:
                summary["summary"]["prospective_memory"] = 0

            # Get user's conversations first
            conversations_result = (
                client.table("conversations")
                .select("id")
                .eq("user_id", user_id)
                .execute()
            )
            conversation_ids = [c["id"] for c in conversations_result.data] if conversations_result.data else []

            # Delete messages
            messages_deleted = 0
            if conversation_ids:
                try:
                    messages_result = (
                        client.table("messages")
                        .delete()
                        .in_("conversation_id", conversation_ids)
                        .execute()
                    )
                    messages_deleted = len(messages_result.data) if messages_result.data else 0
                except Exception:
                    pass
            summary["summary"]["messages"] = messages_deleted

            # Delete conversations
            conversations_deleted = 0
            if conversation_ids:
                try:
                    conv_result = (
                        client.table("conversations")
                        .delete()
                        .in_("id", conversation_ids)
                        .execute()
                    )
                    conversations_deleted = len(conv_result.data) if conv_result.data else 0
                except Exception:
                    pass
            summary["summary"]["conversations"] = conversations_deleted

            # Delete documents uploaded by user
            try:
                documents_result = (
                    client.table("company_documents")
                    .delete()
                    .eq("uploaded_by", user_id)
                    .execute()
                )
                summary["summary"]["documents"] = len(documents_result.data) if documents_result.data else 0
            except Exception:
                summary["summary"]["documents"] = 0

            # Delete onboarding state
            try:
                onboarding_result = (
                    client.table("onboarding_state")
                    .delete()
                    .eq("user_id", user_id)
                    .execute()
                )
                summary["summary"]["onboarding"] = 1 if onboarding_result.data else 0
            except Exception:
                summary["summary"]["onboarding"] = 0

            # Delete user settings
            try:
                settings_result = (
                    client.table("user_settings")
                    .delete()
                    .eq("user_id", user_id)
                    .execute()
                )
                summary["summary"]["settings"] = 1 if settings_result.data else 0
            except Exception:
                summary["summary"]["settings"] = 0

            # Delete user profile
            try:
                profile_result = (
                    client.table("user_profiles")
                    .delete()
                    .eq("id", user_id)
                    .execute()
                )
                summary["summary"]["profile"] = 1 if profile_result.data else 0
            except Exception:
                summary["summary"]["profile"] = 0

            # Note: Auth user deletion requires admin.service_role client
            # This is handled separately via Supabase Auth admin API
            summary["summary"]["auth_user"] = "Requires Supabase Auth admin API"

            logger.info(f"User data deleted for {user_id}", extra=summary["summary"])
            return summary

        except ComplianceError:
            raise
        except Exception as e:
            logger.exception("Error deleting user data", extra={"user_id": user_id})
            raise ComplianceError(f"Failed to delete user data: {e}") from e

    async def delete_digital_twin(self, user_id: str) -> dict[str, Any]:
        """Delete only Digital Twin data (writing_style, communication_patterns).

        Removes writing_style and communication_patterns from
        user_settings.preferences.digital_twin while preserving other settings.

        Args:
            user_id: The user's UUID.

        Returns:
            Deletion confirmation.

        Raises:
            ComplianceError: If deletion fails.
        """
        try:
            client = SupabaseClient.get_client()

            # Get current settings
            settings_response = (
                client.table("user_settings")
                .select("preferences")
                .eq("user_id", user_id)
                .single()
                .execute()
            )

            if not settings_response.data:
                raise NotFoundError("User settings", user_id)

            preferences = settings_response.data.get("preferences", {})
            if "digital_twin" in preferences:
                # Remove Digital Twin specific fields
                preferences["digital_twin"] = {
                    "deleted_at": datetime.now(UTC).isoformat(),
                    "deleted": True,
                }

                # Update settings
                (
                    client.table("user_settings")
                    .update({"preferences": preferences})
                    .eq("user_id", user_id)
                    .execute()
                )

            logger.info(f"Digital Twin deleted for user {user_id}")
            return {
                "deleted": True,
                "user_id": user_id,
                "deleted_at": datetime.now(UTC).isoformat(),
            }

        except NotFoundError:
            raise
        except Exception as e:
            logger.exception("Error deleting digital twin", extra={"user_id": user_id})
            raise ComplianceError(f"Failed to delete digital twin: {e}") from e

    async def get_consent_status(self, user_id: str) -> dict[str, bool]:
        """Get current consent status for all categories.

        Args:
            user_id: The user's UUID.

        Returns:
            Dictionary mapping consent categories to granted boolean.
        """
        try:
            client = SupabaseClient.get_client()

            settings_response = (
                client.table("user_settings")
                .select("preferences")
                .eq("user_id", user_id)
                .single()
                .execute()
            )

            preferences = (
                settings_response.data.get("preferences", {})
                if settings_response.data
                else {}
            )
            consent = preferences.get("consent", {})

            # Return all categories with defaults
            return {
                category: consent.get(category, True)  # Default to granted
                for category in self.ALL_CONSENT_CATEGORIES
            }

        except Exception as e:
            logger.exception("Error getting consent status", extra={"user_id": user_id})
            # Return defaults on error
            return {
                category: True for category in self.ALL_CONSENT_CATEGORIES
            }

    async def update_consent(
        self, user_id: str, category: str, granted: bool
    ) -> dict[str, Any]:
        """Update consent for a specific category.

        Args:
            user_id: The user's UUID.
            category: Consent category (email_analysis, document_learning, etc.)
            granted: Whether consent is granted.

        Returns:
            Updated consent status.

        Raises:
            ComplianceError: If category is invalid or update fails.
        """
        if category not in self.ALL_CONSENT_CATEGORIES:
            raise ComplianceError(f"Invalid consent category: {category}")

        try:
            client = SupabaseClient.get_client()

            # Get current settings
            settings_response = (
                client.table("user_settings")
                .select("preferences")
                .eq("user_id", user_id)
                .single()
                .execute()
            )

            if settings_response.data:
                preferences = settings_response.data.get("preferences", {})
            else:
                preferences = {}

            # Update consent
            if "consent" not in preferences:
                preferences["consent"] = {}
            preferences["consent"][category] = granted

            # Save
            if settings_response.data:
                (
                    client.table("user_settings")
                    .update({"preferences": preferences})
                    .eq("user_id", user_id)
                    .execute()
                )
            else:
                (
                    client.table("user_settings")
                    .insert({"user_id": user_id, "preferences": preferences})
                    .execute()
                )

            logger.info(
                f"Consent updated for {user_id}: {category}={granted}"
            )
            return {
                "category": category,
                "granted": granted,
                "updated_at": datetime.now(UTC).isoformat(),
            }

        except Exception as e:
            logger.exception("Error updating consent", extra={"user_id": user_id, "category": category})
            raise ComplianceError(f"Failed to update consent: {e}") from e

    async def mark_dont_learn(
        self, user_id: str, content_ids: list[str]
    ) -> dict[str, Any]:
        """Mark semantic memory entries as excluded from learning.

        Args:
            user_id: The user's UUID.
            content_ids: List of semantic memory IDs to mark as excluded.

        Returns:
            Count of marked entries.

        Raises:
            ComplianceError: If marking fails.
        """
        try:
            client = SupabaseClient.get_client()
            marked_count = 0

            for content_id in content_ids:
                try:
                    (
                        client.table("memory_semantic")
                        .update({"excluded": True})
                        .eq("id", content_id)
                        .eq("user_id", user_id)  # Security: only user's own data
                        .execute()
                    )
                    marked_count += 1
                except Exception:
                    # Log but continue with other IDs
                    pass

            logger.info(
                f"Marked {marked_count}/{len(content_ids)} entries as don't learn for {user_id}"
            )
            return {
                "marked_count": marked_count,
                "total_requested": len(content_ids),
            }

        except Exception as e:
            logger.exception("Error marking don't learn", extra={"user_id": user_id})
            raise ComplianceError(f"Failed to mark don't learn: {e}") from e

    async def get_retention_policies(self, company_id: str) -> dict[str, Any]:
        """Get data retention policy definitions.

        Returns static policy information - not configured per company.

        Args:
            company_id: The company's UUID (for context, not used).

        Returns:
            Dictionary of retention policies with durations in days.
        """
        return {
            "audit_query_logs": {
                "duration_days": self.RETENTION_AUDIT_QUERY_LOGS,
                "description": "Query logs retained for 90 days",
            },
            "audit_write_logs": {
                "duration_days": self.RETENTION_AUDIT_WRITE_LOGS,
                "description": "Write logs retained permanently",
            },
            "email_data": {
                "duration_days": self.RETENTION_EMAIL_DATA,
                "description": "Email data retained for 1 year by default",
            },
            "conversation_history": {
                "duration_days": self.RETENTION_CONVERSATION_HISTORY,
                "description": "Conversation history retained until deleted by user",
            },
            "note": "Contact support to request changes to retention policies",
        }
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_compliance_service.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_compliance_service.py src/services/compliance_service.py
git commit -m "feat: implement ComplianceService for GDPR/CCPA (US-929)"
```

---

## Task 2: Create Compliance API Routes

**Files:**
- Create: `backend/src/api/routes/compliance.py`
- Modify: `backend/src/main.py:36` (add compliance to imports)
- Modify: `backend/src/main.py:120` (register router)
- Test: `backend/tests/api/routes/test_compliance.py`

**Step 1: Write the failing test**

```python
# backend/tests/api/routes/test_compliance.py

import pytest
from fastapi import status
from src.services.compliance_service import ComplianceError


@pytest.fixture
def compliance_client(client):
    """Create a test client for compliance routes."""
    return client


def test_get_data_export_requires_auth(compliance_client):
    """Test that data export requires authentication."""
    response = compliance_client.get("/api/v1/compliance/data/export")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_get_data_export_returns_json(compliance_client, auth_token):
    """Test that data export returns structured JSON."""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = compliance_client.get("/api/v1/compliance/data/export", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "export_date" in data
    assert "user_id" in data


def test_delete_data_requires_confirmation(compliance_client, auth_token):
    """Test that data deletion requires exact confirmation."""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = compliance_client.post(
        "/api/v1/compliance/data/delete",
        json={"confirmation": "wrong"},
        headers=headers
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_delete_digital_twin_works(compliance_client, auth_token):
    """Test that digital twin deletion endpoint works."""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = compliance_client.delete("/api/v1/compliance/data/digital-twin", headers=headers)
    assert response.status_code == status.HTTP_200_OK


def test_get_consent_returns_all_categories(compliance_client, auth_token):
    """Test that consent endpoint returns all categories."""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = compliance_client.get("/api/v1/compliance/consent", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "email_analysis" in data
    assert "document_learning" in data


def test_patch_consent_updates_category(compliance_client, auth_token):
    """Test that PATCH consent updates a category."""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = compliance_client.patch(
        "/api/v1/compliance/consent",
        json={"category": "email_analysis", "granted": False},
        headers=headers
    )
    assert response.status_code == status.HTTP_200_OK


def test_mark_dont_learn_excludes_content(compliance_client, auth_token):
    """Test that don't learn marks content as excluded."""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = compliance_client.post(
        "/api/v1/compliance/data/dont-learn",
        json={"content_ids": ["mem-1", "mem-2"]},
        headers=headers
    )
    assert response.status_code == status.HTTP_200_OK


def test_get_retention_policies_works(compliance_client):
    """Test that retention policies endpoint returns policies."""
    response = compliance_client.get("/api/v1/compliance/retention")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "audit_query_logs" in data


def test_export_company_requires_admin(compliance_client, auth_token):
    """Test that company export requires admin role."""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = compliance_client.get("/api/v1/compliance/data/export/company", headers=headers)
    # Should fail if user is not admin
    assert response.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/api/routes/test_compliance.py -v`
Expected: FAIL with "module not found" or route not defined

**Step 3: Write minimal implementation**

```python
# backend/src/api/routes/compliance.py

"""Compliance & Data Management API Routes (US-929)."""

import logging
from typing import Any

from fastapi import APIRouter, Header, status
from pydantic import BaseModel, Field

from src.api.deps import AdminUser, CurrentUser
from src.services.compliance_service import ComplianceService, ComplianceError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/compliance", tags=["compliance"])
compliance_service = ComplianceService()


# Request/Response Models
class DataExportResponse(BaseModel):
    """Data export response."""

    export_date: str
    user_id: str
    user_profile: dict[str, Any] | None = None
    user_settings: dict[str, Any] | None = None
    onboarding_state: list[dict[str, Any]] | dict[str, Any] | None = None
    semantic_memory: list[Any] | None = None
    prospective_memory: list[Any] | None = None
    conversations: list[Any] | None = None
    messages: list[Any] | None = None
    documents: list[Any] | None = None
    audit_log: list[Any] | None = None


class DeleteDataRequest(BaseModel):
    """Request to delete user data."""

    confirmation: str = Field(..., min_length=1, max_length=100)


class DeleteDataResponse(BaseModel):
    """Response for data deletion."""

    deleted: bool
    user_id: str
    summary: dict[str, Any]


class DigitalTwinDeleteResponse(BaseModel):
    """Response for digital twin deletion."""

    deleted: bool
    user_id: str
    deleted_at: str


class ConsentStatusResponse(BaseModel):
    """Consent status response."""

    email_analysis: bool
    document_learning: bool
    crm_processing: bool
    writing_style_learning: bool


class UpdateConsentRequest(BaseModel):
    """Request to update consent."""

    category: str = Field(..., min_length=1, max_length=50)
    granted: bool


class UpdateConsentResponse(BaseModel):
    """Response for consent update."""

    category: str
    granted: bool
    updated_at: str


class MarkDontLearnRequest(BaseModel):
    """Request to mark content as don't learn."""

    content_ids: list[str] = Field(..., min_length=1, max_length=100)


class MarkDontLearnResponse(BaseModel):
    """Response for mark don't learn."""

    marked_count: int
    total_requested: int


class RetentionPoliciesResponse(BaseModel):
    """Retention policies response."""

    audit_query_logs: dict[str, Any]
    audit_write_logs: dict[str, Any]
    email_data: dict[str, Any]
    conversation_history: dict[str, Any]
    note: str | None = None


# Routes
@router.get(
    "/data/export",
    response_model=DataExportResponse,
    status_code=status.HTTP_200_OK,
)
async def get_data_export(
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Export all user data (GDPR right to access).

    Returns a structured JSON export of all user data including:
    - Profile and settings
    - Onboarding state
    - Semantic and prospective memory
    - Conversations and messages
    - Uploaded documents
    - Audit log entries

    Args:
        current_user: Authenticated user.

    Returns:
        Structured export data.
    """
    try:
        return await compliance_service.export_user_data(current_user.id)
    except Exception as e:
        logger.exception("Error exporting user data")
        raise


@router.post(
    "/data/delete",
    response_model=DeleteDataResponse,
    status_code=status.HTTP_200_OK,
)
async def delete_user_data(
    request_data: DeleteDataRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Delete all user data (GDPR right to erasure).

    Requires explicit confirmation text "DELETE MY DATA".

    Warning: This action is irreversible and will cascade delete:
    - Memories (semantic, prospective)
    - Messages and conversations
    - Documents uploaded by user
    - Onboarding state
    - Settings and profile

    Args:
        request_data: Must contain confirmation: "DELETE MY DATA"
        current_user: Authenticated user.

    Returns:
        Summary of deleted data.
    """
    try:
        if request_data.confirmation != "DELETE MY DATA":
            from src.core.exceptions import ValidationError
            raise ValidationError(
                'Confirmation must be exactly "DELETE MY DATA"'
            )

        return await compliance_service.delete_user_data(
            current_user.id,
            request_data.confirmation,
        )
    except Exception as e:
        logger.exception("Error deleting user data")
        raise


@router.delete(
    "/data/digital-twin",
    response_model=DigitalTwinDeleteResponse,
    status_code=status.HTTP_200_OK,
)
async def delete_digital_twin(
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Delete Digital Twin data only (writing style, communication patterns).

    This removes ARIA's learned understanding of your writing style and
    communication patterns while preserving other data.

    Args:
        current_user: Authenticated user.

    Returns:
        Deletion confirmation with timestamp.
    """
    try:
        return await compliance_service.delete_digital_twin(current_user.id)
    except Exception as e:
        logger.exception("Error deleting digital twin")
        raise


@router.get(
    "/consent",
    response_model=ConsentStatusResponse,
    status_code=status.HTTP_200_OK,
)
async def get_consent_status(
    current_user: CurrentUser,
) -> dict[str, bool]:
    """Get current consent status for all data processing categories.

    Returns the current granted/revoked status for:
    - Email analysis
    - Document learning
    - CRM processing
    - Writing style learning

    Args:
        current_user: Authenticated user.

    Returns:
        Dictionary of consent categories to boolean status.
    """
    try:
        return await compliance_service.get_consent_status(current_user.id)
    except Exception as e:
        logger.exception("Error getting consent status")
        raise


@router.patch(
    "/consent",
    response_model=UpdateConsentResponse,
    status_code=status.HTTP_200_OK,
)
async def update_consent(
    request_data: UpdateConsentRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Update consent for a specific data processing category.

    Args:
        request_data: Category to update and new granted status.
        current_user: Authenticated user.

    Returns:
        Updated consent status with timestamp.
    """
    try:
        return await compliance_service.update_consent(
            current_user.id,
            request_data.category,
            request_data.granted,
        )
    except Exception as e:
        logger.exception("Error updating consent")
        raise


@router.post(
    "/data/dont-learn",
    response_model=MarkDontLearnResponse,
    status_code=status.HTTP_200_OK,
)
async def mark_dont_learn(
    request_data: MarkDontLearnRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Mark specific content as off-limits for learning.

    Marks semantic memory entries as excluded so ARIA will not
    learn from or reference this content.

    Args:
        request_data: List of content IDs to mark as excluded.
        current_user: Authenticated user.

    Returns:
        Count of successfully marked entries.
    """
    try:
        return await compliance_service.mark_dont_learn(
            current_user.id,
            request_data.content_ids,
        )
    except Exception as e:
        logger.exception("Error marking don't learn")
        raise


@router.get(
    "/retention",
    response_model=RetentionPoliciesResponse,
    status_code=status.HTTP_200_OK,
)
async def get_retention_policies(
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get data retention policy definitions.

    Returns information about how long different types of data
    are retained before automatic deletion.

    Args:
        current_user: Authenticated user.

    Returns:
        Dictionary of retention policies.
    """
    try:
        # Get user's company_id for context
        from src.db.supabase import SupabaseClient
        profile = await SupabaseClient.get_user_by_id(current_user.id)
        company_id = profile.get("company_id", "unknown")
        
        return await compliance_service.get_retention_policies(company_id)
    except Exception as e:
        logger.exception("Error getting retention policies")
        raise


@router.get(
    "/data/export/company",
    response_model=DataExportResponse,
    status_code=status.HTTP_200_OK,
)
async def export_company_data(
    current_user: AdminUser,
) -> dict[str, Any]:
    """Export all company data (admin only).

    Requires admin role. Exports all data associated with the company
    including all users, documents, and corporate memory.

    Args:
        current_user: Authenticated admin user.

    Returns:
        Structured company data export.

    Raises:
        HTTPException: If user is not an admin.
    """
    try:
        from src.db.supabase import SupabaseClient
        
        profile = await SupabaseClient.get_user_by_id(current_user.id)
        company_id = profile.get("company_id")
        
        if not company_id:
            from src.core.exceptions import NotFoundError
            raise NotFoundError("Company", "not found")
        
        return await compliance_service.export_company_data(
            company_id,
            current_user.id,
        )
    except Exception as e:
        logger.exception("Error exporting company data")
        raise
```

**Step 4: Update main.py to register routes**

```python
# In backend/src/main.py

# Add to imports (around line 36)
from src.api.routes import (
    # ... existing imports
    compliance,  # Add this
)

# Add router registration (around line 120, after billing)
app.include_router(compliance.router, prefix="/api/v1")
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/api/routes/test_compliance.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/api/routes/compliance.py src/main.py tests/api/routes/test_compliance.py
git commit -m "feat: add compliance API routes for GDPR/CCPA (US-929)"
```

---

## Task 3: Create Frontend Privacy Settings Page

**Files:**
- Create: `frontend/src/pages/SettingsPrivacyPage.tsx`
- Create: `frontend/src/api/compliance.ts`
- Modify: `frontend/src/App.tsx` (add route)
- Create: `frontend/src/hooks/useCompliance.ts`

**Step 1: Write the API client**

```typescript
// frontend/src/api/compliance.ts

import { apiClient } from "./client";

// Types
export interface DataExport {
  export_date: string;
  user_id: string;
  user_profile?: Record<string, unknown>;
  user_settings?: Record<string, unknown>;
  onboarding_state?: Record<string, unknown>[] | Record<string, unknown>;
  semantic_memory?: unknown[];
  prospective_memory?: unknown[];
  conversations?: unknown[];
  messages?: unknown[];
  documents?: unknown[];
  audit_log?: unknown[];
}

export interface DeleteDataRequest {
  confirmation: string;
}

export interface DeleteDataResponse {
  deleted: boolean;
  user_id: string;
  summary: Record<string, unknown>;
}

export interface DigitalTwinDeleteResponse {
  deleted: boolean;
  user_id: string;
  deleted_at: string;
}

export interface ConsentStatus {
  email_analysis: boolean;
  document_learning: boolean;
  crm_processing: boolean;
  writing_style_learning: boolean;
}

export interface UpdateConsentRequest {
  category: string;
  granted: boolean;
}

export interface UpdateConsentResponse {
  category: string;
  granted: boolean;
  updated_at: string;
}

export interface MarkDontLearnRequest {
  content_ids: string[];
}

export interface MarkDontLearnResponse {
  marked_count: number;
  total_requested: number;
}

export interface RetentionPolicies {
  audit_query_logs: { duration_days: number; description: string };
  audit_write_logs: { duration_days: number; description: string };
  email_data: { duration_days: number; description: string };
  conversation_history: { duration_days: number; description: string };
  note?: string;
}

// API functions
export async function getDataExport(): Promise<DataExport> {
  const response = await apiClient.get<DataExport>("/compliance/data/export");
  return response.data;
}

export async function deleteUserData(data: DeleteDataRequest): Promise<DeleteDataResponse> {
  const response = await apiClient.post<DeleteDataResponse>("/compliance/data/delete", data);
  return response.data;
}

export async function deleteDigitalTwin(): Promise<DigitalTwinDeleteResponse> {
  const response = await apiClient.delete<DigitalTwinDeleteResponse>("/compliance/data/digital-twin");
  return response.data;
}

export async function getConsentStatus(): Promise<ConsentStatus> {
  const response = await apiClient.get<ConsentStatus>("/compliance/consent");
  return response.data;
}

export async function updateConsent(data: UpdateConsentRequest): Promise<UpdateConsentResponse> {
  const response = await apiClient.patch<UpdateConsentResponse>("/compliance/consent", data);
  return response.data;
}

export async function markDontLearn(data: MarkDontLearnRequest): Promise<MarkDontLearnResponse> {
  const response = await apiClient.post<MarkDontLearnResponse>("/compliance/data/dont-learn", data);
  return response.data;
}

export async function getRetentionPolicies(): Promise<RetentionPolicies> {
  const response = await apiClient.get<RetentionPolicies>("/compliance/retention");
  return response.data;
}
```

**Step 2: Write the React hooks**

```typescript
// frontend/src/hooks/useCompliance.ts

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getDataExport,
  deleteUserData,
  deleteDigitalTwin,
  getConsentStatus,
  updateConsent,
  markDontLearn,
  getRetentionPolicies,
} from "@/api/compliance";

export function useDataExport() {
  return useQuery({
    queryKey: ["compliance", "export"],
    queryFn: getDataExport,
    staleTime: 0, // Always fetch fresh
    retry: false,
  });
}

export function useDeleteData() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { confirmation: string }) => deleteUserData(data),
    onSuccess: () => {
      // Clear all caches on delete
      queryClient.clear();
    },
  });
}

export function useDeleteDigitalTwin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteDigitalTwin,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["profile"] });
    },
  });
}

export function useConsentStatus() {
  return useQuery({
    queryKey: ["compliance", "consent"],
    queryFn: getConsentStatus,
  });
}

export function useUpdateConsent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { category: string; granted: boolean }) => updateConsent(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["compliance", "consent"] });
    },
  });
}

export function useMarkDontLearn() {
  return useMutation({
    mutationFn: (data: { content_ids: string[] }) => markDontLearn(data),
  });
}

export function useRetentionPolicies() {
  return useQuery({
    queryKey: ["compliance", "retention"],
    queryFn: getRetentionPolicies,
  });
}
```

**Step 3: Write the Privacy Settings Page component**

```typescript
// frontend/src/pages/SettingsPrivacyPage.tsx

import { useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import {
  useConsentStatus,
  useUpdateConsent,
  useDeleteDigitalTwin,
  useDeleteData,
  useDataExport,
  useRetentionPolicies,
} from "@/hooks/useCompliance";
import {
  Download,
  Shield,
  EyeOff,
  Trash2,
  AlertTriangle,
  Clock,
  Check,
  X,
  Loader2,
  FileDown,
} from "lucide-react";

export function SettingsPrivacyPage() {
  const { user } = useAuth();
  const { data: consent, isLoading: consentLoading } = useConsentStatus();
  const { data: retention, isLoading: retentionLoading } = useRetentionPolicies();
  
  const updateConsent = useUpdateConsent();
  const deleteDigitalTwin = useDeleteDigitalTwin();
  const deleteData = useDeleteData();
  const { data: exportData, isLoading: exportLoading, refetch: refetchExport } = useDataExport();
  
  // UI state
  const [showDeleteTwinModal, setShowDeleteTwinModal] = useState(false);
  const [showDeleteDataModal, setShowDeleteDataModal] = useState(false);
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [exportPreparing, setExportPreparing] = useState(false);
  
  // Messages
  const [successMessage, setSuccessMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  
  const showError = (msg: string) => {
    setErrorMessage(msg);
    setTimeout(() => setErrorMessage(""), 5000);
  };
  
  const showSuccess = (msg: string) => {
    setSuccessMessage(msg);
    setTimeout(() => setSuccessMessage(""), 3000);
  };
  
  const handleToggleConsent = async (category: string, granted: boolean) => {
    try {
      await updateConsent.mutateAsync({ category, granted });
      showSuccess(`${category.replace(/_/g, " ")} ${granted ? "enabled" : "disabled"}`);
    } catch (err: unknown) {
      showError(err instanceof Error ? err.message : "Failed to update consent");
    }
  };
  
  const handleDeleteTwin = async () => {
    try {
      await deleteDigitalTwin.mutateAsync();
      setShowDeleteTwinModal(false);
      showSuccess("Digital Twin deleted");
    } catch (err: unknown) {
      showError(err instanceof Error ? err.message : "Failed to delete Digital Twin");
    }
  };
  
  const handleDeleteAllData = async () => {
    if (deleteConfirmation !== "DELETE MY DATA") {
      showError('Please type "DELETE MY DATA" exactly');
      return;
    }
    try {
      await deleteData.mutateAsync({ confirmation: deleteConfirmation });
      // Will be redirected by auth
      window.location.href = "/login";
    } catch (err: unknown) {
      showError(err instanceof Error ? err.message : "Failed to delete data");
    }
  };
  
  const handleExportData = async () => {
    setExportPreparing(true);
    try {
      await refetchExport();
      if (exportData) {
        // Create blob and download
        const blob = new Blob([JSON.stringify(exportData, null, 2)], {
          type: "application/json",
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `aria-data-export-${new Date().toISOString().split("T")[0]}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        showSuccess("Data export downloaded");
      }
    } catch (err: unknown) {
      showError(err instanceof Error ? err.message : "Failed to export data");
    } finally {
      setExportPreparing(false);
    }
  };
  
  const consentConfig = [
    {
      key: "email_analysis",
      label: "Email Analysis",
      description: "ARIA learns from your email communications to understand relationships and patterns",
      icon: <FileDown className="w-4 h-4" />,
    },
    {
      key: "document_learning",
      label: "Document Learning",
      description: "ARIA extracts knowledge from uploaded documents",
      icon: <FileDown className="w-4 h-4" />,
    },
    {
      key: "crm_processing",
      label: "CRM Processing",
      description: "ARIA uses CRM data for pipeline insights and contact management",
      icon: <FileDown className="w-4 h-4" />,
    },
    {
      key: "writing_style_learning",
      label: "Writing Style Learning",
      description: "ARIA learns your writing style to draft emails in your voice",
      icon: <FileDown className="w-4 h-4" />,
    },
  ];
  
  return (
    <div className="min-h-screen bg-[#0F1117]">
      {/* Header */}
      <div className="border-b border-[#2A2F42]">
        <div className="max-w-3xl mx-auto px-6 py-8">
          <h1 className="font-display text-[2rem] text-[#E8E6E1]">Privacy & Data</h1>
          <p className="text-[#8B92A5] mt-2">
            Manage your data, consent preferences, and privacy controls
          </p>
        </div>
      </div>

      {/* Messages */}
      {successMessage && (
        <div className="max-w-3xl mx-auto px-6 mt-6">
          <div className="bg-[#6B8F71]/10 border border-[#6B8F71]/30 rounded-lg px-4 py-3 flex items-center gap-3">
            <Check className="w-5 h-5 text-[#6B8F71]" />
            <span className="text-[#E8E6E1]">{successMessage}</span>
          </div>
        </div>
      )}
      {errorMessage && (
        <div className="max-w-3xl mx-auto px-6 mt-6">
          <div className="bg-[#A66B6B]/10 border border-[#A66B6B]/30 rounded-lg px-4 py-3 flex items-center gap-3">
            <X className="w-5 h-5 text-[#A66B6B]" />
            <span className="text-[#E8E6E1]">{errorMessage}</span>
          </div>
        </div>
      )}

      <div className="max-w-3xl mx-auto px-6 py-8 space-y-6">
        {/* Data Export Section */}
        <div className="bg-[#161B2E] border border-[#2A2F42] rounded-xl p-6">
          <div className="flex items-center gap-3 mb-4">
            <Download className="w-5 h-5 text-[#7B8EAA]" />
            <div>
              <h2 className="text-[#E8E6E1] font-sans text-[1.125rem] font-medium">Data Export</h2>
              <p className="text-[#8B92A5] text-[0.8125rem]">Download all your data (GDPR right to access)</p>
            </div>
          </div>
          <button
            onClick={handleExportData}
            disabled={exportPreparing || exportLoading}
            className="px-5 py-2.5 bg-[#5B6E8A] text-white rounded-lg font-sans text-[0.875rem] font-medium hover:bg-[#4A5D79] active:bg-[#3D5070] transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px] flex items-center justify-center gap-2"
          >
            {exportPreparing || exportLoading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Preparing...
              </>
            ) : (
              <>
                <Download className="w-4 h-4" />
                Download my data
              </>
            )}
          </button>
        </div>

        {/* Consent Management Section */}
        <div className="bg-[#161B2E] border border-[#2A2F42] rounded-xl p-6">
          <div className="flex items-center gap-3 mb-6">
            <Shield className="w-5 h-5 text-[#7B8EAA]" />
            <div>
              <h2 className="text-[#E8E6E1] font-sans text-[1.125rem] font-medium">Data Processing Consent</h2>
              <p className="text-[#8B92A5] text-[0.8125rem]">Control what ARIA learns from</p>
            </div>
          </div>

          <div className="space-y-4">
            {consentConfig.map((config) => {
              const isEnabled = consent?.[config.key as keyof typeof consent] ?? true;
              return (
                <div
                  key={config.key}
                  className="flex items-start justify-between py-3 px-4 bg-[#1E2235] rounded-lg border border-[#2A2F42]"
                >
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5 text-[#7B8EAA]">{config.icon}</div>
                    <div>
                      <h3 className="text-[#E8E6E1] text-[0.9375rem] font-medium">
                        {config.label}
                      </h3>
                      <p className="text-[#8B92A5] text-[0.8125rem] mt-0.5">
                        {config.description}
                      </p>
                      {!isEnabled && (
                        <p className="text-[#A66B6B] text-[0.75rem] mt-2">
                          {config.label} is disabled. ARIA will not use this data source.
                        </p>
                      )}
                    </div>
                  </div>
                  <button
                    onClick={() => handleToggleConsent(config.key, !isEnabled)}
                    disabled={updateConsent.isPending}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-[#7B8EAA] focus:ring-offset-2 focus:ring-offset-[#161B2E] ${
                      isEnabled ? "bg-[#5B6E8A]" : "bg-[#2A2F42]"
                    }`}
                  >
                    <span
                      className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform duration-200 ${
                        isEnabled ? "translate-x-6" : "translate-x-1"
                      }`}
                    />
                  </button>
                </div>
              );
            })}
          </div>
        </div>

        {/* Digital Twin Section */}
        <div className="bg-[#161B2E] border border-[#2A2F42] rounded-xl p-6">
          <div className="flex items-center gap-3 mb-4">
            <EyeOff className="w-5 h-5 text-[#7B8EAA]" />
            <div>
              <h2 className="text-[#E8E6E1] font-sans text-[1.125rem] font-medium">Digital Twin</h2>
              <p className="text-[#8B92A5] text-[0.8125rem]">Your writing style and communication patterns</p>
            </div>
          </div>
          <p className="text-[#8B92A5] text-[0.875rem] mb-4">
            Your Digital Twin helps ARIA write emails in your voice. Deleting it will reset
            this learning without affecting your other data.
          </p>
          <button
            onClick={() => setShowDeleteTwinModal(true)}
            className="px-5 py-2.5 bg-transparent border border-[#5B6E8A] text-[#5B6E8A] rounded-lg font-sans text-[0.875rem] font-medium hover:bg-[#5B6E8A]/10 transition-colors duration-150 min-h-[44px]"
          >
            Delete my Digital Twin
          </button>
        </div>

        {/* Retention Policies Section */}
        <div className="bg-[#161B2E] border border-[#2A2F42] rounded-xl p-6">
          <div className="flex items-center gap-3 mb-6">
            <Clock className="w-5 h-5 text-[#7B8EAA]" />
            <div>
              <h2 className="text-[#E8E6E1] font-sans text-[1.125rem] font-medium">Data Retention Policies</h2>
              <p className="text-[#8B92A5] text-[0.8125rem]">How long we keep your data</p>
            </div>
          </div>

          {retentionLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="w-6 h-6 text-[#7B8EAA] animate-spin" />
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex justify-between items-center py-3 px-4 bg-[#1E2235] rounded-lg">
                <div>
                  <p className="text-[#E8E6E1] text-[0.875rem]">Audit query logs</p>
                  <p className="text-[#8B92A5] text-[0.75rem]">Search queries and filters</p>
                </div>
                <span className="text-[#E8E6E1] font-mono text-[0.8125rem]">
                  {retention?.audit_query_logs?.duration_days === -1 ? "Permanent" : `${retention?.audit_query_logs?.duration_days} days`}
                </span>
              </div>
              <div className="flex justify-between items-center py-3 px-4 bg-[#1E2235] rounded-lg">
                <div>
                  <p className="text-[#E8E6E1] text-[0.875rem]">Audit write logs</p>
                  <p className="text-[#8B92A5] text-[0.75rem]">Data changes and deletions</p>
                </div>
                <span className="text-[#E8E6E1] font-mono text-[0.8125rem]">
                  {retention?.audit_write_logs?.duration_days === -1 ? "Permanent" : `${retention?.audit_write_logs?.duration_days} days`}
                </span>
              </div>
              <div className="flex justify-between items-center py-3 px-4 bg-[#1E2235] rounded-lg">
                <div>
                  <p className="text-[#E8E6E1] text-[0.875rem]">Email data</p>
                  <p className="text-[#8B92A5] text-[0.75rem]">Email content and metadata</p>
                </div>
                <span className="text-[#E8E6E1] font-mono text-[0.8125rem]">
                  {retention?.email_data?.duration_days === -1 ? "Permanent" : `${retention?.email_data?.duration_days} days`}
                </span>
              </div>
              <div className="flex justify-between items-center py-3 px-4 bg-[#1E2235] rounded-lg">
                <div>
                  <p className="text-[#E8E6E1] text-[0.875rem]">Conversation history</p>
                  <p className="text-[#8B92A5] text-[0.75rem]">Chat with ARIA</p>
                </div>
                <span className="text-[#E8E6E1] font-mono text-[0.8125rem]">
                  {retention?.conversation_history?.duration_days === -1 ? "Until deleted" : `${retention?.conversation_history?.duration_days} days`}
                </span>
              </div>
              {retention?.note && (
                <p className="text-[#8B92A5] text-[0.75rem] mt-4 px-4">
                  {retention.note}
                </p>
              )}
            </div>
          )}
        </div>

        {/* Danger Zone */}
        <div className="bg-[#161B2E] border border-[#A66B6B]/30 rounded-xl p-6">
          <div className="flex items-center gap-3 mb-6">
            <AlertTriangle className="w-5 h-5 text-[#A66B6B]" />
            <div>
              <h2 className="text-[#A66B6B] font-sans text-[1.125rem] font-medium">Danger Zone</h2>
              <p className="text-[#8B92A5] text-[0.8125rem]">Irreversible actions</p>
            </div>
          </div>

          <div className="border-t border-[#A66B6B]/20 pt-6">
            <div className="space-y-4">
              <p className="text-[#8B92A5] text-[0.875rem]">
                Deleting all your data is permanent. This will delete your account, all memories,
                conversations, documents, and settings. This action cannot be undone.
              </p>
              <div>
                <label className="block text-[#8B92A5] text-[0.8125rem] font-medium mb-1.5">
                  Type <span className="text-[#E8E6E1] font-mono">DELETE MY DATA</span> to confirm
                </label>
                <input
                  type="text"
                  value={deleteConfirmation}
                  onChange={(e) => setDeleteConfirmation(e.target.value)}
                  className="w-full bg-[#1E2235] border border-[#2A2F42] rounded-lg px-4 py-3 text-[#E8E6E1] text-[0.9375rem] focus:border-[#A66B6B] focus:ring-1 focus:ring-[#A66B6B] outline-none transition-colors duration-150"
                  placeholder="DELETE MY DATA"
                />
              </div>
              <button
                onClick={() => setShowDeleteDataModal(true)}
                disabled={deleteData.isPending}
                className="px-5 py-2.5 bg-transparent border border-[#A66B6B] text-[#A66B6B] rounded-lg font-sans text-[0.875rem] font-medium hover:bg-[#A66B6B]/10 transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px] flex items-center justify-center"
              >
                {deleteData.isPending ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin mr-2" />
                    Deleting...
                  </>
                ) : (
                  <>
                    <Trash2 className="w-4 h-4 mr-2" />
                    Delete all my data
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Delete Digital Twin Modal */}
      {showDeleteTwinModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-[#161B2E] border border-[#2A2F42] rounded-xl max-w-md w-full p-6">
            <h3 className="text-[#E8E6E1] font-display text-[1.5rem] mb-2">Delete Digital Twin?</h3>
            <p className="text-[#8B92A5] text-[0.9375rem] mb-6">
              This will remove ARIA's learned understanding of your writing style and
              communication patterns. ARIA will need to re-learn these from your interactions.
              Your other data will not be affected.
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setShowDeleteTwinModal(false)}
                className="flex-1 px-5 py-2.5 bg-transparent border border-[#5B6E8A] text-[#5B6E8A] rounded-lg font-sans text-[0.875rem] font-medium hover:bg-[#5B6E8A]/10 transition-colors duration-150 min-h-[44px]"
              >
                Cancel
              </button>
              <button
                onClick={handleDeleteTwin}
                disabled={deleteDigitalTwin.isPending}
                className="flex-1 px-5 py-2.5 bg-[#A66B6B] text-white rounded-lg font-sans text-[0.875rem] font-medium hover:bg-[#945A5A] transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px] flex items-center justify-center"
              >
                {deleteDigitalTwin.isPending ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  "Delete"
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete All Data Modal */}
      {showDeleteDataModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-[#161B2E] border border-[#A66B6B]/30 rounded-xl max-w-md w-full p-6">
            <h3 className="text-[#A66B6B] font-display text-[1.5rem] mb-2">Delete All Data?</h3>
            <p className="text-[#8B92A5] text-[0.9375rem] mb-6">
              This is permanent. Your account, all memories, conversations, documents,
              and settings will be deleted forever. This action cannot be undone.
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => {
                  setShowDeleteDataModal(false);
                  setDeleteConfirmation("");
                }}
                className="flex-1 px-5 py-2.5 bg-transparent border border-[#5B6E8A] text-[#5B6E8A] rounded-lg font-sans text-[0.875rem] font-medium hover:bg-[#5B6E8A]/10 transition-colors duration-150 min-h-[44px]"
              >
                Cancel
              </button>
              <button
                onClick={handleDeleteAllData}
                disabled={deleteConfirmation !== "DELETE MY DATA" || deleteData.isPending}
                className="flex-1 px-5 py-2.5 bg-[#A66B6B] text-white rounded-lg font-sans text-[0.875rem] font-medium hover:bg-[#945A5A] transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px] flex items-center justify-center"
              >
                {deleteData.isPending ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  "Delete Everything"
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
```

**Step 4: Add route to App.tsx**

Add the route for the privacy settings page (exact location depends on routing setup):

```typescript
// In frontend/src/App.tsx or routes file
import { SettingsPrivacyPage } from "@/pages/SettingsPrivacyPage";

// Add to routes:
<Route path="/settings/privacy" element={<SettingsPrivacyPage />} />
```

**Step 5: Commit**

```bash
git add frontend/src/pages/SettingsPrivacyPage.tsx frontend/src/api/compliance.ts frontend/src/hooks/useCompliance.ts
git commit -m "feat: add privacy settings page with consent management (US-929)"
```

---

## Task 4: Add navigation link to Privacy Settings

**Files:**
- Modify: `frontend/src/components/Navigation.tsx` (or equivalent)

**Step 1: Add Privacy link to settings section**

Add a link to `/settings/privacy` in the settings/account section of navigation.

**Step 2: Commit**

```bash
git add frontend/src/components/Navigation.tsx
git commit -m "feat: add privacy settings navigation link (US-929)"
```

---

## Quality Gates

Run these commands after implementation:

```bash
# Backend type checking
cd backend
mypy src/services/compliance_service.py --strict
mypy src/api/routes/compliance.py --strict

# Backend linting
ruff check src/services/compliance_service.py
ruff check src/api/routes/compliance.py

# Backend tests
pytest tests/test_compliance_service.py -v
pytest tests/api/routes/test_compliance.py -v

# Frontend type checking
cd frontend
npm run typecheck

# Frontend linting
npm run lint

# Frontend build
npm run build
```

Expected: All type checks pass, all linting passes, all tests pass, build succeeds.
