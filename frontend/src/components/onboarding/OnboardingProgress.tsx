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
                  ${isCurrent ? "bg-[#F5F5F0]" : ""}
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
                    ${isCurrent ? "font-medium text-[#1A1D27]" : ""}
                    ${isCompleted ? "text-[#5A7D60]" : ""}
                    ${isSkipped ? "text-[#6B7280]" : ""}
                    ${!isCurrent && !isCompleted && !isSkipped ? "text-[#6B7280]" : ""}
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
                  ${isCurrent ? "w-8 bg-[#5B6E8A]" : "w-4"}
                  ${isCompleted ? "bg-[#5A7D60]" : ""}
                  ${isSkipped ? "bg-[#E2E0DC]" : ""}
                  ${!isCurrent && !isCompleted && !isSkipped ? "bg-[#E2E0DC]" : ""}
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
      <span className={`${baseClasses} bg-[#5A7D60]/10`}>
        <Check size={14} strokeWidth={2} className="text-[#5A7D60]" />
      </span>
    );
  }

  if (isSkipped) {
    return (
      <span className={`${baseClasses} bg-[#E2E0DC]`}>
        <Minus size={12} strokeWidth={2} className="text-[#6B7280]" />
      </span>
    );
  }

  if (isCurrent) {
    return (
      <span className={`${baseClasses} bg-[#5B6E8A]/10 ring-1 ring-[#5B6E8A]/30`}>
        <span className="w-2 h-2 rounded-full bg-[#5B6E8A]" />
      </span>
    );
  }

  return (
    <span className={`${baseClasses} bg-[#F5F5F0]`}>
      <span className="w-1.5 h-1.5 rounded-full bg-[#E2E0DC]" />
    </span>
  );
}
