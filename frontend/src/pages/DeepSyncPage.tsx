/** DeepSync page - Integration sync management (US-942). */

import { useState } from "react";
import { Link } from "react-router-dom";
import { DashboardLayout } from "@/components/DashboardLayout";
import {
  useSyncStatus,
  useTriggerSync,
  useUpdateSyncConfig,
} from "@/hooks/useDeepSync";
import type { SyncResult } from "@/api/deepSync";

// ---------------------------------------------------------------------------
// Utility helpers
// ---------------------------------------------------------------------------

function relativeTime(dateStr: string | null): string {
  if (!dateStr) return "\u2014";
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return "Yesterday";
  if (days < 30) return `${days}d ago`;
  return `${Math.floor(days / 30)}mo ago`;
}

function futureTime(dateStr: string | null): string {
  if (!dateStr) return "\u2014";
  const diff = new Date(dateStr).getTime() - Date.now();
  if (diff <= 0) return "Now";
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `in ${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `in ${hours}h`;
  const days = Math.floor(hours / 24);
  return `in ${days}d`;
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1).replace(/_/g, " ");
}

function statusBadgeClasses(status: string | null): string {
  switch (status) {
    case "success":
      return "bg-emerald-500/20 text-emerald-400 border-emerald-500/30";
    case "failed":
      return "bg-red-500/20 text-red-400 border-red-500/30";
    case "pending":
    case "in_progress":
      return "bg-yellow-500/20 text-yellow-400 border-yellow-500/30";
    default:
      return "bg-slate-500/20 text-slate-400 border-slate-500/30";
  }
}

function formatIntervalLabel(minutes: number): string {
  if (minutes < 60) return `${minutes}m`;
  if (minutes < 1440) {
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return m > 0 ? `${h}h ${m}m` : `${h}h`;
  }
  return "24h";
}

// Labeled stops for the interval slider
const INTERVAL_STOPS = [
  { value: 5, label: "5m" },
  { value: 15, label: "15m" },
  { value: 30, label: "30m" },
  { value: 60, label: "1h" },
  { value: 120, label: "2h" },
  { value: 360, label: "6h" },
  { value: 720, label: "12h" },
  { value: 1440, label: "24h" },
];

// ---------------------------------------------------------------------------
// Inline SVG icons (no external icon library)
// ---------------------------------------------------------------------------

function SyncIcon({ className = "w-5 h-5" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="23 4 23 10 17 10" />
      <polyline points="1 20 1 14 7 14" />
      <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
    </svg>
  );
}

function ClockIcon({ className = "w-5 h-5" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  );
}

function CheckCircleIcon({ className = "w-5 h-5" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
      <polyline points="22 4 12 14.01 9 11.01" />
    </svg>
  );
}

function AlertCircleIcon({ className = "w-5 h-5" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="8" x2="12" y2="12" />
      <line x1="12" y1="16" x2="12.01" y2="16" />
    </svg>
  );
}

function SettingsIcon({ className = "w-5 h-5" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  );
}

function LinkIcon({ className = "w-5 h-5" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
      <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
    </svg>
  );
}

function DatabaseIcon({ className = "w-5 h-5" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <ellipse cx="12" cy="5" rx="9" ry="3" />
      <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
      <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Sync Result Inline Display
// ---------------------------------------------------------------------------

function SyncResultDisplay({ result }: { result: SyncResult }) {
  return (
    <div className="mt-3 bg-[#0F1117] rounded-lg p-3 border border-[#2A2F42]">
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div>
          <span className="text-[#8B92A5]">Processed</span>
          <span className="ml-2 text-[#E8E6E1] font-mono">{result.records_processed}</span>
        </div>
        <div>
          <span className="text-[#8B92A5]">Succeeded</span>
          <span className="ml-2 text-emerald-400 font-mono">{result.records_succeeded}</span>
        </div>
        <div>
          <span className="text-[#8B92A5]">Failed</span>
          <span className="ml-2 text-red-400 font-mono">{result.records_failed}</span>
        </div>
        <div>
          <span className="text-[#8B92A5]">Memory entries</span>
          <span className="ml-2 text-[#E8E6E1] font-mono">{result.memory_entries_created}</span>
        </div>
      </div>
      {result.duration_seconds != null && (
        <p className="text-xs text-[#8B92A5] mt-2">
          Completed in {result.duration_seconds.toFixed(1)}s ({(result.success_rate * 100).toFixed(0)}% success)
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Loading Skeleton
// ---------------------------------------------------------------------------

function StatusCardSkeleton() {
  return (
    <div className="bg-[#161B2E] rounded-xl border border-[#2A2F42] p-6 animate-pulse">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-10 h-10 rounded-lg bg-[#2A2F42]" />
        <div className="flex-1">
          <div className="h-4 w-24 bg-[#2A2F42] rounded mb-2" />
          <div className="h-3 w-16 bg-[#2A2F42] rounded" />
        </div>
      </div>
      <div className="space-y-3">
        <div className="h-3 w-full bg-[#2A2F42] rounded" />
        <div className="h-3 w-2/3 bg-[#2A2F42] rounded" />
      </div>
      <div className="h-9 w-full bg-[#2A2F42] rounded-lg mt-4" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function DeepSyncPage() {
  const { data: statuses, isLoading, error } = useSyncStatus();
  const triggerSync = useTriggerSync();
  const updateConfig = useUpdateSyncConfig();

  // Track sync results per integration type
  const [syncResults, setSyncResults] = useState<Record<string, SyncResult>>({});

  // Config form state
  const [syncInterval, setSyncInterval] = useState(60);
  const [autoPushEnabled, setAutoPushEnabled] = useState(true);
  const [configSaved, setConfigSaved] = useState(false);

  function handleTriggerSync(integrationType: string) {
    triggerSync.mutate(integrationType, {
      onSuccess: (result) => {
        setSyncResults((prev) => ({ ...prev, [integrationType]: result }));
      },
    });
  }

  function handleSaveConfig(e: React.FormEvent) {
    e.preventDefault();
    updateConfig.mutate(
      { sync_interval_minutes: syncInterval, auto_push_enabled: autoPushEnabled },
      {
        onSuccess: () => {
          setConfigSaved(true);
          setTimeout(() => setConfigSaved(false), 3000);
        },
      },
    );
  }

  // Find the nearest interval stop for the slider
  function snapToStop(value: number): number {
    let closest = INTERVAL_STOPS[0].value;
    let minDist = Math.abs(value - closest);
    for (const stop of INTERVAL_STOPS) {
      const dist = Math.abs(value - stop.value);
      if (dist < minDist) {
        minDist = dist;
        closest = stop.value;
      }
    }
    return closest;
  }

  const hasIntegrations = statuses && statuses.length > 0;

  return (
    <DashboardLayout>
      <div className="p-4 lg:p-8 min-h-screen bg-[#0F1117]">
        <div className="max-w-6xl mx-auto space-y-8">
          {/* ---- Header ---- */}
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-[#161B2E] border border-[#2A2F42]">
              <SyncIcon className="w-6 h-6 text-[#5B6E8A]" />
            </div>
            <div>
              <h1 className="font-display text-3xl text-[#E8E6E1]">Integration Sync</h1>
              <p className="text-sm text-[#8B92A5] mt-0.5">
                Monitor and manage data synchronization across your connected integrations
              </p>
            </div>
          </div>

          {/* ---- Error State ---- */}
          {error && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 flex items-start gap-3">
              <AlertCircleIcon className="w-5 h-5 text-red-400 mt-0.5 flex-shrink-0" />
              <div>
                <p className="text-red-400 font-medium text-sm">Failed to load sync status</p>
                <p className="text-red-400/70 text-xs mt-1">
                  {error instanceof Error ? error.message : "An unexpected error occurred. Please try again."}
                </p>
              </div>
            </div>
          )}

          {/* ---- Loading State ---- */}
          {isLoading && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              <StatusCardSkeleton />
              <StatusCardSkeleton />
              <StatusCardSkeleton />
            </div>
          )}

          {/* ---- Empty State ---- */}
          {!isLoading && !error && !hasIntegrations && (
            <div className="bg-[#161B2E] rounded-xl border border-[#2A2F42] p-12 text-center">
              <div className="inline-flex p-4 rounded-full bg-[#0F1117] border border-[#2A2F42] mb-4">
                <LinkIcon className="w-8 h-8 text-[#8B92A5]" />
              </div>
              <h2 className="text-lg font-medium text-[#E8E6E1] mb-2">
                No integrations connected
              </h2>
              <p className="text-sm text-[#8B92A5] mb-6 max-w-md mx-auto">
                Connect your CRM, email, or calendar integrations to start syncing data with ARIA.
              </p>
              <Link
                to="/settings/integrations"
                className="inline-flex items-center gap-2 px-5 py-2.5 bg-[#5B6E8A] text-white text-sm font-medium rounded-lg hover:bg-[#4A5D79] transition-colors"
              >
                <LinkIcon className="w-4 h-4" />
                Connect Integrations
              </Link>
            </div>
          )}

          {/* ---- Sync Status Cards ---- */}
          {!isLoading && hasIntegrations && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {statuses.map((status) => {
                const isSyncing =
                  triggerSync.isPending &&
                  triggerSync.variables === status.integration_type;
                const result = syncResults[status.integration_type];

                return (
                  <div
                    key={status.integration_type}
                    className="bg-[#161B2E] rounded-xl border border-[#2A2F42] p-6 flex flex-col"
                  >
                    {/* Card header */}
                    <div className="flex items-center justify-between mb-4">
                      <div className="flex items-center gap-3">
                        <div className="p-2 rounded-lg bg-[#0F1117] border border-[#2A2F42]">
                          <DatabaseIcon className="w-5 h-5 text-[#5B6E8A]" />
                        </div>
                        <div>
                          <h3 className="text-[#E8E6E1] font-medium text-sm">
                            {capitalize(status.integration_type)}
                          </h3>
                          <span
                            className={`inline-block text-xs px-2 py-0.5 rounded border mt-1 ${statusBadgeClasses(status.last_sync_status)}`}
                          >
                            {status.last_sync_status
                              ? capitalize(status.last_sync_status)
                              : "Never synced"}
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Sync details */}
                    <div className="space-y-2 mb-4 flex-1">
                      <div className="flex items-center gap-2 text-xs">
                        <ClockIcon className="w-3.5 h-3.5 text-[#8B92A5]" />
                        <span className="text-[#8B92A5]">Last sync:</span>
                        <span className="text-[#E8E6E1]">
                          {relativeTime(status.last_sync_at)}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 text-xs">
                        <ClockIcon className="w-3.5 h-3.5 text-[#8B92A5]" />
                        <span className="text-[#8B92A5]">Next sync:</span>
                        <span className="text-[#E8E6E1]">
                          {futureTime(status.next_sync_at)}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 text-xs">
                        <CheckCircleIcon className="w-3.5 h-3.5 text-[#8B92A5]" />
                        <span className="text-[#8B92A5]">Total syncs:</span>
                        <span className="text-[#E8E6E1] font-mono">
                          {status.sync_count}
                        </span>
                      </div>
                    </div>

                    {/* Sync Now button */}
                    <button
                      onClick={() => handleTriggerSync(status.integration_type)}
                      disabled={isSyncing}
                      className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-[#5B6E8A] text-white text-sm font-medium rounded-lg hover:bg-[#4A5D79] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      <SyncIcon className={`w-4 h-4 ${isSyncing ? "animate-spin" : ""}`} />
                      {isSyncing ? "Syncing..." : "Sync Now"}
                    </button>

                    {/* Sync result inline */}
                    {result && <SyncResultDisplay result={result} />}

                    {/* Sync error */}
                    {triggerSync.isError &&
                      triggerSync.variables === status.integration_type && (
                        <div className="mt-3 bg-red-500/10 border border-red-500/30 rounded-lg p-3">
                          <p className="text-xs text-red-400">
                            Sync failed:{" "}
                            {triggerSync.error instanceof Error
                              ? triggerSync.error.message
                              : "Unknown error"}
                          </p>
                        </div>
                      )}
                  </div>
                );
              })}
            </div>
          )}

          {/* ---- Sync Configuration ---- */}
          {!isLoading && hasIntegrations && (
            <div className="bg-[#161B2E] rounded-xl border border-[#2A2F42] p-6">
              <div className="flex items-center gap-3 mb-6">
                <SettingsIcon className="w-5 h-5 text-[#5B6E8A]" />
                <h2 className="text-lg font-medium text-[#E8E6E1]">
                  Sync Configuration
                </h2>
              </div>

              <form onSubmit={handleSaveConfig} className="space-y-6">
                {/* Sync interval */}
                <div>
                  <label className="block text-sm font-medium text-[#E8E6E1] mb-2">
                    Sync Interval
                  </label>
                  <p className="text-xs text-[#8B92A5] mb-3">
                    How often ARIA automatically pulls data from your integrations.
                    Current: <span className="text-[#E8E6E1] font-mono">{formatIntervalLabel(syncInterval)}</span>
                  </p>
                  <input
                    type="range"
                    min={5}
                    max={1440}
                    step={1}
                    value={syncInterval}
                    onChange={(e) => setSyncInterval(snapToStop(parseInt(e.target.value, 10)))}
                    className="w-full h-2 bg-[#2A2F42] rounded-lg appearance-none cursor-pointer accent-[#5B6E8A]"
                  />
                  <div className="flex justify-between mt-2">
                    {INTERVAL_STOPS.map((stop) => (
                      <button
                        key={stop.value}
                        type="button"
                        onClick={() => setSyncInterval(stop.value)}
                        className={`text-xs px-1.5 py-0.5 rounded transition-colors ${
                          syncInterval === stop.value
                            ? "text-[#E8E6E1] bg-[#5B6E8A]/30"
                            : "text-[#8B92A5] hover:text-[#E8E6E1]"
                        }`}
                      >
                        {stop.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Auto-push toggle */}
                <div className="flex items-center justify-between py-3 border-t border-[#2A2F42]">
                  <div>
                    <label
                      htmlFor="auto-push-toggle"
                      className="text-sm font-medium text-[#E8E6E1] cursor-pointer"
                    >
                      Auto-push changes
                    </label>
                    <p className="text-xs text-[#8B92A5] mt-0.5">
                      Automatically push ARIA updates back to your CRM and integrations
                    </p>
                  </div>
                  <label
                    htmlFor="auto-push-toggle"
                    className="relative inline-flex items-center cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      id="auto-push-toggle"
                      checked={autoPushEnabled}
                      onChange={(e) => setAutoPushEnabled(e.target.checked)}
                      className="sr-only peer"
                    />
                    <div className="w-11 h-6 bg-[#2A2F42] peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-[#5B6E8A] rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-[#5B6E8A]" />
                  </label>
                </div>

                {/* Save button */}
                <div className="flex items-center gap-3 pt-2">
                  <button
                    type="submit"
                    disabled={updateConfig.isPending}
                    className="px-5 py-2.5 bg-[#5B6E8A] text-white text-sm font-medium rounded-lg hover:bg-[#4A5D79] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    {updateConfig.isPending ? "Saving..." : "Save Configuration"}
                  </button>

                  {/* Success toast */}
                  {configSaved && (
                    <div className="flex items-center gap-2 text-sm text-emerald-400">
                      <CheckCircleIcon className="w-4 h-4" />
                      Configuration saved
                    </div>
                  )}

                  {/* Error message */}
                  {updateConfig.isError && (
                    <div className="flex items-center gap-2 text-sm text-red-400">
                      <AlertCircleIcon className="w-4 h-4" />
                      {updateConfig.error instanceof Error
                        ? updateConfig.error.message
                        : "Failed to save configuration"}
                    </div>
                  )}
                </div>
              </form>
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
