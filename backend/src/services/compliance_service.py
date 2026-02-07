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

from src.core.exceptions import NotFoundError
from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


class ComplianceError(Exception):
    """Compliance operation error.

    Note: Using standard Exception instead of ARIAException to follow
    the pattern in billing_service.py which also uses a custom exception
    class that inherits directly from Exception.
    """

    def __init__(self, message: str = "Compliance operation failed") -> None:
        """Initialize compliance error.

        Args:
            message: Error details.
        """
        self.message = message
        self.code = "COMPLIANCE_ERROR"
        self.status_code = 500
        super().__init__(message)


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
                    if conversation_ids:
                        messages_response = (
                            client.table("messages")
                            .select("*")
                            .in_("conversation_id", conversation_ids)
                            .execute()
                        )
                        export_data["messages"] = messages_response.data
                    else:
                        export_data["messages"] = []
                except Exception:
                    export_data["messages"] = []
            else:
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
            try:
                conversations_result = (
                    client.table("conversations")
                    .select("id")
                    .eq("user_id", user_id)
                    .execute()
                )
                conversation_ids = [c["id"] for c in conversations_result.data] if conversations_result.data else []
            except Exception:
                conversation_ids = []

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
            NotFoundError: If user settings not found.
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

        except Exception:
            logger.exception("Error getting consent status", extra={"user_id": user_id})
            # Return defaults on error
            return dict.fromkeys(self.ALL_CONSENT_CATEGORIES, True)

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

    async def get_retention_policies(self, company_id: str | None = None) -> dict[str, Any]:  # noqa: ARG002
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
