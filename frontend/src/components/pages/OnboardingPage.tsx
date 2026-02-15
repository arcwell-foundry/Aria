import { useState, useCallback, useRef, useEffect, useMemo, type ReactNode } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  Loader2,
  Upload,
  FileText,
  Mail,
  Check,
  Target,
  Building2,
  Calendar,
  MessageSquare,
  ExternalLink,
  ChevronLeft,
  type LucideIcon,
} from "lucide-react";
import { MessageBubble } from "@/components/conversation/MessageBubble";
import { ProgressBar } from "@/components/primitives/ProgressBar";
import type { Message } from "@/types/chat";
import {
  completeStep,
  skipStep,
  getOnboardingState,
  saveEmailPrivacyConfig,
  type OnboardingStep,
  type OnboardingStateResponse,
  type GoalSuggestion,
  type WritingStyleFingerprint,
  type PrivacyExclusion,
} from "@/api/onboarding";
import {
  useDocumentUpload,
  useDocuments,
  useEmailConnect,
  useEmailStatus,
  useEmailBootstrapStatus,
  useFirstGoalSuggestions,
  useCreateFirstGoal,
  useActivateAria,
  useCompanyDiscovery,
  useAnalyzeWriting,
  useExtractTextFromFile,
  useIntegrationWizardStatus,
  useConnectIntegration,
  emailKeys,
} from "@/hooks/useOnboarding";
import { useEnrichmentStatus } from "@/hooks/useEnrichmentStatus";
import { useActivationStatus } from "@/hooks/useActivationStatus";
import type { EmailProvider } from "@/api/emailIntegration";
import { recordEmailConnection } from "@/api/emailIntegration";
import type { CompanyDocument } from "@/api/documents";
import type { IntegrationAppName, IntegrationStatus } from "@/api/onboarding";
import { IntelligenceMoment } from "@/components/onboarding/IntelligenceMoment";
import { EmailBootstrapProgress } from "@/components/onboarding/EmailBootstrapProgress";

// --- Animation direction type ---
type AnimationDirection = "forward" | "backward" | "none";

// --- Animated Step Content Wrapper ---
function AnimatedStepContent({
  children,
  direction,
  stepKey,
}: {
  children: ReactNode;
  direction: AnimationDirection;
  stepKey: string;
}) {
  if (direction === "none") {
    return <div>{children}</div>;
  }

  const enterClass =
    direction === "forward"
      ? "onboarding-step-enter-right"
      : "onboarding-step-enter-left";

  // Use key to force re-mount and trigger animation
  return (
    <div key={stepKey} className={enterClass}>
      {children}
    </div>
  );
}

// --- Animated Message Wrapper ---
function AnimatedMessage({
  children,
  messageKey,
}: {
  children: ReactNode;
  messageKey: string;
}) {
  return (
    <div key={messageKey} className="onboarding-message-in">
      {children}
    </div>
  );
}

// --- Animated Form Field Wrapper ---
function AnimatedField({
  children,
  index,
  fieldKey,
}: {
  children: ReactNode;
  index: number;
  fieldKey: string;
}) {
  const delayClass = `onboarding-field-delay-${Math.min(index, 5)}`;
  return (
    <div key={fieldKey} className={`onboarding-field-in ${delayClass}`}>
      {children}
    </div>
  );
}

// --- Animated Connection Button ---
function AnimatedConnectionButton({
  isConnected,
  isPending,
  onConnect,
  onDisconnect,
  connectLabel,
  connectedLabel,
  icon: Icon,
  disabled = false,
  className = "",
}: {
  isConnected: boolean;
  isPending: boolean;
  onConnect: () => void;
  onDisconnect?: () => void;
  connectLabel: string;
  connectedLabel: string;
  icon: LucideIcon;
  disabled?: boolean;
  className?: string;
}) {
  // Use connection state as key to force re-render and re-trigger animations
  // This ensures the CSS animations play fresh each time connection state changes
  const animationKey = isConnected ? "connected" : "disconnected";

  const handleClick = () => {
    if (isConnected && onDisconnect) {
      onDisconnect();
    } else if (!isConnected) {
      onConnect();
    }
  };

  const baseClasses = "flex items-center justify-center gap-2 rounded-lg border px-4 py-3 text-sm font-medium transition-colors duration-300 disabled:opacity-60";

  const stateClasses = isConnected
    ? "border-green-500/30 bg-green-500/10 text-green-400 connection-success"
    : "border-white/10 bg-white/[0.03] text-[var(--text-primary,#F1F1F1)] hover:border-white/20";

  return (
    <button
      key={animationKey}
      onClick={handleClick}
      disabled={disabled || isPending}
      className={`${baseClasses} ${stateClasses} ${className}`}
    >
      <span className="connection-text-wrapper">
        {isConnected ? (
          <>
            <Check className="h-4 w-4 connection-checkmark" />
            <span className="connection-text-in">
              {connectedLabel}
            </span>
          </>
        ) : isPending ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            <span>Connecting...</span>
          </>
        ) : (
          <>
            <Icon className="h-4 w-4" />
            <span>{connectLabel}</span>
          </>
        )}
      </span>
    </button>
  );
}

// --- Step configuration ---

const STEP_ORDER: OnboardingStep[] = [
  "company_discovery",
  "document_upload",
  "user_profile",
  "writing_samples",
  "email_integration",
  "integration_wizard",
  "first_goal",
  "activation",
];

interface StepConfig {
  ariaMessage: string;
  inputMode: "text" | "action_panel" | "none";
  skippable: boolean;
  placeholder?: string;
}

const STEP_CONFIG: Record<OnboardingStep, StepConfig> = {
  company_discovery: {
    ariaMessage:
      "Let's start with your company. I'll use this to research your market, map your competitors, and build a complete picture of your industry — so I'm never starting from zero.",
    inputMode: "action_panel",
    skippable: false,
  },
  document_upload: {
    ariaMessage:
      "Upload any documents that would help me understand your business — pitch decks, product guides, competitive analyses, territory plans. I'll extract key insights and remember everything.",
    inputMode: "action_panel",
    skippable: true,
  },
  user_profile: {
    ariaMessage:
      "Now tell me about you. Your role and background help me calibrate how I communicate on your behalf and what intelligence matters most to you.",
    inputMode: "action_panel",
    skippable: false,
  },
  writing_samples: {
    ariaMessage:
      "Share examples of how you write — emails, LinkedIn posts, reports. The more I see, the better I match your voice. You can also skip this and I'll learn from your sent emails instead.",
    inputMode: "action_panel",
    skippable: true,
  },
  email_integration: {
    ariaMessage:
      "Let me connect to your email so I can map your relationships, spot warm leads, and understand your communication patterns. Your privacy controls come first.",
    inputMode: "action_panel",
    skippable: true,
  },
  integration_wizard: {
    ariaMessage:
      "Connect your tools and I'll unify everything into one intelligence layer. No more switching between Salesforce, calendar, and Slack to piece together what's happening.",
    inputMode: "action_panel",
    skippable: true,
  },
  first_goal: {
    ariaMessage:
      "What should I focus on first? I'll suggest goals based on what I've learned about your company, but you can set your own priority.",
    inputMode: "action_panel",
    skippable: false,
  },
  activation: {
    ariaMessage:
      "Everything is connected. I'm activating my agents to start working on your behalf. Here's what I've learned and what I'm doing first.",
    inputMode: "none",
    skippable: false,
  },
};

const STEP_DISPLAY_NAMES: Record<OnboardingStep, string> = {
  company_discovery: "Company",
  document_upload: "Documents",
  user_profile: "Profile",
  writing_samples: "Writing Style",
  email_integration: "Email",
  integration_wizard: "Integrations",
  first_goal: "First Goal",
  activation: "Activation",
};

// --- Helpers ---

function createMessage(
  role: "aria" | "user",
  content: string,
  id?: string,
): Message {
  return {
    id: id ?? crypto.randomUUID(),
    role,
    content,
    rich_content: [],
    ui_commands: [],
    suggestions: [],
    timestamp: new Date().toISOString(),
  };
}

function stepIndex(step: OnboardingStep): number {
  return STEP_ORDER.indexOf(step);
}

// --- Action Panel: Company Discovery ---

function CompanyDiscoveryPanel({
  onComplete,
  initialData,
}: {
  onComplete: (response: OnboardingStateResponse) => void;
  initialData?: Record<string, unknown>;
}) {
  const [companyName, setCompanyName] = useState((initialData?.company_name as string) || "");
  const [website, setWebsite] = useState((initialData?.website as string) || "");
  const [email, setEmail] = useState((initialData?.email as string) || "");
  const [error, setError] = useState<string | null>(null);
  const [showIntelligence, setShowIntelligence] = useState(false);
  const [intelligenceData, setIntelligenceData] = useState<{
    companyName?: string;
    productCount?: number;
    competitorCount?: number;
    classification?: {
      company_type?: string;
      therapeutic_areas?: string[];
    } | null;
  }>({});
  const discoveryMutation = useCompanyDiscovery();

  const handleSubmit = useCallback(async () => {
    setError(null);

    if (!companyName.trim()) {
      setError("Please enter your company name.");
      return;
    }
    if (!website.trim()) {
      setError("Please enter your company website.");
      return;
    }
    if (!email.trim()) {
      setError("Please enter your work email.");
      return;
    }

    // Start intelligence moment
    setShowIntelligence(true);
    setIntelligenceData({ companyName: companyName.trim() });

    try {
      // The backend now handles step completion and returns OnboardingStateResponse directly
      const response = await discoveryMutation.mutateAsync({
        company_name: companyName.trim(),
        website: website.trim(),
        email: email.trim(),
      });

      // Update intelligence data with results from step_data
      const stepData = response.state.step_data.company_discovery as {
        company_name?: string;
      } | undefined;
      setIntelligenceData({
        companyName: stepData?.company_name || companyName.trim(),
        productCount: 3, // Placeholder - would come from enrichment API
        competitorCount: 5, // Placeholder
        classification: null, // Would be populated by enrichment
      });

      // Advance to the next step
      onComplete(response);
    } catch {
      setShowIntelligence(false);
      setError("Failed to validate company. Please try again.");
    }
  }, [companyName, website, email, discoveryMutation, onComplete]);

  // Show intelligence moment during processing
  if (showIntelligence) {
    return (
      <IntelligenceMoment
        step="company_discovery"
        responseData={intelligenceData}
        isLoading={discoveryMutation.isPending}
        minDuration={2500}
      />
    );
  }

  return (
    <div className="mx-auto w-full max-w-2xl space-y-4">
      <div className="space-y-3">
        <AnimatedField index={0} fieldKey="company-name">
          <input
            value={companyName}
            onChange={(e) => setCompanyName(e.target.value)}
            placeholder="Company name"
            className="w-full rounded-lg border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-[var(--text-primary,#F1F1F1)] placeholder-[var(--text-tertiary,#6B7280)] outline-none transition focus:border-[var(--color-accent,#2E66FF)]"
            onKeyDown={(e) => {
              if (e.key === "Enter") void handleSubmit();
            }}
          />
        </AnimatedField>
        <AnimatedField index={1} fieldKey="website">
          <input
            value={website}
            onChange={(e) => setWebsite(e.target.value)}
            placeholder="Website (e.g. acme.com)"
            className="w-full rounded-lg border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-[var(--text-primary,#F1F1F1)] placeholder-[var(--text-tertiary,#6B7280)] outline-none transition focus:border-[var(--color-accent,#2E66FF)]"
            onKeyDown={(e) => {
              if (e.key === "Enter") void handleSubmit();
            }}
          />
        </AnimatedField>
        <AnimatedField index={2} fieldKey="email">
          <input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            type="email"
            placeholder="Work email"
            className="w-full rounded-lg border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-[var(--text-primary,#F1F1F1)] placeholder-[var(--text-tertiary,#6B7280)] outline-none transition focus:border-[var(--color-accent,#2E66FF)]"
            onKeyDown={(e) => {
              if (e.key === "Enter") void handleSubmit();
            }}
          />
        </AnimatedField>
      </div>

      {error && (
        <AnimatedField index={3} fieldKey="error">
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
            {error}
          </div>
        </AnimatedField>
      )}

      <AnimatedField index={4} fieldKey="submit">
        <button
          onClick={() => void handleSubmit()}
          disabled={
            !companyName.trim() ||
            !website.trim() ||
            !email.trim() ||
            discoveryMutation.isPending
          }
          className="rounded-lg bg-[var(--color-accent,#2E66FF)] px-4 py-2.5 text-sm font-medium text-white transition hover:bg-[var(--color-accent,#2E66FF)]/90 disabled:opacity-40"
        >
          Continue
        </button>
      </AnimatedField>
    </div>
  );
}

// --- Action Panel: User Profile ---

function UserProfilePanel({
  onComplete,
  initialData,
}: {
  onComplete: (response: OnboardingStateResponse) => void;
  initialData?: Record<string, unknown>;
}) {
  const [fullName, setFullName] = useState((initialData?.full_name as string) || "");
  const [title, setTitle] = useState((initialData?.title as string) || "");
  const [department, setDepartment] = useState((initialData?.department as string) || "");
  const [linkedinUrl, setLinkedinUrl] = useState((initialData?.linkedin_url as string) || "");
  const [phone, setPhone] = useState((initialData?.phone as string) || "");
  const [roleType, setRoleType] = useState((initialData?.role_type as string) || "");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showIntelligence, setShowIntelligence] = useState(false);
  const [intelligenceData, setIntelligenceData] = useState<{
    linkedinFound?: boolean;
    roleType?: string;
  }>({});

  const roleOptions = [
    { value: "sales", label: "Sales" },
    { value: "bd", label: "Business Development" },
    { value: "marketing", label: "Marketing" },
    { value: "commercial_ops", label: "Commercial Ops" },
    { value: "leadership", label: "Leadership" },
    { value: "other", label: "Other" },
  ];

  const handleSubmit = useCallback(async () => {
    setError(null);

    if (!fullName.trim()) {
      setError("Please enter your full name.");
      return;
    }
    if (!title.trim()) {
      setError("Please enter your job title.");
      return;
    }
    if (!department.trim()) {
      setError("Please enter your department.");
      return;
    }
    if (!roleType) {
      setError("Please select your role type.");
      return;
    }

    // Start intelligence moment
    setShowIntelligence(true);
    setIntelligenceData({
      linkedinFound: linkedinUrl.trim().length > 0,
      roleType: roleType,
    });

    setIsSubmitting(true);
    try {
      const response = await completeStep("user_profile", {
        full_name: fullName.trim(),
        title: title.trim(),
        department: department.trim(),
        linkedin_url: linkedinUrl.trim() || null,
        phone: phone.trim() || null,
        role_type: roleType,
      });
      onComplete(response);
    } catch {
      setShowIntelligence(false);
      setError("Failed to save profile. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  }, [fullName, title, department, linkedinUrl, phone, roleType, onComplete]);

  // Show intelligence moment during processing
  if (showIntelligence) {
    return (
      <IntelligenceMoment
        step="user_profile"
        responseData={intelligenceData}
        isLoading={isSubmitting}
        minDuration={1800}
      />
    );
  }

  return (
    <div className="mx-auto w-full max-w-2xl space-y-4">
      <div className="space-y-3">
        <AnimatedField index={0} fieldKey="full-name">
          <input
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            placeholder="Full name"
            className="w-full rounded-lg border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-[var(--text-primary,#F1F1F1)] placeholder-[var(--text-tertiary,#6B7280)] outline-none transition focus:border-[var(--color-accent,#2E66FF)]"
            onKeyDown={(e) => {
              if (e.key === "Enter") void handleSubmit();
            }}
          />
        </AnimatedField>
        <AnimatedField index={1} fieldKey="title">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Job title"
            className="w-full rounded-lg border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-[var(--text-primary,#F1F1F1)] placeholder-[var(--text-tertiary,#6B7280)] outline-none transition focus:border-[var(--color-accent,#2E66FF)]"
            onKeyDown={(e) => {
              if (e.key === "Enter") void handleSubmit();
            }}
          />
        </AnimatedField>
        <AnimatedField index={2} fieldKey="department">
          <input
            value={department}
            onChange={(e) => setDepartment(e.target.value)}
            placeholder="Department"
            className="w-full rounded-lg border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-[var(--text-primary,#F1F1F1)] placeholder-[var(--text-tertiary,#6B7280)] outline-none transition focus:border-[var(--color-accent,#2E66FF)]"
            onKeyDown={(e) => {
              if (e.key === "Enter") void handleSubmit();
            }}
          />
        </AnimatedField>
        <AnimatedField index={3} fieldKey="role-type">
          <select
            value={roleType}
            onChange={(e) => setRoleType(e.target.value)}
            className="w-full rounded-lg border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-[var(--text-primary,#F1F1F1)] outline-none transition focus:border-[var(--color-accent,#2E66FF)]"
          >
            <option value="" disabled className="text-[var(--text-tertiary,#6B7280)]">
              Select your role type
            </option>
            {roleOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </AnimatedField>
        <AnimatedField index={4} fieldKey="linkedin">
          <input
            value={linkedinUrl}
            onChange={(e) => setLinkedinUrl(e.target.value)}
            placeholder="LinkedIn URL (optional)"
            className="w-full rounded-lg border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-[var(--text-primary,#F1F1F1)] placeholder-[var(--text-tertiary,#6B7280)] outline-none transition focus:border-[var(--color-accent,#2E66FF)]"
            onKeyDown={(e) => {
              if (e.key === "Enter") void handleSubmit();
            }}
          />
        </AnimatedField>
        <AnimatedField index={5} fieldKey="phone">
          <input
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            type="tel"
            placeholder="Phone number (optional)"
            className="w-full rounded-lg border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-[var(--text-primary,#F1F1F1)] placeholder-[var(--text-tertiary,#6B7280)] outline-none transition focus:border-[var(--color-accent,#2E66FF)]"
            onKeyDown={(e) => {
              if (e.key === "Enter") void handleSubmit();
            }}
          />
        </AnimatedField>
      </div>

      {error && (
        <AnimatedField index={6} fieldKey="error">
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
            {error}
          </div>
        </AnimatedField>
      )}

      <AnimatedField index={7} fieldKey="submit">
        <button
          onClick={() => void handleSubmit()}
          disabled={
            !fullName.trim() ||
            !title.trim() ||
            !department.trim() ||
            !roleType ||
            isSubmitting
          }
          className="rounded-lg bg-[var(--color-accent,#2E66FF)] px-4 py-2.5 text-sm font-medium text-white transition hover:bg-[var(--color-accent,#2E66FF)]/90 disabled:opacity-40"
        >
          Continue
        </button>
      </AnimatedField>
    </div>
  );
}

// --- Action Panel: Writing Samples ---

const WRITING_SAMPLE_FILE_TYPES = ".txt,.doc,.docx,.pdf";

function WritingSamplesPanel({
  onComplete,
  onSkip,
  emailConnected,
}: {
  onComplete: (response: OnboardingStateResponse) => void;
  onSkip: () => void;
  emailConnected: boolean;
}) {
  const [samples, setSamples] = useState<string[]>([]);
  const [sampleSources, setSampleSources] = useState<string[]>([]); // Track source (pasted/file)
  const [currentSample, setCurrentSample] = useState("");
  const [fingerprint, setFingerprint] = useState<WritingStyleFingerprint | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [showIntelligence, setShowIntelligence] = useState(false);
  const [intelligenceData, setIntelligenceData] = useState<{
    writingFingerprint?: WritingStyleFingerprint | null;
    sampleCount?: number;
  }>({});
  const fileInputRef = useRef<HTMLInputElement>(null);
  const analyzeMutation = useAnalyzeWriting();
  const extractTextMutation = useExtractTextFromFile();

  const handleAddSample = useCallback(() => {
    const text = currentSample.trim();
    if (!text) return;
    setSamples((prev) => [...prev, text]);
    setSampleSources((prev) => [...prev, "pasted"]);
    setCurrentSample("");
    setError(null);
  }, [currentSample]);

  const handleRemoveSample = useCallback((index: number) => {
    setSamples((prev) => prev.filter((_, i) => i !== index));
    setSampleSources((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const handleFiles = useCallback(
    async (files: FileList | null) => {
      if (!files) return;

      for (const file of Array.from(files)) {
        // Check file type
        const ext = file.name.toLowerCase().split(".").pop();
        if (!["txt", "doc", "docx", "pdf"].includes(ext || "")) {
          setError(`Unsupported file type: .${ext}. Supported: .txt, .doc, .docx, .pdf`);
          continue;
        }

        // For .txt files, read directly
        if (ext === "txt") {
          try {
            const text = await file.text();
            if (text.trim()) {
              setSamples((prev) => [...prev, text.trim()]);
              setSampleSources((prev) => [...prev, file.name]);
            }
          } catch {
            setError(`Failed to read file: ${file.name}`);
          }
        } else {
          // For .doc, .docx, .pdf, use backend extraction
          try {
            const result = await extractTextMutation.mutateAsync(file);
            if (result.text.trim()) {
              setSamples((prev) => [...prev, result.text]);
              setSampleSources((prev) => [...prev, file.name]);
            }
          } catch (e) {
            setError(`Failed to extract text from ${file.name}: ${e instanceof Error ? e.message : "Unknown error"}`);
          }
        }
      }
    },
    [extractTextMutation],
  );

  const handleAnalyze = useCallback(async () => {
    if (samples.length === 0) {
      setError("Please add at least one writing sample.");
      return;
    }
    setError(null);

    // Start intelligence moment
    setShowIntelligence(true);
    setIntelligenceData({ sampleCount: samples.length });

    try {
      const result = await analyzeMutation.mutateAsync(samples);
      setFingerprint(result);
      setIntelligenceData({
        writingFingerprint: result,
        sampleCount: samples.length,
      });
      const response = await completeStep("writing_samples", {
        sample_count: samples.length,
        confidence: result.confidence,
      });
      onComplete(response);
    } catch {
      setShowIntelligence(false);
      setError("Analysis failed. Please try again.");
    }
  }, [samples, analyzeMutation, onComplete]);

  const traitBar = (label: string, value: number) => (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-[var(--text-secondary,#A1A1AA)]">{label}</span>
        <span className="font-mono text-[var(--text-tertiary,#6B7280)]">
          {Math.round(value * 100)}%
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/10">
        <div
          className="h-full rounded-full bg-[var(--color-accent,#2E66FF)] transition-all"
          style={{ width: `${value * 100}%` }}
        />
      </div>
    </div>
  );

  const isProcessing = analyzeMutation.isPending || extractTextMutation.isPending;

  // Show intelligence moment during analysis
  if (showIntelligence) {
    return (
      <IntelligenceMoment
        step="writing_samples"
        responseData={intelligenceData}
        isLoading={analyzeMutation.isPending}
        minDuration={2200}
      />
    );
  }

  return (
    <div className="mx-auto w-full max-w-2xl space-y-4">
      {!fingerprint ? (
        <>
          {/* Instructions */}
          <div className="rounded-lg border border-white/5 bg-white/[0.02] px-4 py-3">
            <p className="text-sm text-[var(--text-secondary,#A1A1AA)]">
              You can paste emails, reports, LinkedIn posts, or any writing. The more samples, the better ARIA matches your voice.
            </p>
          </div>

          {/* File upload drop zone */}
          <div
            className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-6 transition ${
              isDragging
                ? "border-[var(--color-accent,#2E66FF)] bg-[var(--color-accent,#2E66FF)]/5"
                : "border-white/10 hover:border-white/20"
            }`}
            onClick={() => fileInputRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setIsDragging(false);
              void handleFiles(e.dataTransfer.files);
            }}
          >
            <Upload className="mb-2 h-6 w-6 text-[var(--text-tertiary,#6B7280)]" />
            <p className="text-sm text-[var(--text-secondary,#A1A1AA)]">
              Drag files here or click to browse
            </p>
            <p className="mt-1 text-xs text-[var(--text-tertiary,#6B7280)]">
              TXT, DOC, DOCX, PDF
            </p>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept={WRITING_SAMPLE_FILE_TYPES}
              className="hidden"
              onChange={(e) => void handleFiles(e.target.files)}
            />
          </div>

          {/* Text input */}
          <div className="space-y-2">
            <textarea
              value={currentSample}
              onChange={(e) => setCurrentSample(e.target.value)}
              placeholder="Or paste a sample directly here..."
              rows={4}
              className="w-full resize-none rounded-lg border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-[var(--text-primary,#F1F1F1)] placeholder-[var(--text-tertiary,#6B7280)] outline-none transition focus:border-[var(--color-accent,#2E66FF)]"
            />
            <button
              onClick={handleAddSample}
              disabled={!currentSample.trim()}
              className="rounded-lg border border-white/10 bg-white/[0.03] px-4 py-2 text-sm font-medium text-[var(--text-primary,#F1F1F1)] transition hover:border-white/20 disabled:opacity-40"
            >
              Add Sample
            </button>
          </div>

          {/* Sample count badge */}
          {samples.length > 0 && (
            <div className="flex items-center gap-2">
              <span className="rounded-full bg-[var(--color-accent,#2E66FF)]/20 px-2.5 py-0.5 text-xs font-medium text-[var(--color-accent,#2E66FF)]">
                {samples.length} sample{samples.length !== 1 ? "s" : ""} added
              </span>
            </div>
          )}

          {/* Added samples list */}
          {samples.length > 0 && (
            <div className="space-y-2">
              {samples.map((sample, idx) => (
                <div
                  key={idx}
                  className="flex items-start justify-between rounded-lg border border-white/5 bg-white/[0.02] px-4 py-2.5"
                >
                  <div className="mr-3 flex-1">
                    <p className="mb-1 text-xs text-[var(--text-tertiary,#6B7280)]">
                      {sampleSources[idx] === "pasted" ? "Pasted text" : sampleSources[idx]}
                    </p>
                    <p className="line-clamp-2 text-sm text-[var(--text-secondary,#A1A1AA)]">
                      {sample.slice(0, 200)}{sample.length > 200 ? "..." : ""}
                    </p>
                  </div>
                  <button
                    onClick={() => handleRemoveSample(idx)}
                    className="shrink-0 text-xs text-[var(--text-tertiary,#6B7280)] transition hover:text-red-400"
                  >
                    Remove
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* Email learning message */}
          {emailConnected && samples.length > 0 && (
            <div className="rounded-lg border border-[var(--color-accent,#2E66FF)]/20 bg-[var(--color-accent,#2E66FF)]/5 px-4 py-3">
              <p className="text-sm text-[var(--text-secondary,#A1A1AA)]">
                I'll also learn from your sent emails to refine your writing style over time.
              </p>
            </div>
          )}

          {error && (
            <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
              {error}
            </div>
          )}

          {isProcessing && (
            <div className="flex items-center gap-2 text-sm text-[var(--text-tertiary,#6B7280)]">
              <Loader2 className="h-4 w-4 animate-spin" />
              {extractTextMutation.isPending ? "Extracting text from file..." : "Analyzing your writing style..."}
            </div>
          )}

          <div className="flex items-center gap-3">
            <button
              onClick={() => void handleAnalyze()}
              disabled={samples.length === 0 || isProcessing}
              className="rounded-lg bg-[var(--color-accent,#2E66FF)] px-4 py-2.5 text-sm font-medium text-white transition hover:bg-[var(--color-accent,#2E66FF)]/90 disabled:opacity-40"
            >
              Analyze My Style
            </button>
            <button
              onClick={onSkip}
              className="text-sm text-[var(--text-tertiary,#6B7280)] transition hover:text-[var(--text-secondary,#A1A1AA)]"
            >
              Skip — ARIA will learn from your emails instead
            </button>
          </div>
        </>
      ) : (
        <div className="space-y-4 rounded-lg border border-white/10 bg-white/[0.03] p-5">
          <h3 className="text-sm font-medium text-[var(--text-primary,#F1F1F1)]">
            Your Writing Style
          </h3>
          <p className="text-sm text-[var(--text-secondary,#A1A1AA)]">
            {fingerprint.style_summary}
          </p>
          <div className="space-y-3">
            {traitBar("Directness", fingerprint.directness)}
            {traitBar("Warmth", fingerprint.warmth)}
            {traitBar("Assertiveness", fingerprint.assertiveness)}
            {traitBar("Formality", fingerprint.formality_index)}
          </div>
          <div className="flex flex-wrap gap-2 text-xs">
            <span className="rounded-full border border-white/10 px-2.5 py-1 text-[var(--text-secondary,#A1A1AA)]">
              {fingerprint.rhetorical_style}
            </span>
            <span className="rounded-full border border-white/10 px-2.5 py-1 text-[var(--text-secondary,#A1A1AA)]">
              Vocabulary: {fingerprint.vocabulary_sophistication}
            </span>
            <span className="rounded-full border border-white/10 px-2.5 py-1 text-[var(--text-secondary,#A1A1AA)]">
              Confidence: {Math.round(fingerprint.confidence * 100)}%
            </span>
          </div>
          {emailConnected && (
            <p className="text-xs text-[var(--text-tertiary,#6B7280)]">
              I'll continue refining your style as I learn from your sent emails.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// --- Action Panel: Document Upload ---

function DocumentUploadPanel({
  onComplete,
  onSkip,
}: {
  onComplete: (response: OnboardingStateResponse) => void;
  onSkip: () => void;
}) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const uploadMutation = useDocumentUpload();
  const documentsQuery = useDocuments(true);
  const [isDragging, setIsDragging] = useState(false);

  const acceptedTypes =
    ".pdf,.docx,.pptx,.txt,.md,.csv,.xlsx";

  const handleFiles = useCallback(
    (files: FileList | null) => {
      if (!files) return;
      Array.from(files).forEach((file) => {
        uploadMutation.mutate(file);
      });
    },
    [uploadMutation],
  );

  const handleDone = useCallback(async () => {
    const docs = documentsQuery.data ?? [];
    const response = await completeStep("document_upload", {
      document_count: docs.length,
    });
    onComplete(response);
  }, [documentsQuery.data, onComplete]);

  const documents: CompanyDocument[] = documentsQuery.data ?? [];

  const statusBadge = (status: CompanyDocument["processing_status"]) => {
    const styles: Record<string, string> = {
      uploaded: "bg-blue-500/20 text-blue-400",
      processing: "bg-yellow-500/20 text-yellow-400",
      complete: "bg-green-500/20 text-green-400",
      failed: "bg-red-500/20 text-red-400",
    };
    return (
      <span
        className={`rounded px-1.5 py-0.5 text-xs ${styles[status] ?? ""}`}
      >
        {status}
      </span>
    );
  };

  return (
    <div className="mx-auto w-full max-w-2xl space-y-4">
      {/* Drop zone */}
      <div
        className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-10 transition ${
          isDragging
            ? "border-[var(--color-accent,#2E66FF)] bg-[var(--color-accent,#2E66FF)]/5"
            : "border-white/10 hover:border-white/20"
        }`}
        onClick={() => fileInputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragging(false);
          handleFiles(e.dataTransfer.files);
        }}
      >
        <Upload className="mb-3 h-8 w-8 text-[var(--text-tertiary,#6B7280)]" />
        <p className="text-sm text-[var(--text-secondary,#A1A1AA)]">
          Drag files here or click to browse
        </p>
        <p className="mt-1 text-xs text-[var(--text-tertiary,#6B7280)]">
          PDF, DOCX, PPTX, TXT, MD, CSV, XLSX
        </p>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept={acceptedTypes}
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>

      {/* Uploaded files list */}
      {documents.length > 0 && (
        <div className="space-y-2">
          {documents.map((doc) => (
            <div
              key={doc.id}
              className="flex items-center justify-between rounded-lg border border-white/5 bg-white/[0.02] px-4 py-2.5"
            >
              <div className="flex items-center gap-2.5">
                <FileText className="h-4 w-4 text-[var(--text-tertiary,#6B7280)]" />
                <span className="text-sm text-[var(--text-primary,#F1F1F1)]">
                  {doc.filename}
                </span>
              </div>
              {statusBadge(doc.processing_status)}
            </div>
          ))}
        </div>
      )}

      {uploadMutation.isPending && (
        <div className="flex items-center gap-2 text-sm text-[var(--text-tertiary,#6B7280)]">
          <Loader2 className="h-4 w-4 animate-spin" />
          Uploading...
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => void handleDone()}
          disabled={documents.length === 0}
          className="rounded-lg bg-[var(--color-accent,#2E66FF)] px-4 py-2.5 text-sm font-medium text-white transition hover:bg-[var(--color-accent,#2E66FF)]/90 disabled:opacity-40"
        >
          Done
        </button>
        <button
          onClick={onSkip}
          className="text-sm text-[var(--text-tertiary,#6B7280)] transition hover:text-[var(--text-secondary,#A1A1AA)]"
        >
          Skip for now
        </button>
      </div>
    </div>
  );
}

// --- Action Panel: Email Integration ---

const DATE_RANGE_OPTIONS = [
  { value: 30, label: "30 days" },
  { value: 60, label: "60 days" },
  { value: 90, label: "90 days" },
  { value: 180, label: "180 days" },
  { value: 365, label: "1 year" },
] as const;

function EmailIntegrationPanel({
  onComplete,
  onSkip,
}: {
  onComplete: (response: OnboardingStateResponse) => void;
  onSkip: () => void;
}) {
  const connectMutation = useEmailConnect();
  // EmailIntegrationPanel is only rendered when on email_integration step,
  // so always enable status checking here
  const statusQuery = useEmailStatus(true);

  // Bootstrap status - only poll after privacy config is saved
  const [showBootstrapProgress, setShowBootstrapProgress] = useState(false);
  const bootstrapStatusQuery = useEmailBootstrapStatus(showBootstrapProgress);

  // Privacy config state
  const [ingestionScopeDays, setIngestionScopeDays] = useState(60);
  const [excludedDomains, setExcludedDomains] = useState("");
  const [excludedSenders, setExcludedSenders] = useState("");
  const [attachmentIngestion, setAttachmentIngestion] = useState(false);

  const googleConnected = statusQuery.data?.google?.connected ?? false;
  const microsoftConnected = statusQuery.data?.microsoft?.connected ?? false;
  const anyConnected = googleConnected || microsoftConnected;

  const handleConnect = useCallback(
    async (provider: EmailProvider) => {
      const result = await connectMutation.mutateAsync(provider);
      // Store provider in sessionStorage to retrieve after OAuth callback
      sessionStorage.setItem("pending_email_provider", provider);
      // Redirect in current tab instead of opening new window
      window.location.href = result.auth_url;
    },
    [connectMutation],
  );

  const handleSavePrivacyAndStartBootstrap = useCallback(async () => {
    const provider = googleConnected ? "google" : "microsoft";

    // Build privacy exclusions from inputs
    const privacyExclusions: PrivacyExclusion[] = [];

    // Parse excluded domains (comma-separated)
    if (excludedDomains.trim()) {
      const domains = excludedDomains
        .split(",")
        .map((d) => d.trim())
        .filter((d) => d.length > 0);
      domains.forEach((domain) => {
        privacyExclusions.push({ type: "domain", value: domain });
      });
    }

    // Parse excluded senders (comma-separated)
    if (excludedSenders.trim()) {
      const senders = excludedSenders
        .split(",")
        .map((s) => s.trim())
        .filter((s) => s.length > 0);
      senders.forEach((sender) => {
        privacyExclusions.push({ type: "sender", value: sender });
      });
    }

    // Save privacy config
    try {
      await saveEmailPrivacyConfig({
        provider,
        privacy_exclusions: privacyExclusions,
        ingestion_scope_days: ingestionScopeDays,
        attachment_ingestion: attachmentIngestion,
      });
    } catch (error) {
      console.error("Failed to save email privacy config:", error);
      // Continue anyway - privacy config is optional
    }

    // Show bootstrap progress - backend triggers bootstrap automatically after record-connection
    setShowBootstrapProgress(true);
  }, [
    googleConnected,
    excludedDomains,
    excludedSenders,
    ingestionScopeDays,
    attachmentIngestion,
  ]);

  const handleBootstrapComplete = useCallback(async () => {
    const provider = googleConnected ? "google" : "microsoft";
    // Complete the step
    const response = await completeStep("email_integration", { provider });
    onComplete(response);
  }, [googleConnected, onComplete]);

  // Show bootstrap progress after privacy config is saved
  if (showBootstrapProgress && bootstrapStatusQuery.data) {
    return (
      <EmailBootstrapProgress
        status={bootstrapStatusQuery.data}
        provider={googleConnected ? "google" : "microsoft"}
        onContinue={() => void handleBootstrapComplete()}
        onSkip={onSkip}
      />
    );
  }

  return (
    <div className="mx-auto w-full max-w-2xl space-y-4">
      <div className="flex gap-3">
        {/* Gmail button */}
        <AnimatedConnectionButton
          isConnected={googleConnected}
          isPending={connectMutation.isPending}
          onConnect={() => void handleConnect("google")}
          connectLabel="Connect Gmail"
          connectedLabel="Gmail Connected"
          icon={Mail}
          className="flex-1"
        />

        {/* Outlook button */}
        <AnimatedConnectionButton
          isConnected={microsoftConnected}
          isPending={connectMutation.isPending}
          onConnect={() => void handleConnect("microsoft")}
          connectLabel="Connect Outlook"
          connectedLabel="Outlook Connected"
          icon={Mail}
          className="flex-1"
        />
      </div>

      {connectMutation.isPending && (
        <div className="flex items-center gap-2 text-sm text-[var(--text-tertiary,#6B7280)]">
          <Loader2 className="h-4 w-4 animate-spin" />
          Opening authentication window...
        </div>
      )}

      {/* Privacy Controls - shown after connection */}
      {anyConnected && (
        <div className="mt-6 space-y-4 rounded-lg border border-white/10 bg-white/[0.02] p-4">
          <p className="text-sm text-[var(--text-secondary,#A1A1AA)]">
            Before I start reading your emails, let me know your comfort level.
            You can always adjust these later in Settings.
          </p>

          {/* Date Range Selector */}
          <div className="space-y-2">
            <label className="block text-sm font-medium text-[var(--text-primary,#F1F1F1)]">
              How far back should I read?
            </label>
            <select
              value={ingestionScopeDays}
              onChange={(e) => setIngestionScopeDays(Number(e.target.value))}
              className="w-full rounded-lg border border-white/10 bg-[var(--surface-secondary,#1A1D24)] px-3 py-2 text-sm text-[var(--text-primary,#F1F1F1)] focus:border-[var(--color-accent,#2E66FF)] focus:outline-none"
            >
              {DATE_RANGE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>

          {/* Exclude Domains */}
          <div className="space-y-2">
            <label className="block text-sm font-medium text-[var(--text-primary,#F1F1F1)]">
              Exclude domains
              <span className="ml-1 font-normal text-[var(--text-tertiary,#6B7280)]">
                (comma-separated, e.g. personal.gmail.com)
              </span>
            </label>
            <input
              type="text"
              value={excludedDomains}
              onChange={(e) => setExcludedDomains(e.target.value)}
              placeholder="e.g. newsletters.com, personal.gmail.com"
              className="w-full rounded-lg border border-white/10 bg-[var(--surface-secondary,#1A1D24)] px-3 py-2 text-sm text-[var(--text-primary,#F1F1F1)] placeholder:text-[var(--text-tertiary,#6B7280)] focus:border-[var(--color-accent,#2E66FF)] focus:outline-none"
            />
          </div>

          {/* Exclude Senders */}
          <div className="space-y-2">
            <label className="block text-sm font-medium text-[var(--text-primary,#F1F1F1)]">
              Exclude specific senders
              <span className="ml-1 font-normal text-[var(--text-tertiary,#6B7280)]">
                (comma-separated email addresses)
              </span>
            </label>
            <input
              type="text"
              value={excludedSenders}
              onChange={(e) => setExcludedSenders(e.target.value)}
              placeholder="e.g. spouse@personal.com, hr@company.com"
              className="w-full rounded-lg border border-white/10 bg-[var(--surface-secondary,#1A1D24)] px-3 py-2 text-sm text-[var(--text-primary,#F1F1F1)] placeholder:text-[var(--text-tertiary,#6B7280)] focus:border-[var(--color-accent,#2E66FF)] focus:outline-none"
            />
          </div>

          {/* Attachment Toggle */}
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setAttachmentIngestion(!attachmentIngestion)}
              className={`flex h-5 w-9 shrink-0 items-center rounded-full transition-colors ${
                attachmentIngestion
                  ? "bg-[var(--color-accent,#2E66FF)]"
                  : "bg-white/20"
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  attachmentIngestion ? "translate-x-4" : "translate-x-0.5"
                }`}
              />
            </button>
            <span className="text-sm text-[var(--text-primary,#F1F1F1)]">
              Allow me to read attachments
            </span>
          </div>
        </div>
      )}

      <div className="flex items-center gap-3">
        <button
          onClick={() => void handleSavePrivacyAndStartBootstrap()}
          disabled={!anyConnected}
          className="rounded-lg bg-[var(--color-accent,#2E66FF)] px-4 py-2.5 text-sm font-medium text-white transition hover:bg-[var(--color-accent,#2E66FF)]/90 disabled:opacity-40"
        >
          Continue
        </button>
        <button
          onClick={onSkip}
          className="text-sm text-[var(--text-tertiary,#6B7280)] transition hover:text-[var(--text-secondary,#A1A1AA)]"
        >
          Skip for now
        </button>
      </div>
    </div>
  );
}

// --- Action Panel: Integration Wizard ---

function IntegrationWizardPanel({
  onComplete,
  onSkip,
}: {
  onComplete: (response: OnboardingStateResponse) => void;
  onSkip: () => void;
}) {
  const statusQuery = useIntegrationWizardStatus(true);
  const connectMutation = useConnectIntegration();
  const [connectingApp, setConnectingApp] = useState<IntegrationAppName | null>(null);

  const allIntegrations = useMemo(() => {
    const data = statusQuery.data;
    return [
      ...(data?.crm ?? []),
      ...(data?.calendar ?? []),
      ...(data?.messaging ?? []),
    ];
  }, [statusQuery.data]);

  const connectedCount = useMemo(
    () => allIntegrations.filter((i) => i.connected).length,
    [allIntegrations]
  );

  const handleConnect = useCallback(
    async (appName: IntegrationAppName) => {
      setConnectingApp(appName);
      try {
        const result = await connectMutation.mutateAsync(appName);
        // Redirect in current tab instead of opening new window
        window.location.href = result.auth_url;
      } finally {
        setConnectingApp(null);
      }
    },
    [connectMutation],
  );

  const handleContinue = useCallback(async () => {
    const connectedNames = allIntegrations
      .filter((i) => i.connected)
      .map((i) => i.name);
    const response = await completeStep("integration_wizard", {
      connected_integrations: connectedNames,
    });
    onComplete(response);
  }, [allIntegrations, onComplete]);

  const renderIntegrationButton = (integration: IntegrationStatus) => {
    const isConnecting = connectingApp === integration.name;
    const isPending = connectMutation.isPending && isConnecting;

    return (
      <AnimatedConnectionButton
        key={integration.name}
        isConnected={integration.connected}
        isPending={isPending}
        onConnect={() => void handleConnect(integration.name)}
        connectLabel={`Connect ${integration.display_name}`}
        connectedLabel={`${integration.display_name} Connected`}
        icon={ExternalLink}
        className="w-full"
      />
    );
  };

  const renderCategory = (
    title: string,
    icon: React.ReactNode,
    items: IntegrationStatus[]
  ) => (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-[var(--text-tertiary,#6B7280)]">
        {icon}
        {title}
      </div>
      <div className="space-y-2">
        {items.map(renderIntegrationButton)}
      </div>
    </div>
  );

  if (statusQuery.isLoading) {
    return (
      <div className="mx-auto w-full max-w-2xl space-y-4">
        <div className="flex items-center gap-2 text-sm text-[var(--text-tertiary,#6B7280)]">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading available integrations...
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-2xl space-y-5">
      {renderCategory("CRM", <Building2 className="h-3.5 w-3.5" />, statusQuery.data?.crm ?? [])}
      {renderCategory("Calendar", <Calendar className="h-3.5 w-3.5" />, statusQuery.data?.calendar ?? [])}
      {renderCategory("Messaging", <MessageSquare className="h-3.5 w-3.5" />, statusQuery.data?.messaging ?? [])}

      {connectedCount > 0 && (
        <p className="text-sm text-green-400">
          {connectedCount} integration{connectedCount !== 1 ? "s" : ""} connected
        </p>
      )}

      <div className="flex items-center gap-3">
        <button
          onClick={() => void handleContinue()}
          className="rounded-lg bg-[var(--color-accent,#2E66FF)] px-4 py-2.5 text-sm font-medium text-white transition hover:bg-[var(--color-accent,#2E66FF)]/90 disabled:opacity-40"
        >
          Continue
        </button>
        <button
          onClick={onSkip}
          className="text-sm text-[var(--text-tertiary,#6B7280)] transition hover:text-[var(--text-secondary,#A1A1AA)]"
        >
          Skip for now
        </button>
      </div>
    </div>
  );
}

// --- Action Panel: First Goal ---

function FirstGoalPanel({
  onComplete,
}: {
  onComplete: (response: OnboardingStateResponse) => void;
}) {
  const suggestionsQuery = useFirstGoalSuggestions(true);
  const createGoalMutation = useCreateFirstGoal();
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [manualTitle, setManualTitle] = useState("");

  const suggestions: GoalSuggestion[] =
    suggestionsQuery.data?.suggestions ?? [];

  const handleSelectGoal = useCallback(
    async (suggestion: GoalSuggestion) => {
      const goalResult = await createGoalMutation.mutateAsync({
        title: suggestion.title,
        description: suggestion.description,
        goal_type: suggestion.goal_type,
      });
      const response = await completeStep("first_goal", {
        goal_id: goalResult.goal.id,
      });
      onComplete(response);
    },
    [createGoalMutation, onComplete],
  );

  const handleManualGoal = useCallback(async () => {
    if (!manualTitle.trim()) return;
    const goalResult = await createGoalMutation.mutateAsync({
      title: manualTitle.trim(),
    });
    const response = await completeStep("first_goal", {
      goal_id: goalResult.goal.id,
    });
    onComplete(response);
  }, [manualTitle, createGoalMutation, onComplete]);

  const categoryColors: Record<string, string> = {
    pipeline: "bg-blue-500/20 text-blue-400",
    intelligence: "bg-purple-500/20 text-purple-400",
    communication: "bg-green-500/20 text-green-400",
    strategy: "bg-amber-500/20 text-amber-400",
  };

  const urgencyColors: Record<string, string> = {
    high: "bg-red-500/20 text-red-400",
    medium: "bg-yellow-500/20 text-yellow-400",
    low: "bg-green-500/20 text-green-400",
  };

  if (suggestionsQuery.isLoading) {
    return (
      <div className="mx-auto w-full max-w-2xl space-y-3">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="h-28 animate-pulse rounded-lg border border-white/5 bg-white/[0.02]"
          />
        ))}
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-2xl space-y-3">
      {suggestions.length > 0 ? (
        suggestions.map((suggestion, idx) => (
          <button
            key={idx}
            onClick={() => {
              setSelectedIndex(idx);
              void handleSelectGoal(suggestion);
            }}
            disabled={createGoalMutation.isPending}
            className={`w-full rounded-lg border p-4 text-left transition ${
              selectedIndex === idx
                ? "border-[var(--color-accent,#2E66FF)] bg-[var(--color-accent,#2E66FF)]/5"
                : "border-white/5 bg-white/[0.02] hover:border-white/15"
            } disabled:opacity-60`}
          >
            <div className="mb-2 flex items-start justify-between">
              <h3 className="text-sm font-medium text-[var(--text-primary,#F1F1F1)]">
                {suggestion.title}
              </h3>
              <div className="flex gap-1.5">
                <span
                  className={`rounded px-1.5 py-0.5 text-xs ${categoryColors[suggestion.category] ?? "bg-white/10 text-white/60"}`}
                >
                  {suggestion.category}
                </span>
                <span
                  className={`rounded px-1.5 py-0.5 text-xs ${urgencyColors[suggestion.urgency] ?? "bg-white/10 text-white/60"}`}
                >
                  {suggestion.urgency}
                </span>
              </div>
            </div>
            <p className="mb-1.5 text-sm text-[var(--text-secondary,#A1A1AA)]">
              {suggestion.description}
            </p>
            <p className="text-xs italic text-[var(--text-tertiary,#6B7280)]">
              {suggestion.reason}
            </p>
            {selectedIndex === idx && createGoalMutation.isPending && (
              <div className="mt-2 flex items-center gap-2 text-xs text-[var(--color-accent,#2E66FF)]">
                <Loader2 className="h-3 w-3 animate-spin" />
                Creating goal...
              </div>
            )}
          </button>
        ))
      ) : (
        /* Fallback: manual goal entry */
        <div className="space-y-3">
          <p className="text-sm text-[var(--text-secondary,#A1A1AA)]">
            Tell me what you'd like to accomplish first:
          </p>
          <div className="flex gap-3">
            <input
              value={manualTitle}
              onChange={(e) => setManualTitle(e.target.value)}
              placeholder="e.g. Build pipeline for Q3 targets"
              className="flex-1 rounded-lg border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-[var(--text-primary,#F1F1F1)] placeholder-[var(--text-tertiary,#6B7280)] outline-none transition focus:border-[var(--color-accent,#2E66FF)]"
              onKeyDown={(e) => {
                if (e.key === "Enter") void handleManualGoal();
              }}
            />
            <button
              onClick={() => void handleManualGoal()}
              disabled={!manualTitle.trim() || createGoalMutation.isPending}
              className="rounded-lg bg-[var(--color-accent,#2E66FF)] px-4 py-2.5 text-sm font-medium text-white transition hover:bg-[var(--color-accent,#2E66FF)]/90 disabled:opacity-40"
            >
              {createGoalMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Target className="h-4 w-4" />
              )}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// --- Action Panel: Activation ---

function ActivationPanel({
  onReady,
}: {
  onReady: () => void;
}) {
  const activateMutation = useActivateAria();
  const enrichment = useEnrichmentStatus(true);
  const activation = useActivationStatus(true);
  const hasTriggered = useRef(false);
  const hasCompleted = useRef(false);

  // Trigger activation on mount
  useEffect(() => {
    if (!hasTriggered.current) {
      hasTriggered.current = true;
      activateMutation.mutate();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const enrichmentDone = enrichment.isComplete;
  const activationDone = activation.data?.status === "complete";
  const allDone = enrichmentDone && activationDone;

  // Derive progress
  let progress = 10;
  let statusText = "Enriching company data...";

  if (enrichmentDone && !activationDone) {
    progress = 60;
    statusText = "Deploying agents...";
  } else if (allDone) {
    progress = 100;
    statusText = "Almost ready...";
  } else if (enrichment.isInProgress) {
    progress = 35;
    statusText = "Enriching company data...";
  }

  useEffect(() => {
    if (allDone && !hasCompleted.current) {
      hasCompleted.current = true;
      const timer = setTimeout(() => {
        onReady();
      }, 2000);
      return () => clearTimeout(timer);
    }
  }, [allDone, onReady]);

  return (
    <div className="mx-auto w-full max-w-2xl space-y-4">
      <ProgressBar
        value={progress}
        variant="default"
        size="md"
        animated={!allDone}
        className="w-full"
      />
      <div className="flex items-center gap-3 rounded-lg border border-white/5 bg-white/[0.02] px-4 py-3">
        {allDone ? (
          <Check className="h-5 w-5 text-green-400" />
        ) : (
          <Loader2 className="h-5 w-5 animate-spin text-[var(--color-accent,#2E66FF)]" />
        )}
        <span className="text-sm text-[var(--text-secondary,#A1A1AA)]">
          {statusText}
        </span>
      </div>
    </div>
  );
}

// --- Main OnboardingPage ---

export function OnboardingPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const [messages, setMessages] = useState<Message[]>([]);
  const [currentStep, setCurrentStep] = useState<OnboardingStep | null>(null);
  const [activeActionPanel, setActiveActionPanel] =
    useState<OnboardingStep | null>(null);
  const [isInitialized, setIsInitialized] = useState(false);
  const [inputValue, setInputValue] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const [completedSteps, setCompletedSteps] = useState<string[]>([]);
  const [skippedSteps, setSkippedSteps] = useState<string[]>([]);
  const [stepData, setStepData] = useState<Record<string, unknown>>({});
  const bottomRef = useRef<HTMLDivElement>(null);

  // Animation state
  const [animationDirection, setAnimationDirection] = useState<AnimationDirection>("none");
  const [stepKey, setStepKey] = useState(0);
  const [animatingDot, setAnimatingDot] = useState<string | null>(null);
  const prevProgressRef = useRef(0);

  // Check email connection status (for writing samples panel)
  // Only poll when on email_integration step; otherwise just check once
  const emailStatusQuery = useEmailStatus(currentStep === "email_integration");
  const emailConnected = (emailStatusQuery.data?.google?.connected ?? false) ||
    (emailStatusQuery.data?.microsoft?.connected ?? false);

  // Auto-scroll on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, activeActionPanel]);

  // --- State resumption on mount ---
  useEffect(() => {
    getOnboardingState()
      .then((stateResponse) => {
        if (stateResponse.is_complete) {
          navigate("/", { replace: true });
          return;
        }

        const step = stateResponse.state.current_step;
        const stateCompletedSteps = stateResponse.state.completed_steps;
        const stateSkippedSteps = stateResponse.state.skipped_steps;
        const stateStepData = stateResponse.state.step_data;

        // Store step state for back navigation
        setCompletedSteps(stateCompletedSteps);
        setSkippedSteps(stateSkippedSteps);
        setStepData(stateStepData);

        // Only show the CURRENT step's ARIA message - previous steps are represented by progress dots
        setMessages([
          createMessage("aria", STEP_CONFIG[step].ariaMessage),
        ]);
        setCurrentStep(step);
        if (STEP_CONFIG[step].inputMode === "action_panel") {
          setActiveActionPanel(step);
        }
        setIsInitialized(true);
      })
      .catch(() => {
        // Bootstrap from first step
        setMessages([
          createMessage(
            "aria",
            STEP_CONFIG.company_discovery.ariaMessage,
            "greeting",
          ),
        ]);
        setCurrentStep("company_discovery");
        setIsInitialized(true);
      });
  }, [navigate]);

  // --- OAuth callback detection ---
  // Handle Composio OAuth redirect with status=success&connected_account_id=XXX
  // Use ref to ensure we only process the callback once
  const oauthCallbackProcessedRef = useRef(false);

  useEffect(() => {
    // Skip if already processed
    if (oauthCallbackProcessedRef.current) {
      return;
    }

    const status = searchParams.get("status");
    const connectedAccountId = searchParams.get("connected_account_id");

    if (status === "success" && connectedAccountId) {
      // Mark as processed immediately
      oauthCallbackProcessedRef.current = true;

      // Retrieve provider from sessionStorage (set before OAuth redirect)
      const pendingProvider = sessionStorage.getItem("pending_email_provider");
      // Map provider to integration_type
      const integrationType = pendingProvider === "microsoft" ? "outlook" : "gmail";

      console.log("[OAuth] Processing callback:", {
        status,
        connectedAccountId,
        pendingProvider,
        integrationType,
      });

      // Clean URL params immediately to prevent re-triggering
      window.history.replaceState({}, "", window.location.pathname);

      // Record the connection explicitly in the database
      recordEmailConnection({
        integration_type: integrationType,
        connection_id: connectedAccountId,
      })
        .then(() => {
          console.log("[OAuth] Connection recorded successfully");
          // Clear the pending provider
          sessionStorage.removeItem("pending_email_provider");
          // Invalidate email status to refresh UI
          queryClient.invalidateQueries({ queryKey: emailKeys.status() });
        })
        .catch((error) => {
          console.error("[OAuth] Failed to record email connection:", error);
          // Still invalidate to trigger backend auto-discovery as fallback
          queryClient.invalidateQueries({ queryKey: emailKeys.status() });
        });
    }
  }, [searchParams, queryClient]);

  // --- Navigation helpers ---

  const advanceToStep = useCallback(
    (nextStep: OnboardingStep, direction: AnimationDirection = "forward") => {
      const currentIndex = currentStep ? stepIndex(currentStep) : -1;
      const nextIndex = stepIndex(nextStep);

      // Determine animation direction if not specified
      const actualDirection = direction === "none"
        ? (nextIndex > currentIndex ? "forward" : "backward")
        : direction;

      setAnimationDirection(actualDirection);
      setStepKey((k) => k + 1);
      setCurrentStep(nextStep);
      setInputValue("");

      const config = STEP_CONFIG[nextStep];
      // REPLACE messages - only show current step, previous step content is gone
      setMessages([createMessage("aria", config.ariaMessage)]);

      if (config.inputMode === "action_panel") {
        setActiveActionPanel(nextStep);
      } else {
        setActiveActionPanel(null);
      }

      // Activation step has no panel in activeActionPanel — it renders based on currentStep
      if (nextStep === "activation") {
        setActiveActionPanel(null);
      }

      // Trigger dot animation for completed step
      if (actualDirection === "forward" && currentStep) {
        setAnimatingDot(currentStep);
        setTimeout(() => setAnimatingDot(null), 300);
      }
    },
    [currentStep],
  );

  const advanceFromResponse = useCallback(
    (response: OnboardingStateResponse) => {
      if (response.is_complete) {
        navigate("/", { replace: true });
        return;
      }
      // Update step state tracking
      setCompletedSteps(response.state.completed_steps);
      setSkippedSteps(response.state.skipped_steps);
      setStepData(response.state.step_data);
      advanceToStep(response.state.current_step, "forward");
    },
    [advanceToStep, navigate],
  );

  // Navigate to a specific step (for back navigation and clicking on completed steps)
  const goToStep = useCallback(
    (targetStep: OnboardingStep) => {
      if (!currentStep) return;

      const currentIndex = stepIndex(currentStep);
      const targetIndex = stepIndex(targetStep);
      const direction: AnimationDirection = targetIndex < currentIndex ? "backward" : "forward";

      setAnimationDirection(direction);
      setStepKey((k) => k + 1);
      setCurrentStep(targetStep);
      setInputValue("");

      const config = STEP_CONFIG[targetStep];
      // Update the ARIA message for the new step
      setMessages([createMessage("aria", config.ariaMessage)]);

      if (config.inputMode === "action_panel") {
        setActiveActionPanel(targetStep);
      } else {
        setActiveActionPanel(null);
      }

      if (targetStep === "activation") {
        setActiveActionPanel(null);
      }
    },
    [currentStep],
  );

  // Go back to previous step
  const goBack = useCallback(() => {
    if (!currentStep) return;

    const currentIndex = stepIndex(currentStep);
    if (currentIndex <= 0) return; // Can't go back from first step

    const previousStep = STEP_ORDER[currentIndex - 1];

    // REPLACE messages - only show previous step
    setMessages([createMessage("aria", STEP_CONFIG[previousStep].ariaMessage)]);

    goToStep(previousStep);
  }, [currentStep, goToStep]);

  // Check if we can go back
  const canGoBack = currentStep ? stepIndex(currentStep) > 0 : false;

  const handleSend = useCallback(async () => {
    const text = inputValue.trim();
    if (!text || isProcessing || !currentStep) return;

    setInputValue("");
    setMessages((prev) => [...prev, createMessage("user", text)]);
    setIsProcessing(true);

    try {
      const response = await completeStep(currentStep, { user_input: text });
      advanceFromResponse(response);
    } catch {
      setMessages((prev) => [
        ...prev,
        createMessage(
          "aria",
          "I had trouble saving that. Let's try again — could you repeat what you said?",
        ),
      ]);
    } finally {
      setIsProcessing(false);
    }
  }, [inputValue, isProcessing, currentStep, advanceFromResponse]);

  const handleSkip = useCallback(async () => {
    if (!currentStep) return;

    setMessages((prev) => [
      ...prev,
      createMessage("user", "I'll skip this for now."),
    ]);
    setIsProcessing(true);

    try {
      const response = await skipStep(currentStep);
      advanceFromResponse(response);
    } catch {
      setMessages((prev) => [
        ...prev,
        createMessage(
          "aria",
          "I had trouble with that. Let's try moving forward.",
        ),
      ]);
    } finally {
      setIsProcessing(false);
    }
  }, [currentStep, advanceFromResponse]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        void handleSend();
      }
    },
    [handleSend],
  );

  const handleActivationReady = useCallback(() => {
    setMessages((prev) => [
      ...prev,
      createMessage("aria", "Everything's ready. Let's get to work."),
    ]);
    setTimeout(() => {
      navigate("/", { replace: true });
    }, 2000);
  }, [navigate]);

  // --- Derived state ---

  const currentConfig = currentStep ? STEP_CONFIG[currentStep] : null;
  const showTextInput = currentConfig?.inputMode === "text";
  const isInputDisabled = isProcessing || !showTextInput;
  const progressPercent = currentStep
    ? ((stepIndex(currentStep)) / STEP_ORDER.length) * 100
    : 0;

  // Track progress changes for smooth bar animation
  const progressChanged = progressPercent !== prevProgressRef.current;
  if (progressChanged) {
    prevProgressRef.current = progressPercent;
  }

  if (!isInitialized) {
    return (
      <div className="flex h-screen items-center justify-center bg-[var(--bg-primary,#0A0A0B)]">
        <Loader2 className="h-6 w-6 animate-spin text-[var(--color-accent,#2E66FF)]" />
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col bg-[var(--bg-primary,#0A0A0B)] text-[var(--text-primary,#F1F1F1)]">
      {/* Header */}
      <header className="border-b border-white/5 px-6 py-4">
        <div className="mx-auto max-w-2xl">
          <div className="mb-3 flex items-center justify-between">
            {/* Back button */}
            <div className="w-20">
              {canGoBack && (
                <button
                  onClick={goBack}
                  className="flex items-center gap-1 text-sm text-[var(--text-tertiary,#6B7280)] transition hover:text-[var(--text-secondary,#A1A1AA)]"
                >
                  <ChevronLeft className="h-4 w-4" />
                  Back
                </button>
              )}
            </div>

            <h1 className="font-display text-xl italic text-[var(--text-primary,#F1F1F1)]">
              Welcome to ARIA
            </h1>

            <div className="w-20" />
          </div>

          {/* Step indicators */}
          <div className="mb-3 flex items-center justify-center gap-1.5">
            {STEP_ORDER.map((step, idx) => {
              const isCompleted = completedSteps.includes(step) || skippedSteps.includes(step);
              const isSkipped = skippedSteps.includes(step);
              const isCurrent = step === currentStep;
              const isPast = currentStep ? idx < stepIndex(currentStep) : false;
              const isClickable = isCompleted || isSkipped || isPast;
              const isAnimating = animatingDot === step;

              return (
                <button
                  key={step}
                  onClick={() => isClickable && goToStep(step)}
                  disabled={!isClickable}
                  className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-medium transition ${
                    isAnimating ? "onboarding-dot-complete" : ""
                  } ${
                    isCurrent
                      ? "bg-[var(--color-accent,#2E66FF)] text-white"
                      : isCompleted
                        ? "cursor-pointer bg-green-500/20 text-green-400 hover:bg-green-500/30"
                        : isSkipped
                          ? "cursor-pointer bg-yellow-500/20 text-yellow-400 hover:bg-yellow-500/30"
                          : isPast
                            ? "cursor-pointer bg-white/10 text-[var(--text-tertiary,#6B7280)] hover:bg-white/15"
                            : "bg-white/5 text-[var(--text-tertiary,#6B7280)]"
                  }`}
                  title={STEP_DISPLAY_NAMES[step]}
                >
                  {isCompleted ? (
                    <Check
                      className={`h-3 w-3 ${isAnimating ? "onboarding-checkmark-draw" : ""}`}
                      style={isAnimating ? { strokeDasharray: 24, strokeDashoffset: 0 } : undefined}
                    />
                  ) : isSkipped ? (
                    "—"
                  ) : (
                    idx + 1
                  )}
                </button>
              );
            })}
          </div>

          <div className="overflow-hidden rounded-full bg-white/5">
            <div
              className="h-1.5 rounded-full bg-[var(--color-accent,#2E66FF)] transition-[width] duration-400 ease-out"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>
      </header>

      {/* Conversation area */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="mx-auto flex max-w-2xl flex-col gap-4">
          {messages.map((msg, idx) => (
            <AnimatedMessage key={msg.id} messageKey={msg.id}>
              <MessageBubble
                message={msg}
                isFirstInGroup={
                  idx === 0 || messages[idx - 1].role !== msg.role
                }
              />
            </AnimatedMessage>
          ))}

          {isProcessing && (
            <div className="flex items-center gap-2 px-4 py-2 text-sm text-[var(--text-tertiary,#6B7280)]">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>ARIA is thinking...</span>
            </div>
          )}

          {/* Action panels with animation wrapper */}
          <AnimatedStepContent direction={animationDirection} stepKey={String(stepKey)}>
            {activeActionPanel === "company_discovery" && (
              <CompanyDiscoveryPanel
                onComplete={advanceFromResponse}
                initialData={stepData.company_discovery as Record<string, unknown> | undefined}
              />
            )}

            {activeActionPanel === "document_upload" && (
              <DocumentUploadPanel
                onComplete={advanceFromResponse}
                onSkip={() => void handleSkip()}
              />
            )}

            {activeActionPanel === "user_profile" && (
              <UserProfilePanel
                onComplete={advanceFromResponse}
                initialData={stepData.user_profile as Record<string, unknown> | undefined}
              />
            )}

            {activeActionPanel === "writing_samples" && (
              <WritingSamplesPanel
                onComplete={advanceFromResponse}
                onSkip={() => void handleSkip()}
                emailConnected={emailConnected}
              />
            )}

            {activeActionPanel === "email_integration" && (
              <EmailIntegrationPanel
                onComplete={advanceFromResponse}
                onSkip={() => void handleSkip()}
              />
            )}

            {activeActionPanel === "integration_wizard" && (
              <IntegrationWizardPanel
                onComplete={advanceFromResponse}
                onSkip={() => void handleSkip()}
              />
            )}

            {activeActionPanel === "first_goal" && (
              <FirstGoalPanel onComplete={advanceFromResponse} />
            )}

            {currentStep === "activation" && (
              <ActivationPanel onReady={handleActivationReady} />
            )}
          </AnimatedStepContent>

          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input bar */}
      {showTextInput && (
        <div className="border-t border-white/5 px-4 py-4">
          <div className="mx-auto max-w-2xl">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void handleSend();
              }}
              className="flex items-end gap-3"
            >
              <textarea
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={isInputDisabled}
                placeholder={
                  currentConfig?.placeholder ?? "Type your response..."
                }
                rows={1}
                className="flex-1 resize-none rounded-lg border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-[var(--text-primary,#F1F1F1)] placeholder-[var(--text-tertiary,#6B7280)] outline-none transition focus:border-[var(--color-accent,#2E66FF)] disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={!inputValue.trim() || isInputDisabled}
                className="rounded-lg bg-[var(--color-accent,#2E66FF)] px-4 py-3 text-sm font-medium text-white transition hover:bg-[var(--color-accent,#2E66FF)]/90 disabled:opacity-40"
              >
                Send
              </button>
            </form>
            {currentConfig?.skippable && (
              <button
                onClick={() => void handleSkip()}
                disabled={isProcessing}
                className="mt-2 text-sm text-[var(--text-tertiary,#6B7280)] transition hover:text-[var(--text-secondary,#A1A1AA)]"
              >
                Skip for now
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
