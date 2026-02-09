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
  activeStep?: OnboardingStep;
  completedSteps: string[];
  skippedSteps: string[];
  onStepClick?: (step: OnboardingStep) => void;
}

export function OnboardingProgress({
  currentStep,
  activeStep,
  completedSteps,
  skippedSteps,
  onStepClick,
}: OnboardingProgressProps) {
  const displayStep = activeStep ?? currentStep;

  return (
    <nav aria-label="Onboarding progress" className="w-full">
      {/* Desktop: vertical list */}
      <ol className="hidden md:flex flex-col gap-1">
        {STEPS.map((step) => {
          const isCompleted = completedSteps.includes(step.key);
          const isSkipped = skippedSteps.includes(step.key);
          const isCurrent = step.key === currentStep;
          const isActive = step.key === displayStep;
          const isClickable =
            onStepClick != null && (isCompleted || isSkipped || isCurrent);

          const inner = (
            <>
              <StepIndicator
                isCompleted={isCompleted}
                isSkipped={isSkipped}
                isCurrent={isCurrent}
              />
              <span
                className={`
                  font-sans text-[13px] leading-snug
                  ${isActive ? "font-medium text-content" : ""}
                  ${isCompleted && !isActive ? "text-success" : ""}
                  ${isSkipped && !isActive ? "text-secondary" : ""}
                  ${!isActive && !isCompleted && !isSkipped ? "text-secondary" : ""}
                `}
              >
                {step.label}
              </span>
            </>
          );

          const classes = `
            flex items-center gap-3 rounded-lg px-3 py-2.5 w-full text-left
            transition-colors duration-150
            ${isActive ? "bg-subtle" : ""}
            ${isClickable && !isActive ? "hover:bg-subtle/50" : ""}
          `;

          return (
            <li key={step.key}>
              {isClickable ? (
                <button
                  type="button"
                  onClick={() => onStepClick(step.key)}
                  className={`${classes} cursor-pointer`}
                  aria-current={isActive ? "step" : undefined}
                  aria-label={`${step.label}${isCompleted ? " — completed" : ""}${isSkipped ? " — skipped" : ""}${isActive ? " — viewing" : ""}${isCurrent && !isActive ? " — current step" : ""}`}
                >
                  {inner}
                </button>
              ) : (
                <div
                  className={classes}
                  aria-current={isActive ? "step" : undefined}
                  aria-label={`${step.label} — not yet available`}
                >
                  {inner}
                </div>
              )}
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
          const isActive = step.key === displayStep;
          const isClickable =
            onStepClick != null && (isCompleted || isSkipped || isCurrent);

          const dotClasses = `
            h-1.5 rounded-full transition-all duration-300
            ${isActive ? "w-8 bg-interactive" : "w-4"}
            ${isCompleted && !isActive ? "bg-success" : ""}
            ${isSkipped && !isActive ? "bg-border" : ""}
            ${!isActive && !isCompleted && !isSkipped ? "bg-border" : ""}
          `;

          return (
            <li
              key={step.key}
              aria-current={isActive ? "step" : undefined}
              aria-label={`${step.label}${isCompleted ? " — completed" : ""}${isSkipped ? " — skipped" : ""}${isActive ? " — viewing" : ""}`}
            >
              {isClickable ? (
                <button
                  type="button"
                  onClick={() => onStepClick(step.key)}
                  className={`${dotClasses} cursor-pointer`}
                  aria-label={`Go to ${step.label}`}
                />
              ) : (
                <div className={dotClasses} />
              )}
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
