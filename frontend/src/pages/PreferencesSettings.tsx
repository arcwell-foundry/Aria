import { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { DashboardLayout } from "@/components/DashboardLayout";
import { usePreferences, useUpdatePreferences } from "@/hooks/usePreferences";
import type { DefaultTone, MeetingBriefLeadHours } from "@/api/preferences";

// Lead hours options
const LEAD_HOURS_OPTIONS: { value: MeetingBriefLeadHours; label: string }[] = [
  { value: 24, label: "24 hours" },
  { value: 12, label: "12 hours" },
  { value: 6, label: "6 hours" },
  { value: 2, label: "2 hours" },
];

// Tone options
const TONE_OPTIONS: { value: DefaultTone; label: string; description: string }[] = [
  { value: "formal", label: "Formal", description: "Professional and business-like" },
  { value: "friendly", label: "Friendly", description: "Warm and approachable" },
  { value: "urgent", label: "Urgent", description: "Direct and action-oriented" },
];

// Success toast component
function SuccessToast({ show, onHide }: { show: boolean; onHide: () => void }) {
  useEffect(() => {
    if (show) {
      const timer = setTimeout(onHide, 2000);
      return () => clearTimeout(timer);
    }
  }, [show, onHide]);

  return (
    <AnimatePresence>
      {show && (
        <motion.div
          initial={{ opacity: 0, y: 50 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 50 }}
          transition={{ type: "spring", damping: 25, stiffness: 300 }}
          className="fixed bottom-6 right-6 z-50"
        >
          <div className="flex items-center gap-2 px-4 py-3 bg-emerald-500/90 backdrop-blur-sm text-white rounded-xl shadow-lg shadow-emerald-500/25">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            <span className="text-sm font-medium">Preferences saved</span>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

// Loading skeleton
function PreferencesSettingsSkeleton() {
  return (
    <div className="space-y-8">
      {[1, 2, 3, 4].map((i) => (
        <div key={i} className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6">
          <div className="h-6 bg-slate-700 rounded w-1/4 mb-4 animate-pulse" />
          <div className="space-y-3">
            <div className="h-4 bg-slate-700 rounded w-2/3 animate-pulse" />
            <div className="h-10 bg-slate-700 rounded w-full animate-pulse" />
          </div>
        </div>
      ))}
    </div>
  );
}

// Error banner
function ErrorBanner({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      className="mb-6 p-4 bg-red-500/10 border border-red-500/20 rounded-xl"
    >
      <div className="flex items-start gap-3">
        <svg className="w-5 h-5 text-red-400 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <div className="flex-1">
          <p className="text-sm text-red-300">{message}</p>
        </div>
        <button
          onClick={onRetry}
          className="px-3 py-1 text-xs font-medium bg-red-500/20 hover:bg-red-500/30 text-red-300 rounded-lg transition-colors"
        >
          Retry
        </button>
      </div>
    </motion.div>
  );
}

// Section wrapper component
function SettingsSection({
  title,
  description,
  children,
  delay = 0,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
  delay?: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay }}
      className="bg-slate-800/50 backdrop-blur-sm border border-slate-700/50 rounded-2xl p-6"
    >
      <div className="mb-4">
        <h3 className="text-lg font-semibold text-white">{title}</h3>
        {description && <p className="text-sm text-slate-400 mt-1">{description}</p>}
      </div>
      {children}
    </motion.div>
  );
}

// Toggle switch component (Apple-style)
function ToggleSwitch({
  enabled,
  onChange,
  disabled = false,
}: {
  enabled: boolean;
  onChange: (enabled: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={enabled}
      onClick={() => !disabled && onChange(!enabled)}
      disabled={disabled}
      className={`
        relative inline-flex h-7 w-12 shrink-0 cursor-pointer rounded-full border-2 border-transparent
        transition-colors duration-200 ease-in-out focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500
        ${enabled ? "bg-primary-600" : "bg-slate-600"}
        ${disabled ? "opacity-50 cursor-not-allowed" : ""}
      `}
    >
      <span
        className={`
          pointer-events-none inline-block h-6 w-6 transform rounded-full bg-white shadow-lg ring-0
          transition duration-200 ease-in-out
          ${enabled ? "translate-x-5" : "translate-x-0"}
        `}
      />
    </button>
  );
}

// Segmented control component
function SegmentedControl<T extends string>({
  value,
  options,
  onChange,
  disabled = false,
}: {
  value: T;
  options: { value: T; label: string; description?: string }[];
  onChange: (value: T) => void;
  disabled?: boolean;
}) {
  return (
    <div className="grid grid-cols-3 gap-2">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          onClick={() => !disabled && onChange(option.value)}
          disabled={disabled}
          className={`
            relative px-4 py-3 rounded-xl text-sm font-medium transition-all duration-200
            ${
              value === option.value
                ? "bg-primary-600 text-white shadow-lg shadow-primary-600/25"
                : "bg-slate-700/50 text-slate-300 hover:bg-slate-700 hover:text-white"
            }
            ${disabled ? "opacity-50 cursor-not-allowed" : ""}
          `}
        >
          <div className="text-center">
            <div>{option.label}</div>
            {option.description && (
              <div className={`text-xs mt-0.5 ${value === option.value ? "text-white/70" : "text-slate-500"}`}>
                {option.description}
              </div>
            )}
          </div>
        </button>
      ))}
    </div>
  );
}

// Competitor chip component
function CompetitorChip({
  name,
  onRemove,
  disabled = false,
}: {
  name: string;
  onRemove: () => void;
  disabled?: boolean;
}) {
  return (
    <motion.span
      layout
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.8 }}
      className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-700/50 border border-slate-600/50 rounded-full text-sm text-slate-200"
    >
      {name}
      <button
        type="button"
        onClick={onRemove}
        disabled={disabled}
        className={`
          p-0.5 rounded-full hover:bg-slate-600 transition-colors
          ${disabled ? "opacity-50 cursor-not-allowed" : ""}
        `}
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </motion.span>
  );
}

// Main page component
export function PreferencesSettingsPage() {
  const { data: preferences, isLoading, error, refetch } = usePreferences();
  const updateMutation = useUpdatePreferences();

  // Local state for form inputs
  const [briefingTime, setBriefingTime] = useState("08:00");
  const [leadHours, setLeadHours] = useState<MeetingBriefLeadHours>(24);
  const [emailNotifications, setEmailNotifications] = useState(true);
  const [inAppNotifications, setInAppNotifications] = useState(true);
  const [defaultTone, setDefaultTone] = useState<DefaultTone>("friendly");
  const [trackedCompetitors, setTrackedCompetitors] = useState<string[]>([]);
  const [newCompetitor, setNewCompetitor] = useState("");
  const [showSuccess, setShowSuccess] = useState(false);

  // Sync local state with fetched preferences
  useEffect(() => {
    if (preferences) {
      setBriefingTime(preferences.briefing_time);
      setLeadHours(preferences.meeting_brief_lead_hours);
      setEmailNotifications(preferences.notification_email);
      setInAppNotifications(preferences.notification_in_app);
      setDefaultTone(preferences.default_tone);
      setTrackedCompetitors(preferences.tracked_competitors);
    }
  }, [preferences]);

  // Auto-save handler
  const savePreference = useCallback(
    (field: string, value: unknown) => {
      updateMutation.mutate(
        { [field]: value },
        {
          onSuccess: () => {
            setShowSuccess(true);
          },
        }
      );
    },
    [updateMutation]
  );

  // Handle briefing time change
  const handleBriefingTimeChange = (time: string) => {
    setBriefingTime(time);
    savePreference("briefing_time", time);
  };

  // Handle lead hours change
  const handleLeadHoursChange = (hours: MeetingBriefLeadHours) => {
    setLeadHours(hours);
    savePreference("meeting_brief_lead_hours", hours);
  };

  // Handle notification toggles
  const handleEmailNotificationChange = (enabled: boolean) => {
    setEmailNotifications(enabled);
    savePreference("notification_email", enabled);
  };

  const handleInAppNotificationChange = (enabled: boolean) => {
    setInAppNotifications(enabled);
    savePreference("notification_in_app", enabled);
  };

  // Handle tone change
  const handleToneChange = (tone: DefaultTone) => {
    setDefaultTone(tone);
    savePreference("default_tone", tone);
  };

  // Handle competitor management
  const handleAddCompetitor = () => {
    const trimmed = newCompetitor.trim();
    if (trimmed && !trackedCompetitors.includes(trimmed)) {
      const updated = [...trackedCompetitors, trimmed];
      setTrackedCompetitors(updated);
      setNewCompetitor("");
      savePreference("tracked_competitors", updated);
    }
  };

  const handleRemoveCompetitor = (competitor: string) => {
    const updated = trackedCompetitors.filter((c) => c !== competitor);
    setTrackedCompetitors(updated);
    savePreference("tracked_competitors", updated);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleAddCompetitor();
    }
  };

  const isPending = updateMutation.isPending;

  return (
    <DashboardLayout>
      <div className="relative">
        {/* Background pattern */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-800 via-slate-900 to-slate-900 pointer-events-none" />

        <div className="relative max-w-3xl mx-auto px-4 py-8 lg:px-8">
          {/* Header */}
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="mb-8"
          >
            <h1 className="text-3xl font-bold text-white mb-2">Preferences</h1>
            <p className="text-slate-400">
              Customize how ARIA works for you
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
              <svg className="w-5 h-5 text-primary-400 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <p className="text-sm text-primary-300">
                Your preferences are saved automatically as you make changes.
              </p>
            </div>
          </motion.div>

          {/* Error banner */}
          {error && (
            <ErrorBanner
              message="Failed to load preferences. Please try again."
              onRetry={() => refetch()}
            />
          )}

          {/* Loading state */}
          {isLoading ? (
            <PreferencesSettingsSkeleton />
          ) : (
            <div className="space-y-6">
              {/* Daily Briefing Section */}
              <SettingsSection
                title="Daily Briefing"
                description="When would you like to receive your daily briefing?"
                delay={0.1}
              >
                <div className="flex items-center gap-4">
                  <label htmlFor="briefing-time" className="text-sm text-slate-300">
                    Briefing Time
                  </label>
                  <input
                    id="briefing-time"
                    type="time"
                    value={briefingTime}
                    onChange={(e) => handleBriefingTimeChange(e.target.value)}
                    disabled={isPending}
                    className="
                      px-4 py-2.5 bg-slate-900 border border-slate-700 rounded-lg text-white
                      focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent
                      disabled:opacity-50 transition-all
                    "
                  />
                </div>
              </SettingsSection>

              {/* Meeting Brief Section */}
              <SettingsSection
                title="Meeting Briefs"
                description="How early should ARIA prepare your meeting briefs?"
                delay={0.15}
              >
                <div className="space-y-3">
                  <label className="text-sm text-slate-300">Lead Time</label>
                  <div className="grid grid-cols-4 gap-2">
                    {LEAD_HOURS_OPTIONS.map((option) => (
                      <button
                        key={option.value}
                        type="button"
                        onClick={() => handleLeadHoursChange(option.value)}
                        disabled={isPending}
                        className={`
                          px-4 py-2.5 rounded-lg text-sm font-medium transition-all duration-200
                          ${
                            leadHours === option.value
                              ? "bg-primary-600 text-white shadow-lg shadow-primary-600/25"
                              : "bg-slate-700/50 text-slate-300 hover:bg-slate-700 hover:text-white"
                          }
                          disabled:opacity-50
                        `}
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>
                </div>
              </SettingsSection>

              {/* Notifications Section */}
              <SettingsSection
                title="Notifications"
                description="Choose how you want to be notified"
                delay={0.2}
              >
                <div className="space-y-4">
                  <div className="flex items-center justify-between py-2">
                    <div>
                      <div className="text-sm font-medium text-white">Email Notifications</div>
                      <div className="text-xs text-slate-400">Receive updates via email</div>
                    </div>
                    <ToggleSwitch
                      enabled={emailNotifications}
                      onChange={handleEmailNotificationChange}
                      disabled={isPending}
                    />
                  </div>
                  <div className="border-t border-slate-700/50" />
                  <div className="flex items-center justify-between py-2">
                    <div>
                      <div className="text-sm font-medium text-white">In-App Notifications</div>
                      <div className="text-xs text-slate-400">Show notifications in the app</div>
                    </div>
                    <ToggleSwitch
                      enabled={inAppNotifications}
                      onChange={handleInAppNotificationChange}
                      disabled={isPending}
                    />
                  </div>
                </div>
              </SettingsSection>

              {/* Communication Tone Section */}
              <SettingsSection
                title="Communication Style"
                description="Set the default tone for ARIA's communications"
                delay={0.25}
              >
                <SegmentedControl
                  value={defaultTone}
                  options={TONE_OPTIONS}
                  onChange={handleToneChange}
                  disabled={isPending}
                />
              </SettingsSection>

              {/* Competitors Section */}
              <SettingsSection
                title="Tracked Competitors"
                description="Add competitors you want ARIA to monitor"
                delay={0.3}
              >
                <div className="space-y-4">
                  {/* Add competitor input */}
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={newCompetitor}
                      onChange={(e) => setNewCompetitor(e.target.value)}
                      onKeyDown={handleKeyDown}
                      placeholder="Enter competitor name"
                      disabled={isPending}
                      className="
                        flex-1 px-4 py-2.5 bg-slate-900 border border-slate-700 rounded-lg text-white
                        placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500
                        focus:border-transparent disabled:opacity-50 transition-all
                      "
                    />
                    <button
                      type="button"
                      onClick={handleAddCompetitor}
                      disabled={isPending || !newCompetitor.trim()}
                      className="
                        px-4 py-2.5 bg-primary-600 hover:bg-primary-500 text-white rounded-lg
                        font-medium transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed
                        shadow-lg shadow-primary-600/25
                      "
                    >
                      Add
                    </button>
                  </div>

                  {/* Competitor chips */}
                  <div className="flex flex-wrap gap-2">
                    <AnimatePresence>
                      {trackedCompetitors.map((competitor) => (
                        <CompetitorChip
                          key={competitor}
                          name={competitor}
                          onRemove={() => handleRemoveCompetitor(competitor)}
                          disabled={isPending}
                        />
                      ))}
                    </AnimatePresence>
                    {trackedCompetitors.length === 0 && (
                      <p className="text-sm text-slate-500">No competitors tracked yet</p>
                    )}
                  </div>
                </div>
              </SettingsSection>
            </div>
          )}
        </div>
      </div>

      {/* Success toast */}
      <SuccessToast show={showSuccess} onHide={() => setShowSuccess(false)} />
    </DashboardLayout>
  );
}
