"""Tests for AccountService security event constants (US-932 Task 6).

These tests verify that all required security event type constants
are defined in the AccountService.
"""

import pytest

from src.services.account_service import AccountService


def test_all_required_security_event_constants_exist() -> None:
    """Test that all required security event constants are defined.

    Required constants based on US-932 security hardening:
    - EVENT_LOGIN
    - EVENT_LOGIN_FAILED
    - EVENT_LOGOUT
    - EVENT_PASSWORD_CHANGE
    - EVENT_PASSWORD_RESET_REQUEST
    - EVENT_2FA_ENABLED
    - EVENT_2FA_DISABLED
    - EVENT_2FA_VERIFY_FAILED
    - EVENT_SESSION_REVOKED
    - EVENT_ACCOUNT_DELETED
    - EVENT_PROFILE_UPDATED
    - EVENT_ROLE_CHANGED
    - EVENT_DATA_EXPORT
    - EVENT_DATA_DELETION
    """
    required_constants = {
        "EVENT_LOGIN": "login",
        "EVENT_LOGIN_FAILED": "login_failed",
        "EVENT_LOGOUT": "logout",
        "EVENT_PASSWORD_CHANGE": "password_change",
        "EVENT_PASSWORD_RESET_REQUEST": "password_reset_request",
        "EVENT_2FA_ENABLED": "2fa_enabled",
        "EVENT_2FA_DISABLED": "2fa_disabled",
        "EVENT_2FA_VERIFY_FAILED": "2fa_verify_failed",
        "EVENT_SESSION_REVOKED": "session_revoked",
        "EVENT_ACCOUNT_DELETED": "account_deleted",
        "EVENT_PROFILE_UPDATED": "profile_updated",
        "EVENT_ROLE_CHANGED": "role_changed",
        "EVENT_DATA_EXPORT": "data_export",
        "EVENT_DATA_DELETION": "data_deletion",
    }

    for constant_name, expected_value in required_constants.items():
        assert hasattr(AccountService, constant_name), (
            f"AccountService must define {constant_name} constant"
        )
        actual_value = getattr(AccountService, constant_name)
        assert actual_value == expected_value, (
            f"{constant_name} should be '{expected_value}', got '{actual_value}'"
        )


def test_security_event_constants_are_strings() -> None:
    """Test that all security event constants are strings."""
    event_constant_names = [
        "EVENT_LOGIN",
        "EVENT_LOGIN_FAILED",
        "EVENT_LOGOUT",
        "EVENT_PASSWORD_CHANGE",
        "EVENT_PASSWORD_RESET_REQUEST",
        "EVENT_2FA_ENABLED",
        "EVENT_2FA_DISABLED",
        "EVENT_2FA_VERIFY_FAILED",
        "EVENT_SESSION_REVOKED",
        "EVENT_ACCOUNT_DELETED",
        "EVENT_PROFILE_UPDATED",
        "EVENT_ROLE_CHANGED",
        "EVENT_DATA_EXPORT",
        "EVENT_DATA_DELETION",
    ]

    for constant_name in event_constant_names:
        constant_value = getattr(AccountService, constant_name)
        assert isinstance(constant_value, str), (
            f"{constant_name} should be a string, got {type(constant_value).__name__}"
        )
        assert len(constant_value) > 0, f"{constant_name} should not be empty"


def test_event_constant_values_are_snake_case() -> None:
    """Test that event constant values follow snake_case convention."""
    event_constant_names = [
        "EVENT_LOGIN",
        "EVENT_LOGIN_FAILED",
        "EVENT_LOGOUT",
        "EVENT_PASSWORD_CHANGE",
        "EVENT_PASSWORD_RESET_REQUEST",
        "EVENT_2FA_ENABLED",
        "EVENT_2FA_DISABLED",
        "EVENT_2FA_VERIFY_FAILED",
        "EVENT_SESSION_REVOKED",
        "EVENT_ACCOUNT_DELETED",
        "EVENT_PROFILE_UPDATED",
        "EVENT_ROLE_CHANGED",
        "EVENT_DATA_EXPORT",
        "EVENT_DATA_DELETION",
    ]

    for constant_name in event_constant_names:
        constant_value = getattr(AccountService, constant_name)
        # All event values should be lowercase with underscores
        assert constant_value == constant_value.lower(), (
            f"{constant_name} value should be lowercase"
        )
        # Spaces are not allowed
        assert " " not in constant_value, f"{constant_name} value should not contain spaces"


def test_security_event_constants_are_unique() -> None:
    """Test that all security event constants have unique values."""
    event_constant_names = [
        "EVENT_LOGIN",
        "EVENT_LOGIN_FAILED",
        "EVENT_LOGOUT",
        "EVENT_PASSWORD_CHANGE",
        "EVENT_PASSWORD_RESET_REQUEST",
        "EVENT_2FA_ENABLED",
        "EVENT_2FA_DISABLED",
        "EVENT_2FA_VERIFY_FAILED",
        "EVENT_SESSION_REVOKED",
        "EVENT_ACCOUNT_DELETED",
        "EVENT_PROFILE_UPDATED",
        "EVENT_ROLE_CHANGED",
        "EVENT_DATA_EXPORT",
        "EVENT_DATA_DELETION",
    ]

    values = [getattr(AccountService, name) for name in event_constant_names]
    unique_values = set(values)

    assert len(values) == len(unique_values), (
        f"Security event constants must have unique values. "
        f"Found {len(values)} constants but only {len(unique_values)} unique values."
    )
