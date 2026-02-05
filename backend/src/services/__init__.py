"""Services package."""

from src.services import notification_integration
from src.services.crm_audit import (
    CRMAuditEntry,
    CRMAuditOperation,
    CRMAuditService,
    get_crm_audit_service,
)
from src.services.crm_sync import (
    CRMSyncService,
    get_crm_sync_service,
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
from src.services.lead_collaboration import (
    Contribution,
    Contributor,
    LeadCollaborationService,
)
from src.services.notification_service import NotificationService
from src.services.prediction_service import PredictionService

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
]
