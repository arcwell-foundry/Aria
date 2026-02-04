"""Test that all CRM sync and audit services are properly exported from the services package."""

import pytest


class TestServiceExports:
    """Test suite for verifying service module exports."""

    def test_crm_audit_service_exports(self) -> None:
        """Test that CRM audit service classes are exported."""
        from src.services import (
            CRMAuditEntry,
            CRMAuditOperation,
            CRMAuditService,
            get_crm_audit_service,
        )

        # Verify classes are the correct types
        assert CRMAuditService is not None
        assert CRMAuditOperation is not None
        assert CRMAuditEntry is not None
        assert callable(get_crm_audit_service)

    def test_crm_sync_service_exports(self) -> None:
        """Test that CRM sync service classes are exported."""
        from src.services import (
            CRMSyncService,
            get_crm_sync_service,
        )

        # Verify classes are the correct types
        assert CRMSyncService is not None
        assert callable(get_crm_sync_service)

    def test_crm_sync_model_exports(self) -> None:
        """Test that CRM sync model classes are exported."""
        from src.services import (
            ConflictResolution,
            CRMProvider,
            CRMRecord,
            CRMSyncModelError,
            CRMSyncState,
            SyncConflict,
            SyncDirection,
            SyncStatus,
        )

        # Verify all model classes are exported
        assert CRMProvider is not None
        assert CRMSyncState is not None
        assert SyncStatus is not None
        assert SyncDirection is not None
        assert ConflictResolution is not None
        assert SyncConflict is not None
        assert CRMRecord is not None
        assert CRMSyncModelError is not None

    def test_existing_exports_still_work(self) -> None:
        """Test that existing exports still work after adding new ones."""
        from src.services import (
            NotificationService,
            PredictionService,
            notification_integration,
        )

        assert NotificationService is not None
        assert PredictionService is not None
        assert notification_integration is not None

    def test_all_exports_in_dunder_all(self) -> None:
        """Test that __all__ contains all expected exports."""
        from src import services

        expected_exports = {
            # Existing exports
            "NotificationService",
            "PredictionService",
            "notification_integration",
            # CRM audit exports
            "CRMAuditService",
            "CRMAuditOperation",
            "CRMAuditEntry",
            "get_crm_audit_service",
            # CRM sync service exports
            "CRMSyncService",
            "get_crm_sync_service",
            # CRM sync model exports
            "CRMProvider",
            "CRMSyncState",
            "SyncStatus",
            "SyncDirection",
            "ConflictResolution",
            "SyncConflict",
            "CRMRecord",
            "CRMSyncModelError",
        }

        actual_exports = set(services.__all__)

        missing = expected_exports - actual_exports
        assert not missing, f"Missing exports in __all__: {missing}"
