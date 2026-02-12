"""Services package."""

from typing import TYPE_CHECKING

from src.services import notification_integration
from src.services.crm_audit import (
    CRMAuditEntry,
    CRMAuditOperation,
    CRMAuditService,
    get_crm_audit_service,
)
from src.services.crm_sync_models import (
    ConflictResolution,
    CRMProvider,
    CRMRecord,
    CRMSyncModelError,
    CRMSyncState,
    SyncConflict,
    SyncDirection,
    SyncStatus,
)
from src.services.email_service import EmailService
from src.services.lead_collaboration import (
    Contribution,
    Contributor,
    LeadCollaborationService,
)
from src.services.notification_service import NotificationService
from src.services.prediction_service import PredictionService

# Lazy imports to avoid circular dependency with integrations/oauth
if TYPE_CHECKING:
    from src.services.crm_sync import (
        CRMSyncService,
        get_crm_sync_service,
    )
else:
    # Import at runtime but not at module level
    def __getattr__(name: str):
        if name == "CRMSyncService":
            from src.services.crm_sync import CRMSyncService

            return CRMSyncService
        elif name == "get_crm_sync_service":
            from src.services.crm_sync import get_crm_sync_service

            return get_crm_sync_service
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
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
    # Lead collaboration exports
    "LeadCollaborationService",
    "Contribution",
    "Contributor",
    # Email service exports
    "EmailService",
]
