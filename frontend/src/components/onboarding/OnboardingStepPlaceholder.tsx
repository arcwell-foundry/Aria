import { SKIPPABLE_STEPS, type OnboardingStep } from "@/api/onboarding";

const STEP_INFO: Record<OnboardingStep, { title: string; description: string; ariaNote: string }> = {
  company_discovery: {
    title: "Your Company",
    description: "Tell ARIA about your company so she can begin learning about your world.",
    ariaNote: "I'll research your company and start building a picture of your market, competitors, and opportunities.",
  },
  document_upload: {
    title: "Documents",
    description: "Share sales decks, playbooks, or strategy documents for ARIA to learn from.",
    ariaNote: "I'll read and absorb your key documents to understand how your team operates.",
  },
  user_profile: {
    title: "Your Profile",
    description: "Help ARIA understand your role, responsibilities, and how you like to work.",
    ariaNote: "I'll calibrate how I communicate and prioritize based on your working style.",
  },
  writing_samples: {
    title: "Writing Style",
    description: "Share a few emails or messages so ARIA can learn to write in your voice.",
    ariaNote: "I'll study your tone and phrasing so drafts feel genuinely yours.",
  },
  email_integration: {
    title: "Email",
    description: "Connect your email so ARIA can understand your relationships and communication patterns.",
    ariaNote: "I'll map your professional network and learn who matters most to your work.",
  },
  integration_wizard: {
    title: "Integrations",
    description: "Connect your CRM and other tools so ARIA can work alongside your existing workflow.",
    ariaNote: "I'll sync with your systems so insights flow into the tools you already use.",
  },
  first_goal: {
    title: "First Goal",
    description: "Set your first objective and let ARIA begin working toward it.",
    ariaNote: "I'll break this down into actions and start pursuing it autonomously.",
  },
  activation: {
    title: "Activation",
    description: "Review what ARIA has learned and activate her as your department director.",
    ariaNote: "I'll show you everything I've learned and how I plan to help.",
  },
};

interface OnboardingStepPlaceholderProps {
  step: OnboardingStep;
  onComplete: () => void;
  onSkip?: () => void;
  isCompleting: boolean;
  isSkipping: boolean;
}

export function OnboardingStepPlaceholder({
  step,
  onComplete,
  onSkip,
  isCompleting,
  isSkipping,
}: OnboardingStepPlaceholderProps) {
  const info = STEP_INFO[step];
  const isSkippable = SKIPPABLE_STEPS.has(step);

  return (
    <div className="animate-in flex flex-col items-start gap-8 max-w-lg">
      <div className="flex flex-col gap-3">
        <h1
          className="text-[32px] leading-[1.2] text-content"
          style={{ fontFamily: "var(--font-display)" }}
        >
          {info.title}
        </h1>
        <p className="font-sans text-[15px] leading-relaxed text-content">
          {info.description}
        </p>
      </div>

      <div className="rounded-xl bg-subtle border border-border px-5 py-4 w-full">
        <p
          className="font-sans text-[13px] leading-relaxed text-secondary italic"
        >
          {info.ariaNote}
        </p>
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={onComplete}
          disabled={isCompleting || isSkipping}
          className="
            bg-interactive text-white rounded-lg px-5 py-2.5
            font-sans font-medium text-[15px]
            hover:bg-interactive-hover active:bg-interactive-hover
            transition-colors duration-150
            focus:outline-none focus:ring-2 focus:ring-interactive focus:ring-offset-2
            disabled:opacity-50 disabled:cursor-not-allowed
            cursor-pointer
          "
        >
          {isCompleting ? "Saving..." : "Continue"}
        </button>

        {isSkippable && onSkip && (
          <button
            onClick={onSkip}
            disabled={isCompleting || isSkipping}
            className="
              bg-transparent text-secondary rounded-lg px-4 py-2.5
              font-sans text-[15px]
              hover:bg-subtle
              transition-colors duration-150
              focus:outline-none focus:ring-2 focus:ring-interactive focus:ring-offset-2
              disabled:opacity-50 disabled:cursor-not-allowed
              cursor-pointer
            "
          >
            {isSkipping ? "Skipping..." : "Skip for now"}
          </button>
        )}
      </div>
    </div>
  );
}
