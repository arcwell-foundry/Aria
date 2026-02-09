import { useState, useEffect } from "react";
import {
  Mail,
  Shield,
  Check,
  X,
  Loader2,
  Plus,
  ChevronDown,
} from "lucide-react";
import {
  connectEmail,
  getEmailStatus,
  saveEmailPrivacy,
  type EmailProvider,
  type PrivacyExclusion,
  type EmailIntegrationConfig,
} from "@/api/emailIntegration";

interface EmailIntegrationStepProps {
  onComplete: () => void;
  onSkip: () => void;
}

export function EmailIntegrationStep({
  onComplete,
  onSkip,
}: EmailIntegrationStepProps) {
  const [connecting, setConnecting] = useState<EmailProvider | null>(null);
  const [privacyExclusions, setPrivacyExclusions] = useState<PrivacyExclusion[]>([]);
  const [newExclusion, setNewExclusion] = useState<{
    type: "sender" | "domain" | "category";
    value: string;
  }>({ type: "sender", value: "" });
  const [ingestionScope, setIngestionScope] = useState(365);
  const [attachmentIngestion, setAttachmentIngestion] = useState(false);
  const [categoryToggles, setCategoryToggles] = useState({
    personal: false,
    financial: false,
    medical: false,
  });
  const [isSaving, setIsSaving] = useState(false);
  const [currentProvider, setCurrentProvider] = useState<EmailProvider | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(true);

  useEffect(() => {
    loadEmailStatus();
  }, []);

  const loadEmailStatus = async () => {
    setLoadingStatus(true);
    try {
      const status = await getEmailStatus();
      if (status.google.connected) setCurrentProvider("google");
      else if (status.microsoft.connected) setCurrentProvider("microsoft");
    } catch (error) {
      console.error("Failed to load email status:", error);
    } finally {
      setLoadingStatus(false);
    }
  };

  const handleConnect = async (provider: EmailProvider) => {
    setConnecting(provider);
    try {
      const response = await connectEmail(provider);
      if (response.status === "pending" && response.auth_url) {
        // Map provider to integration type for the callback page
        const typeMap: Record<string, string> = { google: "gmail", microsoft: "outlook" };
        sessionStorage.setItem("pending_integration", typeMap[provider] || provider);
        sessionStorage.setItem("pending_connection_id", response.connection_id);
        sessionStorage.setItem("pending_integration_origin", "onboarding");
        // Redirect to OAuth flow
        window.location.href = response.auth_url;
      }
    } catch (error) {
      console.error("Failed to connect email:", error);
      setConnecting(null);
    }
  };

  const handleAddExclusion = () => {
    if (!newExclusion.value.trim()) return;

    const exclusion: PrivacyExclusion = {
      type: newExclusion.type,
      value: newExclusion.value.trim(),
    };

    setPrivacyExclusions([...privacyExclusions, exclusion]);
    setNewExclusion({ type: "sender", value: "" });
  };

  const handleRemoveExclusion = (index: number) => {
    setPrivacyExclusions(privacyExclusions.filter((_, i) => i !== index));
  };

  const handleCategoryToggle = (category: keyof typeof categoryToggles) => {
    const newValue = !categoryToggles[category];
    setCategoryToggles({ ...categoryToggles, [category]: newValue });

    // Add or remove category-based exclusions
    const categoryMap = {
      personal: ["spouse/partner", "family"],
      financial: ["financial/banking"],
      medical: ["medical"],
    };

    if (newValue) {
      const newExclusions = categoryMap[category].map((value) => ({
        type: "category" as const,
        value,
      }));
      setPrivacyExclusions([...privacyExclusions, ...newExclusions]);
    } else {
      setPrivacyExclusions(
        privacyExclusions.filter(
          (e) => !categoryMap[category].includes(e.value)
        )
      );
    }
  };

  const handleComplete = async () => {
    setIsSaving(true);
    try {
      const provider = currentProvider || "google";
      const config: EmailIntegrationConfig = {
        provider,
        scopes: ["gmail.readonly"],
        privacy_exclusions: privacyExclusions,
        ingestion_scope_days: ingestionScope,
        attachment_ingestion: attachmentIngestion,
      };

      await saveEmailPrivacy(config);
      onComplete();
    } catch (error) {
      console.error("Failed to save privacy config:", error);
    } finally {
      setIsSaving(false);
    }
  };

  const isConnected = currentProvider !== null;

  return (
    <div className="flex flex-col gap-8 max-w-md animate-in fade-in slide-in-from-bottom-4 duration-400">
      {/* Header */}
      <div className="flex flex-col gap-3">
        <h1 className="text-[32px] leading-[1.2] text-content font-display">
          Connect your email
        </h1>
        <p className="font-sans text-[15px] leading-relaxed text-secondary">
          ARIA learns your communication style, relationships, and priorities from
          your email — with your privacy fully in control.
        </p>
      </div>

      {/* Provider Selection */}
      {!isConnected && !loadingStatus && (
        <div className="flex flex-col gap-4">
          <p className="font-sans text-[13px] font-medium text-content">
            Choose your email provider
          </p>
          <div className="grid grid-cols-2 gap-4">
            {/* Gmail */}
            <button
              type="button"
              onClick={() => handleConnect("google")}
              disabled={connecting !== null}
              className={`
                bg-white border rounded-xl p-5 flex flex-col items-center gap-3
                transition-all duration-200 cursor-pointer focus:outline-none
                focus:ring-2 focus:ring-interactive focus:ring-offset-2
                ${
                  connecting === "google"
                    ? "border-interactive bg-subtle"
                    : "border-border hover:border-interactive hover:shadow-sm"
                }
                disabled:opacity-50 disabled:cursor-not-allowed
              `}
            >
              <Mail size={24} strokeWidth={1.5} className="text-interactive" />
              <span className="font-sans text-[15px] font-medium text-content">
                {connecting === "google" ? "Connecting..." : "Connect"}
              </span>
              <span className="font-sans text-[13px] text-secondary">
                Google Workspace
              </span>
            </button>

            {/* Outlook */}
            <button
              type="button"
              onClick={() => handleConnect("microsoft")}
              disabled={connecting !== null}
              className={`
                bg-white border rounded-xl p-5 flex flex-col items-center gap-3
                transition-all duration-200 cursor-pointer focus:outline-none
                focus:ring-2 focus:ring-interactive focus:ring-offset-2
                ${
                  connecting === "microsoft"
                    ? "border-interactive bg-subtle"
                    : "border-border hover:border-interactive hover:shadow-sm"
                }
                disabled:opacity-50 disabled:cursor-not-allowed
              `}
            >
              <Mail size={24} strokeWidth={1.5} className="text-interactive" />
              <span className="font-sans text-[15px] font-medium text-content">
                {connecting === "microsoft" ? "Connecting..." : "Connect"}
              </span>
              <span className="font-sans text-[13px] text-secondary">
                Microsoft 365
              </span>
            </button>
          </div>
        </div>
      )}

      {/* Loading State */}
      {loadingStatus && (
        <div className="flex items-center justify-center py-12">
          <Loader2 size={24} strokeWidth={1.5} className="text-interactive animate-spin" />
        </div>
      )}

      {/* Privacy Controls - shown after connection */}
      {isConnected && (
        <>
          <div className="flex items-center gap-2 bg-success/10 border border-success rounded-lg px-4 py-2.5">
            <Check size={16} strokeWidth={1.5} className="text-success" />
            <span className="font-sans text-[13px] font-medium text-success">
              Connected to {currentProvider === "google" ? "Google Workspace" : "Microsoft 365"}
            </span>
          </div>

          {/* Privacy Controls Section */}
          <div className="flex flex-col gap-5">
            <h2 className="font-sans text-[18px] font-medium text-content">
              Your privacy controls
            </h2>

            {/* Exclusion List */}
            <div className="flex flex-col gap-3">
              <label className="font-sans text-[13px] font-medium text-secondary">
                Exclude senders or domains
              </label>
              <p className="font-sans text-[13px] text-secondary">
                We recommend excluding personal email (spouse, doctor, bank)
              </p>

              <div className="flex gap-2">
                <select
                  value={newExclusion.type}
                  onChange={(e) =>
                    setNewExclusion({
                      ...newExclusion,
                      type: e.target.value as "sender" | "domain" | "category",
                    })
                  }
                  className="bg-white border border-border rounded-lg px-3 py-2.5 text-[15px] font-sans focus:outline-none focus:border-interactive focus:ring-1 focus:ring-interactive"
                >
                  <option value="sender">Sender</option>
                  <option value="domain">Domain</option>
                  <option value="category">Category</option>
                </select>
                <input
                  type="text"
                  value={newExclusion.value}
                  onChange={(e) =>
                    setNewExclusion({ ...newExclusion, value: e.target.value })
                  }
                  placeholder={
                    newExclusion.type === "sender"
                      ? "email@example.com"
                      : newExclusion.type === "domain"
                        ? "example.com"
                        : "category name"
                  }
                  onKeyPress={(e) => e.key === "Enter" && handleAddExclusion()}
                  className="flex-1 bg-white border border-border rounded-lg px-4 py-2.5 text-[15px] font-sans focus:outline-none focus:border-interactive focus:ring-1 focus:ring-interactive"
                />
                <button
                  type="button"
                  onClick={handleAddExclusion}
                  className="bg-interactive text-white rounded-lg px-4 py-2.5 font-sans text-[13px] font-medium hover:bg-interactive-hover transition-colors duration-150 cursor-pointer focus:outline-none focus:ring-2 focus:ring-interactive focus:ring-offset-2 flex items-center gap-2"
                >
                  <Plus size={16} />
                  Add
                </button>
              </div>

              {/* Exclusion Chips */}
              {privacyExclusions.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {privacyExclusions.map((exclusion, index) => (
                    <span
                      key={index}
                      className="inline-flex items-center gap-1.5 bg-subtle border border-border rounded-lg px-3 py-1.5 text-[13px] text-content font-sans"
                    >
                      <span className="font-medium">{exclusion.type}:</span>
                      <span>{exclusion.value}</span>
                      <button
                        type="button"
                        onClick={() => handleRemoveExclusion(index)}
                        className="text-secondary hover:text-content transition-colors cursor-pointer focus:outline-none focus:ring-1 focus:ring-interactive rounded p-0.5"
                      >
                        <X size={14} strokeWidth={1.5} />
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </div>

            {/* Category Toggles */}
            <div className="flex flex-col gap-3">
              <label className="font-sans text-[13px] font-medium text-secondary">
                Suggested exclusions (auto-detected)
              </label>

              <div className="flex flex-col gap-2">
                {[
                  { key: "personal" as const, label: "Personal emails" },
                  { key: "financial" as const, label: "Financial/banking" },
                  { key: "medical" as const, label: "Medical" },
                ].map(({ key, label }) => (
                  <label
                    key={key}
                    className="flex items-center justify-between bg-white border border-border rounded-lg px-4 py-3 cursor-pointer hover:border-interactive transition-colors duration-150"
                  >
                    <span className="font-sans text-[15px] text-content">
                      {label}
                    </span>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.preventDefault();
                        handleCategoryToggle(key);
                      }}
                      className={`
                        relative w-11 h-6 rounded-full transition-colors duration-200
                        focus:outline-none focus:ring-2 focus:ring-interactive focus:ring-offset-2
                        ${
                          categoryToggles[key]
                            ? "bg-interactive"
                            : "bg-border"
                        }
                      `}
                    >
                      <span
                        className={`
                          absolute top-1 left-1 bg-white rounded-full w-4 h-4
                          transition-transform duration-200 shadow-sm
                          ${
                            categoryToggles[key]
                              ? "translate-x-5"
                              : "translate-x-0"
                          }
                        `}
                      />
                    </button>
                  </label>
                ))}
              </div>
            </div>

            {/* Ingestion Scope */}
            <div className="flex flex-col gap-2">
              <label className="font-sans text-[13px] font-medium text-secondary">
                How much email history should ARIA learn from?
              </label>
              <div className="relative">
                <select
                  value={ingestionScope}
                  onChange={(e) =>
                    setIngestionScope(Number(e.target.value))
                  }
                  className="w-full bg-white border border-border rounded-lg px-4 py-2.5 text-[15px] font-sans appearance-none focus:outline-none focus:border-interactive focus:ring-1 focus:ring-interactive cursor-pointer"
                >
                  <option value={90}>Last 3 months</option>
                  <option value={180}>Last 6 months</option>
                  <option value={365}>Last 1 year</option>
                </select>
                <ChevronDown
                  size={16}
                  strokeWidth={1.5}
                  className="absolute right-4 top-1/2 -translate-y-1/2 text-secondary pointer-events-none"
                />
              </div>
            </div>

            {/* Attachment Handling */}
            <label className="flex items-center justify-between bg-white border border-border rounded-lg px-4 py-3 cursor-pointer hover:border-interactive transition-colors duration-150">
              <div className="flex flex-col gap-0.5">
                <span className="font-sans text-[15px] text-content">
                  Also learn from attachments
                </span>
                <span className="font-sans text-[13px] text-secondary">
                  Requires per-attachment approval
                </span>
              </div>
              <button
                type="button"
                onClick={(e) => {
                  e.preventDefault();
                  setAttachmentIngestion(!attachmentIngestion);
                }}
                className={`
                  relative w-11 h-6 rounded-full transition-colors duration-200
                  focus:outline-none focus:ring-2 focus:ring-interactive focus:ring-offset-2
                  ${
                    attachmentIngestion
                      ? "bg-interactive"
                      : "bg-border"
                  }
                `}
              >
                <span
                  className={`
                    absolute top-1 left-1 bg-white rounded-full w-4 h-4
                    transition-transform duration-200 shadow-sm
                    ${
                      attachmentIngestion
                        ? "translate-x-5"
                        : "translate-x-0"
                    }
                  `}
                />
              </button>
            </label>
          </div>

          {/* Trust Statement */}
          <div className="bg-white border border-border rounded-xl p-5">
            <div className="flex gap-3">
              <Shield size={20} strokeWidth={1.5} className="text-interactive shrink-0" />
              <p className="font-sans text-[13px] leading-relaxed text-secondary">
                Your email is encrypted at rest. Content is never shared between
                users, even within your company. You can disconnect and delete all
                email data at any time.
              </p>
            </div>
          </div>

          {/* ARIA Presence */}
          <div className="flex flex-col gap-2 bg-subtle border border-border rounded-xl p-5">
            <p className="font-sans text-[15px] leading-relaxed text-content italic">
              "Email is where your professional life lives. Even with basic
              access, I'll understand your relationships, priorities, and
              communication patterns."
            </p>
            <p className="font-sans text-[13px] text-secondary">— ARIA</p>
          </div>
        </>
      )}

      {/* Actions */}
      <div className="flex flex-col gap-3 pt-2">
        {isConnected && (
          <button
            type="button"
            onClick={handleComplete}
            disabled={isSaving}
            className="bg-interactive text-white rounded-lg px-5 py-2.5 font-sans font-medium hover:bg-interactive-hover transition-colors duration-150 cursor-pointer focus:outline-none focus:ring-2 focus:ring-interactive focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {isSaving ? (
              <>
                <Loader2 size={16} strokeWidth={1.5} className="animate-spin" />
                Saving...
              </>
            ) : (
              "Continue"
            )}
          </button>
        )}

        <button
          type="button"
          onClick={onSkip}
          disabled={isSaving}
          className="bg-transparent text-secondary rounded-lg px-4 py-2 font-sans text-[13px] hover:bg-subtle transition-colors duration-150 cursor-pointer focus:outline-none focus:ring-2 focus:ring-interactive focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Skip for now — you can connect email from your profile
        </button>
      </div>
    </div>
  );
}
