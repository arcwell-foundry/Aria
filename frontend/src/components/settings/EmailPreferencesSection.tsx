import { Mail, Shield, Bell, Loader2, AlertCircle } from "lucide-react";
import { useEmailPreferences, useUpdateEmailPreferences } from "@/hooks/useEmailPreferences";
import type { EmailPreferences } from "@/api/emailPreferences";

interface EmailPreferenceItemProps {
  icon: React.ReactNode;
  title: string;
  description: string;
  enabled: boolean;
  disabled?: boolean;
  tooltip?: string;
  onChange: (enabled: boolean) => void;
}

function ToggleSwitch({
  enabled,
  disabled = false,
  onChange,
}: {
  enabled: boolean;
  disabled?: boolean;
  onChange: () => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={enabled}
      disabled={disabled}
      onClick={() => !disabled && onChange()}
      className={`
        relative inline-flex h-7 w-12 shrink-0 cursor-pointer rounded-full border-2 border-transparent
        transition-colors duration-200 ease-in-out focus:outline-none focus-visible:ring-2 focus-visible:ring-interactive
        ${enabled ? "bg-interactive" : "bg-border"}
        ${disabled ? "opacity-50 cursor-not-allowed" : ""}
      `}
    >
      <span
        className={`
          pointer-events-none inline-block h-6 w-6 transform rounded-full bg-white shadow-lg ring-0
          transition duration-200 ease-in-out
          ${enabled ? "translate-x-6" : "translate-x-0"}
        `}
      />
    </button>
  );
}

function EmailPreferenceItem({
  icon,
  title,
  description,
  enabled,
  disabled = false,
  tooltip,
  onChange,
}: EmailPreferenceItemProps) {
  return (
    <div className="email-preference-item flex items-start justify-between py-4 border-b border-border last:border-b-0">
      <div className="flex items-start gap-3 flex-1">
        <div className="w-10 h-10 rounded-full bg-subtle flex items-center justify-center flex-shrink-0">
          {icon}
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h3 className="text-content font-sans text-[0.9375rem] font-medium">
              {title}
            </h3>
            {disabled && tooltip && (
              <div className="group relative">
                <button
                  type="button"
                  className="text-interactive hover:text-interactive-hover transition-colors duration-150"
                  aria-label={`More information about ${title}`}
                >
                  <AlertCircle className="w-4 h-4" />
                </button>
                <div className="absolute left-1/2 -translate-x-1/2 bottom-full mb-2 px-3 py-2 bg-subtle border border-border rounded-lg text-secondary text-[0.75rem] whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity duration-150 pointer-events-none z-10">
                  {tooltip}
                  <div className="absolute top-full left-1/2 -translate-x-1/2 -mt-0.5">
                    <div className="border-4 border-transparent border-t-border" />
                  </div>
                </div>
              </div>
            )}
          </div>
          <p className="text-secondary text-[0.8125rem] mt-0.5">{description}</p>
        </div>
      </div>
      <div className="ml-4 flex-shrink-0">
        <ToggleSwitch
          enabled={enabled}
          disabled={disabled}
          onChange={() => onChange(!enabled)}
        />
      </div>
    </div>
  );
}

export function EmailPreferencesSection() {
  const {
    data: preferences,
    isLoading,
    isError,
  } = useEmailPreferences();
  const updatePreferences = useUpdateEmailPreferences();

  const handleToggle = async (
    key: keyof EmailPreferences,
    value: boolean
  ) => {
    updatePreferences.mutate({
      [key]: value,
    });
  };

  if (isLoading) {
    return (
      <div className="bg-elevated border border-border rounded-xl p-6">
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 text-interactive animate-spin" data-testid="loading-spinner" />
        </div>
      </div>
    );
  }

  if (isError || !preferences) {
    return (
      <div className="bg-elevated border border-border rounded-xl p-6">
        <div className="flex items-center gap-3 py-8 text-critical">
          <AlertCircle className="w-5 h-5 flex-shrink-0" />
          <p className="text-[0.875rem]">
            Failed to load email preferences. Please try again.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="email-preferences-section bg-elevated border border-border rounded-xl p-6">
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-full bg-subtle flex items-center justify-center">
          <Mail className="w-5 h-5 text-interactive" />
        </div>
        <div>
          <h2 className="text-content font-sans text-[1.125rem] font-medium">
            Email Notifications
          </h2>
          <p className="text-secondary text-[0.8125rem]">
            Manage which emails you receive from ARIA
          </p>
        </div>
      </div>

      <div className="space-y-1">
        <EmailPreferenceItem
          icon={<Bell className="w-5 h-5 text-interactive" />}
          title="Weekly Summary"
          description="Receive a weekly digest of your ARIA activity and insights"
          enabled={preferences.weekly_summary}
          onChange={(enabled) => handleToggle("weekly_summary", enabled)}
        />

        <EmailPreferenceItem
          icon={<Bell className="w-5 h-5 text-interactive" />}
          title="Feature Announcements"
          description="Stay updated with new features and improvements"
          enabled={preferences.feature_announcements}
          onChange={(enabled) => handleToggle("feature_announcements", enabled)}
        />

        <EmailPreferenceItem
          icon={<Shield className="w-5 h-5 text-success" />}
          title="Security Alerts"
          description="Important security notifications about your account"
          enabled={preferences.security_alerts}
          disabled={true}
          tooltip="Security alerts cannot be disabled as they are essential for account safety"
          onChange={() => {}}
        />
      </div>
    </div>
  );
}
