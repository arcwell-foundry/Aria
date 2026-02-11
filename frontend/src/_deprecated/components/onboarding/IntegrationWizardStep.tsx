import { type JSX, useState, useEffect } from "react";
import {
  AlertTriangle,
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
  saveIntegrationPreferences,
  type IntegrationAppName,
  type IntegrationStatus,
} from "@/api/onboarding";

interface IntegrationWizardStepProps {
  onComplete: () => void;
}

// Inline SVG logos at 32x32
function SalesforceLogo() {
  return (
    <svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M13.3 6.7c1.2-1.3 2.9-2 4.7-2 2.3 0 4.3 1.2 5.5 3 1-.5 2.1-.7 3.2-.7 4.1 0 7.3 3.3 7.3 7.3 0 4.1-3.3 7.3-7.3 7.3-.5 0-1.1-.1-1.6-.2-1 1.7-2.9 2.9-5 2.9-1 0-1.9-.2-2.7-.7-1.1 2-3.2 3.4-5.7 3.4-2.8 0-5.2-1.8-6.1-4.3-.5.1-1 .2-1.5.2C1.8 22.9 0 20.2 0 17c0-2.4 1.3-4.5 3.2-5.7-.2-.7-.3-1.4-.3-2.1C2.9 5.1 6.1 2 10 2c1.3 0 2.4.3 3.3 1 0 0 0 3.7 0 3.7z" fill="#00A1E0"/>
    </svg>
  );
}

function HubSpotLogo() {
  return (
    <svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M23.5 13.2V9.6c1-.5 1.7-1.5 1.7-2.7V6.8c0-1.7-1.4-3-3-3h-.1c-1.7 0-3 1.4-3 3v.1c0 1.2.7 2.2 1.7 2.7v3.6c-1.5.3-2.8 1-3.9 1.9l-10.3-8c.1-.3.2-.7.2-1.1 0-1.8-1.5-3.2-3.2-3.2C2 5.8.5 7.2.5 9s1.5 3.2 3.2 3.2c.6 0 1.2-.2 1.7-.5l10.1 7.9c-1 1.2-1.6 2.8-1.6 4.5 0 3.9 3.1 7 7 7s7-3.1 7-7c0-3.5-2.6-6.4-6.4-6.9zm-2.6 10.7c-2.1 0-3.8-1.7-3.8-3.8s1.7-3.8 3.8-3.8 3.8 1.7 3.8 3.8-1.7 3.8-3.8 3.8z" fill="#FF7A59"/>
    </svg>
  );
}

function GoogleCalendarLogo() {
  return (
    <svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="4" y="6" width="24" height="22" rx="2" fill="#FFFFFF"/>
      <rect x="4" y="6" width="24" height="6" rx="2" fill="#4285F4"/>
      <rect x="9" y="4" width="2" height="4" rx="1" fill="#4285F4"/>
      <rect x="21" y="4" width="2" height="4" rx="1" fill="#4285F4"/>
      <rect x="8" y="15" width="4" height="3" rx="0.5" fill="#EA4335"/>
      <rect x="14" y="15" width="4" height="3" rx="0.5" fill="#FBBC04"/>
      <rect x="20" y="15" width="4" height="3" rx="0.5" fill="#34A853"/>
      <rect x="8" y="21" width="4" height="3" rx="0.5" fill="#4285F4"/>
      <rect x="14" y="21" width="4" height="3" rx="0.5" fill="#34A853"/>
      <rect x="20" y="21" width="4" height="3" rx="0.5" fill="#EA4335"/>
    </svg>
  );
}

function OutlookLogo() {
  return (
    <svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M19 4v8.5l8-4.5V6c0-1.1-.9-2-2-2h-6z" fill="#0364B8"/>
      <path d="M19 12.5L27 8v14c0 1.1-.9 2-2 2H19V12.5z" fill="#0078D4"/>
      <path d="M19 24h6c1.1 0 2-.9 2-2v-2l-8 4z" fill="#1490DF"/>
      <path d="M3 8c0-1.1.9-2 2-2h12v20H5c-1.1 0-2-.9-2-2V8z" fill="#0078D4"/>
      <ellipse cx="11" cy="16" rx="4.5" ry="5" fill="#FFFFFF" fillOpacity="0.9"/>
      <ellipse cx="11" cy="16" rx="3" ry="3.5" stroke="#0078D4" strokeWidth="1.5" fill="none"/>
    </svg>
  );
}

function SlackLogo() {
  return (
    <svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M7.5 18.5c0 1.4-1.1 2.5-2.5 2.5S2.5 19.9 2.5 18.5 3.6 16 5 16h2.5v2.5z" fill="#E01E5A"/>
      <path d="M8.8 18.5c0-1.4 1.1-2.5 2.5-2.5s2.5 1.1 2.5 2.5v6.2c0 1.4-1.1 2.5-2.5 2.5s-2.5-1.1-2.5-2.5v-6.2z" fill="#E01E5A"/>
      <path d="M11.3 7.5C9.9 7.5 8.8 6.4 8.8 5s1.1-2.5 2.5-2.5 2.5 1.1 2.5 2.5v2.5h-2.5z" fill="#36C5F0"/>
      <path d="M11.3 8.8c1.4 0 2.5 1.1 2.5 2.5s-1.1 2.5-2.5 2.5H5c-1.4 0-2.5-1.1-2.5-2.5s1.1-2.5 2.5-2.5h6.3z" fill="#36C5F0"/>
      <path d="M22.3 11.3c0-1.4 1.1-2.5 2.5-2.5s2.5 1.1 2.5 2.5-1.1 2.5-2.5 2.5h-2.5v-2.5z" fill="#2EB67D"/>
      <path d="M21 11.3c0 1.4-1.1 2.5-2.5 2.5s-2.5-1.1-2.5-2.5V5c0-1.4 1.1-2.5 2.5-2.5S21 3.6 21 5v6.3z" fill="#2EB67D"/>
      <path d="M18.5 22.3c1.4 0 2.5 1.1 2.5 2.5s-1.1 2.5-2.5 2.5-2.5-1.1-2.5-2.5v-2.5h2.5z" fill="#ECB22E"/>
      <path d="M18.5 21c-1.4 0-2.5-1.1-2.5-2.5s1.1-2.5 2.5-2.5h6.2c1.4 0 2.5 1.1 2.5 2.5S26.1 21 24.7 21h-6.2z" fill="#ECB22E"/>
    </svg>
  );
}

// Map provider names to their logo components
const PROVIDER_LOGOS: Record<string, () => JSX.Element> = {
  SALESFORCE: SalesforceLogo,
  HUBSPOT: HubSpotLogo,
  GOOGLECALENDAR: GoogleCalendarLogo,
  OUTLOOK365CALENDAR: OutlookLogo,
  SLACK: SlackLogo,
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
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

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
    setErrorMessage(null);
    try {
      const response = await connectIntegration(appName);
      if (response.status === "error") {
        setErrorMessage(response.message ?? "Failed to initiate connection.");
        setConnecting(null);
        return;
      }
      if (response.status === "pending" && response.auth_url) {
        sessionStorage.setItem("pending_integration", appName);
        sessionStorage.setItem("pending_connection_id", response.connection_id);
        sessionStorage.setItem("pending_integration_origin", "onboarding");
        window.location.href = response.auth_url;
      }
    } catch (error) {
      console.error("Failed to connect integration:", error);
      setErrorMessage("Unable to connect. Please try again.");
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
    const LogoComponent = PROVIDER_LOGOS[integration.name];
    const isConnecting = connecting === integration.name;
    const isDisconnecting = disconnecting === integration.name;

    return (
      <div
        key={integration.name}
        className={`
          relative bg-[#161B2E] border rounded-xl p-4 flex items-center justify-between
          transition-all duration-[250ms]
          ${
            integration.connected
              ? "border-[#6B8F71]"
              : "border-[#2A2F42] hover:border-[#7B8EAA] hover:shadow-lg"
          }
        `}
      >
        {integration.connected && (
          <div className="absolute top-2 right-2">
            <div className="flex items-center gap-1.5 bg-[#6B8F71]/20 text-[#6B8F71] rounded-full px-2 py-0.5 text-[11px] font-medium font-sans">
              <Check size={10} strokeWidth={2} />
              Connected
            </div>
          </div>
        )}

        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg flex items-center justify-center bg-[#1E2235]">
            {LogoComponent ? <LogoComponent /> : null}
          </div>

          <div className="flex flex-col gap-0.5">
            <span className="font-sans text-[15px] font-medium text-[#E8E6E1]">
              {integration.display_name}
            </span>
            {!integration.connected && (
              <span className="font-sans text-[13px] text-[#8B92A5]">
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
              className="text-[13px] font-sans bg-transparent border border-[#2A2F42] text-[#8B92A5] rounded-lg px-3 py-1.5 hover:border-[#A66B6B] hover:text-[#A66B6B] transition-colors duration-150 cursor-pointer focus:outline-none focus:ring-2 focus:ring-[#7B8EAA] focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isDisconnecting ? "Disconnecting..." : "Disconnect"}
            </button>
          ) : (
            <button
              type="button"
              onClick={() => handleConnect(integration.name)}
              disabled={connecting !== null}
              className={`
                font-sans text-[13px] font-medium px-3 py-1.5 rounded-lg
                transition-colors duration-150 cursor-pointer
                focus:outline-none focus:ring-2 focus:ring-[#7B8EAA] focus:ring-offset-2
                ${
                  isConnecting
                    ? "bg-[#1E2235] text-[#8B92A5]"
                    : "bg-[#7B8EAA] text-white hover:bg-[#95A5BD]"
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
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <Icon size={18} strokeWidth={1.5} className="text-[#7B8EAA]" />
            <span className="font-display text-[18px] text-[#E8E6E1]">
              {CATEGORY_LABELS[category]}
            </span>
          </div>
          <p className="font-sans text-[13px] text-[#8B92A5] ml-7">
            {CATEGORY_DESCRIPTIONS[category]}
          </p>
        </div>

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
        <h1 className="text-[32px] leading-[1.2] text-[#E8E6E1] font-display">
          Connect your tools
        </h1>
        <p className="font-sans text-[15px] leading-relaxed text-[#8B92A5]">
          The more ARIA knows, the more she can do.
        </p>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 size={24} strokeWidth={1.5} className="text-[#7B8EAA] animate-spin" />
        </div>
      ) : (
        <>
          {/* Integration sections */}
          <div className="flex flex-col gap-8">
            {renderCategory("crm", statuses.crm)}
            {renderCategory("calendar", statuses.calendar)}
            {renderCategory("messaging", statuses.messaging)}
          </div>

          {/* Error banner */}
          {errorMessage && (
            <div className="flex items-start gap-3 bg-[#A66B6B]/10 border border-[#A66B6B]/30 rounded-xl p-4">
              <AlertTriangle size={18} strokeWidth={1.5} className="text-[#A66B6B] mt-0.5 shrink-0" />
              <div className="flex flex-col gap-1">
                <span className="font-sans text-[14px] font-medium text-[#A66B6B]">
                  Connection failed
                </span>
                <p className="font-sans text-[13px] text-[#A66B6B]/80 leading-relaxed">
                  {errorMessage}
                </p>
              </div>
            </div>
          )}

          {/* ARIA quote */}
          <div className="flex flex-col gap-2 bg-[#161B2E] border border-[#2A2F42] rounded-xl p-5">
            <p className="font-display text-[15px] leading-relaxed text-[#E8E6E1] italic">
              "Each connection multiplies my effectiveness. CRM + Calendar
              together is where the magic really starts."
            </p>
            <p className="font-sans text-[13px] text-[#8B92A5]">— ARIA</p>
          </div>

          {/* Connected count indicator */}
          {totalConnected > 0 && (
            <div className="flex items-center gap-2 bg-[#6B8F71]/10 border border-[#6B8F71]/30 rounded-lg px-4 py-2.5">
              <Check size={16} strokeWidth={1.5} className="text-[#6B8F71]" />
              <span className="font-sans text-[13px] font-medium text-[#6B8F71]">
                {totalConnected} integration{totalConnected > 1 ? "s" : ""} connected
              </span>
            </div>
          )}

          {/* Actions */}
          <div className="flex flex-col gap-3 pt-2">
            <button
              type="button"
              onClick={async () => {
                try {
                  const slackChannels = statuses.messaging
                    .filter((i) => i.connected && i.name === "SLACK")
                    .map((i) => i.name);
                  await saveIntegrationPreferences({
                    slack_channels: slackChannels,
                    notification_enabled: true,
                    sync_frequency_hours: 1,
                  });
                } catch (e) {
                  console.error("Failed to save integration preferences:", e);
                }
                onComplete();
              }}
              className="bg-interactive text-white rounded-lg px-5 py-2.5 font-sans font-medium text-[15px] hover:bg-interactive-hover active:bg-interactive-hover transition-colors duration-150 cursor-pointer focus:outline-none focus:ring-2 focus:ring-interactive focus:ring-offset-2"
            >
              Continue
            </button>
            <p className="font-sans text-[13px] text-[#8B92A5] text-center">
              You can connect integrations anytime from your profile settings
            </p>
          </div>
        </>
      )}
    </div>
  );
}
