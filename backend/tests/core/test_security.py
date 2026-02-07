"""Tests for security middleware and headers (US-932)."""

from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


def test_security_headers_present_on_all_responses():
    """Test that all responses include required security headers."""
    response = client.get("/health")

    assert response.status_code == 200
    assert "X-Frame-Options" in response.headers
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "X-Content-Type-Options" in response.headers
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "X-XSS-Protection" in response.headers
    assert response.headers["X-XSS-Protection"] == "1; mode=block"
    assert "Referrer-Policy" in response.headers
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "Permissions-Policy" in response.headers


def test_csp_header_correctly_formatted():
    """Test that Content-Security-Policy header is correctly formatted."""
    response = client.get("/health")

    assert "Content-Security-Policy" in response.headers
    csp = response.headers["Content-Security-Policy"]

    # Verify key CSP directives
    assert "default-src 'self'" in csp
    assert "script-src 'self' 'unsafe-inline'" in csp
    assert "style-src 'self' 'unsafe-inline'" in csp
    assert "font-src 'self' https://fonts.gstatic.com" in csp
    assert "img-src 'self' data: https:" in csp
    assert "connect-src 'self'" in csp
    assert "https://*.supabase.co" in csp
    assert "https://api.anthropic.com" in csp
    assert "https://api.exa.ai" in csp
    assert "https://api.stripe.com" in csp


def test_permissions_policy_restricts_sensitive_features():
    """Test that Permissions-Policy restricts camera, microphone, geolocation."""
    response = client.get("/health")

    permissions = response.headers["Permissions-Policy"]
    assert "camera=()" in permissions
    assert "microphone=()" in permissions
    assert "geolocation=()" in permissions


def test_trusted_host_middleware_is_registered():
    """Test that TrustedHostMiddleware is registered."""
    middleware_classes = [m.cls for m in app.user_middleware]
    assert TrustedHostMiddleware in middleware_classes
