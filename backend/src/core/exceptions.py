"""Custom exceptions for ARIA backend."""

from typing import Any


class ARIAException(Exception):
    """Base exception for all ARIA-specific errors."""

    def __init__(
        self,
        message: str,
        code: str,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize ARIA exception.

        Args:
            message: Human-readable error message.
            code: Machine-readable error code.
            status_code: HTTP status code.
            details: Additional error details.
        """
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class NotFoundError(ARIAException):
    """Resource not found error (404)."""

    def __init__(self, resource: str, resource_id: str | None = None) -> None:
        """Initialize not found error.

        Args:
            resource: Name of the resource that was not found.
            resource_id: Optional ID of the resource.
        """
        message = f"{resource} not found"
        if resource_id:
            message = f"{resource} with ID '{resource_id}' not found"
        super().__init__(
            message=message,
            code="NOT_FOUND",
            status_code=404,
            details={"resource": resource, "resource_id": resource_id},
        )


class AuthenticationError(ARIAException):
    """Authentication failed error (401)."""

    def __init__(self, message: str = "Authentication required") -> None:
        """Initialize authentication error.

        Args:
            message: Error message.
        """
        super().__init__(
            message=message,
            code="AUTHENTICATION_ERROR",
            status_code=401,
        )


class AuthorizationError(ARIAException):
    """Authorization/permission denied error (403)."""

    def __init__(self, message: str = "Permission denied") -> None:
        """Initialize authorization error.

        Args:
            message: Error message.
        """
        super().__init__(
            message=message,
            code="AUTHORIZATION_ERROR",
            status_code=403,
        )


class ValidationError(ARIAException):
    """Input validation error (400)."""

    def __init__(
        self, message: str, field: str | None = None, details: dict[str, Any] | None = None
    ) -> None:
        """Initialize validation error.

        Args:
            message: Error message.
            field: Name of the invalid field.
            details: Additional validation details.
        """
        error_details = details or {}
        if field:
            error_details["field"] = field
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            status_code=400,
            details=error_details,
        )


class ConflictError(ARIAException):
    """Resource conflict error (409)."""

    def __init__(self, message: str, resource: str | None = None) -> None:
        """Initialize conflict error.

        Args:
            message: Error message.
            resource: Name of the conflicting resource.
        """
        details = {}
        if resource:
            details["resource"] = resource
        super().__init__(
            message=message,
            code="CONFLICT",
            status_code=409,
            details=details,
        )


class DatabaseError(ARIAException):
    """Database operation error (500)."""

    def __init__(self, message: str = "A database error occurred") -> None:
        """Initialize database error.

        Args:
            message: Error message.
        """
        super().__init__(
            message=message,
            code="DATABASE_ERROR",
            status_code=500,
        )


class ExternalServiceError(ARIAException):
    """External service error (502)."""

    def __init__(self, service: str, message: str | None = None) -> None:
        """Initialize external service error.

        Args:
            service: Name of the external service.
            message: Optional error message.
        """
        error_message = message or f"Error communicating with {service}"
        super().__init__(
            message=error_message,
            code="EXTERNAL_SERVICE_ERROR",
            status_code=502,
            details={"service": service},
        )


class GraphitiConnectionError(ARIAException):
    """Neo4j/Graphiti connection error (503)."""

    def __init__(self, message: str = "Unknown error") -> None:
        """Initialize Graphiti connection error.

        Args:
            message: Error details.
        """
        super().__init__(
            message=f"Failed to connect to Neo4j: {message}",
            code="GRAPHITI_CONNECTION_ERROR",
            status_code=503,
        )
