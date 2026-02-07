"""Profile Page Service (US-921).

Provides a unified profile API that merges user details, company details,
documents, and integrations. Saves trigger US-922 Memory Merge Pipeline
via ProfileMergeService.
"""

import asyncio
import logging
from typing import Any, cast

from src.core.exceptions import ARIAException, NotFoundError
from src.db.supabase import SupabaseClient
from src.memory.profile_merge import ProfileMergeService

logger = logging.getLogger(__name__)

# Fields users are allowed to update on their own profile
ALLOWED_USER_FIELDS = frozenset(
    {
        "full_name",
        "title",
        "department",
        "linkedin_url",
        "avatar_url",
        "communication_preferences",
        "privacy_exclusions",
        "default_tone",
        "tracked_competitors",
    }
)

# Fields allowed for company updates (admin only)
ALLOWED_COMPANY_FIELDS = frozenset(
    {
        "name",
        "website",
        "industry",
        "sub_vertical",
        "description",
        "key_products",
    }
)

# Fields allowed for preferences updates
ALLOWED_PREFERENCE_FIELDS = frozenset(
    {
        "communication_preferences",
        "default_tone",
        "tracked_competitors",
        "privacy_exclusions",
    }
)


class ProfileService:
    """Service for unified profile management across user, company, and integrations."""

    def __init__(self) -> None:
        """Initialize ProfileService."""
        self._client: Any = None

    @property
    def db(self) -> Any:
        """Get Supabase client lazily.

        Returns:
            Supabase client instance.
        """
        if self._client is None:
            self._client = SupabaseClient.get_client()
        return self._client

    async def get_full_profile(self, user_id: str) -> dict[str, Any]:
        """Get merged profile view: user + company + integrations.

        Args:
            user_id: The user's UUID.

        Returns:
            Dict with keys: user, company, integrations.

        Raises:
            NotFoundError: If user profile not found.
            ARIAException: If operation fails.
        """
        try:
            # Fetch user profile
            profile = await SupabaseClient.get_user_by_id(user_id)

            # Fetch company if user has one
            company = None
            company_id = profile.get("company_id")
            if company_id:
                try:
                    response = (
                        self.db.table("companies")
                        .select("*")
                        .eq("id", company_id)
                        .single()
                        .execute()
                    )
                    company = response.data
                except Exception:
                    logger.warning(
                        "Failed to fetch company for profile",
                        extra={"user_id": user_id, "company_id": company_id},
                    )

            # Fetch integrations
            integrations: list[dict[str, Any]] = []
            try:
                response = (
                    self.db.table("user_integrations").select("*").eq("user_id", user_id).execute()
                )
                integrations = response.data or []
            except Exception:
                logger.warning(
                    "Failed to fetch integrations for profile",
                    extra={"user_id": user_id},
                )

            return {
                "user": {
                    "id": profile["id"],
                    "full_name": profile.get("full_name"),
                    "title": profile.get("title"),
                    "department": profile.get("department"),
                    "linkedin_url": profile.get("linkedin_url"),
                    "avatar_url": profile.get("avatar_url"),
                    "company_id": profile.get("company_id"),
                    "role": profile.get("role", "user"),
                    "communication_preferences": profile.get("communication_preferences", {}),
                    "privacy_exclusions": profile.get("privacy_exclusions", []),
                    "default_tone": profile.get("default_tone", "friendly"),
                    "tracked_competitors": profile.get("tracked_competitors", []),
                    "created_at": profile.get("created_at"),
                    "updated_at": profile.get("updated_at"),
                },
                "company": company,
                "integrations": integrations,
            }

        except NotFoundError:
            raise
        except Exception as e:
            logger.exception("Error fetching full profile", extra={"user_id": user_id})
            raise ARIAException(
                message="Failed to fetch profile",
                code="PROFILE_FETCH_FAILED",
                status_code=500,
            ) from e

    async def update_user_details(
        self,
        user_id: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Update user profile fields.

        Filters to allowed fields only. Fires US-922 Memory Merge Pipeline
        as a background task after saving.

        Args:
            user_id: The user's UUID.
            data: Dict of fields to update.

        Returns:
            Updated user profile row with merge_pending flag.

        Raises:
            ARIAException: If operation fails.
        """
        try:
            # Filter to allowed fields only
            update_data = {k: v for k, v in data.items() if k in ALLOWED_USER_FIELDS}

            if not update_data:
                profile = await self.get_full_profile(user_id)
                return profile["user"]

            # Snapshot old data for US-922 diff detection
            old_profile = await SupabaseClient.get_user_by_id(user_id)
            old_data = {k: old_profile.get(k) for k in update_data}

            response = (
                self.db.table("user_profiles").update(update_data).eq("id", user_id).execute()
            )

            if not response.data:
                raise NotFoundError("User profile", user_id)

            # Log audit event
            await self._log_audit_event(
                user_id=user_id,
                event_type="profile_updated",
                metadata={"fields": list(update_data.keys()), "section": "user_details"},
            )

            # Fire US-922 Memory Merge Pipeline (background)
            asyncio.create_task(
                ProfileMergeService().process_update(user_id, old_data, update_data)
            )

            result = cast(dict[str, Any], response.data[0])
            result["merge_pending"] = True
            return result

        except NotFoundError:
            raise
        except Exception as e:
            logger.exception("Error updating user details", extra={"user_id": user_id})
            raise ARIAException(
                message="Failed to update user details",
                code="USER_UPDATE_FAILED",
                status_code=500,
            ) from e

    async def update_company_details(
        self,
        user_id: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Update company details. Admin only.

        Args:
            user_id: The requesting user's UUID.
            data: Dict of company fields to update.

        Returns:
            Updated company row.

        Raises:
            ARIAException: If user is not admin or has no company.
        """
        try:
            # Verify admin role
            profile = await SupabaseClient.get_user_by_id(user_id)
            if profile.get("role") != "admin":
                raise ARIAException(
                    message="Only admins can update company details",
                    code="INSUFFICIENT_PERMISSIONS",
                    status_code=403,
                )

            company_id = profile.get("company_id")
            if not company_id:
                raise ARIAException(
                    message="No company associated with user",
                    code="NO_COMPANY",
                    status_code=400,
                )

            # Filter to allowed fields
            update_data = {k: v for k, v in data.items() if k in ALLOWED_COMPANY_FIELDS}

            if not update_data:
                response = (
                    self.db.table("companies").select("*").eq("id", company_id).single().execute()
                )
                return cast(dict[str, Any], response.data)

            # Snapshot old company data for US-922 diff detection
            old_company_resp = (
                self.db.table("companies").select("*").eq("id", company_id).single().execute()
            )
            old_company = (
                cast(dict[str, Any], old_company_resp.data) if old_company_resp.data else {}
            )
            old_data = {k: old_company.get(k) for k in update_data}

            response = self.db.table("companies").update(update_data).eq("id", company_id).execute()

            if not response.data:
                raise NotFoundError("Company", company_id)

            # Log audit event
            await self._log_audit_event(
                user_id=user_id,
                event_type="company_updated",
                metadata={"fields": list(update_data.keys()), "company_id": company_id},
            )

            # Fire US-922 Memory Merge Pipeline (background)
            # Include company_id in new_data so re-enrichment can use it
            merge_data = {**update_data, "id": company_id}
            asyncio.create_task(ProfileMergeService().process_update(user_id, old_data, merge_data))

            result = cast(dict[str, Any], response.data[0])
            result["merge_pending"] = True
            return result

        except ARIAException:
            raise
        except NotFoundError:
            raise
        except Exception as e:
            logger.exception(
                "Error updating company details",
                extra={"user_id": user_id},
            )
            raise ARIAException(
                message="Failed to update company details",
                code="COMPANY_UPDATE_FAILED",
                status_code=500,
            ) from e

    async def list_documents(self, user_id: str) -> dict[str, Any]:
        """List company and user documents.

        Args:
            user_id: The user's UUID.

        Returns:
            Dict with company_documents and user_documents lists.
        """
        try:
            profile = await SupabaseClient.get_user_by_id(user_id)
            company_id = profile.get("company_id")

            # Fetch company documents
            company_docs: list[dict[str, Any]] = []
            if company_id:
                try:
                    response = (
                        self.db.table("company_documents")
                        .select("*")
                        .eq("company_id", company_id)
                        .order("created_at", desc=True)
                        .execute()
                    )
                    company_docs = response.data or []
                except Exception:
                    logger.warning(
                        "Failed to fetch company documents",
                        extra={"user_id": user_id, "company_id": company_id},
                    )

            # Fetch user documents (private)
            user_docs: list[dict[str, Any]] = []
            try:
                response = (
                    self.db.table("user_documents")
                    .select("*")
                    .eq("user_id", user_id)
                    .order("created_at", desc=True)
                    .execute()
                )
                user_docs = response.data or []
            except Exception:
                logger.warning(
                    "Failed to fetch user documents",
                    extra={"user_id": user_id},
                )

            return {
                "company_documents": company_docs,
                "user_documents": user_docs,
            }

        except NotFoundError:
            raise
        except Exception as e:
            logger.exception("Error listing documents", extra={"user_id": user_id})
            raise ARIAException(
                message="Failed to list documents",
                code="DOCUMENTS_LIST_FAILED",
                status_code=500,
            ) from e

    async def update_preferences(
        self,
        user_id: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Update communication/notification preferences on user_profiles.

        Args:
            user_id: The user's UUID.
            data: Preference fields to update.

        Returns:
            Updated preference fields from user profile.
        """
        try:
            update_data = {k: v for k, v in data.items() if k in ALLOWED_PREFERENCE_FIELDS}

            if not update_data:
                profile = await self.get_full_profile(user_id)
                return profile["user"]

            response = (
                self.db.table("user_profiles").update(update_data).eq("id", user_id).execute()
            )

            if not response.data:
                raise NotFoundError("User profile", user_id)

            # Log audit event
            await self._log_audit_event(
                user_id=user_id,
                event_type="preferences_updated",
                metadata={"fields": list(update_data.keys())},
            )

            return cast(dict[str, Any], response.data[0])

        except NotFoundError:
            raise
        except Exception as e:
            logger.exception("Error updating preferences", extra={"user_id": user_id})
            raise ARIAException(
                message="Failed to update preferences",
                code="PREFERENCES_UPDATE_FAILED",
                status_code=500,
            ) from e

    async def _log_audit_event(
        self,
        user_id: str,
        event_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log a profile change event to the audit log.

        Args:
            user_id: The user's UUID.
            event_type: Type of event.
            metadata: Additional context.
        """
        try:
            self.db.table("security_audit_log").insert(
                {
                    "user_id": user_id,
                    "event_type": event_type,
                    "metadata": metadata or {},
                }
            ).execute()
        except Exception:
            logger.exception(
                "Failed to log audit event",
                extra={"user_id": user_id, "event_type": event_type},
            )
