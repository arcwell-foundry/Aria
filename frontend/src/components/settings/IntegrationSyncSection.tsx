import {
  RefreshCw,
  Clock,
  CheckCircle,
  AlertCircle,
  Loader2,
} from "lucide-react";
import { useSyncStatus, useTriggerSync } from "@/hooks/useDeepSync";
import { useState } from "react";

interface SyncStatusCardProps {
  integrationType: string;
  displayName: string;
  lastSyncAt: string | null;
  lastSyncStatus: string | null;
  syncCount: number;
  onSync: (integrationType: string) => void;
  isSyncing: boolean;
}

function formatTime(timeStr: string | null): string {
  if (!timeStr) return "Never";
  const date = new Date(timeStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return "Just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffMins < 1440) return `${Math.floor(diffMins / 60)}h ago`;
  return date.toLocaleDateString();
}

function getStatusIcon(lastSyncStatus: string | null, isSyncing: boolean): React.ReactNode {
  if (isSyncing) {
    return <Loader2 className="w-4 h-4 text-interactive animate-spin" />;
  }
  if (lastSyncStatus === "success") {
    return <CheckCircle className="w-4 h-4 text-success" />;
  }
  if (lastSyncStatus === "failed") {
    return <AlertCircle className="w-4 h-4 text-critical" />;
  }
  return <Clock className="w-4 h-4 text-interactive" />;
}

function getStatusText(lastSyncStatus: string | null, isSyncing: boolean): string {
  if (isSyncing) return "Syncing...";
  if (lastSyncStatus === "success") return "Up to date";
  if (lastSyncStatus === "failed") return "Sync failed";
  if (lastSyncStatus === "pending") return "Sync pending";
  return "Not synced";
}

function SyncStatusCard({
  integrationType,
  displayName,
  lastSyncAt,
  lastSyncStatus,
  syncCount,
  onSync,
  isSyncing,
}: SyncStatusCardProps) {
  return (
    <div className="flex items-center justify-between py-4 border-b border-border last:border-b-0">
      <div className="flex items-start gap-3 flex-1">
        <div className="w-10 h-10 rounded-full bg-subtle flex items-center justify-center flex-shrink-0">
          {getStatusIcon(lastSyncStatus, isSyncing)}
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h3 className="text-content font-sans text-[0.9375rem] font-medium">
              {displayName}
            </h3>
          </div>
          <div className="flex items-center gap-3 mt-0.5">
            <p className="text-secondary text-[0.8125rem]">
              Last synced: {formatTime(lastSyncAt)}
            </p>
            {syncCount > 0 && (
              <span className="text-interactive text-[0.75rem]">
                ({syncCount} {syncCount === 1 ? "sync" : "synces"})
              </span>
            )}
          </div>
          <p className="text-interactive text-[0.75rem] mt-0.5">
            {getStatusText(lastSyncStatus, isSyncing)}
          </p>
        </div>
      </div>
      <div className="ml-4 flex-shrink-0">
        <button
          type="button"
          onClick={() => onSync(integrationType)}
          disabled={isSyncing}
          className={`
            inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-[0.8125rem] font-medium
            transition-colors duration-150
            ${
              isSyncing
                ? "bg-border text-interactive cursor-not-allowed"
                : "bg-interactive text-content hover:bg-interactive-hover"
            }
          `}
        >
          <RefreshCw className={`w-4 h-4 ${isSyncing ? "animate-spin" : ""}`} />
          {isSyncing ? "Syncing..." : "Sync Now"}
        </button>
      </div>
    </div>
  );
}

const DISPLAY_NAME_MAP: Record<string, string> = {
  salesforce: "Salesforce",
  hubspot: "HubSpot",
  google_calendar: "Google Calendar",
  outlook: "Outlook Calendar",
  gmail: "Gmail",
};

export function IntegrationSyncSection() {
  const { data: syncStatus, isLoading, isError } = useSyncStatus();
  const triggerSync = useTriggerSync();
  const [syncingIntegration, setSyncingIntegration] = useState<string | null>(null);

  const handleSync = async (integrationType: string) => {
    setSyncingIntegration(integrationType);
    try {
      await triggerSync.mutateAsync(integrationType);
    } finally {
      setSyncingIntegration(null);
    }
  };

  if (isLoading) {
    return (
      <div className="bg-elevated border border-border rounded-xl p-6">
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 text-interactive animate-spin" />
        </div>
      </div>
    );
  }

  if (isError || !syncStatus) {
    return (
      <div className="bg-elevated border border-border rounded-xl p-6">
        <div className="flex items-center gap-3 py-8 text-critical">
          <AlertCircle className="w-5 h-5 flex-shrink-0" />
          <p className="text-[0.875rem]">
            Failed to load sync status. Please try again.
          </p>
        </div>
      </div>
    );
  }

  if (syncStatus.length === 0) {
    return (
      <div className="bg-elevated border border-border rounded-xl p-6">
        <div className="flex items-center gap-3 py-8 text-interactive">
          <Clock className="w-5 h-5 flex-shrink-0" />
          <p className="text-[0.875rem]">
            No integrations connected. Connect an integration to see sync status.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-elevated border border-border rounded-xl p-6">
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-full bg-subtle flex items-center justify-center">
          <RefreshCw className="w-5 h-5 text-interactive" />
        </div>
        <div>
          <h2 className="text-content font-sans text-[1.125rem] font-medium">
            Integration Sync Status
          </h2>
          <p className="text-secondary text-[0.8125rem]">
            Manage sync status and manually trigger integrations to sync
          </p>
        </div>
      </div>

      <div className="space-y-1">
        {syncStatus.map((status) => (
          <SyncStatusCard
            key={status.integration_type}
            integrationType={status.integration_type}
            displayName={
              DISPLAY_NAME_MAP[status.integration_type] ?? status.integration_type
            }
            lastSyncAt={status.last_sync_at}
            lastSyncStatus={status.last_sync_status}
            syncCount={status.sync_count}
            onSync={handleSync}
            isSyncing={syncingIntegration === status.integration_type}
          />
        ))}
      </div>
    </div>
  );
}
