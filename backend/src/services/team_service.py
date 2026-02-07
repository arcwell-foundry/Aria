"""Team & Company Administration Service (US-927).

Provides functionality for:
- Team member management (invite, change role, deactivate/reactivate)
- Company administration
- Role-based access control
"""

import logging
import secrets
from datetime import datetime, timedelta
from typing import Any

from src.core.config import settings
from src.core.exceptions import ARIAException, NotFoundError, ValidationError
from src.db.supabase import SupabaseClient
from supabase import Client

logger = logging.getLogger(__name__)


class TeamService:
    """Service for team and company administration operations."""

    VALID_ROLES = {"user", "manager", "admin"}
    INVITE_EXPIRY_DAYS = 7
    ESCALATION_THRESHOLD = 5  # Users without verified admin before escalation

    def __init__(self) -> None:
        """Initialize TeamService."""
        self._client: Client | None = None

    @property
    def client(self) -> Client:
        """Get Supabase client.

        Returns:
            Initialized Supabase client.
        """
        if self._client is None:
            self._client = SupabaseClient.get_client()
        return self._client

    async def list_team(self, company_id: str) -> list[dict[str, Any]]:
        """List all users at a company with their profiles.

        Args:
            company_id: The company's UUID.

        Returns:
            List of team members with id, name, email, role, status, last_active.
        """
        try:
            response = (
                self.client.table("user_profiles")
                .select("id", "full_name", "role", "is_active", "created_at", "updated_at")
                .eq("company_id", company_id)
                .order("created_at", desc=True)
                .execute()
            )

            team: list[dict[str, Any]] = []
            for member in response.data or []:  # type: ignore
                # Get email from auth.users via admin API
                try:
                    user_data = self.client.auth.admin.get_user_by_id(member["id"])  # type: ignore
                    email = user_data.user.email if user_data and user_data.user else "Unknown"  # type: ignore
                except Exception:
                    email = "Unknown"

                team.append(
                    {
                        "id": member["id"],  # type: ignore
                        "full_name": member.get("full_name"),  # type: ignore
                        "email": email,
                        "role": member.get("role", "user"),  # type: ignore
                        "is_active": member.get("is_active", True),  # type: ignore
                        "last_active": member.get("updated_at"),  # type: ignore
                        "created_at": member.get("created_at"),  # type: ignore
                    }
                )

            return team

        except Exception as e:
            logger.exception("Error listing team", extra={"company_id": company_id})
            raise ARIAException(
                message="Failed to list team members",
                code="TEAM_LIST_FAILED",
                status_code=500,
            ) from e

    async def invite_member(
        self,
        company_id: str,
        invited_by: str,
        email: str,
        role: str = "user",
    ) -> dict[str, Any]:
        """Create a team invite with unique token.

        Args:
            company_id: The company's UUID.
            invited_by: The user ID creating the invite.
            email: Email address to invite.
            role: Role to assign (user, manager, admin).

        Returns:
            Created invite record.
        """
        try:
            if role not in self.VALID_ROLES:
                raise ValidationError(
                    f"Invalid role. Must be one of: {', '.join(self.VALID_ROLES)}"
                )

            # Check if user already has a pending invite
            existing_invite = (
                self.client.table("team_invites")
                .select("*")
                .eq("company_id", company_id)
                .eq("email", email.lower())
                .eq("status", "pending")
                .execute()
            )

            if existing_invite.data:
                raise ValidationError("User already has a pending invite")

            # Generate unique token
            token = secrets.token_urlsafe(32)

            # Create invite
            invite_data = {
                "company_id": company_id,
                "invited_by": invited_by,
                "email": email.lower(),
                "role": role,
                "token": token,
                "status": "pending",
                "expires_at": (
                    datetime.now() + timedelta(days=self.INVITE_EXPIRY_DAYS)
                ).isoformat(),
            }

            response = self.client.table("team_invites").insert(invite_data).execute()

            if not response.data:
                raise ARIAException(
                    message="Failed to create invite",
                    code="INVITE_CREATE_FAILED",
                    status_code=500,
                )

            # Send team invite email
            try:
                from src.services.email_service import EmailService
                email_service = EmailService()
                invite_url = f"{settings.APP_URL}/accept-invite?token={token}"
                await email_service.send_team_invite(
                    to=email.lower(),
                    inviter_name="Your colleague",
                    company_name="Your company",
                    invite_url=invite_url,
                )
            except Exception as email_error:
                logger.warning(
                    "Failed to send invite email",
                    extra={"email": email, "error": str(email_error)},
                )

            # Check for escalation trigger (>5 users without verified admin)
            await self._check_escalation_trigger(company_id)

            logger.info(
                "Team invite created",
                extra={"company_id": company_id, "email": email, "role": role},
            )

            return response.data[0]  # type: ignore

        except ValidationError:
            raise
        except Exception as e:
            logger.exception(
                "Error creating invite", extra={"company_id": company_id, "email": email}
            )
            raise ARIAException(
                message="Failed to create invite",
                code="INVITE_CREATE_FAILED",
                status_code=500,
            ) from e

    async def accept_invite(self, token: str, user_id: str) -> dict[str, Any]:
        """Accept a team invite and link user to company.

        Args:
            token: Invite token.
            user_id: The user's UUID accepting the invite.

        Returns:
            Updated user profile.
        """
        try:
            # Find invite
            response = (
                self.client.table("team_invites")
                .select("*")
                .eq("token", token)
                .eq("status", "pending")
                .execute()
            )

            if not response.data:
                raise ValidationError("Invalid or expired invite token")

            invite = response.data[0]  # type: ignore

            # Check expiry
            expires_at = datetime.fromisoformat(invite["expires_at"])  # type: ignore
            if datetime.now() > expires_at:
                raise ValidationError("Invite token has expired")

            # Link user to company
            (
                self.client.table("user_profiles")
                .update(
                    {
                        "company_id": invite["company_id"],  # type: ignore
                        "role": invite["role"],  # type: ignore
                    }
                )
                .eq("id", user_id)
                .execute()
            )

            # Mark invite as accepted
            (
                self.client.table("team_invites")
                .update({"status": "accepted"})
                .eq("token", token)
                .execute()
            )

            logger.info(
                "Invite accepted",
                extra={"user_id": user_id, "company_id": invite["company_id"]},  # type: ignore
            )

            return await SupabaseClient.get_user_by_id(user_id)

        except ValidationError:
            raise
        except Exception as e:
            logger.exception("Error accepting invite", extra={"token": token, "user_id": user_id})
            raise ARIAException(
                message="Failed to accept invite",
                code="INVITE_ACCEPT_FAILED",
                status_code=500,
            ) from e

    async def change_role(
        self,
        company_id: str,
        user_id: str,
        new_role: str,
    ) -> dict[str, Any]:
        """Change a user's role.

        Args:
            company_id: The company's UUID.
            user_id: The user's UUID to change role for.
            new_role: New role (user, manager, admin).

        Raises:
            ValidationError: If this is the last admin or role is invalid.
        """
        try:
            if new_role not in self.VALID_ROLES:
                raise ValidationError(
                    f"Invalid role. Must be one of: {', '.join(self.VALID_ROLES)}"
                )

            # Check if this is the last admin
            if new_role != "admin":
                admin_response = (
                    self.client.table("user_profiles")
                    .select("id", count="exact")  # type: ignore
                    .eq("company_id", company_id)
                    .eq("role", "admin")
                    .eq("is_active", True)
                    .execute()
                )

                # Check if the user being changed is currently an admin
                current_user = await SupabaseClient.get_user_by_id(user_id)
                is_current_admin = current_user.get("role") == "admin"  # type: ignore

                admin_count = admin_response.count or 0  # type: ignore
                if is_current_admin and admin_count <= 1:
                    raise ValidationError("Cannot demote the last admin")

            # Update role
            (
                self.client.table("user_profiles")
                .update({"role": new_role})
                .eq("id", user_id)
                .execute()
            )

            logger.info("User role changed", extra={"user_id": user_id, "new_role": new_role})

            return await SupabaseClient.get_user_by_id(user_id)

        except ValidationError:
            raise
        except Exception as e:
            logger.exception(
                "Error changing role", extra={"user_id": user_id, "new_role": new_role}
            )
            raise ARIAException(
                message="Failed to change role",
                code="ROLE_CHANGE_FAILED",
                status_code=500,
            ) from e

    async def deactivate_user(self, user_id: str) -> None:
        """Soft deactivate a user.

        Args:
            user_id: The user's UUID to deactivate.
        """
        try:
            self.client.table("user_profiles").update({"is_active": False}).eq(
                "id", user_id
            ).execute()

            logger.info("User deactivated", extra={"user_id": user_id})

        except Exception as e:
            logger.exception("Error deactivating user", extra={"user_id": user_id})
            raise ARIAException(
                message="Failed to deactivate user",
                code="USER_DEACTIVATION_FAILED",
                status_code=500,
            ) from e

    async def reactivate_user(self, user_id: str) -> None:
        """Reactivate a deactivated user.

        Args:
            user_id: The user's UUID to reactivate.
        """
        try:
            self.client.table("user_profiles").update({"is_active": True}).eq(
                "id", user_id
            ).execute()

            logger.info("User reactivated", extra={"user_id": user_id})

        except Exception as e:
            logger.exception("Error reactivating user", extra={"user_id": user_id})
            raise ARIAException(
                message="Failed to reactivate user",
                code="USER_REACTIVATION_FAILED",
                status_code=500,
            ) from e

    async def get_company(self, company_id: str) -> dict[str, Any]:
        """Get company details.

        Args:
            company_id: The company's UUID.

        Returns:
            Company data.
        """
        try:
            return await SupabaseClient.get_company_by_id(company_id)

        except NotFoundError:
            raise
        except Exception as e:
            logger.exception("Error fetching company", extra={"company_id": company_id})
            raise ARIAException(
                message="Failed to fetch company",
                code="COMPANY_FETCH_FAILED",
                status_code=500,
            ) from e

    async def update_company(
        self,
        company_id: str,
        name: str | None = None,
        settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update company details.

        Args:
            company_id: The company's UUID.
            name: Optional new company name.
            settings: Optional company settings to update.

        Returns:
            Updated company data.
        """
        try:
            update_data: dict[str, Any] = {}
            if name is not None:
                update_data["name"] = name
            if settings is not None:
                update_data["settings"] = settings

            if not update_data:
                return await self.get_company(company_id)

            response = (
                self.client.table("companies").update(update_data).eq("id", company_id).execute()
            )

            if not response.data:
                raise ARIAException(
                    message="Failed to update company",
                    code="COMPANY_UPDATE_FAILED",
                    status_code=500,
                )

            logger.info(
                "Company updated",
                extra={"company_id": company_id, "fields": list(update_data.keys())},
            )

            return response.data[0]  # type: ignore

        except ARIAException:
            raise
        except Exception as e:
            logger.exception("Error updating company", extra={"company_id": company_id})
            raise ARIAException(
                message="Failed to update company",
                code="COMPANY_UPDATE_FAILED",
                status_code=500,
            ) from e

    async def list_pending_invites(self, company_id: str) -> list[dict[str, Any]]:
        """List pending invites for a company.

        Args:
            company_id: The company's UUID.

        Returns:
            List of pending invites.
        """
        try:
            response = (
                self.client.table("team_invites")
                .select("*")
                .eq("company_id", company_id)
                .eq("status", "pending")
                .order("created_at", desc=True)
                .execute()
            )

            return response.data or []  # type: ignore

        except Exception:
            logger.exception("Error listing invites", extra={"company_id": company_id})
            return []

    async def cancel_invite(self, invite_id: str, company_id: str) -> None:
        """Cancel a pending invite.

        Args:
            invite_id: The invite's UUID.
            company_id: The company's UUID (for validation).
        """
        try:
            self.client.table("team_invites").update({"status": "cancelled"}).eq(
                "id", invite_id
            ).eq("company_id", company_id).execute()

            logger.info("Invite cancelled", extra={"invite_id": invite_id})

        except Exception as e:
            logger.exception("Error cancelling invite", extra={"invite_id": invite_id})
            raise ARIAException(
                message="Failed to cancel invite",
                code="INVITE_CANCEL_FAILED",
                status_code=500,
            ) from e

    async def resend_invite(self, invite_id: str, company_id: str) -> dict[str, Any]:
        """Resend a pending invite (extends expiry).

        Args:
            invite_id: The invite's UUID.
            company_id: The company's UUID (for validation).

        Returns:
            Updated invite record.
        """
        try:
            new_expiry = (datetime.now() + timedelta(days=self.INVITE_EXPIRY_DAYS)).isoformat()

            response = (
                self.client.table("team_invites")
                .update({"expires_at": new_expiry})
                .eq("id", invite_id)
                .eq("company_id", company_id)
                .execute()
            )

            if not response.data:
                raise ARIAException(
                    message="Failed to resend invite",
                    code="INVITE_RESEND_FAILED",
                    status_code=500,
                )

            logger.info("Invite resent", extra={"invite_id": invite_id})

            return response.data[0]  # type: ignore

        except ARIAException:
            raise
        except Exception as e:
            logger.exception("Error resending invite", extra={"invite_id": invite_id})
            raise ARIAException(
                message="Failed to resend invite",
                code="INVITE_RESEND_FAILED",
                status_code=500,
            ) from e

    async def _check_escalation_trigger(self, company_id: str) -> bool:
        """Check if company should be flagged for escalation review.

        A company is flagged if it has >5 active users but no verified admin.

        Args:
            company_id: The company's UUID.

        Returns:
            True if escalation trigger met.
        """
        try:
            # Count active users
            user_response = (
                self.client.table("user_profiles")
                .select("id", count="exact")  # type: ignore
                .eq("company_id", company_id)
                .eq("is_active", True)
                .execute()
            )

            # Count admins
            admin_response = (
                self.client.table("user_profiles")
                .select("id", count="exact")  # type: ignore
                .eq("company_id", company_id)
                .eq("role", "admin")
                .eq("is_active", True)
                .execute()
            )

            user_count = user_response.count or 0  # type: ignore
            admin_count = admin_response.count or 0  # type: ignore

            if user_count > self.ESCALATION_THRESHOLD and admin_count == 0:
                # Log escalation event
                logger.warning(
                    "Escalation trigger: Company with >5 users and no verified admin",
                    extra={"company_id": company_id, "user_count": user_count},
                )
                # TODO: Send notification to platform admins
                return True

            return False

        except Exception:
            logger.exception("Error checking escalation trigger", extra={"company_id": company_id})
            return False
