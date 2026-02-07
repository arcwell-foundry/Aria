"""Security middleware and headers for ARIA API (US-932).

This module provides:
- SecurityHeadersMiddleware: Adds security headers to all responses
- setup_security: Convenience function to configure all security middleware
"""

import logging
from collections.abc import Awaitable, Callable

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# CSP directive configuration
CSP_DIRECTIVES = [
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline'",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data: https:",
    "connect-src 'self' https://*.supabase.co https://api.anthropic.com https://api.exa.ai https://api.stripe.com",
]

CSP_HEADER = "; ".join(CSP_DIRECTIVES)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all HTTP responses.

    Implements OWASP recommended security headers:
    - X-Frame-Options: DENY (prevent clickjacking)
    - X-Content-Type-Options: nosniff (prevent MIME sniffing)
    - X-XSS-Protection: 1; mode=block (legacy XSS protection)
    - Referrer-Policy: strict-origin-when-cross-origin
    - Permissions-Policy: Restrict sensitive browser features
    - Content-Security-Policy: Control resource loading
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Process request and add security headers to response.

        Args:
            request: Incoming HTTP request.
            call_next: Next middleware or route handler.

        Returns:
            Response with security headers added.
        """
        response = await call_next(request)

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Prevent MIME sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Legacy XSS protection (for older browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Control referrer information
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Restrict sensitive browser features
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        # Content Security Policy
        response.headers["Content-Security-Policy"] = CSP_HEADER

        return response


def setup_security(app: FastAPI) -> None:
    """Set up all security middleware for the FastAPI application.

    Args:
        app: FastAPI application instance.

    Example:
        from src.core.security import setup_security
        setup_security(app)
    """
    app.add_middleware(SecurityHeadersMiddleware)
    logger.info("Security headers middleware registered")


__all__ = [
    "SecurityHeadersMiddleware",
    "setup_security",
    "CSP_HEADER",
]
