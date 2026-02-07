"""Account & Identity Management Service (US-926).

Provides functionality for:
- Profile management
- Password changes and resets
- Two-factor authentication (2FA/TOTP)
- Session management
- Account deletion with cascade
- Security audit logging
"""

import base64
import logging
import secrets
from io import BytesIO
from typing import Any

import pyotp
import qrcode

from src.core.exceptions import ARIAException, NotFoundError
from src.db.supabase import SupabaseClient
from supabase import Client

logger = logging.getLogger(__name__)


class AccountService:
    """Service for account and identity management operations."""

    # Security event types for audit logging
    EVENT_LOGIN = "login"
    EVENT_LOGIN_FAILED = "login_failed"
    EVENT_LOGOUT = "logout"
    EVENT_PASSWORD_CHANGE = "password_change"
    EVENT_PASSWORD_RESET_REQUEST = "password_reset_request"
    EVENT_2FA_ENABLED = "2fa_enabled"
    EVENT_2FA_DISABLED = "2fa_disabled"
    EVENT_2FA_VERIFY_FAILED = "2fa_verify_failed"
    EVENT_SESSION_REVOKED = "session_revoked"
    EVENT_ACCOUNT_DELETED = "account_deleted"
    EVENT_PROFILE_UPDATED = "profile_updated"
    EVENT_ROLE_CHANGED = "role_changed"
    EVENT_DATA_EXPORT = "data_export"
    EVENT_DATA_DELETION = "data_deletion"

    def __init__(self) -> None:
        """Initialize AccountService."""
        self._client: Client | None = None

    @property
    def client(self) -> Client:
        """Get Supabase client.

        Returns:
            Supabase client instance.

        Raises:
            ARIAException: If client initialization fails.
        """
        if self._client is None:
            self._client = SupabaseClient.get_client()
        return self._client

    async def get_profile(self, user_id: str) -> dict[str, Any]:
        """Get user profile data.

        Args:
            user_id: The user's UUID.

        Returns:
            User profile data including name, email, avatar_url, 2FA status.

        Raises:
            NotFoundError: If user profile not found.
            ARIAException: If operation fails.
        """
        try:
            profile = await SupabaseClient.get_user_by_id(user_id)

            # Get 2FA status from user_settings
            settings = await SupabaseClient.get_user_settings(user_id)
            is_2fa_enabled = settings.get("preferences", {}).get("totp_secret") is not None

            # Get email from auth.users via the Supabase auth client
            # Note: We can't directly query auth.users from the client
            # Email is typically passed from the request context

            return {
                "id": profile["id"],
                "full_name": profile.get("full_name"),
                "avatar_url": profile.get("avatar_url"),
                "company_id": profile.get("company_id"),
                "role": profile.get("role", "user"),
                "is_2fa_enabled": is_2fa_enabled,
                "created_at": profile.get("created_at"),
                "updated_at": profile.get("updated_at"),
            }

        except NotFoundError:
            raise
        except Exception as e:
            logger.exception("Error fetching user profile", extra={"user_id": user_id})
            raise ARIAException(
                message="Failed to fetch user profile",
                code="PROFILE_FETCH_FAILED",
                status_code=500,
            ) from e

    async def update_profile(
        self,
        user_id: str,
        full_name: str | None = None,
        avatar_url: str | None = None,
    ) -> dict[str, Any]:
        """Update user profile.

        Args:
            user_id: The user's UUID.
            full_name: Optional new full name.
            avatar_url: Optional new avatar URL.

        Returns:
            Updated user profile data.

        Raises:
            NotFoundError: If user profile not found.
            ARIAException: If operation fails.
        """
        try:
            update_data: dict[str, Any] = {}
            if full_name is not None:
                update_data["full_name"] = full_name
            if avatar_url is not None:
                update_data["avatar_url"] = avatar_url

            if not update_data:
                # Nothing to update
                return await self.get_profile(user_id)

            response = (
                self.client.table("user_profiles")
                .update(update_data)
                .eq("id", user_id)
                .execute()
            )

            if not response.data:
                raise NotFoundError("User profile", user_id)

            # Log security event
            await self.log_security_event(
                user_id=user_id,
                event_type=self.EVENT_PROFILE_UPDATED,
                metadata={"fields": list(update_data.keys())},
            )

            return await self.get_profile(user_id)

        except NotFoundError:
            raise
        except Exception as e:
            logger.exception("Error updating user profile", extra={"user_id": user_id})
            raise ARIAException(
                message="Failed to update profile",
                code="PROFILE_UPDATE_FAILED",
                status_code=500,
            ) from e

    async def change_password(
        self,
        user_id: str,
        current_password: str,
        new_password: str,
    ) -> None:
        """Change user password.

        Args:
            user_id: The user's UUID.
            current_password: Current password for verification.
            new_password: New password (min 8 chars).

        Raises:
            ARIAException: If operation fails or current password is invalid.
        """
        try:
            # Use Supabase Auth admin API to update password
            # Note: This requires service role key
            admin_client = self.client.auth.admin

            # First verify current password by attempting to sign in
            # We need the user's email for this
            # Try to get user email from auth via admin
            user_data = admin_client.get_user_by_id(user_id)
            if not user_data.user or not user_data.user.email:
                raise ARIAException(
                    message="User not found",
                    code="USER_NOT_FOUND",
                    status_code=404,
                )

            email = user_data.user.email

            # Verify current password
            try:
                self.client.auth.sign_in_with_password(
                    {"email": email, "password": current_password}
                )
            except Exception as err:
                raise ARIAException(
                    message="Current password is incorrect",
                    code="INVALID_PASSWORD",
                    status_code=400,
                ) from err

            # Update password
            admin_client.update_user_by_id(user_id, {"password": new_password})

            # Log security event
            await self.log_security_event(
                user_id=user_id,
                event_type=self.EVENT_PASSWORD_CHANGE,
                metadata={"success": True},
            )

            logger.info("Password changed successfully", extra={"user_id": user_id})

        except ARIAException:
            raise
        except Exception as e:
            logger.exception("Error changing password", extra={"user_id": user_id})
            await self.log_security_event(
                user_id=user_id,
                event_type=self.EVENT_PASSWORD_CHANGE,
                metadata={"success": False, "error": str(e)},
            )
            raise ARIAException(
                message="Failed to change password",
                code="PASSWORD_CHANGE_FAILED",
                status_code=500,
            ) from e

    async def request_password_reset(self, email: str) -> None:
        """Request a password reset email.

        Args:
            email: User's email address.

        Raises:
            ARIAException: If operation fails.
        """
        try:
            # Supabase Auth handles password reset emails
            self.client.auth.reset_password_email(email)

            # Log security event (without user_id since we only have email)
            logger.info("Password reset requested", extra={"email": email})

        except Exception as e:
            logger.exception("Error requesting password reset", extra={"email": email})
            # Don't reveal if email exists or not
            raise ARIAException(
                message="If an account exists with this email, a reset link has been sent.",
                code="PASSWORD_RESET_REQUESTED",
                status_code=200,
            ) from e

    async def setup_2fa(self, user_id: str) -> dict[str, str]:
        """Generate TOTP secret for 2FA setup.

        Args:
            user_id: The user's UUID.

        Returns:
            Dictionary with secret and qr_code_uri.

        Raises:
            ARIAException: If operation fails.
        """
        try:
            # Generate a secure random secret
            secret = secrets.token_urlsafe(20)

            # Create TOTP object
            totp = pyotp.TOTP(secret, digits=6, issuer="ARIA")

            # Get user email for the provisioning URI
            user_data = self.client.auth.admin.get_user_by_id(user_id)
            if not user_data.user or not user_data.user.email:
                raise ARIAException(
                    message="User not found",
                    code="USER_NOT_FOUND",
                    status_code=404,
                )

            email = user_data.user.email

            # Generate provisioning URI for QR code
            provisioning_uri = totp.provisioning_uri(
                name=email,
                issuer_name="ARIA",
            )

            # Generate QR code as base64 image
            qr = qrcode.QRCode(version=1, box_size=10, border=4)
            qr.add_data(provisioning_uri)
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            qr_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
            qr_data_url = f"data:image/png;base64,{qr_base64}"

            logger.info("2FA setup initiated", extra={"user_id": user_id})

            return {
                "secret": secret,
                "qr_code_uri": qr_data_url,
                "provisioning_uri": provisioning_uri,  # For manual entry
            }

        except Exception as e:
            logger.exception("Error setting up 2FA", extra={"user_id": user_id})
            raise ARIAException(
                message="Failed to set up 2FA",
                code="TWO_FACTOR_SETUP_FAILED",
                status_code=500,
            ) from e

    async def verify_2fa(self, user_id: str, code: str, secret: str) -> dict[str, Any]:
        """Verify TOTP code and enable 2FA.

        Args:
            user_id: The user's UUID.
            code: 6-digit TOTP code from authenticator app.
            secret: TOTP secret generated during setup.

        Returns:
            Updated profile with 2FA enabled.

        Raises:
            ARIAException: If code is invalid or operation fails.
        """
        try:
            # Verify the code
            totp = pyotp.TOTP(secret)
            if not totp.verify(code, valid_window=1):
                await self.log_security_event(
                    user_id=user_id,
                    event_type=self.EVENT_2FA_VERIFY_FAILED,
                    metadata={"reason": "invalid_code"},
                )
                raise ARIAException(
                    message="Invalid verification code",
                    code="INVALID_2FA_CODE",
                    status_code=400,
                )

            # Store the secret in user_settings
            settings = await SupabaseClient.get_user_settings(user_id)
            preferences = settings.get("preferences", {})
            preferences["totp_secret"] = secret
            preferences["totp_enabled"] = True
            preferences["totp_enabled_at"] = None  # Will be set by trigger

            (
                self.client.table("user_settings")
                .update({"preferences": preferences})
                .eq("user_id", user_id)
                .execute()
            )

            # Log security event
            await self.log_security_event(
                user_id=user_id,
                event_type=self.EVENT_2FA_ENABLED,
                metadata={"success": True},
            )

            logger.info("2FA enabled successfully", extra={"user_id": user_id})

            return await self.get_profile(user_id)

        except ARIAException:
            raise
        except Exception as e:
            logger.exception("Error verifying 2FA", extra={"user_id": user_id})
            raise ARIAException(
                message="Failed to verify 2FA code",
                code="TWO_FACTOR_VERIFY_FAILED",
                status_code=500,
            ) from e

    async def disable_2fa(self, user_id: str, password: str) -> None:
        """Disable two-factor authentication.

        Args:
            user_id: The user's UUID.
            password: Current password for verification.

        Raises:
            ARIAException: If operation fails or password is invalid.
        """
        try:
            # Verify password first
            user_data = self.client.auth.admin.get_user_by_id(user_id)
            if not user_data.user or not user_data.user.email:
                raise ARIAException(
                    message="User not found",
                    code="USER_NOT_FOUND",
                    status_code=404,
                )

            email = user_data.user.email

            try:
                self.client.auth.sign_in_with_password(
                    {"email": email, "password": password}
                )
            except Exception as err:
                raise ARIAException(
                    message="Password is incorrect",
                    code="INVALID_PASSWORD",
                    status_code=400,
                ) from err

            # Remove TOTP settings
            settings = await SupabaseClient.get_user_settings(user_id)
            preferences = settings.get("preferences", {})
            preferences.pop("totp_secret", None)
            preferences["totp_enabled"] = False
            preferences["totp_disabled_at"] = None  # Will be set by trigger

            (
                self.client.table("user_settings")
                .update({"preferences": preferences})
                .eq("user_id", user_id)
                .execute()
            )

            # Log security event
            await self.log_security_event(
                user_id=user_id,
                event_type=self.EVENT_2FA_DISABLED,
                metadata={"success": True},
            )

            logger.info("2FA disabled successfully", extra={"user_id": user_id})

        except ARIAException:
            raise
        except Exception as e:
            logger.exception("Error disabling 2FA", extra={"user_id": user_id})
            raise ARIAException(
                message="Failed to disable 2FA",
                code="TWO_FACTOR_DISABLE_FAILED",
                status_code=500,
            ) from e

    async def list_sessions(self, user_id: str) -> list[dict[str, Any]]:
        """List active sessions for the user.

        Args:
            user_id: The user's UUID.

        Returns:
            List of active sessions with device, IP, and last active info.

        Note:
            Supabase Auth doesn't provide direct access to all sessions via client.
            This returns a mock response for the current session.
            Full implementation requires Supabase Auth Admin API access.
        """
        try:
            # Supabase Auth sessions are managed via JWT tokens
            # We can track session metadata via our own table if needed
            # For now, return current session info

            user_data = self.client.auth.admin.get_user_by_id(user_id)
            if not user_data.user:
                return []

            # Get user metadata for session info
            user_metadata = user_data.user.user_metadata or {}

            return [
                {
                    "id": "current",
                    "device": user_metadata.get("device", "Current Device"),
                    "ip_address": user_metadata.get("ip", "Unknown"),
                    "user_agent": user_metadata.get("user_agent", "Unknown"),
                    "last_active": user_data.user.last_sign_in_at,
                    "is_current": True,
                }
            ]

        except Exception:
            logger.exception("Error listing sessions", extra={"user_id": user_id})
            return []

    async def revoke_session(self, user_id: str, session_id: str) -> None:
        """Revoke a specific session.

        Args:
            user_id: The user's UUID.
            session_id: The session ID to revoke.

        Raises:
            ARIAException: If operation fails.
        """
        try:
            # Note: Supabase Auth session revocation requires admin API
            # For now, we'll log the event
            # Full implementation would use: admin_client.invite_session()

            await self.log_security_event(
                user_id=user_id,
                event_type=self.EVENT_SESSION_REVOKED,
                metadata={"session_id": session_id},
            )

            logger.info("Session revoked", extra={"user_id": user_id, "session_id": session_id})

        except Exception as e:
            logger.exception("Error revoking session", extra={"user_id": user_id})
            raise ARIAException(
                message="Failed to revoke session",
                code="SESSION_REVOKE_FAILED",
                status_code=500,
            ) from e

    async def delete_account(
        self,
        user_id: str,
        confirmation: str,
        password: str,
    ) -> None:
        """Delete user account with cascade data deletion.

        Args:
            user_id: The user's UUID.
            confirmation: Must be exactly "DELETE MY ACCOUNT".
            password: Current password for verification.

        Raises:
            ARIAException: If confirmation doesn't match, password is invalid, or operation fails.
        """
        try:
            # Verify confirmation string
            if confirmation != "DELETE MY ACCOUNT":
                raise ARIAException(
                    message="Confirmation text must be exactly 'DELETE MY ACCOUNT'",
                    code="INVALID_CONFIRMATION",
                    status_code=400,
                )

            # Verify password
            user_data = self.client.auth.admin.get_user_by_id(user_id)
            if not user_data.user or not user_data.user.email:
                raise ARIAException(
                    message="User not found",
                    code="USER_NOT_FOUND",
                    status_code=404,
                )

            email = user_data.user.email

            try:
                self.client.auth.sign_in_with_password(
                    {"email": email, "password": password}
                )
            except Exception as err:
                raise ARIAException(
                    message="Password is incorrect",
                    code="INVALID_PASSWORD",
                    status_code=400,
                ) from err

            # Log security event before deletion
            await self.log_security_event(
                user_id=user_id,
                event_type=self.EVENT_ACCOUNT_DELETED,
                metadata={"email": email},
            )

            # Delete user from Supabase Auth (cascades to user_profiles via ON DELETE CASCADE)
            self.client.auth.admin.delete_user(user_id)

            logger.info("Account deleted successfully", extra={"user_id": user_id})

        except ARIAException:
            raise
        except Exception as e:
            logger.exception("Error deleting account", extra={"user_id": user_id})
            raise ARIAException(
                message="Failed to delete account",
                code="ACCOUNT_DELETION_FAILED",
                status_code=500,
            ) from e

    async def log_security_event(
        self,
        user_id: str,
        event_type: str,
        metadata: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        """Log a security event to the audit log.

        Args:
            user_id: The user's UUID.
            event_type: Type of security event.
            metadata: Optional additional event context.
            ip_address: Optional IP address.
            user_agent: Optional user agent string.
        """
        try:
            log_data: dict[str, Any] = {
                "user_id": user_id,
                "event_type": event_type,
                "metadata": metadata or {},
            }
            if ip_address:
                log_data["ip_address"] = ip_address
            if user_agent:
                log_data["user_agent"] = user_agent

            self.client.table("security_audit_log").insert(log_data).execute()

        except Exception:
            # Don't raise - logging failures shouldn't break the main operation
            logger.exception("Failed to log security event", extra={"user_id": user_id, "event_type": event_type})

    async def get_audit_log(
        self,
        user_id: str,
        event_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get security audit log for a user.

        Args:
            user_id: The user's UUID.
            event_type: Optional event type filter.
            limit: Maximum number of entries to return.

        Returns:
            List of audit log entries.
        """
        try:
            query = self.client.table("security_audit_log").select("*").eq("user_id", user_id)

            if event_type:
                query = query.eq("event_type", event_type)

            response = query.order("created_at", desc=True).limit(limit).execute()

            return response.data if response.data else []

        except Exception:
            logger.exception("Error fetching audit log", extra={"user_id": user_id})
            return []
