import { useState, useEffect } from "react";
import {
  Check,
  Loader2,
  Link as LinkIcon,
  Calendar,
  MessageSquare,
} from "lucide-react";
import {
  getIntegrationWizardStatus,
  connectIntegration,
  disconnectIntegration,
  type IntegrationAppName,
  type IntegrationStatus,
} from "@/api/onboarding";

interface IntegrationWizardStepProps {
  onComplete: () => void;
}

// Provider display configuration
const PROVIDER_CONFIG = {
  SALESFORCE: { icon: "SF", color: "text-[#00A1E0]" },
  HUBSPOT: { icon: "H", color: "text-[#FF7A59]" },
  GOOGLECALENDAR: { icon: "G", color: "text-[#4285F4]" },
  OUTLOOK365CALENDAR: { icon: "O", color: "text-[#0078D4]" },
  SLACK: { icon: "S", color: "text-[#4A154B]" },
};

const CATEGORY_ICONS = {
  crm: LinkIcon,
  calendar: Calendar,
  messaging: MessageSquare,
};

const CATEGORY_LABELS = {
  crm: "CRM",
  calendar: "Calendar",
  messaging: "Messaging",
};

const CATEGORY_DESCRIPTIONS = {
  crm: "Pipeline visibility, deal tracking, contact enrichment",
  calendar: "Meeting prep, scheduling intelligence, availability awareness",
  messaging: "Team context, communication patterns, channel monitoring",
};

export function IntegrationWizardStep({
  onComplete,
}: IntegrationWizardStepProps) {
  const [statuses, setStatuses] = useState<{
    crm: IntegrationStatus[];
    calendar: IntegrationStatus[];
    messaging: IntegrationStatus[];
  }>({ crm: [], calendar: [], messaging: [] });
  const [connecting, setConnecting] = useState<IntegrationAppName | null>(null);
  const [disconnecting, setDisconnecting] = useState<IntegrationAppName | null>(
    null
  );
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadStatuses();
  }, []);

  const loadStatuses = async () => {
    setLoading(true);
    try {
      const response = await getIntegrationWizardStatus();
      setStatuses({
        crm: response.crm,
        calendar: response.calendar,
        messaging: response.messaging,
      });
    } catch (error) {
      console.error("Failed to load integration statuses:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleConnect = async (appName: IntegrationAppName) => {
    setConnecting(appName);
    try {
      const response = await connectIntegration(appName);
      if (response.status === "pending" && response.auth_url) {
        // Redirect to OAuth flow
        window.location.href = response.auth_url;
      }
    } catch (error) {
      console.error("Failed to connect integration:", error);
      setConnecting(null);
    }
  };

  const handleDisconnect = async (appName: IntegrationAppName) => {
    setDisconnecting(appName);
    try {
      await disconnectIntegration(appName);
      await loadStatuses();
    } catch (error) {
      console.error("Failed to disconnect integration:", error);
    } finally {
      setDisconnecting(null);
    }
  };

  const renderProviderCard = (integration: IntegrationStatus) => {
    const config = PROVIDER_CONFIG[integration.name];
    const isConnecting = connecting === integration.name;
    const isDisconnecting = disconnecting === integration.name;

    return (
      <div
        key={integration.name}
        className={`
          relative bg-white border rounded-xl p-4 flex items-center justify-between
          transition-all duration-200
          ${
            integration.connected
              ? "border-success bg-success/5"
              : "border-border"
          }
        `}
      >
        {integration.connected && (
          <div className="absolute top-2 right-2">
            <div className="flex items-center gap-1.5 bg-success text-white rounded-full px-2 py-0.5 text-[11px] font-medium">
              <Check size={10} strokeWidth={2} />
              Connected
            </div>
          </div>
        )}

        <div className="flex items-center gap-3">
          {/* Logo placeholder */}
          <div
            className={`
              w-10 h-10 rounded-lg flex items-center justify-center
              font-sans font-bold text-[15px]
              ${integration.connected ? "bg-success/10" : "bg-subtle"}
              ${config.color}
            `}
          >
            {config.icon}
          </div>

          <div className="flex flex-col gap-0.5">
            <span className="font-sans text-[15px] font-medium text-content">
              {integration.display_name}
            </span>
            {!integration.connected && (
              <span className="font-sans text-[13px] text-secondary">
                Connect your account
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          {integration.connected ? (
            <button
              type="button"
              onClick={() => handleDisconnect(integration.name)}
              disabled={isDisconnecting}
              className="text-[13px] text-secondary hover:text-content transition-colors cursor-pointer focus:outline-none focus:ring-1 focus:ring-interactive rounded px-2 py-1 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isDisconnecting ? "Disconnecting..." : "Disconnect"}
            </button>
          ) : (
            <button
              type="button"
              onClick={() => handleConnect(integration.name)}
              disabled={isConnecting !== null}
              className={`
                font-sans text-[13px] font-medium px-3 py-1.5 rounded-lg
                transition-colors duration-150 cursor-pointer
                focus:outline-none focus:ring-2 focus:ring-interactive focus:ring-offset-2
                ${
                  isConnecting
                    ? "bg-subtle text-secondary"
                    : "bg-interactive text-white hover:bg-interactive-hover"
                }
                disabled:opacity-50 disabled:cursor-not-allowed
              `}
            >
              {isConnecting ? "Connecting..." : "Connect"}
            </button>
          )}
        </div>
      </div>
    );
  };

  const renderCategory = (
    category: keyof typeof CATEGORY_LABELS,
    integrations: IntegrationStatus[]
  ) => {
    if (integrations.length === 0) return null;

    const Icon = CATEGORY_ICONS[category];

    return (
      <div className="flex flex-col gap-4">
        {/* Category header */}
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <Icon size={18} strokeWidth={1.5} className="text-interactive" />
            <span className="font-sans text-[15px] font-medium text-content">
              {CATEGORY_LABELS[category]}
            </span>
          </div>
          <p className="font-sans text-[13px] text-secondary ml-7">
            {CATEGORY_DESCRIPTIONS[category]}
          </p>
        </div>

        {/* Provider cards */}
        <div className="grid grid-cols-2 gap-3">
          {integrations.map((integration) => renderProviderCard(integration))}
        </div>
      </div>
    );
  };

  const totalConnected =
    statuses.crm.filter((i) => i.connected).length +
    statuses.calendar.filter((i) => i.connected).length +
    statuses.messaging.filter((i) => i.connected).length;

  return (
    <div className="flex flex-col gap-8 max-w-2xl animate-in fade-in slide-in-from-bottom-4 duration-400">
      {/* Header */}
      <div className="flex flex-col gap-3">
        <h1 className="text-[32px] leading-[1.2] text-content font-display">
          Connect your tools
        </h1>
        <p className="font-sans text-[15px] leading-relaxed text-secondary">
          The more ARIA knows, the more she can do.
        </p>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 size={24} strokeWidth={1.5} className="text-interactive animate-spin" />
        </div>
      ) : (
        <>
          {/* Integration sections */}
          <div className="flex flex-col gap-8">
            {renderCategory("crm", statuses.crm)}
            {renderCategory("calendar", statuses.calendar)}
            {renderCategory("messaging", statuses.messaging)}
          </div>

          {/* ARIA presence */}
          <div className="flex flex-col gap-2 bg-subtle border border-border rounded-xl p-5">
            <p className="font-sans text-[15px] leading-relaxed text-content italic">
              "Each connection multiplies my effectiveness. CRM + Calendar
              together is where the magic really starts."
            </p>
            <p className="font-sans text-[13px] text-secondary">— ARIA</p>
          </div>

          {/* Connected count indicator */}
          {totalConnected > 0 && (
            <div className="flex items-center gap-2 bg-success/10 border border-success rounded-lg px-4 py-2.5">
              <Check size={16} strokeWidth={1.5} className="text-success" />
              <span className="font-sans text-[13px] font-medium text-success">
                {totalConnected} integration{totalConnected > 1 ? "s" : ""} connected
              </span>
            </div>
          )}

          {/* Actions */}
          <div className="flex flex-col gap-3 pt-2">
            <button
              type="button"
              onClick={onComplete}
              className="bg-interactive text-white rounded-lg px-5 py-2.5 font-sans font-medium hover:bg-interactive-hover transition-colors duration-150 cursor-pointer focus:outline-none focus:ring-2 focus:ring-interactive focus:ring-offset-2"
            >
              Continue
            </button>
            <p className="font-sans text-[13px] text-secondary text-center">
              You can connect integrations anytime from your profile settings
            </p>
          </div>
        </>
      )}
    </div>
  );
}
