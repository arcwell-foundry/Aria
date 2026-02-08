import { Check, Minus } from "lucide-react";
import type { OnboardingStep } from "@/api/onboarding";

interface StepDefinition {
  key: OnboardingStep;
  label: string;
}

const STEPS: StepDefinition[] = [
  { key: "company_discovery", label: "Company" },
  { key: "document_upload", label: "Documents" },
  { key: "user_profile", label: "Your Profile" },
  { key: "writing_samples", label: "Writing Style" },
  { key: "email_integration", label: "Email" },
  { key: "integration_wizard", label: "Integrations" },
  { key: "first_goal", label: "First Goal" },
  { key: "activation", label: "Activation" },
];

interface OnboardingProgressProps {
  currentStep: OnboardingStep;
  completedSteps: string[];
  skippedSteps: string[];
}

export function OnboardingProgress({
  currentStep,
  completedSteps,
  skippedSteps,
}: OnboardingProgressProps) {
  return (
    <nav aria-label="Onboarding progress" className="w-full">
      {/* Desktop: vertical list */}
      <ol className="hidden md:flex flex-col gap-1">
        {STEPS.map((step) => {
          const isCompleted = completedSteps.includes(step.key);
          const isSkipped = skippedSteps.includes(step.key);
          const isCurrent = step.key === currentStep;

          return (
            <li key={step.key}>
              <div
                className={`
                  flex items-center gap-3 rounded-lg px-3 py-2.5
                  transition-colors duration-150
                  ${isCurrent ? "bg-subtle" : ""}
                `}
                aria-current={isCurrent ? "step" : undefined}
                aria-label={`${step.label}${isCompleted ? " — completed" : ""}${isSkipped ? " — skipped" : ""}${isCurrent ? " — current step" : ""}`}
              >
                <StepIndicator
                  isCompleted={isCompleted}
                  isSkipped={isSkipped}
                  isCurrent={isCurrent}
                />
                <span
                  className={`
                    font-sans text-[13px] leading-snug
                    ${isCurrent ? "font-medium text-content" : ""}
                    ${isCompleted ? "text-success" : ""}
                    ${isSkipped ? "text-secondary" : ""}
                    ${!isCurrent && !isCompleted && !isSkipped ? "text-secondary" : ""}
                  `}
                >
                  {step.label}
                </span>
              </div>
            </li>
          );
        })}
      </ol>

      {/* Mobile: horizontal compact steps */}
      <ol className="flex md:hidden items-center gap-1.5 justify-center py-2">
        {STEPS.map((step) => {
          const isCompleted = completedSteps.includes(step.key);
          const isSkipped = skippedSteps.includes(step.key);
          const isCurrent = step.key === currentStep;

          return (
            <li
              key={step.key}
              aria-current={isCurrent ? "step" : undefined}
              aria-label={`${step.label}${isCompleted ? " — completed" : ""}${isSkipped ? " — skipped" : ""}${isCurrent ? " — current step" : ""}`}
            >
              <div
                className={`
                  h-1.5 rounded-full transition-all duration-300
                  ${isCurrent ? "w-8 bg-interactive" : "w-4"}
                  ${isCompleted ? "bg-success" : ""}
                  ${isSkipped ? "bg-border" : ""}
                  ${!isCurrent && !isCompleted && !isSkipped ? "bg-border" : ""}
                `}
              />
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

function StepIndicator({
  isCompleted,
  isSkipped,
  isCurrent,
}: {
  isCompleted: boolean;
  isSkipped: boolean;
  isCurrent: boolean;
}) {
  const baseClasses =
    "flex items-center justify-center w-6 h-6 rounded-full shrink-0 transition-all duration-150";

  if (isCompleted) {
    return (
      <span className={`${baseClasses} bg-success/10`}>
        <Check size={14} strokeWidth={2} className="text-success" />
      </span>
    );
  }

  if (isSkipped) {
    return (
      <span className={`${baseClasses} bg-border`}>
        <Minus size={12} strokeWidth={2} className="text-secondary" />
      </span>
    );
  }

  if (isCurrent) {
    return (
      <span className={`${baseClasses} bg-interactive/10 ring-1 ring-interactive/30`}>
        <span className="w-2 h-2 rounded-full bg-interactive" />
      </span>
    );
  }

  return (
    <span className={`${baseClasses} bg-subtle`}>
      <span className="w-1.5 h-1.5 rounded-full bg-border" />
    </span>
  );
}
