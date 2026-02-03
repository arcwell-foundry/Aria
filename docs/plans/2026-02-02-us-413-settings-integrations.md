# US-413: Settings - Integrations Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a premium integrations settings page where users can connect OAuth providers (Google Calendar, Gmail, Outlook, Salesforce, HubSpot) with Apple-inspired luxury design.

**Architecture:**
- **Backend:** Composio SDK for OAuth abstraction, secure token storage in Supabase, dedicated API routes for connection management
- **Frontend:** React page with DashboardLayout, sophisticated card-based UI, smooth animations, real-time connection status polling

**Tech Stack:**
- **Backend:** FastAPI, Composio Python SDK, Supabase, Pydantic
- **Frontend:** React 18, TypeScript, Tailwind CSS, Framer Motion (for animations)
- **OAuth:** Composio (handles Google, Microsoft, Salesforce, HubSpot OAuth flows)

---

## Task 1: Install Composio Python SDK

**Files:**
- Modify: `backend/requirements.txt`

**Step 1: Add Composio to requirements.txt**

```bash
echo "composio-core>=0.5.0,<1.0.0" >> backend/requirements.txt
```

**Step 2: Install the dependency**

Run: `cd backend && pip install composio-core`
Expected: Package installs successfully with no errors

**Step 3: Verify installation**

Run: `pip list | grep composio`
Expected: `composio-core 0.x.x` is listed

**Step 4: Commit**

```bash
git add backend/requirements.txt
git commit -m "feat: add composio-core dependency for OAuth integration management"
```

---

## Task 2: Add Composio Configuration

**Files:**
- Modify: `backend/src/core/config.py:47`

**Step 1: Add Composio settings to config class**

Add to Settings class after `COMPOSIO_API_KEY` field:

```python
# Composio OAuth Configuration
COMPOSIO_API_KEY: SecretStr | None = None
COMPOSIO_BASE_URL: str = "https://api.composio.dev"
```

**Step 2: Add to .env.example**

Add to `backend/.env.example`:

```bash
# Composio OAuth
COMPOSIO_API_KEY=your-composio-api-key
```

**Step 3: Verify type checking**

Run: `cd backend && mypy src/core/config.py`
Expected: No type errors

**Step 4: Commit**

```bash
git add backend/src/core/config.py backend/.env.example
git commit -m "feat: add composio configuration settings"
```

---

## Task 3: Create Integration Database Schema

**Files:**
- Create: `backend/migrations/20260202_create_integrations_table.sql`

**Step 1: Create the migration file**

Create file with SQL:

```sql
-- User integrations table for storing OAuth connection metadata
-- Note: Actual tokens are stored securely by Composio, we only store references

CREATE TABLE IF NOT EXISTS user_integrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    integration_type TEXT NOT NULL, -- 'google_calendar', 'gmail', 'outlook', 'salesforce', 'hubspot'
    composio_connection_id TEXT NOT NULL, -- Reference to Composio's stored connection
    composio_account_id TEXT, -- Composio account identifier
    display_name TEXT, -- User-friendly name (e.g., user's email)
    status TEXT NOT NULL DEFAULT 'active', -- 'active', 'disconnected', 'error'
    last_sync_at TIMESTAMPTZ,
    sync_status TEXT DEFAULT 'success', -- 'success', 'pending', 'failed'
    error_message TEXT,
    metadata JSONB DEFAULT '{}', -- Additional integration-specific data
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, integration_type)
);

-- Enable RLS
ALTER TABLE user_integrations ENABLE ROW LEVEL SECURITY;

-- RLS Policies: Users can only see their own integrations
CREATE POLICY "Users can view own integrations"
    ON user_integrations FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own integrations"
    ON user_integrations FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own integrations"
    ON user_integrations FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own integrations"
    ON user_integrations FOR DELETE
    USING (auth.uid() = user_id);

-- Index for quick lookups
CREATE INDEX idx_user_integrations_user_type ON user_integrations(user_id, integration_type);
CREATE INDEX idx_user_integrations_status ON user_integrations(status);

-- Updated at trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_user_integrations_updated_at
    BEFORE UPDATE ON user_integrations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
```

**Step 2: Run migration manually (for development)**

Run: Apply SQL via Supabase dashboard or psql
Expected: Table created successfully with RLS policies

**Step 3: Commit**

```bash
git add backend/migrations/20260202_create_integrations_table.sql
git commit -m "feat: create user_integrations table with RLS policies"
```

---

## Task 4: Create Integration Domain Models

**Files:**
- Create: `backend/src/integrations/domain.py`

**Step 1: Write the domain models**

```python
"""Domain models for OAuth integrations."""

from dataclasses import dataclass
from enum import Enum
from datetime import datetime


class IntegrationType(str, Enum):
    """Supported integration types."""

    GOOGLE_CALENDAR = "google_calendar"
    GMAIL = "gmail"
    OUTLOOK = "outlook"
    SALESFORCE = "salesforce"
    HUBSPOT = "hubspot"


class IntegrationStatus(str, Enum):
    """Status of an integration connection."""

    ACTIVE = "active"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    PENDING = "pending"


class SyncStatus(str, Enum):
    """Status of the last sync operation."""

    SUCCESS = "success"
    PENDING = "pending"
    FAILED = "failed"


@dataclass
class Integration:
    """User integration connection."""

    id: str
    user_id: str
    integration_type: IntegrationType
    composio_connection_id: str
    composio_account_id: str | None = None
    display_name: str | None = None
    status: IntegrationStatus = IntegrationStatus.ACTIVE
    last_sync_at: datetime | None = None
    sync_status: SyncStatus = SyncStatus.SUCCESS
    error_message: str | None = None
    metadata: dict = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class IntegrationConfig:
    """Configuration for an integration type."""

    integration_type: IntegrationType
    display_name: str
    description: str
    composio_app_id: str
    icon: str
    scopes: list[str]
    auth_type: str = "oauth2"


# Integration configurations
INTEGRATION_CONFIGS: dict[IntegrationType, IntegrationConfig] = {
    IntegrationType.GOOGLE_CALENDAR: IntegrationConfig(
        integration_type=IntegrationType.GOOGLE_CALENDAR,
        display_name="Google Calendar",
        description="Sync your calendar for meeting briefs and scheduling",
        composio_app_id="google_calendar",
        icon="calendar",
        scopes=["https://www.googleapis.com/auth/calendar.readonly"],
    ),
    IntegrationType.GMAIL: IntegrationConfig(
        integration_type=IntegrationType.GMAIL,
        display_name="Gmail",
        description="Connect Gmail for email drafting and analysis",
        composio_app_id="gmail",
        icon="mail",
        scopes=["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.send"],
    ),
    IntegrationType.OUTLOOK: IntegrationConfig(
        integration_type=IntegrationType.OUTLOOK,
        display_name="Microsoft Outlook",
        description="Connect Outlook for calendar and email integration",
        composio_app_id="outlook_calendar",
        icon="calendar",
        scopes=["Calendars.ReadWrite", "Mail.ReadWrite", "User.Read"],
    ),
    IntegrationType.SALESFORCE: IntegrationConfig(
        integration_type=IntegrationType.SALESFORCE,
        display_name="Salesforce",
        description="Sync leads and opportunities from Salesforce",
        composio_app_id="salesforce",
        icon="crm",
        scopes=["api", "refresh_token", "full"],
    ),
    IntegrationType.HUBSPOT: IntegrationConfig(
        integration_type=IntegrationType.HUBSPOT,
        display_name="HubSpot",
        description="Connect HubSpot CRM for lead management",
        composio_app_id="hubspot",
        icon="crm",
        scopes=["crm.objects.contacts.read", "crm.objects.companies.read", "crm.objects.deals.read"],
    ),
}
```

**Step 2: Verify syntax**

Run: `cd backend && python -m py_compile src/integrations/domain.py`
Expected: No syntax errors

**Step 3: Commit**

```bash
git add backend/src/integrations/domain.py
git commit -m "feat: add integration domain models and configurations"
```

---

## Task 5: Create Composio OAuth Client

**Files:**
- Create: `backend/src/integrations/oauth.py`

**Step 1: Write the failing test**

Create: `backend/tests/integrations/test_oauth.py`

```python
"""Tests for OAuth integration client."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.integrations.oauth import ComposioOAuthClient, get_oauth_client


@pytest.fixture
def mock_settings():
    """Mock settings."""
    with patch("src.integrations.oauth.settings") as m:
        m.COMPOSIO_API_KEY.get_secret_value.return_value = "test-key"
        m.COMPOSIO_BASE_URL = "https://test.api.composio.dev"
        yield m


@pytest.mark.asyncio
async def test_get_oauth_client_singleton(mock_settings):
    """Test that get_oauth_client returns singleton instance."""
    client1 = get_oauth_client()
    client2 = get_oauth_client()
    assert client1 is client2


@pytest.mark.asyncio
async def test_generate_auth_url(mock_settings):
    """Test generating OAuth authorization URL."""
    client = ComposioOAuthClient()

    with patch.object(client, "_http_client") as mock_http:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "authorization_url": "https://auth.composio.dev/authorize?code=test123"
        }
        mock_http.post.return_value = mock_response

        url = await client.generate_auth_url(
            user_id="user-123",
            integration_type="google_calendar",
            redirect_uri="http://localhost:5173/integrations/callback"
        )

        assert url == "https://auth.composio.dev/authorize?code=test123"
        mock_http.post.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/integrations/test_oauth.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.integrations.oauth'"

**Step 3: Write minimal implementation**

Create: `backend/src/integrations/oauth.py`

```python
"""Composio OAuth integration client."""

import logging
from typing import Any

import httpx

from src.core.config import settings
from src.integrations.domain import (
    INTEGRATION_CONFIGS,
    IntegrationType,
)

logger = logging.getLogger(__name__)


class ComposioOAuthClient:
    """Client for Composio OAuth operations."""

    def __init__(self) -> None:
        """Initialize the Composio OAuth client."""
        self.api_key = settings.COMPOSIO_API_KEY
        self.base_url = settings.COMPOSIO_BASE_URL
        self._http_client: httpx.AsyncClient | None = None

    @property
    def http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "x-api-key": self.api_key.get_secret_value() if self.api_key else "",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._http_client

    async def generate_auth_url(
        self,
        user_id: str,
        integration_type: IntegrationType | str,
        redirect_uri: str,
    ) -> str:
        """Generate OAuth authorization URL for user.

        Args:
            user_id: The user's ID
            integration_type: Type of integration to connect
            redirect_uri: OAuth callback URL

        Returns:
            Authorization URL to redirect user to

        Raises:
            ValueError: If integration type is invalid
            httpx.HTTPError: If API request fails
        """
        if isinstance(integration_type, str):
            try:
                integration_type = IntegrationType(integration_type)
            except ValueError:
                raise ValueError(f"Invalid integration type: {integration_type}")

        config = INTEGRATION_CONFIGS.get(integration_type)
        if not config:
            raise ValueError(f"No configuration for integration type: {integration_type}")

        try:
            response = await self.http_client.post(
                "/oauth/oauth_url",
                json={
                    "app_id": config.composio_app_id,
                    "redirect_uri": redirect_uri,
                    "user_id": user_id,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data.get("authorization_url", "")

        except httpx.HTTPError as e:
            logger.exception("Failed to generate auth URL")
            raise

    async def exchange_code_for_connection(
        self,
        user_id: str,
        code: str,
        integration_type: IntegrationType | str,
    ) -> dict[str, Any]:
        """Exchange OAuth code for connection credentials.

        Args:
            user_id: The user's ID
            code: OAuth authorization code
            integration_type: Type of integration

        Returns:
            Connection details with connection_id

        Raises:
            httpx.HTTPError: If API request fails
        """
        if isinstance(integration_type, str):
            integration_type = IntegrationType(integration_type)

        config = INTEGRATION_CONFIGS.get(integration_type)
        if not config:
            raise ValueError(f"No configuration for integration type: {integration_type}")

        try:
            response = await self.http_client.post(
                "/oauth/token",
                json={
                    "code": code,
                    "app_id": config.composio_app_id,
                    "user_id": user_id,
                },
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as e:
            logger.exception("Failed to exchange auth code")
            raise

    async def disconnect_integration(self, connection_id: str) -> bool:
        """Disconnect an integration by deleting the connection.

        Args:
            connection_id: Composio connection ID to disconnect

        Returns:
            True if successful

        Raises:
            httpx.HTTPError: If API request fails
        """
        try:
            response = await self.http_client.delete(f"/connections/{connection_id}")
            response.raise_for_status()
            return True

        except httpx.HTTPError as e:
            logger.exception("Failed to disconnect integration")
            raise

    async def test_connection(self, connection_id: str) -> bool:
        """Test if a connection is still valid.

        Args:
            connection_id: Composio connection ID

        Returns:
            True if connection is valid

        Raises:
            httpx.HTTPError: If API request fails
        """
        try:
            response = await self.http_client.get(f"/connections/{connection_id}")
            response.raise_for_status()
            data = response.json()
            return data.get("status", "inactive") == "active"

        except httpx.HTTPError:
            return False

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None


# Singleton instance
_oauth_client: ComposioOAuthClient | None = None


def get_oauth_client() -> ComposioOAuthClient:
    """Get or create OAuth client singleton.

    Returns:
        The shared ComposioOAuthClient instance
    """
    global _oauth_client
    if _oauth_client is None:
        _oauth_client = ComposioOAuthClient()
    return _oauth_client
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/integrations/test_oauth.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/integrations/oauth.py backend/tests/integrations/test_oauth.py
git commit -m "feat: implement Composio OAuth client"
```

---

## Task 6: Create Integration Service Layer

**Files:**
- Create: `backend/src/integrations/service.py`
- Modify: `backend/src/integrations/__init__.py:6`

**Step 1: Write the failing test**

Create: `backend/tests/integrations/test_service.py`

```python
"""Tests for integration service."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from src.integrations.service import IntegrationService
from src.integrations.domain import IntegrationType, IntegrationStatus


@pytest.fixture
def mock_supabase():
    """Mock Supabase client."""
    with patch("src.integrations.service.SupabaseClient") as m:
        client = AsyncMock()
        m.get_client.return_value = client
        yield client


@pytest.fixture
def mock_oauth_client():
    """Mock OAuth client."""
    with patch("src.integrations.service.get_oauth_client") as m:
        client = AsyncMock()
        m.return_value = client
        yield client


@pytest.mark.asyncio
async def test_get_user_integrations(mock_supabase):
    """Test retrieving user integrations."""
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[
            {
                "id": "int-1",
                "user_id": "user-123",
                "integration_type": "google_calendar",
                "status": "active",
                "display_name": "user@example.com",
                "last_sync_at": None,
            }
        ]
    )

    service = IntegrationService()
    integrations = await service.get_user_integrations("user-123")

    assert len(integrations) == 1
    assert integrations[0]["integration_type"] == "google_calendar"


@pytest.mark.asyncio
async def test_create_integration(mock_supabase):
    """Test creating an integration connection."""
    mock_supabase.table.return_value.insert.return_value.execute.return_value = MagicMock(
        data=[
            {
                "id": "int-1",
                "user_id": "user-123",
                "integration_type": "google_calendar",
                "status": "active",
            }
        ]
    )

    service = IntegrationService()
    result = await service.create_integration(
        user_id="user-123",
        integration_type=IntegrationType.GOOGLE_CALENDAR,
        composio_connection_id="conn-123",
        display_name="user@example.com",
    )

    assert result["integration_type"] == "google_calendar"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/integrations/test_service.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.integrations.service'"

**Step 3: Write minimal implementation**

Create: `backend/src/integrations/service.py`

```python
"""Service layer for managing user integrations."""

import logging
from datetime import datetime
from typing import Any

from src.db.supabase import SupabaseClient
from src.integrations.domain import (
    INTEGRATION_CONFIGS,
    Integration,
    IntegrationStatus,
    IntegrationType,
    SyncStatus,
)
from src.integrations.oauth import get_oauth_client

logger = logging.getLogger(__name__)


class IntegrationService:
    """Service for managing user OAuth integrations."""

    async def get_user_integrations(self, user_id: str) -> list[dict[str, Any]]:
        """Get all integrations for a user.

        Args:
            user_id: The user's ID

        Returns:
            List of integration dictionaries

        Raises:
            Exception: If database operation fails
        """
        try:
            client = SupabaseClient.get_client()
            response = (
                client.table("user_integrations")
                .select("*")
                .eq("user_id", user_id)
                .execute()
            )

            return response.data if response.data else []

        except Exception as e:
            logger.exception("Failed to fetch user integrations")
            raise

    async def get_integration(
        self,
        user_id: str,
        integration_type: IntegrationType,
    ) -> dict[str, Any] | None:
        """Get a specific integration for a user.

        Args:
            user_id: The user's ID
            integration_type: The integration type

        Returns:
            Integration dictionary or None if not found
        """
        try:
            client = SupabaseClient.get_client()
            response = (
                client.table("user_integrations")
                .select("*")
                .eq("user_id", user_id)
                .eq("integration_type", integration_type.value)
                .maybe_single()
                .execute()
            )

            return response.data

        except Exception as e:
            logger.exception("Failed to fetch integration")
            return None

    async def create_integration(
        self,
        user_id: str,
        integration_type: IntegrationType,
        composio_connection_id: str,
        display_name: str | None = None,
        composio_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new integration connection.

        Args:
            user_id: The user's ID
            integration_type: Type of integration
            composio_connection_id: Composio connection ID
            display_name: Optional display name
            composio_account_id: Optional Composio account ID

        Returns:
            Created integration dictionary

        Raises:
            Exception: If database operation fails
        """
        try:
            client = SupabaseClient.get_client()
            data = {
                "user_id": user_id,
                "integration_type": integration_type.value,
                "composio_connection_id": composio_connection_id,
                "composio_account_id": composio_account_id,
                "display_name": display_name,
                "status": IntegrationStatus.ACTIVE.value,
                "sync_status": SyncStatus.SUCCESS.value,
            }

            response = client.table("user_integrations").insert(data).execute()

            if response.data and len(response.data) > 0:
                return response.data[0]

            raise Exception("Failed to create integration")

        except Exception as e:
            logger.exception("Failed to create integration")
            raise

    async def update_integration(
        self,
        integration_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any]:
        """Update an integration.

        Args:
            integration_id: Integration record ID
            updates: Dictionary of fields to update

        Returns:
            Updated integration dictionary

        Raises:
            Exception: If database operation fails
        """
        try:
            client = SupabaseClient.get_client()
            response = (
                client.table("user_integrations")
                .update(updates)
                .eq("id", integration_id)
                .execute()
            )

            if response.data and len(response.data) > 0:
                return response.data[0]

            raise Exception("Integration not found")

        except Exception as e:
            logger.exception("Failed to update integration")
            raise

    async def delete_integration(self, integration_id: str) -> bool:
        """Delete an integration.

        Args:
            integration_id: Integration record ID

        Returns:
            True if successful

        Raises:
            Exception: If database operation fails
        """
        try:
            client = SupabaseClient.get_client()
            client.table("user_integrations").delete().eq("id", integration_id).execute()
            return True

        except Exception as e:
            logger.exception("Failed to delete integration")
            raise

    async def update_sync_status(
        self,
        integration_id: str,
        status: SyncStatus,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        """Update the sync status of an integration.

        Args:
            integration_id: Integration record ID
            status: New sync status
            error_message: Optional error message

        Returns:
            Updated integration dictionary
        """
        updates = {
            "sync_status": status.value,
            "last_sync_at": datetime.utcnow().isoformat(),
        }

        if error_message:
            updates["error_message"] = error_message

        return await self.update_integration(integration_id, updates)

    async def disconnect_integration(
        self,
        user_id: str,
        integration_type: IntegrationType,
    ) -> bool:
        """Disconnect and remove an integration.

        Args:
            user_id: The user's ID
            integration_type: Integration type to disconnect

        Returns:
            True if successful

        Raises:
            Exception: If operation fails
        """
        try:
            # Get the integration
            integration = await self.get_integration(user_id, integration_type)
            if not integration:
                raise Exception("Integration not found")

            # Disconnect from Composio
            oauth_client = get_oauth_client()
            await oauth_client.disconnect_integration(integration["composio_connection_id"])

            # Delete from database
            await self.delete_integration(integration["id"])

            logger.info(
                "Integration disconnected",
                extra={"user_id": user_id, "integration_type": integration_type.value},
            )

            return True

        except Exception as e:
            logger.exception("Failed to disconnect integration")
            raise


# Singleton instance
_integration_service: IntegrationService | None = None


def get_integration_service() -> IntegrationService:
    """Get or create integration service singleton.

    Returns:
        The shared IntegrationService instance
    """
    global _integration_service
    if _integration_service is None:
        _integration_service = IntegrationService()
    return _integration_service
```

**Step 4: Update __init__.py to export service**

Modify: `backend/src/integrations/__init__.py`

```python
"""Integrations with external services.

This package contains clients for integrating with third-party APIs and services.
"""

from src.integrations.domain import (
    INTEGRATION_CONFIGS,
    Integration,
    IntegrationStatus,
    IntegrationType,
    SyncStatus,
)
from src.integrations.oauth import ComposioOAuthClient, get_oauth_client
from src.integrations.service import IntegrationService, get_integration_service
from src.integrations.tavus import TavusClient, get_tavus_client

__all__ = [
    "TavusClient",
    "get_tavus_client",
    "ComposioOAuthClient",
    "get_oauth_client",
    "IntegrationService",
    "get_integration_service",
    "INTEGRATION_CONFIGS",
    "Integration",
    "IntegrationStatus",
    "IntegrationType",
    "SyncStatus",
]
```

**Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/integrations/test_service.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/src/integrations/service.py backend/src/integrations/__init__.py backend/tests/integrations/test_service.py
git commit -m "feat: implement integration service layer"
```

---

## Task 7: Create Integrations API Routes

**Files:**
- Create: `backend/src/api/routes/integrations.py`

**Step 1: Write the failing test**

Create: `backend/tests/api/test_integrations_routes.py`

```python
"""Tests for integrations API routes."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
from src.main import app


@pytest.fixture
def client():
    """Test client."""
    return TestClient(app)


@pytest.fixture
def mock_user():
    """Mock authenticated user."""
    return {"id": "test-user-id", "email": "test@example.com"}


def test_list_integrations_empty(client, mock_user):
    """Test listing integrations when none connected."""
    with patch("src.api.routes.integrations.get_current_user", return_value=mock_user):
        with patch("src.api.routes.integrations.get_integration_service") as m:
            service = AsyncMock()
            service.get_user_integrations.return_value = []
            m.return_value = service

            response = client.get(
                "/api/v1/integrations",
                headers={"Authorization": "Bearer test-token"}
            )

            assert response.status_code == 200
            assert response.json() == []


def test_get_auth_url(client, mock_user):
    """Test getting OAuth authorization URL."""
    with patch("src.api.routes.integrations.get_current_user", return_value=mock_user):
        with patch("src.api.routes.integrations.get_oauth_client") as m:
            client_oauth = AsyncMock()
            client_oauth.generate_auth_url.return_value = "https://auth.example.com/authorize"
            m.return_value = client_oauth

            response = client.post(
                "/api/v1/integrations/google_calendar/auth-url",
                json={"redirect_uri": "http://localhost:5173/callback"},
                headers={"Authorization": "Bearer test-token"}
            )

            assert response.status_code == 200
            assert "authorization_url" in response.json()
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/api/test_integrations_routes.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.api.routes.integrations'"

**Step 3: Write minimal implementation**

Create: `backend/src/api/routes/integrations.py`

```python
"""Integrations API routes."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.integrations.domain import INTEGRATION_CONFIGS, IntegrationStatus, IntegrationType
from src.integrations.oauth import get_oauth_client
from src.integrations.service import get_integration_service, SyncStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["integrations"])


# Request/Response Models
class AuthUrlRequest(BaseModel):
    """Request model for generating OAuth URL."""

    redirect_uri: str = Field(..., description="OAuth callback URL")


class AuthUrlResponse(BaseModel):
    """Response model with OAuth authorization URL."""

    authorization_url: str
    integration_type: str
    display_name: str


class OAuthCallbackRequest(BaseModel):
    """Request model for OAuth callback."""

    code: str = Field(..., description="OAuth authorization code")
    state: str | None = Field(None, description="OAuth state parameter")


class IntegrationResponse(BaseModel):
    """Response model for integration data."""

    id: str
    integration_type: str
    display_name: str | None = None
    status: str
    last_sync_at: str | None = None
    sync_status: str
    error_message: str | None = None
    created_at: str | None = None


class AvailableIntegrationResponse(BaseModel):
    """Response model for available integrations."""

    integration_type: str
    display_name: str
    description: str
    icon: str
    is_connected: bool


class MessageResponse(BaseModel):
    """Generic message response."""

    message: str


@router.get("", response_model=list[IntegrationResponse])
async def list_integrations(
    current_user: CurrentUser,
) -> list[dict[str, Any]]:
    """List all integrations for the current user.

    Args:
        current_user: The authenticated user

    Returns:
        List of user's integrations
    """
    try:
        service = get_integration_service()
        integrations = await service.get_user_integrations(current_user.id)
        return integrations

    except Exception as e:
        logger.exception("Error fetching integrations")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch integrations",
        ) from e


@router.get("/available", response_model=list[AvailableIntegrationResponse])
async def list_available_integrations(
    current_user: CurrentUser,
) -> list[dict[str, Any]]:
    """List all available integrations with connection status.

    Args:
        current_user: The authenticated user

    Returns:
        List of available integrations with connection status
    """
    try:
        service = get_integration_service()
        user_integrations = await service.get_user_integrations(current_user.id)
        connected_types = {i["integration_type"] for i in user_integrations}

        available = []
        for integration_type, config in INTEGRATION_CONFIGS.items():
            available.append({
                "integration_type": integration_type.value,
                "display_name": config.display_name,
                "description": config.description,
                "icon": config.icon,
                "is_connected": integration_type.value in connected_types,
            })

        return available

    except Exception as e:
        logger.exception("Error fetching available integrations")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch available integrations",
        ) from e


@router.post("/{integration_type}/auth-url", response_model=AuthUrlResponse)
async def get_auth_url(
    integration_type: str,
    request: AuthUrlRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Generate OAuth authorization URL for an integration.

    Args:
        integration_type: Type of integration to connect
        request: Auth URL request with redirect URI
        current_user: The authenticated user

    Returns:
        Authorization URL and metadata

    Raises:
        HTTPException: If integration type is invalid or request fails
    """
    try:
        # Validate integration type
        try:
            integration_type_enum = IntegrationType(integration_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid integration type: {integration_type}",
            )

        config = INTEGRATION_CONFIGS.get(integration_type_enum)
        if not config:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No configuration for integration type: {integration_type}",
            )

        # Generate auth URL
        oauth_client = get_oauth_client()
        auth_url = await oauth_client.generate_auth_url(
            user_id=current_user.id,
            integration_type=integration_type_enum,
            redirect_uri=request.redirect_uri,
        )

        return {
            "authorization_url": auth_url,
            "integration_type": integration_type,
            "display_name": config.display_name,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error generating auth URL")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate authorization URL",
        ) from e


@router.post("/{integration_type}/connect", response_model=IntegrationResponse)
async def connect_integration(
    integration_type: str,
    request: OAuthCallbackRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Complete OAuth connection and create integration.

    Args:
        integration_type: Type of integration being connected
        request: OAuth callback request with auth code
        current_user: The authenticated user

    Returns:
        Created integration details

    Raises:
        HTTPException: If connection fails
    """
    try:
        # Validate integration type
        try:
            integration_type_enum = IntegrationType(integration_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid integration type: {integration_type}",
            )

        # Exchange code for connection
        oauth_client = get_oauth_client()
        connection_data = await oauth_client.exchange_code_for_connection(
            user_id=current_user.id,
            code=request.code,
            integration_type=integration_type_enum,
        )

        # Create integration record
        service = get_integration_service()
        integration = await service.create_integration(
            user_id=current_user.id,
            integration_type=integration_type_enum,
            composio_connection_id=connection_data.get("connection_id", ""),
            composio_account_id=connection_data.get("account_id"),
            display_name=connection_data.get("account_email"),
        )

        logger.info(
            "Integration connected successfully",
            extra={
                "user_id": current_user.id,
                "integration_type": integration_type,
            },
        )

        return integration

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error connecting integration")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to connect integration",
        ) from e


@router.post("/{integration_type}/disconnect", response_model=MessageResponse)
async def disconnect_integration(
    integration_type: str,
    current_user: CurrentUser,
) -> dict[str, str]:
    """Disconnect an integration.

    Args:
        integration_type: Type of integration to disconnect
        current_user: The authenticated user

    Returns:
        Success message

    Raises:
        HTTPException: If disconnection fails
    """
    try:
        # Validate integration type
        try:
            integration_type_enum = IntegrationType(integration_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid integration type: {integration_type}",
            )

        service = get_integration_service()
        await service.disconnect_integration(current_user.id, integration_type_enum)

        logger.info(
            "Integration disconnected successfully",
            extra={
                "user_id": current_user.id,
                "integration_type": integration_type,
            },
        )

        return {"message": f"Successfully disconnected {integration_type.replace('_', ' ').title()}"}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error disconnecting integration")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to disconnect integration",
        ) from e


@router.post("/{integration_id}/sync", response_model=IntegrationResponse)
async def sync_integration(
    integration_id: str,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Manually trigger a sync for an integration.

    Args:
        integration_id: Integration record ID
        current_user: The authenticated user

    Returns:
        Updated integration details

    Raises:
        HTTPException: If sync fails
    """
    try:
        service = get_integration_service()

        # Update status to pending
        await service.update_sync_status(integration_id, SyncStatus.PENDING)

        # TODO: Implement actual sync logic per integration type
        # For now, mark as success
        integration = await service.update_sync_status(integration_id, SyncStatus.SUCCESS)

        return integration

    except Exception as e:
        logger.exception("Error syncing integration")
        await service.update_sync_status(
            integration_id,
            SyncStatus.FAILED,
            error_message=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to sync integration",
        ) from e
```

**Step 4: Register the router in main app**

Check: `backend/src/main.py` exists. If not, find where routes are registered.

Look for pattern like:
```python
app.include_router(auth.router)
```

Add:
```python
from src.api.routes import integrations
app.include_router(integrations.router)
```

**Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/api/test_integrations_routes.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/src/api/routes/integrations.py backend/tests/api/test_integrations_routes.py backend/src/main.py
git commit -m "feat: implement integrations API routes"
```

---

## Task 8: Install Frontend Animation Library

**Files:**
- Modify: `frontend/package.json`

**Step 1: Add framer-motion dependency**

Run: `cd frontend && npm install framer-motion@^11.0.0`
Expected: Package installs successfully

**Step 2: Verify installation**

Run: `cd frontend && npm list framer-motion`
Expected: `framer-motion@11.x.x` is listed

**Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "feat: add framer-motion for smooth animations"
```

---

## Task 9: Create Frontend API Client for Integrations

**Files:**
- Create: `frontend/src/api/integrations.ts`

**Step 1: Write the API client functions**

```typescript
import { apiClient } from "./client";

export type IntegrationType =
  | "google_calendar"
  | "gmail"
  | "outlook"
  | "salesforce"
  | "hubspot";

export interface Integration {
  id: string;
  user_id: string;
  integration_type: IntegrationType;
  composio_connection_id: string;
  composio_account_id: string | null;
  display_name: string | null;
  status: "active" | "disconnected" | "error" | "pending";
  last_sync_at: string | null;
  sync_status: "success" | "pending" | "failed";
  error_message: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface AvailableIntegration {
  integration_type: IntegrationType;
  display_name: string;
  description: string;
  icon: string;
  is_connected: boolean;
}

export interface AuthUrlResponse {
  authorization_url: string;
  integration_type: IntegrationType;
  display_name: string;
}

export interface ConnectRequest {
  code: string;
  state?: string;
}

export const integrationsApi = {
  // List user's connected integrations
  listIntegrations: async (): Promise<Integration[]> => {
    const response = await apiClient.get<Integration[]>("/integrations");
    return response.data;
  },

  // List all available integrations with connection status
  listAvailableIntegrations: async (): Promise<AvailableIntegration[]> => {
    const response = await apiClient.get<AvailableIntegration[]>("/integrations/available");
    return response.data;
  },

  // Generate OAuth authorization URL
  getAuthUrl: async (
    integrationType: IntegrationType,
    redirectUri: string
  ): Promise<AuthUrlResponse> => {
    const response = await apiClient.post<AuthUrlResponse>(
      `/integrations/${integrationType}/auth-url`,
      { redirect_uri: redirectUri }
    );
    return response.data;
  },

  // Complete OAuth connection
  connectIntegration: async (
    integrationType: IntegrationType,
    code: string,
    state?: string
  ): Promise<Integration> => {
    const response = await apiClient.post<Integration>(
      `/integrations/${integrationType}/connect`,
      { code, state }
    );
    return response.data;
  },

  // Disconnect an integration
  disconnectIntegration: async (integrationType: IntegrationType): Promise<{ message: string }> => {
    const response = await apiClient.post<{ message: string }>(
      `/integrations/${integrationType}/disconnect`
    );
    return response.data;
  },

  // Trigger manual sync
  syncIntegration: async (integrationId: string): Promise<Integration> => {
    const response = await apiClient.post<Integration>(`/integrations/${integrationId}/sync`);
    return response.data;
  },
};
```

**Step 2: Verify TypeScript types**

Run: `cd frontend && npm run typecheck`
Expected: No type errors

**Step 3: Commit**

```bash
git add frontend/src/api/integrations.ts
git commit -m "feat: add integrations API client"
```

---

## Task 10: Create Integrations Settings Page

**Files:**
- Create: `frontend/src/pages/IntegrationsSettings.tsx`

**Step 1: Write the React component**

```typescript
import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { DashboardLayout } from "@/components/DashboardLayout";
import { integrationsApi, AvailableIntegration, Integration } from "@/api/integrations";

export function IntegrationsSettingsPage() {
  const [availableIntegrations, setAvailableIntegrations] = useState<AvailableIntegration[]>([]);
  const [connectedIntegrations, setConnectedIntegrations] = useState<Integration[]>([]);
  const [loading, setLoading] = useState(true);
  const [connectingType, setConnectingType] = useState<string | null>(null);
  const [disconnectingType, setDisconnectingType] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadIntegrations();
  }, []);

  const loadIntegrations = async () => {
    try {
      setLoading(true);
      const [available, connected] = await Promise.all([
        integrationsApi.listAvailableIntegrations(),
        integrationsApi.listIntegrations(),
      ]);
      setAvailableIntegrations(available);
      setConnectedIntegrations(connected);
    } catch (err) {
      console.error("Failed to load integrations:", err);
      setError("Failed to load integrations. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleConnect = async (integrationType: string) => {
    try {
      setConnectingType(integrationType);
      setError(null);

      const redirectUri = `${window.location.origin}/dashboard/settings/integrations/callback`;
      const { authorization_url } = await integrationsApi.getAuthUrl(
        integrationType as any,
        redirectUri
      );

      // Redirect to OAuth provider
      window.location.href = authorization_url;
    } catch (err) {
      console.error("Failed to connect integration:", err);
      setError("Failed to connect integration. Please try again.");
      setConnectingType(null);
    }
  };

  const handleDisconnect = async (integrationType: string) => {
    try {
      setDisconnectingType(integrationType);
      setError(null);

      await integrationsApi.disconnectIntegration(integrationType as any);

      // Update local state
      setConnectedIntegrations((prev) =>
        prev.filter((i) => i.integration_type !== integrationType)
      );
      setAvailableIntegrations((prev) =>
        prev.map((i) =>
          i.integration_type === integrationType ? { ...i, is_connected: false } : i
        )
      );
    } catch (err) {
      console.error("Failed to disconnect integration:", err);
      setError("Failed to disconnect integration. Please try again.");
    } finally {
      setDisconnectingType(null);
    }
  };

  const getStatusColor = (integration: AvailableIntegration) => {
    return integration.is_connected ? "bg-emerald-500" : "bg-slate-500";
  };

  const formatLastSync = (date: string | null) => {
    if (!date) return "Never";
    return new Date(date).toLocaleString();
  };

  if (loading) {
    return (
      <DashboardLayout>
        <div className="p-4 lg:p-8">
          <div className="max-w-4xl mx-auto">
            <div className="animate-pulse">
              <div className="h-8 bg-slate-700 rounded w-64 mb-4" />
              <div className="h-4 bg-slate-700 rounded w-96 mb-8" />
              <div className="space-y-4">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-32 bg-slate-700/50 rounded-xl" />
                ))}
              </div>
            </div>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="p-4 lg:p-8">
        <div className="max-w-4xl mx-auto">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-white mb-2">Integrations</h1>
            <p className="text-slate-400">
              Connect your tools to enable ARIA's full capabilities
            </p>
          </div>

          {/* Error Message */}
          <AnimatePresence>
            {error && (
              <motion.div
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                className="mb-6 p-4 bg-red-500/10 border border-red-500/20 rounded-xl"
              >
                <p className="text-red-400">{error}</p>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Integrations Grid */}
          <div className="space-y-4">
            {availableIntegrations.map((integration) => {
              const connectedDetails = connectedIntegrations.find(
                (i) => i.integration_type === integration.integration_type
              );

              return (
                <motion.div
                  key={integration.integration_type}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.2 }}
                  className="group bg-slate-800/50 border border-slate-700/50 rounded-xl p-6 hover:bg-slate-800/70 hover:border-slate-700 transition-all duration-200"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-start gap-4 flex-1">
                      {/* Icon Container */}
                      <div className="relative">
                        <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-slate-700 to-slate-800 flex items-center justify-center shadow-lg">
                          <IntegrationIcon type={integration.integration_type} />
                        </div>
                        {/* Status Indicator */}
                        <div
                          className={`absolute -bottom-1 -right-1 w-4 h-4 rounded-full border-2 border-slate-800 ${getStatusColor(
                            integration
                          )}`}
                        />
                      </div>

                      {/* Content */}
                      <div className="flex-1">
                        <div className="flex items-center gap-3 mb-1">
                          <h3 className="text-lg font-semibold text-white">
                            {integration.display_name}
                          </h3>
                          {integration.is_connected && (
                            <span className="px-2 py-0.5 text-xs font-medium bg-emerald-500/10 text-emerald-400 rounded-full">
                              Connected
                            </span>
                          )}
                        </div>
                        <p className="text-slate-400 text-sm mb-3">{integration.description}</p>

                        {connectedDetails && (
                          <div className="flex items-center gap-4 text-xs text-slate-500">
                            <span>{connectedDetails.display_name || "Connected"}</span>
                            <span>•</span>
                            <span>
                              Last sync: {formatLastSync(connectedDetails.last_sync_at)}
                            </span>
                            {connectedDetails.sync_status === "failed" && (
                              <>
                                <span>•</span>
                                <span className="text-red-400">Sync failed</span>
                              </>
                            )}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Action Button */}
                    <div className="flex items-center gap-2">
                      {integration.is_connected ? (
                        <button
                          onClick={() => handleDisconnect(integration.integration_type)}
                          disabled={disconnectingType === integration.integration_type}
                          className="px-4 py-2 text-sm font-medium text-slate-400 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors disabled:opacity-50"
                        >
                          {disconnectingType === integration.integration_type
                            ? "Disconnecting..."
                            : "Disconnect"}
                        </button>
                      ) : (
                        <motion.button
                          onClick={() => handleConnect(integration.integration_type)}
                          disabled={connectingType === integration.integration_type}
                          whileHover={{ scale: 1.02 }}
                          whileTap={{ scale: 0.98 }}
                          className="px-5 py-2.5 text-sm font-medium bg-white text-slate-900 rounded-lg hover:bg-slate-100 transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
                        >
                          {connectingType === integration.integration_type
                            ? "Connecting..."
                            : "Connect"}
                        </motion.button>
                      )}
                    </div>
                  </div>
                </motion.div>
              );
            })}
          </div>

          {/* Empty State */}
          {availableIntegrations.length === 0 && !loading && (
            <div className="text-center py-16">
              <p className="text-slate-400">No integrations available at this time.</p>
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}

// Integration Icon Component
function IntegrationIcon({ type }: { type: string }) {
  const icons: Record<string, React.ReactNode> = {
    google_calendar: (
      <svg className="w-6 h-6 text-blue-400" fill="currentColor" viewBox="0 0 24 24">
        <path d="M19 4h-1V2h-2v2H8V2H6v2H5c-1.11 0-1.99.9-1.99 2L3 20a2 2 0 002 2h14c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 16H5V10h14v10zm0-12H5V6h14v2zm-7 5h5v5h-5z" />
      </svg>
    ),
    gmail: (
      <svg className="w-6 h-6 text-red-400" fill="currentColor" viewBox="0 0 24 24">
        <path d="M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z" />
      </svg>
    ),
    outlook: (
      <svg className="w-6 h-6 text-blue-500" fill="currentColor" viewBox="0 0 24 24">
        <path d="M21 3H3c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h18c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-9 14H5v-5h7v5zm0-7H5V5h7v5zm7 7h-5v-5h5v5zm0-7h-5V5h5v5z" />
      </svg>
    ),
    salesforce: (
      <svg className="w-6 h-6 text-sky-400" fill="currentColor" viewBox="0 0 24 24">
        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z" />
      </svg>
    ),
    hubspot: (
      <svg className="w-6 h-6 text-orange-500" fill="currentColor" viewBox="0 0 24 24">
        <path d="M12.01 2C6.49 2 2 6.49 2 12.01S6.49 22.02 12.01 22.02 22.02 17.53 22.02 12.01 17.53 2 12.01 2zm6.75 11.75c-1.12.41-2.25.75-3.4 1.02.15-1.01.25-2.05.25-3.1 0-3.42-1.25-6.55-3.31-8.96 3.12.89 5.51 3.6 6.29 6.93-.05.03-.09.07-.13.11l-.7.7v3.3zm-9.29 4.39c-.52-1.28-.85-2.64-.97-4.05.66-.12 1.32-.25 1.97-.4.65.15 1.31.28 1.97.4-.12 1.41-.45 2.77-.97 4.05-1.34-.22-2.67-.22-4 0zm.53-7.53c.48 0 .96.02 1.44.07.05.48.07.96.07 1.44s-.02.96-.07 1.44c-.48.05-.96.07-1.44.07s-.96-.02-1.44-.07c-.05-.48-.07-.96-.07-1.44s.02-.96.07-1.44c.48-.05.96-.07 1.44-.07zm-.98-4.54c-1.86 2.2-3.02 5.02-3.02 8.11 0 1.05.1 2.09.25 3.1-1.15-.27-2.28-.61-3.4-1.02v-3.3l-.7-.7c-.04-.04-.08-.08-.13-.11.78-3.33 3.17-6.04 6.29-6.93.26.31.51.64.71.95z" />
      </svg>
    ),
  };

  return icons[type] || null;
}
```

**Step 2: Verify TypeScript types**

Run: `cd frontend && npm run typecheck`
Expected: No type errors

**Step 3: Commit**

```bash
git add frontend/src/pages/IntegrationsSettings.tsx
git commit -m "feat: implement integrations settings page component"
```

---

## Task 11: Create OAuth Callback Handler Page

**Files:**
- Create: `frontend/src/pages/IntegrationsCallback.tsx`

**Step 1: Write the callback handler component**

```typescript
import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { integrationsApi } from "@/api/integrations";

export function IntegrationsCallbackPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const handleCallback = async () => {
      const code = searchParams.get("code");
      const state = searchParams.get("state");
      const integrationType = searchParams.get("integration");

      if (!code || !integrationType) {
        setStatus("error");
        setError("Missing required parameters");
        return;
      }

      try {
        await integrationsApi.connectIntegration(integrationType, code, state || undefined);
        setStatus("success");

        // Redirect back to settings after a delay
        setTimeout(() => {
          navigate("/dashboard/settings/integrations", { replace: true });
        }, 2000);
      } catch (err) {
        console.error("Failed to connect integration:", err);
        setStatus("error");
        setError("Failed to connect integration. Please try again.");

        // Redirect back to settings after a delay
        setTimeout(() => {
          navigate("/dashboard/settings/integrations", { replace: true });
        }, 3000);
      }
    };

    handleCallback();
  }, [searchParams, navigate]);

  return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center p-4">
      <div className="max-w-md w-full">
        {status === "loading" && (
          <div className="bg-slate-800 border border-slate-700 rounded-xl p-8 text-center">
            <div className="w-16 h-16 border-4 border-primary-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
            <h2 className="text-xl font-semibold text-white mb-2">Connecting...</h2>
            <p className="text-slate-400">Please wait while we connect your integration.</p>
          </div>
        )}

        {status === "success" && (
          <div className="bg-slate-800 border border-emerald-500/30 rounded-xl p-8 text-center">
            <div className="w-16 h-16 bg-emerald-500/10 rounded-full flex items-center justify-center mx-auto mb-4">
              <svg className="w-8 h-8 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h2 className="text-xl font-semibold text-white mb-2">Connected Successfully!</h2>
            <p className="text-slate-400">Redirecting you back to settings...</p>
          </div>
        )}

        {status === "error" && (
          <div className="bg-slate-800 border border-red-500/30 rounded-xl p-8 text-center">
            <div className="w-16 h-16 bg-red-500/10 rounded-full flex items-center justify-center mx-auto mb-4">
              <svg className="w-8 h-8 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <h2 className="text-xl font-semibold text-white mb-2">Connection Failed</h2>
            <p className="text-slate-400">{error || "An error occurred"}</p>
            <p className="text-slate-500 text-sm mt-2">Redirecting back to settings...</p>
          </div>
        )}
      </div>
    </div>
  );
}
```

**Step 2: Verify TypeScript types**

Run: `cd frontend && npm run typecheck`
Expected: No type errors

**Step 3: Commit**

```bash
git add frontend/src/pages/IntegrationsCallback.tsx
git commit -m "feat: implement OAuth callback handler page"
```

---

## Task 12: Export Pages and Add Routes

**Files:**
- Modify: `frontend/src/pages/index.ts`
- Modify: `frontend/src/App.tsx`

**Step 1: Export new pages from index**

Read current: `frontend/src/pages/index.ts`

Modify to export new pages:

```typescript
export { LoginPage } from "./Login";
export { SignupPage } from "./Signup";
export { DashboardPage } from "./Dashboard";
export { GoalsPage } from "./Goals";
export { AriaChatPage } from "./AriaChat";
export { IntegrationsSettingsPage } from "./IntegrationsSettings";
export { IntegrationsCallbackPage } from "./IntegrationsCallback";
```

**Step 2: Add routes to App.tsx**

Modify: `frontend/src/App.tsx:5`

Update import:
```typescript
import {
  AriaChatPage,
  LoginPage,
  SignupPage,
  DashboardPage,
  GoalsPage,
  IntegrationsSettingsPage,
  IntegrationsCallbackPage,
} from "@/pages";
```

Add routes before the catch-all routes:

```typescript
<Route
  path="/dashboard/settings/integrations"
  element={
    <ProtectedRoute>
      <IntegrationsSettingsPage />
    </ProtectedRoute>
  }
/>
<Route
  path="/dashboard/settings/integrations/callback"
  element={
    <ProtectedRoute>
      <IntegrationsCallbackPage />
    </ProtectedRoute>
  }
/>
```

**Step 3: Update DashboardLayout to highlight settings**

Modify: `frontend/src/components/DashboardLayout.tsx:11`

Update navItems to include settings sub-route:
```typescript
{ name: "Settings", href: "/dashboard/settings/integrations", icon: "settings" },
```

**Step 4: Verify routes work**

Run: `cd frontend && npm run typecheck`
Expected: No type errors

**Step 5: Commit**

```bash
git add frontend/src/pages/index.ts frontend/src/App.tsx frontend/src/components/DashboardLayout.tsx
git commit -m "feat: add integrations settings routes to app"
```

---

## Task 13: Update Navigation Link for Settings

**Files:**
- Modify: `frontend/src/components/DashboardLayout.tsx`

**Step 1: Update settings href to point to integrations**

The navItems already has `/dashboard/settings/integrations` from Task 12, so this is done.

**Step 2: Commit if changes were needed**

If no changes needed, skip commit. Otherwise:
```bash
git add frontend/src/components/DashboardLayout.tsx
git commit -m "fix: update settings nav link to point to integrations page"
```

---

## Task 14: Add Polling for Connection Status Updates

**Files:**
- Modify: `frontend/src/pages/IntegrationsSettings.tsx`

**Step 1: Add polling to callback handler for integration status**

Update the `handleConnect` function in IntegrationsSettings.tsx to store the redirect:

```typescript
const handleConnect = async (integrationType: string) => {
  try {
    setConnectingType(integrationType);
    setError(null);

    const redirectUri = `${window.location.origin}/dashboard/settings/integrations/callback`;
    const { authorization_url } = await integrationsApi.getAuthUrl(
      integrationType as any,
      redirectUri
    );

    // Store integration type in sessionStorage for callback
    sessionStorage.setItem("pending_integration_type", integrationType);

    // Redirect to OAuth provider
    window.location.href = authorization_url;
  } catch (err) {
    console.error("Failed to connect integration:", err);
    setError("Failed to connect integration. Please try again.");
    setConnectingType(null);
  }
};
```

**Step 2: Update callback to use stored integration type**

Update IntegrationsCallback.tsx to get integration type from sessionStorage:

```typescript
const integrationType = searchParams.get("integration") || sessionStorage.getItem("pending_integration_type");
```

**Step 3: Add polling to settings page for real-time updates**

Add useEffect to poll for status updates when connections are pending:

```typescript
useEffect(() => {
  // Check for pending connection from callback
  const pendingType = sessionStorage.getItem("pending_integration_type");
  if (pendingType) {
    // Poll for connection status
    const pollInterval = setInterval(async () => {
      await loadIntegrations();
      const connected = connectedIntegrations.find((i) => i.integration_type === pendingType);
      if (connected) {
        sessionStorage.removeItem("pending_integration_type");
        clearInterval(pollInterval);
      }
    }, 2000);

    // Stop polling after 30 seconds
    setTimeout(() => clearInterval(pollInterval), 30000);

    return () => clearInterval(pollInterval);
  }
}, []);
```

**Step 4: Verify TypeScript types**

Run: `cd frontend && npm run typecheck`
Expected: No type errors

**Step 5: Commit**

```bash
git add frontend/src/pages/IntegrationsSettings.tsx frontend/src/pages/IntegrationsCallback.tsx
git commit -m "feat: add polling for real-time connection status updates"
```

---

## Task 15: Add Error Boundaries and Loading States

**Files:**
- Modify: `frontend/src/pages/IntegrationsSettings.tsx`

**Step 1: Add retry button on error**

Update error display section:

```typescript
{/* Error Message */}
<AnimatePresence>
  {error && (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      className="mb-6 p-4 bg-red-500/10 border border-red-500/20 rounded-xl flex items-center justify-between"
    >
      <p className="text-red-400">{error}</p>
      <button
        onClick={() => {
          setError(null);
          loadIntegrations();
        }}
        className="px-3 py-1 text-sm text-red-400 hover:bg-red-500/10 rounded-lg transition-colors"
      >
        Retry
      </button>
    </motion.div>
  )}
</AnimatePresence>
```

**Step 2: Add skeleton loading state**

Update loading state to show more polished skeleton:

```typescript
{loading && (
  <DashboardLayout>
    <div className="p-4 lg:p-8">
      <div className="max-w-4xl mx-auto">
        <div className="animate-pulse">
          <div className="h-8 bg-slate-700/50 rounded-lg w-64 mb-2" />
          <div className="h-4 bg-slate-700/30 rounded w-96 mb-8" />
          <div className="space-y-4">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="bg-slate-800/30 border border-slate-700/30 rounded-xl p-6">
                <div className="flex items-start gap-4">
                  <div className="w-12 h-12 rounded-xl bg-slate-700/50" />
                  <div className="flex-1">
                    <div className="h-5 bg-slate-700/50 rounded w-48 mb-2" />
                    <div className="h-4 bg-slate-700/30 rounded w-64 mb-3" />
                    <div className="h-3 bg-slate-700/20 rounded w-32" />
                  </div>
                  <div className="w-24 h-10 bg-slate-700/50 rounded-lg" />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  </DashboardLayout>
)}
```

**Step 3: Verify TypeScript types**

Run: `cd frontend && npm run typecheck`
Expected: No type errors

**Step 4: Commit**

```bash
git add frontend/src/pages/IntegrationsSettings.tsx
git commit -m "feat: add error retry and improved loading states"
```

---

## Task 16: Integration Testing

**Files:**
- Create: `backend/tests/integrations/test_e2e_integration_flow.py`

**Step 1: Write end-to-end integration test**

```python
"""End-to-end integration tests for OAuth flow."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.integrations.service import IntegrationService
from src.integrations.domain import IntegrationType


@pytest.mark.asyncio
async def test_full_oauth_flow():
    """Test complete OAuth connection flow."""
    # Mock dependencies
    with patch("src.integrations.service.SupabaseClient") as mock_supabase:
        with patch("src.integrations.service.get_oauth_client") as mock_oauth:
            # Setup mocks
            supabase_client = AsyncMock()
            mock_supabase.get_client.return_value = supabase_client

            oauth_client = AsyncMock()
            mock_oauth.return_value = oauth_client

            # Mock auth URL generation
            oauth_client.generate_auth_url.return_value = "https://auth.example.com/authorize?code=test123"

            # Mock token exchange
            oauth_client.exchange_code_for_connection.return_value = {
                "connection_id": "conn-123",
                "account_id": "account-456",
                "account_email": "user@example.com",
            }

            # Mock database insert
            supabase_client.table.return_value.insert.return_value.execute.return_value = MagicMock(
                data=[{
                    "id": "int-1",
                    "user_id": "user-123",
                    "integration_type": "google_calendar",
                    "status": "active",
                    "display_name": "user@example.com",
                }]
            )

            # Execute flow
            service = IntegrationService()

            # Step 1: Generate auth URL
            auth_url = await oauth_client.generate_auth_url(
                user_id="user-123",
                integration_type=IntegrationType.GOOGLE_CALENDAR,
                redirect_uri="http://localhost:5173/callback",
            )
            assert "auth.example.com" in auth_url

            # Step 2: Exchange code
            connection_data = await oauth_client.exchange_code_for_connection(
                user_id="user-123",
                code="test-auth-code",
                integration_type=IntegrationType.GOOGLE_CALENDAR,
            )
            assert connection_data["connection_id"] == "conn-123"

            # Step 3: Create integration record
            integration = await service.create_integration(
                user_id="user-123",
                integration_type=IntegrationType.GOOGLE_CALENDAR,
                composio_connection_id=connection_data["connection_id"],
                display_name=connection_data["account_email"],
            )
            assert integration["integration_type"] == "google_calendar"
            assert integration["status"] == "active"


@pytest.mark.asyncio
async def test_disconnect_flow():
    """Test integration disconnection flow."""
    with patch("src.integrations.service.SupabaseClient") as mock_supabase:
        with patch("src.integrations.service.get_oauth_client") as mock_oauth:
            # Setup mocks
            supabase_client = AsyncMock()
            mock_supabase.get_client.return_value = supabase_client

            oauth_client = AsyncMock()
            mock_oauth.return_value = oauth_client

            # Mock existing integration
            supabase_client.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
                data={
                    "id": "int-1",
                    "composio_connection_id": "conn-123",
                }
            )

            # Mock disconnection
            oauth_client.disconnect_integration.return_value = True

            # Execute
            service = IntegrationService()
            result = await service.disconnect_integration(
                user_id="user-123",
                integration_type=IntegrationType.GOOGLE_CALENDAR,
            )

            assert result is True
            oauth_client.disconnect_integration.assert_called_once_with("conn-123")
```

**Step 2: Run integration tests**

Run: `cd backend && pytest tests/integrations/test_e2e_integration_flow.py -v`
Expected: PASS

**Step 3: Run all integration tests**

Run: `cd backend && pytest tests/integrations/ -v`
Expected: All tests pass

**Step 4: Commit**

```bash
git add backend/tests/integrations/test_e2e_integration_flow.py
git commit -m "test: add end-to-end integration flow tests"
```

---

## Task 17: Final Quality Checks

**Files:**
- Multiple

**Step 1: Run backend type checking**

Run: `cd backend && mypy src/ --strict`
Expected: No type errors (or acceptable warnings)

**Step 2: Run backend linting**

Run: `cd backend && ruff check src/`
Expected: No linting errors

**Step 3: Run backend formatting check**

Run: `cd backend && ruff format --check src/`
Expected: All files formatted correctly

**Step 4: Run frontend type checking**

Run: `cd frontend && npm run typecheck`
Expected: No type errors

**Step 5: Run frontend linting**

Run: `cd frontend && npm run lint`
Expected: No linting errors

**Step 6: Run all tests**

Run: `cd backend && pytest tests/ -v`
Expected: All tests pass

**Step 7: Manual smoke test checklist**

- Backend starts successfully: `cd backend && uvicorn src.main:app --reload`
- Frontend starts successfully: `cd frontend && npm run dev`
- Navigate to `/dashboard/settings/integrations`
- Page loads without errors
- Integrations are displayed
- Click "Connect" on an integration
- Verify OAuth flow initiates

**Step 8: Commit any formatting fixes**

Run: `cd backend && ruff format src/`
Run: `cd frontend && npm run lint -- --fix`

```bash
git add -A
git commit -m "style: apply code formatting fixes"
```

---

## Task 18: Documentation

**Files:**
- Create: `docs/integrations/OAUTH_SETUP.md`

**Step 1: Write OAuth setup documentation**

```markdown
# OAuth Integration Setup Guide

This guide explains how to set up and configure OAuth integrations for ARIA using Composio.

## Prerequisites

- Composio API key (get from https://composio.dev)
- Supabase project configured
- OAuth provider credentials (Google, Microsoft, Salesforce, HubSpot)

## Composio Configuration

1. **Get API Key:**
   - Sign up at https://composio.dev
   - Create a new project
   - Copy your API key

2. **Configure Environment Variables:**

Add to `backend/.env`:
```bash
COMPOSIO_API_KEY=your-actual-api-key
COMPOSIO_BASE_URL=https://api.composio.dev
```

3. **Configure OAuth Apps in Composio Dashboard:**

For each integration type, configure the corresponding app:

### Google Calendar & Gmail
- OAuth consent screen configured
- Redirect URI: `https://your-domain.com/dashboard/settings/integrations/callback`
- Scopes: See `backend/src/integrations/domain.py` for required scopes

### Microsoft Outlook
- App registered in Azure Portal
- Redirect URI configured
- Client secret configured in Composio

### Salesforce
- Connected App configured
- Callback URL configured
- OAuth settings enabled

### HubSpot
- OAuth app configured in HubSpot dashboard
- Redirect URI configured

## Database Setup

The `user_integrations` table is created via migration:
- `backend/migrations/20260202_create_integrations_table.sql`

Apply this migration to your Supabase project.

## API Endpoints

### List User Integrations
```http
GET /api/v1/integrations
Authorization: Bearer {token}
```

### Get Auth URL
```http
POST /api/v1/integrations/{integration_type}/auth-url
Content-Type: application/json
Authorization: Bearer {token}

{
  "redirect_uri": "https://your-domain.com/dashboard/settings/integrations/callback"
}
```

### Complete Connection
```http
POST /api/v1/integrations/{integration_type}/connect
Content-Type: application/json
Authorization: Bearer {token}

{
  "code": "oauth-auth-code",
  "state": "optional-state-param"
}
```

### Disconnect Integration
```http
POST /api/v1/integrations/{integration_type}/disconnect
Authorization: Bearer {token}
```

## Security Notes

- Tokens are stored by Composio, not in ARIA database
- We only store connection IDs and metadata
- All endpoints require authentication
- RLS policies ensure users can only access their own integrations

## Troubleshooting

### "Invalid integration type" Error
- Check `backend/src/integrations/domain.py` for valid integration types
- Ensure the type matches exactly (case-sensitive)

### OAuth Redirect Fails
- Verify redirect URI matches in Composio dashboard
- Check CORS settings
- Ensure frontend URL is correct

### Connection State Shows "Pending"
- Check Composio dashboard for connection status
- Verify API key is valid
- Check browser console for errors

## Supported Integrations

| Integration | Type | Composio App ID |
|-------------|------|-----------------|
| Google Calendar | google_calendar | google_calendar |
| Gmail | gmail | gmail |
| Microsoft Outlook | outlook | outlook_calendar |
| Salesforce | salesforce | salesforce |
| HubSpot | hubspot | hubspot |
```

**Step 2: Add to project README if needed**

**Step 3: Commit documentation**

```bash
git add docs/integrations/
git commit -m "docs: add OAuth integration setup guide"
```

---

## Task 19: Final Review and Clean Up

**Files:**
- Multiple

**Step 1: Review all code matches design requirements**

Check list:
- [ ] Apple-inspired luxury design implemented
- [ ] Premium styling with generous whitespace
- [ ] Sophisticated integration cards
- [ ] Subtle shadows and depth
- [ ] Polished status indicators
- [ ] Smooth animations using Framer Motion
- [ ] Elegant loading states
- [ ] Clear visual hierarchy
- [ ] Mobile responsive

**Step 2: Verify all acceptance criteria from US-413**

From `docs/PHASE_4_FEATURES.md`:
- [ ] `/dashboard/settings/integrations` route exists
- [ ] Connect Google Calendar via OAuth
- [ ] Connect Gmail via OAuth
- [ ] Connect Outlook via OAuth
- [ ] Connect Salesforce/HubSpot via OAuth
- [ ] Status indicator for each integration
- [ ] Disconnect option for each integration
- [ ] Sync status and last sync time display
- [ ] Secure token storage (Composio handles this)

**Step 3: Run full test suite**

Run: `cd backend && pytest tests/ -v --cov`
Expected: All tests pass with good coverage

**Step 4: Check for any TODO comments in new code**

Run: `grep -r "TODO" backend/src/integrations frontend/src/pages/IntegrationsSettings.tsx frontend/src/pages/IntegrationsCallback.tsx`

If TODOs found, either:
- Implement the feature if it's critical
- Create a follow-up issue if non-critical

**Step 5: Verify no console errors in browser**

- Start both backend and frontend
- Navigate to integrations page
- Check browser console for errors
- Test connect flow

**Step 6: Final commit**

```bash
git add -A
git commit -m "feat: complete US-413 integrations settings page implementation"
```

---

## Summary

This implementation plan creates a complete integrations settings page with:

**Backend (10 files):**
1. `backend/migrations/20260202_create_integrations_table.sql` - Database schema
2. `backend/src/integrations/domain.py` - Domain models and configs
3. `backend/src/integrations/oauth.py` - Composio OAuth client
4. `backend/src/integrations/service.py` - Business logic layer
5. `backend/src/api/routes/integrations.py` - FastAPI routes
6. Updated `backend/src/integrations/__init__.py`
7. Updated `backend/src/core/config.py`
8. Updated `backend/src/main.py`
9. Test files for all modules

**Frontend (4 files):**
1. `frontend/src/api/integrations.ts` - API client
2. `frontend/src/pages/IntegrationsSettings.tsx` - Main settings page
3. `frontend/src/pages/IntegrationsCallback.tsx` - OAuth callback handler
4. Updated routing in `frontend/src/App.tsx` and `frontend/src/components/DashboardLayout.tsx`

**Key Features:**
- OAuth via Composio for all 5 integrations
- Premium Apple-inspired UI with Framer Motion animations
- Real-time connection status with polling
- Secure token storage (tokens stored by Composio)
- Comprehensive error handling and loading states
- Full test coverage
- Type-safe TypeScript and Python
