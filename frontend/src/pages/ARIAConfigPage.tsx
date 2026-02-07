/* eslint-disable react-hooks/set-state-in-effect -- syncing local state with fetched server data */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Briefcase,
  Handshake,
  Megaphone,
  Crown,
  Wrench,
  RotateCcw,
  X,
  Sparkles,
  Loader2,
} from "lucide-react";
import { DashboardLayout } from "@/components/DashboardLayout";
import {
  useAriaConfig,
  useUpdateAriaConfig,
  useResetPersonality,
  useGeneratePreview,
} from "@/hooks/useAriaConfig";
import type {
  ARIARole,
  NotificationFrequency,
  ResponseDepth,
  PersonalityTraits,
  DomainFocus,
  CommunicationPrefs,
  ARIAConfigUpdateRequest,
} from "@/api/ariaConfig";

// ─── Constants ───────────────────────────────────────────────────────────────

const ROLE_CARDS: {
  value: ARIARole;
  icon: typeof Briefcase;
  label: string;
  description: string;
}[] = [
  {
    value: "sales_ops",
    icon: Briefcase,
    label: "Sales Operations",
    description: "Pipeline management, deal tracking, sales enablement",
  },
  {
    value: "bd_sales",
    icon: Handshake,
    label: "BD/Sales",
    description: "Partnership development, market expansion, deal origination",
  },
  {
    value: "marketing",
    icon: Megaphone,
    label: "Marketing",
    description: "Campaign strategy, brand positioning, market intelligence",
  },
  {
    value: "executive_support",
    icon: Crown,
    label: "Executive Support",
    description:
      "Strategic briefings, decision support, stakeholder management",
  },
  {
    value: "custom",
    icon: Wrench,
    label: "Custom",
    description: "Define your own focus area",
  },
];

const THERAPEUTIC_AREAS = [
  "Oncology",
  "Immunology",
  "Rare Disease",
  "Neurology",
  "Cardiology",
  "Respiratory",
  "Dermatology",
  "Endocrinology",
];

const MODALITIES = [
  "Biologics",
  "Small Molecule",
  "Cell Therapy",
  "Gene Therapy",
  "ADC",
  "mRNA",
  "Radiopharmaceutical",
];

const GEOGRAPHIES = [
  "North America",
  "EU",
  "APAC",
  "Latin America",
  "Middle East & Africa",
];

const PERSONALITY_SLIDERS: {
  key: keyof PersonalityTraits;
  label: string;
  leftLabel: string;
  rightLabel: string;
}[] = [
  {
    key: "proactiveness",
    label: "Proactiveness",
    leftLabel: "Wait for instructions",
    rightLabel: "Take initiative",
  },
  {
    key: "verbosity",
    label: "Verbosity",
    leftLabel: "Just the headlines",
    rightLabel: "Full analysis",
  },
  {
    key: "formality",
    label: "Formality",
    leftLabel: "Casual colleague",
    rightLabel: "Professional advisor",
  },
  {
    key: "assertiveness",
    label: "Assertiveness",
    leftLabel: "Suggest options",
    rightLabel: "Give recommendations",
  },
];

const NOTIFICATION_FREQUENCY_OPTIONS: {
  value: NotificationFrequency;
  label: string;
}[] = [
  { value: "minimal", label: "Minimal" },
  { value: "balanced", label: "Balanced" },
  { value: "aggressive", label: "Aggressive" },
];

const RESPONSE_DEPTH_OPTIONS: { value: ResponseDepth; label: string }[] = [
  { value: "brief", label: "Brief" },
  { value: "moderate", label: "Moderate" },
  { value: "detailed", label: "Detailed" },
];

const CHANNEL_OPTIONS = ["In-App", "Email", "Slack"] as const;

// ─── Utility: Debounce Hook ──────────────────────────────────────────────────

function useDebouncedCallback<T extends (...args: never[]) => void>(
  callback: T,
  delay: number
): T {
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const callbackRef = useRef(callback);

  useEffect(() => {
    callbackRef.current = callback;
  }, [callback]);

  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  return useCallback(
    (...args: Parameters<T>) => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      timeoutRef.current = setTimeout(() => {
        callbackRef.current(...(args as never[]));
      }, delay);
    },
    [delay]
  ) as T;
}

// ─── Sub-components ──────────────────────────────────────────────────────────

function SuccessToast({
  show,
  onHide,
}: {
  show: boolean;
  onHide: () => void;
}) {
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
          <div className="flex items-center gap-2 px-4 py-3 bg-[#5B6E8A]/95 backdrop-blur-sm text-white rounded-xl shadow-lg shadow-[#5B6E8A]/25">
            <svg
              className="w-5 h-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M5 13l4 4L19 7"
              />
            </svg>
            <span className="text-sm font-medium">Configuration saved</span>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function ConfigSkeleton() {
  return (
    <div className="space-y-8">
      {[1, 2, 3, 4].map((i) => (
        <div
          key={i}
          className="bg-white border border-[#E2E0DC] rounded-xl p-6 shadow-sm"
        >
          <div className="h-6 bg-[#E2E0DC] rounded w-1/4 mb-4 animate-pulse" />
          <div className="space-y-3">
            <div className="h-4 bg-[#E2E0DC] rounded w-2/3 animate-pulse" />
            <div className="h-10 bg-[#E2E0DC] rounded w-full animate-pulse" />
          </div>
        </div>
      ))}
    </div>
  );
}

function ErrorBanner({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      className="mb-6 p-4 bg-red-50 border border-red-200 rounded-xl"
    >
      <div className="flex items-start gap-3">
        <svg
          className="w-5 h-5 text-red-500 mt-0.5 flex-shrink-0"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
        <div className="flex-1">
          <p className="text-sm text-red-700">{message}</p>
        </div>
        <button
          onClick={onRetry}
          className="px-3 py-1 text-xs font-medium bg-red-100 hover:bg-red-200 text-red-700 rounded-lg transition-colors"
        >
          Retry
        </button>
      </div>
    </motion.div>
  );
}

function Section({
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
      transition={{ duration: 0.25, ease: "easeInOut", delay }}
      className="bg-white border border-[#E2E0DC] rounded-xl p-6 shadow-sm"
    >
      <div className="mb-5">
        <h3 className="text-lg font-semibold text-[#1A1D27]">{title}</h3>
        {description && (
          <p className="text-sm text-[#6B7280] mt-1">{description}</p>
        )}
      </div>
      {children}
    </motion.div>
  );
}

function ToggleSwitch({
  id,
  enabled,
  onChange,
  disabled = false,
}: {
  id?: string;
  enabled: boolean;
  onChange: (enabled: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      id={id}
      type="button"
      role="switch"
      aria-checked={enabled}
      onClick={() => !disabled && onChange(!enabled)}
      disabled={disabled}
      className={`
        min-h-[44px] flex items-center shrink-0 cursor-pointer
        focus:outline-none focus-visible:ring-2 focus-visible:ring-[#7B8EAA] focus-visible:ring-offset-2
        ${disabled ? "opacity-50 cursor-not-allowed" : ""}
      `}
    >
      <span
        className={`
          relative inline-flex h-7 w-12 min-w-[48px] shrink-0 rounded-full border-2 border-transparent
          transition-colors duration-200 ease-in-out
          ${enabled ? "bg-[#5B6E8A]" : "bg-[#E2E0DC]"}
        `}
      >
        <span
          className={`
            pointer-events-none inline-block h-6 w-6 transform rounded-full bg-white shadow-lg ring-0
            transition duration-200 ease-in-out
            ${enabled ? "translate-x-5" : "translate-x-0"}
          `}
        />
      </span>
    </button>
  );
}

function SegmentedControl<T extends string>({
  id,
  value,
  options,
  onChange,
  disabled = false,
}: {
  id?: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
  disabled?: boolean;
}) {
  return (
    <div id={id} role="radiogroup" className="inline-flex rounded-lg border border-[#E2E0DC] p-1 bg-[#F5F5F0]">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          onClick={() => !disabled && onChange(option.value)}
          disabled={disabled}
          className={`
            px-4 py-2 rounded-md text-sm font-medium transition-all duration-150 ease-out min-h-[44px]
            ${
              value === option.value
                ? "bg-white text-[#1A1D27] shadow-sm border border-[#E2E0DC]"
                : "text-[#6B7280] hover:text-[#1A1D27]"
            }
            ${disabled ? "opacity-50 cursor-not-allowed" : ""}
          `}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

function TagChip({
  label,
  onRemove,
  disabled = false,
}: {
  label: string;
  onRemove: () => void;
  disabled?: boolean;
}) {
  return (
    <motion.span
      layout
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.8 }}
      transition={{ duration: 0.15, ease: "easeOut" }}
      className="inline-flex items-center gap-1.5 bg-[#F5F5F0] border border-[#E2E0DC] rounded-lg px-3 py-1 text-sm text-[#1A1D27]"
    >
      {label}
      <button
        type="button"
        onClick={onRemove}
        disabled={disabled}
        aria-label={`Remove ${label}`}
        className={`
          -m-2 p-2 rounded hover:bg-[#E2E0DC] transition-colors flex items-center justify-center
          ${disabled ? "opacity-50 cursor-not-allowed" : ""}
        `}
      >
        <X className="w-3.5 h-3.5" />
      </button>
    </motion.span>
  );
}

function TagInput({
  tags,
  suggestions,
  onAdd,
  onRemove,
  placeholder,
  disabled = false,
}: {
  tags: string[];
  suggestions?: string[];
  onAdd: (tag: string) => void;
  onRemove: (tag: string) => void;
  placeholder: string;
  disabled?: boolean;
}) {
  const [input, setInput] = useState("");
  const [showDropdown, setShowDropdown] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);

  const filteredSuggestions = useMemo(() => {
    if (!suggestions || !input.trim()) return suggestions ?? [];
    const lower = input.toLowerCase();
    return suggestions.filter(
      (s) => s.toLowerCase().includes(lower) && !tags.includes(s)
    );
  }, [suggestions, input, tags]);

  const handleAdd = useCallback(
    (value: string) => {
      const trimmed = value.trim();
      if (trimmed && !tags.includes(trimmed)) {
        onAdd(trimmed);
      }
      setInput("");
      setShowDropdown(false);
    },
    [tags, onAdd]
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter") {
        e.preventDefault();
        handleAdd(input);
      }
      if (e.key === "Escape") {
        setShowDropdown(false);
      }
    },
    [input, handleAdd]
  );

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (
        wrapperRef.current &&
        !wrapperRef.current.contains(e.target as Node)
      ) {
        setShowDropdown(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div ref={wrapperRef} className="space-y-2">
      <div className="relative">
        <input
          type="text"
          value={input}
          onChange={(e) => {
            setInput(e.target.value);
            if (suggestions) setShowDropdown(true);
          }}
          onFocus={() => {
            if (suggestions) setShowDropdown(true);
          }}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          className="
            w-full px-4 py-2.5 bg-white border border-[#E2E0DC] rounded-lg text-[#1A1D27]
            placeholder-[#6B7280] text-sm
            focus:outline-none focus:ring-2 focus:ring-[#7B8EAA] focus:ring-offset-2
            disabled:opacity-50 transition-all
          "
        />
        {showDropdown && filteredSuggestions.length > 0 && (
          <div className="absolute z-10 mt-1 w-full bg-white border border-[#E2E0DC] rounded-lg shadow-lg max-h-48 overflow-y-auto">
            {filteredSuggestions.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                onClick={() => handleAdd(suggestion)}
                className="w-full text-left px-4 py-2.5 text-sm text-[#1A1D27] hover:bg-[#F5F5F0] transition-colors min-h-[44px]"
              >
                {suggestion}
              </button>
            ))}
          </div>
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        <AnimatePresence>
          {tags.map((tag) => (
            <TagChip
              key={tag}
              label={tag}
              onRemove={() => onRemove(tag)}
              disabled={disabled}
            />
          ))}
        </AnimatePresence>
        {tags.length === 0 && (
          <p className="text-sm text-[#6B7280]">None selected</p>
        )}
      </div>
    </div>
  );
}

// ─── Main Page Component ─────────────────────────────────────────────────────

export function ARIAConfigPage() {
  const { data: config, isLoading, error, refetch } = useAriaConfig();
  const updateMutation = useUpdateAriaConfig();
  const resetMutation = useResetPersonality();
  const previewMutation = useGeneratePreview();

  // Local state for all config fields
  const [role, setRole] = useState<ARIARole>("sales_ops");
  const [customRoleDescription, setCustomRoleDescription] = useState("");
  const [personality, setPersonality] = useState<PersonalityTraits>({
    proactiveness: 0.5,
    verbosity: 0.5,
    formality: 0.5,
    assertiveness: 0.5,
  });
  const [domainFocus, setDomainFocus] = useState<DomainFocus>({
    therapeutic_areas: [],
    modalities: [],
    geographies: [],
  });
  const [competitorWatchlist, setCompetitorWatchlist] = useState<string[]>([]);
  const [communication, setCommunication] = useState<CommunicationPrefs>({
    preferred_channels: ["In-App"],
    notification_frequency: "balanced",
    response_depth: "moderate",
    briefing_time: "08:00",
  });
  const [previewMessage, setPreviewMessage] = useState<string | null>(null);
  const [showSuccess, setShowSuccess] = useState(false);

  // Sync local state with server data
  useEffect(() => {
    if (config) {
      setRole(config.role);
      setCustomRoleDescription(config.custom_role_description ?? "");
      setPersonality(config.personality);
      setDomainFocus(config.domain_focus);
      setCompetitorWatchlist(config.competitor_watchlist);
      setCommunication(config.communication);
    }
  }, [config]);

  // Build the full update request from current state
  const buildRequest = useCallback(
    (overrides?: Partial<ARIAConfigUpdateRequest>): ARIAConfigUpdateRequest => ({
      role,
      custom_role_description: role === "custom" ? customRoleDescription : null,
      personality,
      domain_focus: domainFocus,
      competitor_watchlist: competitorWatchlist,
      communication,
      ...overrides,
    }),
    [role, customRoleDescription, personality, domainFocus, competitorWatchlist, communication]
  );

  // Save with success toast
  const saveConfig = useCallback(
    (overrides?: Partial<ARIAConfigUpdateRequest>) => {
      updateMutation.mutate(buildRequest(overrides), {
        onSuccess: () => setShowSuccess(true),
      });
    },
    [updateMutation, buildRequest]
  );

  // Debounced save for sliders
  const debouncedSave = useDebouncedCallback(
    (overrides?: Partial<ARIAConfigUpdateRequest>) => {
      saveConfig(overrides);
    },
    300
  );

  // ─── Handlers ────────────────────────────────────────────────────────

  const handleRoleChange = useCallback(
    (newRole: ARIARole) => {
      setRole(newRole);
      saveConfig({
        role: newRole,
        custom_role_description:
          newRole === "custom" ? customRoleDescription : null,
      });
    },
    [saveConfig, customRoleDescription]
  );

  const handleCustomRoleBlur = useCallback(() => {
    if (role === "custom") {
      saveConfig({ custom_role_description: customRoleDescription });
    }
  }, [role, customRoleDescription, saveConfig]);

  const handlePersonalityChange = useCallback(
    (key: keyof PersonalityTraits, value: number) => {
      const updated = { ...personality, [key]: value };
      setPersonality(updated);
      debouncedSave({ personality: updated });
    },
    [personality, debouncedSave]
  );

  const handleResetPersonality = useCallback(() => {
    resetMutation.mutate(undefined, {
      onSuccess: (data) => {
        setPersonality(data.personality);
        setShowSuccess(true);
      },
    });
  }, [resetMutation]);

  const handleDomainTagAdd = useCallback(
    (field: keyof DomainFocus, tag: string) => {
      const updated = {
        ...domainFocus,
        [field]: [...domainFocus[field], tag],
      };
      setDomainFocus(updated);
      saveConfig({ domain_focus: updated });
    },
    [domainFocus, saveConfig]
  );

  const handleDomainTagRemove = useCallback(
    (field: keyof DomainFocus, tag: string) => {
      const updated = {
        ...domainFocus,
        [field]: domainFocus[field].filter((t) => t !== tag),
      };
      setDomainFocus(updated);
      saveConfig({ domain_focus: updated });
    },
    [domainFocus, saveConfig]
  );

  const handleCompetitorAdd = useCallback(
    (tag: string) => {
      const updated = [...competitorWatchlist, tag];
      setCompetitorWatchlist(updated);
      saveConfig({ competitor_watchlist: updated });
    },
    [competitorWatchlist, saveConfig]
  );

  const handleCompetitorRemove = useCallback(
    (tag: string) => {
      const updated = competitorWatchlist.filter((c) => c !== tag);
      setCompetitorWatchlist(updated);
      saveConfig({ competitor_watchlist: updated });
    },
    [competitorWatchlist, saveConfig]
  );

  const handleChannelToggle = useCallback(
    (channel: string) => {
      const channels = communication.preferred_channels.includes(channel)
        ? communication.preferred_channels.filter((c) => c !== channel)
        : [...communication.preferred_channels, channel];
      const updated = { ...communication, preferred_channels: channels };
      setCommunication(updated);
      saveConfig({ communication: updated });
    },
    [communication, saveConfig]
  );

  const handleNotificationFrequency = useCallback(
    (freq: NotificationFrequency) => {
      const updated = { ...communication, notification_frequency: freq };
      setCommunication(updated);
      saveConfig({ communication: updated });
    },
    [communication, saveConfig]
  );

  const handleResponseDepth = useCallback(
    (depth: ResponseDepth) => {
      const updated = { ...communication, response_depth: depth };
      setCommunication(updated);
      saveConfig({ communication: updated });
    },
    [communication, saveConfig]
  );

  const handleBriefingTime = useCallback(
    (time: string) => {
      const updated = { ...communication, briefing_time: time };
      setCommunication(updated);
      saveConfig({ communication: updated });
    },
    [communication, saveConfig]
  );

  const handleGeneratePreview = useCallback(() => {
    previewMutation.mutate(buildRequest(), {
      onSuccess: (data) => setPreviewMessage(data.preview_message),
    });
  }, [previewMutation, buildRequest]);

  // Static preview text based on current selections
  const staticPreview = useMemo(() => {
    const roleLabel =
      ROLE_CARDS.find((r) => r.value === role)?.label ?? "Custom";
    const proactiveText =
      personality.proactiveness > 0.6
        ? "proactively surface insights"
        : "wait for your direction";
    const verbosityText =
      personality.verbosity > 0.6 ? "detailed analyses" : "concise summaries";
    const formalityText =
      personality.formality > 0.6
        ? "a professional tone"
        : "a conversational tone";
    return `As your ${roleLabel} assistant, ARIA will ${proactiveText} and deliver ${verbosityText} using ${formalityText}.`;
  }, [role, personality]);

  const isPending = updateMutation.isPending || resetMutation.isPending;

  return (
    <DashboardLayout>
      <div className="bg-[#FAFAF9] min-h-screen">
        <div className="max-w-3xl mx-auto px-4 py-8 lg:px-8">
          {/* ── Section 1: Header ──────────────────────────────────── */}
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, ease: "easeInOut" }}
            className="mb-8"
          >
            <h1 className="text-[32px] font-serif text-[#1A1D27] mb-2">
              Configure ARIA
            </h1>
            <p className="text-[#6B7280]">
              Customize ARIA&apos;s role, personality, and communication style
              to match how you work.
            </p>
          </motion.div>

          {/* Info banner */}
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.05 }}
            className="mb-8 p-4 bg-[#5B6E8A]/5 border border-[#5B6E8A]/20 rounded-xl"
          >
            <div className="flex items-start gap-3">
              <svg
                className="w-5 h-5 text-[#5B6E8A] mt-0.5 flex-shrink-0"
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
              <p className="text-sm text-[#5B6E8A]">
                Your configuration is saved automatically as you make changes.
              </p>
            </div>
          </motion.div>

          {/* Error */}
          {error && (
            <ErrorBanner
              message="Failed to load configuration. Please try again."
              onRetry={() => refetch()}
            />
          )}

          {/* Loading */}
          {isLoading ? (
            <ConfigSkeleton />
          ) : (
            <div className="space-y-6">
              {/* ── Section 2: Role Selector ─────────────────────── */}
              <Section
                title="Role"
                description="Choose the role that best describes how you work with ARIA."
                delay={0.05}
              >
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {ROLE_CARDS.map((card) => {
                    const Icon = card.icon;
                    const isSelected = role === card.value;
                    return (
                      <button
                        key={card.value}
                        type="button"
                        onClick={() => handleRoleChange(card.value)}
                        disabled={isPending}
                        className={`
                          text-left p-4 rounded-xl border transition-all duration-200 ease-in-out min-h-[44px]
                          focus:outline-none focus-visible:ring-2 focus-visible:ring-[#7B8EAA] focus-visible:ring-offset-2
                          ${
                            isSelected
                              ? "border-[#5B6E8A] bg-[#5B6E8A]/5"
                              : "border-[#E2E0DC] bg-white hover:border-[#5B6E8A]/40"
                          }
                          ${isPending ? "opacity-50 cursor-not-allowed" : ""}
                        `}
                      >
                        <Icon
                          strokeWidth={1.5}
                          className={`w-6 h-6 mb-2 ${
                            isSelected
                              ? "text-[#5B6E8A]"
                              : "text-[#6B7280]"
                          }`}
                        />
                        <div
                          className={`text-sm font-medium ${
                            isSelected
                              ? "text-[#1A1D27]"
                              : "text-[#1A1D27]"
                          }`}
                        >
                          {card.label}
                        </div>
                        <div className="text-xs text-[#6B7280] mt-0.5">
                          {card.description}
                        </div>
                      </button>
                    );
                  })}
                </div>

                <AnimatePresence>
                  {role === "custom" && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }}
                      transition={{ duration: 0.2, ease: "easeInOut" }}
                      className="mt-4 overflow-hidden"
                    >
                      <label
                        htmlFor="custom-role"
                        className="block text-sm font-medium text-[#1A1D27] mb-1.5"
                      >
                        Describe your custom role
                      </label>
                      <textarea
                        id="custom-role"
                        value={customRoleDescription}
                        onChange={(e) =>
                          setCustomRoleDescription(e.target.value)
                        }
                        onBlur={handleCustomRoleBlur}
                        placeholder="Describe what you'd like ARIA to focus on..."
                        disabled={isPending}
                        rows={3}
                        className="
                          w-full px-4 py-2.5 bg-white border border-[#E2E0DC] rounded-lg text-[#1A1D27]
                          placeholder-[#6B7280] text-sm resize-none
                          focus:outline-none focus:ring-2 focus:ring-[#7B8EAA] focus:ring-offset-2
                          disabled:opacity-50 transition-all
                        "
                      />
                    </motion.div>
                  )}
                </AnimatePresence>
              </Section>

              {/* ── Section 3: Personality Sliders ────────────────── */}
              <Section
                title="Personality"
                description="Fine-tune how ARIA communicates and behaves."
                delay={0.1}
              >
                <div className="space-y-6">
                  {PERSONALITY_SLIDERS.map((slider) => (
                    <div key={slider.key}>
                      <div className="flex items-center justify-between mb-2">
                        <label
                          htmlFor={`aria-config-${slider.key}`}
                          className="text-sm font-medium text-[#1A1D27]"
                        >
                          {slider.label}
                        </label>
                        <span className="font-mono text-[13px] text-[#6B7280]">
                          {personality[slider.key].toFixed(2)}
                        </span>
                      </div>
                      <input
                        id={`aria-config-${slider.key}`}
                        type="range"
                        min={0}
                        max={1}
                        step={0.01}
                        value={personality[slider.key]}
                        onChange={(e) =>
                          handlePersonalityChange(
                            slider.key,
                            parseFloat(e.target.value)
                          )
                        }
                        disabled={isPending}
                        className="
                          w-full h-2 rounded-full appearance-none cursor-pointer min-h-[44px]
                          bg-[#E2E0DC] accent-[#5B6E8A]
                          disabled:opacity-50 disabled:cursor-not-allowed
                          [&::-webkit-slider-thumb]:appearance-none
                          [&::-webkit-slider-thumb]:w-[22px]
                          [&::-webkit-slider-thumb]:h-[22px]
                          [&::-webkit-slider-thumb]:rounded-full
                          [&::-webkit-slider-thumb]:bg-[#5B6E8A]
                          [&::-webkit-slider-thumb]:border-2
                          [&::-webkit-slider-thumb]:border-white
                          [&::-webkit-slider-thumb]:shadow-md
                          [&::-webkit-slider-thumb]:cursor-pointer
                          [&::-moz-range-thumb]:w-[22px]
                          [&::-moz-range-thumb]:h-[22px]
                          [&::-moz-range-thumb]:rounded-full
                          [&::-moz-range-thumb]:bg-[#5B6E8A]
                          [&::-moz-range-thumb]:border-2
                          [&::-moz-range-thumb]:border-white
                          [&::-moz-range-thumb]:shadow-md
                          [&::-moz-range-thumb]:cursor-pointer
                        "
                      />
                      <div className="flex justify-between mt-1">
                        <span className="text-xs text-[#6B7280]">
                          {slider.leftLabel}
                        </span>
                        <span className="text-xs text-[#6B7280]">
                          {slider.rightLabel}
                        </span>
                      </div>
                    </div>
                  ))}

                  <button
                    type="button"
                    onClick={handleResetPersonality}
                    disabled={isPending || resetMutation.isPending}
                    className="
                      inline-flex items-center gap-2 px-4 py-2.5 text-sm font-medium
                      text-[#5B6E8A] bg-[#F5F5F0] border border-[#E2E0DC] rounded-lg
                      hover:bg-[#E2E0DC] transition-colors duration-150 ease-out
                      focus:outline-none focus-visible:ring-2 focus-visible:ring-[#7B8EAA] focus-visible:ring-offset-2
                      disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px]
                    "
                  >
                    <RotateCcw className="w-4 h-4" />
                    Reset to defaults
                  </button>
                </div>
              </Section>

              {/* ── Section 4: Domain Focus ───────────────────────── */}
              <Section
                title="Domain Focus"
                description="Specify the therapeutic areas, modalities, and geographies you work with."
                delay={0.15}
              >
                <div className="space-y-5">
                  <div>
                    <label className="block text-sm font-medium text-[#1A1D27] mb-2">
                      Therapeutic Areas
                    </label>
                    <TagInput
                      tags={domainFocus.therapeutic_areas}
                      suggestions={THERAPEUTIC_AREAS}
                      onAdd={(tag) =>
                        handleDomainTagAdd("therapeutic_areas", tag)
                      }
                      onRemove={(tag) =>
                        handleDomainTagRemove("therapeutic_areas", tag)
                      }
                      placeholder="Type to search therapeutic areas..."
                      disabled={isPending}
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-[#1A1D27] mb-2">
                      Modalities
                    </label>
                    <TagInput
                      tags={domainFocus.modalities}
                      suggestions={MODALITIES}
                      onAdd={(tag) => handleDomainTagAdd("modalities", tag)}
                      onRemove={(tag) =>
                        handleDomainTagRemove("modalities", tag)
                      }
                      placeholder="Type to search modalities..."
                      disabled={isPending}
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-[#1A1D27] mb-2">
                      Geographies
                    </label>
                    <TagInput
                      tags={domainFocus.geographies}
                      suggestions={GEOGRAPHIES}
                      onAdd={(tag) => handleDomainTagAdd("geographies", tag)}
                      onRemove={(tag) =>
                        handleDomainTagRemove("geographies", tag)
                      }
                      placeholder="Type to search geographies..."
                      disabled={isPending}
                    />
                  </div>
                </div>
              </Section>

              {/* ── Section 5: Competitor Watchlist ───────────────── */}
              <Section
                title="Competitor Watchlist"
                description="Track competitors for market intelligence and battle cards."
                delay={0.2}
              >
                <TagInput
                  tags={competitorWatchlist}
                  onAdd={handleCompetitorAdd}
                  onRemove={handleCompetitorRemove}
                  placeholder="Enter competitor name and press Enter"
                  disabled={isPending}
                />
              </Section>

              {/* ── Section 6: Communication Preferences ──────────── */}
              <Section
                title="Communication Preferences"
                description="Control how and when ARIA reaches out to you."
                delay={0.25}
              >
                <div className="space-y-6">
                  {/* Channel toggles */}
                  <div>
                    <label className="block text-sm font-medium text-[#1A1D27] mb-3">
                      Channels
                    </label>
                    <div className="space-y-3">
                      {CHANNEL_OPTIONS.map((channel) => {
                        const channelId = `aria-config-channel-${channel.toLowerCase().replace(/[^a-z]/g, "-")}`;
                        return (
                          <div
                            key={channel}
                            className="flex items-center justify-between py-2"
                          >
                            <label
                              htmlFor={channelId}
                              className="text-sm text-[#1A1D27]"
                            >
                              {channel}
                            </label>
                            <ToggleSwitch
                              id={channelId}
                              enabled={communication.preferred_channels.includes(
                                channel
                              )}
                              onChange={() => handleChannelToggle(channel)}
                              disabled={isPending}
                            />
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  <div className="border-t border-[#E2E0DC]" />

                  {/* Notification Frequency */}
                  <div>
                    <label
                      htmlFor="aria-config-notification-frequency"
                      className="block text-sm font-medium text-[#1A1D27] mb-3"
                    >
                      Notification Frequency
                    </label>
                    <SegmentedControl
                      id="aria-config-notification-frequency"
                      value={communication.notification_frequency}
                      options={NOTIFICATION_FREQUENCY_OPTIONS}
                      onChange={handleNotificationFrequency}
                      disabled={isPending}
                    />
                  </div>

                  {/* Response Depth */}
                  <div>
                    <label
                      htmlFor="aria-config-response-depth"
                      className="block text-sm font-medium text-[#1A1D27] mb-3"
                    >
                      Response Depth
                    </label>
                    <SegmentedControl
                      id="aria-config-response-depth"
                      value={communication.response_depth}
                      options={RESPONSE_DEPTH_OPTIONS}
                      onChange={handleResponseDepth}
                      disabled={isPending}
                    />
                  </div>

                  <div className="border-t border-[#E2E0DC]" />

                  {/* Briefing Time */}
                  <div className="flex items-center gap-4">
                    <label
                      htmlFor="briefing-time"
                      className="text-sm font-medium text-[#1A1D27]"
                    >
                      Daily Briefing Time
                    </label>
                    <input
                      id="briefing-time"
                      type="time"
                      value={communication.briefing_time}
                      onChange={(e) => handleBriefingTime(e.target.value)}
                      disabled={isPending}
                      className="
                        px-4 py-2.5 bg-white border border-[#E2E0DC] rounded-lg text-[#1A1D27] text-sm
                        focus:outline-none focus:ring-2 focus:ring-[#7B8EAA] focus:ring-offset-2
                        disabled:opacity-50 transition-all min-h-[44px]
                      "
                    />
                  </div>
                </div>
              </Section>

              {/* ── Section 7: Preview Panel ──────────────────────── */}
              <Section
                title="Preview"
                description="See how ARIA will behave with your current settings."
                delay={0.3}
              >
                <div className="space-y-4">
                  <div className="p-4 bg-[#F5F5F0] border border-[#E2E0DC] rounded-lg">
                    <p className="text-sm text-[#1A1D27] italic font-serif leading-relaxed">
                      {previewMessage ?? staticPreview}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={handleGeneratePreview}
                    disabled={previewMutation.isPending || isPending}
                    className="
                      inline-flex items-center gap-2 px-4 py-2.5 text-sm font-medium
                      text-white bg-[#5B6E8A] rounded-lg
                      hover:bg-[#4A5D79] transition-colors duration-150 ease-out
                      focus:outline-none focus-visible:ring-2 focus-visible:ring-[#7B8EAA] focus-visible:ring-offset-2
                      disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px]
                    "
                  >
                    {previewMutation.isPending ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Sparkles className="w-4 h-4" />
                    )}
                    {previewMutation.isPending
                      ? "Generating..."
                      : "Generate preview"}
                  </button>
                </div>
              </Section>
            </div>
          )}
        </div>
      </div>

      <SuccessToast show={showSuccess} onHide={() => setShowSuccess(false)} />
    </DashboardLayout>
  );
}
