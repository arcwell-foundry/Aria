import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { IntegrationType, IntegrationStatus } from "@/api/integrations";
import { DashboardLayout } from "@/components/DashboardLayout";
import {
  useIntegrations,
  useAvailableIntegrations,
  useConnectIntegration,
  useDisconnectIntegration,
} from "@/hooks/useIntegrations";

// Integration metadata
const integrationMetadata: Record<
  IntegrationType,
  { displayName: string; description: string; icon: string; color: string }
> = {
  google_calendar: {
    displayName: "Google Calendar",
    description: "Sync your calendar for intelligent scheduling",
    icon: "calendar",
    color: "bg-blue-500",
  },
  gmail: {
    displayName: "Gmail",
    description: "Analyze communications for insights",
    icon: "mail",
    color: "bg-red-500",
  },
  outlook: {
    displayName: "Microsoft Outlook",
    description: "Calendar and email integration",
    icon: "calendar",
    color: "bg-blue-600",
  },
  salesforce: {
    displayName: "Salesforce",
    description: "CRM integration for lead intelligence",
    icon: "database",
    color: "bg-sky-500",
  },
  hubspot: {
    displayName: "HubSpot",
    description: "Marketing and CRM platform",
    icon: "hub",
    color: "bg-orange-500",
  },
};

// Status badge component
function StatusBadge({ status }: { status: IntegrationStatus }) {
  const statusConfig = {
    active: {
      label: "Connected",
      color: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
      dotColor: "bg-emerald-400",
    },
    disconnected: {
      label: "Disconnected",
      color: "bg-slate-500/10 text-slate-400 border-slate-500/20",
      dotColor: "bg-slate-400",
    },
    error: {
      label: "Error",
      color: "bg-red-500/10 text-red-400 border-red-500/20",
      dotColor: "bg-red-400",
    },
    pending: {
      label: "Pending",
      color: "bg-amber-500/10 text-amber-400 border-amber-500/20",
      dotColor: "bg-amber-400",
    },
  };

  const config = statusConfig[status];

  return (
    <motion.span
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${config.color}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${config.dotColor}`} />
      {config.label}
    </motion.span>
  );
}

// Integration icon component
function IntegrationIcon({ type, className = "" }: { type: IntegrationType; className?: string }) {
  const metadata = integrationMetadata[type];

  const icons: Record<string, React.ReactNode> = {
    calendar: (
      <svg
        className={`w-6 h-6 ${className}`}
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
        />
      </svg>
    ),
    mail: (
      <svg
        className={`w-6 h-6 ${className}`}
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
        />
      </svg>
    ),
    database: (
      <svg
        className={`w-6 h-6 ${className}`}
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4"
        />
      </svg>
    ),
    hub: (
      <svg
        className={`w-6 h-6 ${className}`}
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M13 10V3L4 14h7v7l9-11h-7z"
        />
      </svg>
    ),
  };

  return (
    <div className={`p-3 rounded-xl ${metadata.color} bg-opacity-20`}>
      {icons[metadata.icon] || icons.database}
    </div>
  );
}

// Integration card component
interface IntegrationCardProps {
  type: IntegrationType;
  isConnected: boolean;
  status?: IntegrationStatus;
  lastSync?: string | null;
  onConnect: (type: IntegrationType) => void;
  onDisconnect: (type: IntegrationType) => void;
  isPending: boolean;
}

function IntegrationCard({
  type,
  isConnected,
  status,
  lastSync,
  onConnect,
  onDisconnect,
  isPending,
}: IntegrationCardProps) {
  const metadata = integrationMetadata[type];

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ duration: 0.2 }}
      className="relative group"
    >
      <div className="relative bg-slate-800/50 backdrop-blur-sm border border-slate-700/50 rounded-2xl p-6 hover:border-slate-600/50 transition-all duration-300">
        {/* Subtle gradient glow on hover */}
        <div className="absolute inset-0 bg-gradient-to-br from-slate-700/20 to-transparent rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />

        <div className="relative">
          <div className="flex items-start gap-4">
            <IntegrationIcon type={type} />

            <div className="flex-1 min-w-0">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1">
                  <h3 className="text-lg font-semibold text-white mb-1">
                    {metadata.displayName}
                  </h3>
                  <p className="text-sm text-slate-400 mb-3">
                    {metadata.description}
                  </p>
                </div>

                {isConnected && status && <StatusBadge status={status} />}
              </div>

              {isConnected && lastSync && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="text-xs text-slate-500 mb-4"
                >
                  Last synced: {new Date(lastSync).toLocaleDateString()} at{" "}
                  {new Date(lastSync).toLocaleTimeString()}
                </motion.div>
              )}

              <div className="flex items-center gap-3">
                {isConnected ? (
                  <>
                    <button
                      onClick={() => onDisconnect(type)}
                      disabled={isPending}
                      className="px-4 py-2 text-sm font-medium text-slate-300 hover:text-white hover:bg-slate-700/50 rounded-lg transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      Disconnect
                    </button>
                    <button
                      disabled={isPending}
                      className="px-4 py-2 text-sm font-medium bg-primary-600 hover:bg-primary-500 text-white rounded-lg transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-primary-600/25"
                    >
                      {isPending ? "Connecting..." : "Manage"}
                    </button>
                  </>
                ) : (
                  <button
                    onClick={() => onConnect(type)}
                    disabled={isPending}
                    className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium bg-primary-600 hover:bg-primary-500 text-white rounded-lg transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-primary-600/25"
                  >
                    {isPending ? (
                      <>
                        <motion.svg
                          className="w-4 h-4"
                          animate={{ rotate: 360 }}
                          transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
                          viewBox="0 0 24 24"
                          fill="none"
                        >
                          <circle
                            className="opacity-25"
                            cx="12"
                            cy="12"
                            r="10"
                            stroke="currentColor"
                            strokeWidth="4"
                          />
                          <path
                            className="opacity-75"
                            fill="currentColor"
                            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                          />
                        </motion.svg>
                        Connecting...
                      </>
                    ) : (
                      <>
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M12 4v16m8-8H4"
                          />
                        </svg>
                        Connect
                      </>
                    )}
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );
}

// Loading skeleton
function IntegrationCardSkeleton() {
  return (
    <div className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6">
      <div className="flex items-start gap-4">
        <div className="w-12 h-12 bg-slate-700 rounded-xl animate-pulse" />
        <div className="flex-1 space-y-3">
          <div className="h-5 bg-slate-700 rounded w-1/3 animate-pulse" />
          <div className="h-4 bg-slate-700 rounded w-2/3 animate-pulse" />
          <div className="h-8 bg-slate-700 rounded w-24 animate-pulse" />
        </div>
      </div>
    </div>
  );
}

// Main settings page
export function IntegrationsSettingsPage() {
  const [integrationToConnect, setIntegrationToConnect] =
    useState<IntegrationType | null>(null);

  // Queries
  const { data: integrations, isLoading: isLoadingIntegrations } = useIntegrations();
  const { data: availableIntegrations, isLoading: isLoadingAvailable } =
    useAvailableIntegrations();

  // Mutations
  const connectMutation = useConnectIntegration();
  const disconnectMutation = useDisconnectIntegration();

  // Create a map of connected integrations
  const connectedIntegrationsMap = new Map<IntegrationType, boolean>();
  const integrationStatusMap = new Map<IntegrationType, IntegrationStatus>();
  const lastSyncMap = new Map<IntegrationType, string | null>();

  integrations?.forEach((integration) => {
    connectedIntegrationsMap.set(integration.integration_type, true);
    integrationStatusMap.set(integration.integration_type, integration.status);
    lastSyncMap.set(integration.integration_type, integration.last_sync_at);
  });

  // Handle connect
  const handleConnect = async (type: IntegrationType) => {
    setIntegrationToConnect(type);

    try {
      // Get redirect URI
      const redirectUri = `${window.location.origin}/settings/integrations/callback`;

      // In a real app, you'd call getAuthUrl first
      // For now, we'll simulate the OAuth flow
      window.location.href = `/api/v1/integrations/${type}/auth?redirect_uri=${encodeURIComponent(redirectUri)}`;
    } catch (error) {
      console.error("Failed to initiate OAuth flow:", error);
      setIntegrationToConnect(null);
    }
  };

  // Handle disconnect
  const handleDisconnect = async (type: IntegrationType) => {
    disconnectMutation.mutate(type);
  };

  // Check if any mutation is pending
  const isPending = connectMutation.isPending || disconnectMutation.isPending;

  return (
    <DashboardLayout>
      <div className="relative">
        {/* Background pattern */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-800 via-slate-900 to-slate-900 pointer-events-none" />

        <div className="relative max-w-5xl mx-auto px-4 py-8 lg:px-8">
          {/* Header */}
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="mb-8"
          >
            <h1 className="text-3xl font-bold text-white mb-2">Integrations</h1>
            <p className="text-slate-400">
              Connect your favorite tools to unlock ARIA's full potential
            </p>
          </motion.div>

          {/* Info banner */}
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.1 }}
            className="mb-8 p-4 bg-primary-500/10 border border-primary-500/20 rounded-xl"
          >
            <div className="flex items-start gap-3">
              <svg
                className="w-5 h-5 text-primary-400 mt-0.5 flex-shrink-0"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              <div className="flex-1">
                <p className="text-sm text-primary-300">
                  Connected integrations allow ARIA to access your data and provide
                  intelligent insights. Your credentials are securely stored and never
                  shared.
                </p>
              </div>
            </div>
          </motion.div>

          {/* Loading state */}
          {isLoadingIntegrations || isLoadingAvailable ? (
            <div className="grid gap-4 md:grid-cols-2">
              {[1, 2, 3, 4].map((i) => (
                <IntegrationCardSkeleton key={i} />
              ))}
            </div>
          ) : (
            /* Integrations grid */
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.3 }}
              className="grid gap-4 md:grid-cols-2"
            >
              <AnimatePresence>
                {availableIntegrations?.map((available, index) => (
                  <motion.div
                    key={available.integration_type}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.3, delay: index * 0.05 }}
                  >
                    <IntegrationCard
                      type={available.integration_type}
                      isConnected={available.is_connected}
                      status={integrationStatusMap.get(available.integration_type)}
                      lastSync={lastSyncMap.get(available.integration_type)}
                      onConnect={handleConnect}
                      onDisconnect={handleDisconnect}
                      isPending={
                        isPending && integrationToConnect === available.integration_type
                      }
                    />
                  </motion.div>
                ))}
              </AnimatePresence>
            </motion.div>
          )}

          {/* Empty state */}
          {!isLoadingIntegrations &&
            !isLoadingAvailable &&
            (!availableIntegrations || availableIntegrations.length === 0) && (
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="text-center py-16"
              >
                <div className="w-16 h-16 bg-slate-800 rounded-full flex items-center justify-center mx-auto mb-4">
                  <svg
                    className="w-8 h-8 text-slate-600"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M13 10V3L4 14h7v7l9-11h-7z"
                    />
                  </svg>
                </div>
                <h3 className="text-lg font-semibold text-white mb-2">
                  No integrations available
                </h3>
                <p className="text-slate-400">
                  Integrations will appear here once they are configured.
                </p>
              </motion.div>
            )}
        </div>
      </div>
    </DashboardLayout>
  );
}
