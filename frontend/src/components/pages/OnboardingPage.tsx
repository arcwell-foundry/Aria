import { useState, useCallback, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  Loader2,
  Upload,
  FileText,
  Mail,
  Check,
  Target,
} from "lucide-react";
import { MessageBubble } from "@/components/conversation/MessageBubble";
import { ProgressBar } from "@/components/primitives/ProgressBar";
import type { Message } from "@/types/chat";
import {
  completeStep,
  skipStep,
  getOnboardingState,
  type OnboardingStep,
  type OnboardingStateResponse,
  type GoalSuggestion,
  type WritingStyleFingerprint,
} from "@/api/onboarding";
import {
  useDocumentUpload,
  useDocuments,
  useEmailConnect,
  useEmailStatus,
  useFirstGoalSuggestions,
  useCreateFirstGoal,
  useActivateAria,
  useCompanyDiscovery,
  useAnalyzeWriting,
} from "@/hooks/useOnboarding";
import { useEnrichmentStatus } from "@/hooks/useEnrichmentStatus";
import { useActivationStatus } from "@/hooks/useActivationStatus";
import type { EmailProvider } from "@/api/emailIntegration";
import type { CompanyDocument } from "@/api/documents";

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
      "Welcome! I'm ARIA, your AI Department Director. I'll be working alongside you to transform how your team operates. Let's get started — tell me about your company.",
    inputMode: "action_panel",
    skippable: false,
  },
  document_upload: {
    ariaMessage:
      "I'd love to learn more about your company. If you have any internal documents — pitch decks, product briefs, competitive analyses — upload them here and I'll absorb the key insights.",
    inputMode: "action_panel",
    skippable: true,
  },
  user_profile: {
    ariaMessage:
      "Tell me about yourself so I can personalize my work for you.",
    inputMode: "action_panel",
    skippable: false,
  },
  writing_samples: {
    ariaMessage:
      "I'd like to learn how you communicate so I can draft messages that sound like you. Paste a recent email, report excerpt, or LinkedIn post below — the more samples, the better the match.",
    inputMode: "action_panel",
    skippable: true,
  },
  email_integration: {
    ariaMessage:
      "Let me connect to your email so I can understand your relationships and communication patterns. This helps me prioritize outreach and surface warm leads.",
    inputMode: "action_panel",
    skippable: true,
  },
  integration_wizard: {
    ariaMessage:
      "Would you like to connect any other tools? Tell me which ones you use — Salesforce, HubSpot, Google Calendar, Slack — and I'll wire them up.",
    inputMode: "text",
    skippable: true,
    placeholder: "e.g. Salesforce, Google Calendar, Slack — or type 'skip'",
  },
  first_goal: {
    ariaMessage:
      "Based on what I know so far, here are some goals I'd recommend starting with. Pick one and I'll get to work immediately.",
    inputMode: "action_panel",
    skippable: false,
  },
  activation: {
    ariaMessage:
      "Excellent. Give me a moment while I enrich your company data, deploy your agents, and set up your workspace...",
    inputMode: "none",
    skippable: false,
  },
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
}: {
  onComplete: (response: OnboardingStateResponse) => void;
}) {
  const [companyName, setCompanyName] = useState("");
  const [website, setWebsite] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
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

    const result = await discoveryMutation.mutateAsync({
      company_name: companyName.trim(),
      website: website.trim(),
      email: email.trim(),
    });

    if (!result.success) {
      setError(result.message || result.error);
      return;
    }

    // Advance the onboarding step with company info
    const response = await completeStep("company_discovery", {
      company_id: result.company.id,
      company_name: result.company.name,
    });
    onComplete(response);
  }, [companyName, website, email, discoveryMutation, onComplete]);

  return (
    <div className="mx-auto w-full max-w-2xl space-y-4">
      <div className="space-y-3">
        <input
          value={companyName}
          onChange={(e) => setCompanyName(e.target.value)}
          placeholder="Company name"
          className="w-full rounded-lg border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-[var(--text-primary,#F1F1F1)] placeholder-[var(--text-tertiary,#6B7280)] outline-none transition focus:border-[var(--color-accent,#2E66FF)]"
          onKeyDown={(e) => {
            if (e.key === "Enter") void handleSubmit();
          }}
        />
        <input
          value={website}
          onChange={(e) => setWebsite(e.target.value)}
          placeholder="Website (e.g. acme.com)"
          className="w-full rounded-lg border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-[var(--text-primary,#F1F1F1)] placeholder-[var(--text-tertiary,#6B7280)] outline-none transition focus:border-[var(--color-accent,#2E66FF)]"
          onKeyDown={(e) => {
            if (e.key === "Enter") void handleSubmit();
          }}
        />
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
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          {error}
        </div>
      )}

      {discoveryMutation.isPending && (
        <div className="flex items-center gap-2 text-sm text-[var(--text-tertiary,#6B7280)]">
          <Loader2 className="h-4 w-4 animate-spin" />
          Validating your company...
        </div>
      )}

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
    </div>
  );
}

// --- Action Panel: User Profile ---

function UserProfilePanel({
  onComplete,
}: {
  onComplete: (response: OnboardingStateResponse) => void;
}) {
  const [fullName, setFullName] = useState("");
  const [title, setTitle] = useState("");
  const [department, setDepartment] = useState("");
  const [linkedinUrl, setLinkedinUrl] = useState("");
  const [phone, setPhone] = useState("");
  const [roleType, setRoleType] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

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
      setError("Failed to save profile. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  }, [fullName, title, department, linkedinUrl, phone, roleType, onComplete]);

  return (
    <div className="mx-auto w-full max-w-2xl space-y-4">
      <div className="space-y-3">
        <input
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          placeholder="Full name"
          className="w-full rounded-lg border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-[var(--text-primary,#F1F1F1)] placeholder-[var(--text-tertiary,#6B7280)] outline-none transition focus:border-[var(--color-accent,#2E66FF)]"
          onKeyDown={(e) => {
            if (e.key === "Enter") void handleSubmit();
          }}
        />
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Job title"
          className="w-full rounded-lg border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-[var(--text-primary,#F1F1F1)] placeholder-[var(--text-tertiary,#6B7280)] outline-none transition focus:border-[var(--color-accent,#2E66FF)]"
          onKeyDown={(e) => {
            if (e.key === "Enter") void handleSubmit();
          }}
        />
        <input
          value={department}
          onChange={(e) => setDepartment(e.target.value)}
          placeholder="Department"
          className="w-full rounded-lg border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-[var(--text-primary,#F1F1F1)] placeholder-[var(--text-tertiary,#6B7280)] outline-none transition focus:border-[var(--color-accent,#2E66FF)]"
          onKeyDown={(e) => {
            if (e.key === "Enter") void handleSubmit();
          }}
        />
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
        <input
          value={linkedinUrl}
          onChange={(e) => setLinkedinUrl(e.target.value)}
          placeholder="LinkedIn URL (optional)"
          className="w-full rounded-lg border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-[var(--text-primary,#F1F1F1)] placeholder-[var(--text-tertiary,#6B7280)] outline-none transition focus:border-[var(--color-accent,#2E66FF)]"
          onKeyDown={(e) => {
            if (e.key === "Enter") void handleSubmit();
          }}
        />
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
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          {error}
        </div>
      )}

      {isSubmitting && (
        <div className="flex items-center gap-2 text-sm text-[var(--text-tertiary,#6B7280)]">
          <Loader2 className="h-4 w-4 animate-spin" />
          Saving your profile...
        </div>
      )}

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
    </div>
  );
}

// --- Action Panel: Writing Samples ---

function WritingSamplesPanel({
  onComplete,
  onSkip,
}: {
  onComplete: (response: OnboardingStateResponse) => void;
  onSkip: () => void;
}) {
  const [samples, setSamples] = useState<string[]>([]);
  const [currentSample, setCurrentSample] = useState("");
  const [fingerprint, setFingerprint] = useState<WritingStyleFingerprint | null>(null);
  const [error, setError] = useState<string | null>(null);
  const analyzeMutation = useAnalyzeWriting();

  const handleAddSample = useCallback(() => {
    const text = currentSample.trim();
    if (!text) return;
    setSamples((prev) => [...prev, text]);
    setCurrentSample("");
    setError(null);
  }, [currentSample]);

  const handleRemoveSample = useCallback((index: number) => {
    setSamples((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const handleAnalyze = useCallback(async () => {
    if (samples.length === 0) {
      setError("Please add at least one writing sample.");
      return;
    }
    setError(null);
    try {
      const result = await analyzeMutation.mutateAsync(samples);
      setFingerprint(result);
      const response = await completeStep("writing_samples", {
        sample_count: samples.length,
        confidence: result.confidence,
      });
      onComplete(response);
    } catch {
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

  return (
    <div className="mx-auto w-full max-w-2xl space-y-4">
      {!fingerprint ? (
        <>
          <textarea
            value={currentSample}
            onChange={(e) => setCurrentSample(e.target.value)}
            placeholder="Paste a recent email, report, or LinkedIn post you've written..."
            rows={5}
            className="w-full resize-none rounded-lg border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-[var(--text-primary,#F1F1F1)] placeholder-[var(--text-tertiary,#6B7280)] outline-none transition focus:border-[var(--color-accent,#2E66FF)]"
          />

          <div className="flex items-center gap-3">
            <button
              onClick={handleAddSample}
              disabled={!currentSample.trim()}
              className="rounded-lg border border-white/10 bg-white/[0.03] px-4 py-2 text-sm font-medium text-[var(--text-primary,#F1F1F1)] transition hover:border-white/20 disabled:opacity-40"
            >
              Add Sample
            </button>
            {samples.length > 0 && (
              <span className="rounded-full bg-[var(--color-accent,#2E66FF)]/20 px-2.5 py-0.5 text-xs font-medium text-[var(--color-accent,#2E66FF)]">
                {samples.length} sample{samples.length !== 1 ? "s" : ""} added
              </span>
            )}
          </div>

          {samples.length > 0 && (
            <div className="space-y-2">
              {samples.map((sample, idx) => (
                <div
                  key={idx}
                  className="flex items-start justify-between rounded-lg border border-white/5 bg-white/[0.02] px-4 py-2.5"
                >
                  <p className="mr-3 line-clamp-2 text-sm text-[var(--text-secondary,#A1A1AA)]">
                    {sample}
                  </p>
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

          {error && (
            <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
              {error}
            </div>
          )}

          {analyzeMutation.isPending && (
            <div className="flex items-center gap-2 text-sm text-[var(--text-tertiary,#6B7280)]">
              <Loader2 className="h-4 w-4 animate-spin" />
              Analyzing your writing style...
            </div>
          )}

          <div className="flex items-center gap-3">
            <button
              onClick={() => void handleAnalyze()}
              disabled={samples.length === 0 || analyzeMutation.isPending}
              className="rounded-lg bg-[var(--color-accent,#2E66FF)] px-4 py-2.5 text-sm font-medium text-white transition hover:bg-[var(--color-accent,#2E66FF)]/90 disabled:opacity-40"
            >
              Analyze My Style
            </button>
            <button
              onClick={onSkip}
              className="text-sm text-[var(--text-tertiary,#6B7280)] transition hover:text-[var(--text-secondary,#A1A1AA)]"
            >
              Skip for now
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
          </div>
          <div className="flex flex-wrap gap-2 text-xs">
            <span className="rounded-full border border-white/10 px-2.5 py-1 text-[var(--text-secondary,#A1A1AA)]">
              {fingerprint.rhetorical_style}
            </span>
            <span className="rounded-full border border-white/10 px-2.5 py-1 text-[var(--text-secondary,#A1A1AA)]">
              Formality: {Math.round(fingerprint.formality_index * 100)}%
            </span>
          </div>
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

function EmailIntegrationPanel({
  onComplete,
  onSkip,
}: {
  onComplete: (response: OnboardingStateResponse) => void;
  onSkip: () => void;
}) {
  const connectMutation = useEmailConnect();
  const statusQuery = useEmailStatus(true);
  const [popupBlocked, setPopupBlocked] = useState(false);

  const googleConnected = statusQuery.data?.google?.connected ?? false;
  const microsoftConnected = statusQuery.data?.microsoft?.connected ?? false;
  const anyConnected = googleConnected || microsoftConnected;

  const handleConnect = useCallback(
    async (provider: EmailProvider) => {
      const result = await connectMutation.mutateAsync(provider);
      const popup = window.open(result.auth_url, "_blank");
      if (!popup) {
        setPopupBlocked(true);
      }
    },
    [connectMutation],
  );

  const handleContinue = useCallback(async () => {
    const provider = googleConnected ? "google" : "microsoft";
    const response = await completeStep("email_integration", { provider });
    onComplete(response);
  }, [googleConnected, onComplete]);

  return (
    <div className="mx-auto w-full max-w-2xl space-y-4">
      <div className="flex gap-3">
        {/* Gmail button */}
        <button
          onClick={() => void handleConnect("google")}
          disabled={googleConnected || connectMutation.isPending}
          className={`flex flex-1 items-center justify-center gap-2 rounded-lg border px-4 py-3 text-sm font-medium transition ${
            googleConnected
              ? "border-green-500/30 bg-green-500/10 text-green-400"
              : "border-white/10 bg-white/[0.03] text-[var(--text-primary,#F1F1F1)] hover:border-white/20"
          } disabled:opacity-60`}
        >
          {googleConnected ? (
            <Check className="h-4 w-4" />
          ) : (
            <Mail className="h-4 w-4" />
          )}
          {googleConnected ? "Gmail Connected" : "Connect Gmail"}
        </button>

        {/* Outlook button */}
        <button
          onClick={() => void handleConnect("microsoft")}
          disabled={microsoftConnected || connectMutation.isPending}
          className={`flex flex-1 items-center justify-center gap-2 rounded-lg border px-4 py-3 text-sm font-medium transition ${
            microsoftConnected
              ? "border-green-500/30 bg-green-500/10 text-green-400"
              : "border-white/10 bg-white/[0.03] text-[var(--text-primary,#F1F1F1)] hover:border-white/20"
          } disabled:opacity-60`}
        >
          {microsoftConnected ? (
            <Check className="h-4 w-4" />
          ) : (
            <Mail className="h-4 w-4" />
          )}
          {microsoftConnected ? "Outlook Connected" : "Connect Outlook"}
        </button>
      </div>

      {connectMutation.isPending && (
        <div className="flex items-center gap-2 text-sm text-[var(--text-tertiary,#6B7280)]">
          <Loader2 className="h-4 w-4 animate-spin" />
          Opening authentication window...
        </div>
      )}

      {popupBlocked && (
        <p className="text-sm text-yellow-400">
          Popup was blocked. Please allow popups for this site and try again.
        </p>
      )}

      <div className="flex items-center gap-3">
        <button
          onClick={() => void handleContinue()}
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
  const [messages, setMessages] = useState<Message[]>([]);
  const [currentStep, setCurrentStep] = useState<OnboardingStep | null>(null);
  const [activeActionPanel, setActiveActionPanel] =
    useState<OnboardingStep | null>(null);
  const [isInitialized, setIsInitialized] = useState(false);
  const [inputValue, setInputValue] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

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
        const completedSteps = stateResponse.state.completed_steps;

        // Build summary messages for completed steps
        const resumeMessages: Message[] = [];
        for (const completedStep of STEP_ORDER) {
          if (!completedSteps.includes(completedStep)) break;
          // Add a brief summary ARIA message for the completed step
          resumeMessages.push(
            createMessage(
              "aria",
              STEP_CONFIG[completedStep as OnboardingStep].ariaMessage,
            ),
          );
          resumeMessages.push(
            createMessage("user", "(completed)"),
          );
        }

        // Add the current step's ARIA message
        resumeMessages.push(
          createMessage("aria", STEP_CONFIG[step].ariaMessage),
        );

        setMessages(resumeMessages);
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

  // --- Navigation helpers ---

  const advanceToStep = useCallback(
    (nextStep: OnboardingStep) => {
      setCurrentStep(nextStep);
      setInputValue("");

      const config = STEP_CONFIG[nextStep];
      setMessages((prev) => [...prev, createMessage("aria", config.ariaMessage)]);

      if (config.inputMode === "action_panel") {
        setActiveActionPanel(nextStep);
      } else {
        setActiveActionPanel(null);
      }

      // Activation step has no panel in activeActionPanel — it renders based on currentStep
      if (nextStep === "activation") {
        setActiveActionPanel(null);
      }
    },
    [],
  );

  const advanceFromResponse = useCallback(
    (response: OnboardingStateResponse) => {
      if (response.is_complete) {
        navigate("/", { replace: true });
        return;
      }
      advanceToStep(response.state.current_step);
    },
    [advanceToStep, navigate],
  );

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
          <div className="mb-3 flex items-center justify-center">
            <h1 className="font-display text-xl italic text-[var(--text-primary,#F1F1F1)]">
              Welcome to ARIA
            </h1>
          </div>
          <ProgressBar
            value={progressPercent}
            variant="default"
            size="sm"
            showValue
            formatValue={() => `Step ${currentStep ? stepIndex(currentStep) + 1 : 0} of ${STEP_ORDER.length}`}
          />
        </div>
      </header>

      {/* Conversation area */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="mx-auto flex max-w-2xl flex-col gap-4">
          {messages.map((msg, idx) => (
            <MessageBubble
              key={msg.id}
              message={msg}
              isFirstInGroup={
                idx === 0 || messages[idx - 1].role !== msg.role
              }
            />
          ))}

          {isProcessing && (
            <div className="flex items-center gap-2 px-4 py-2 text-sm text-[var(--text-tertiary,#6B7280)]">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>ARIA is thinking...</span>
            </div>
          )}

          {/* Action panels */}
          {activeActionPanel === "company_discovery" && (
            <CompanyDiscoveryPanel onComplete={advanceFromResponse} />
          )}

          {activeActionPanel === "document_upload" && (
            <DocumentUploadPanel
              onComplete={advanceFromResponse}
              onSkip={() => void handleSkip()}
            />
          )}

          {activeActionPanel === "user_profile" && (
            <UserProfilePanel onComplete={advanceFromResponse} />
          )}

          {activeActionPanel === "writing_samples" && (
            <WritingSamplesPanel
              onComplete={advanceFromResponse}
              onSkip={() => void handleSkip()}
            />
          )}

          {activeActionPanel === "email_integration" && (
            <EmailIntegrationPanel
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
