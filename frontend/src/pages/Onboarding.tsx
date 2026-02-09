import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  useOnboardingState,
  useCompleteStep,
  useSkipStep,
  useInjectedQuestions,
  onboardingKeys,
} from "@/hooks/useOnboarding";
import { SKIPPABLE_STEPS, type OnboardingStep } from "@/api/onboarding";
import { OnboardingProgress } from "@/components/onboarding/OnboardingProgress";
import { OnboardingStepPlaceholder } from "@/components/onboarding/OnboardingStepPlaceholder";
import { CompanyDiscoveryStep } from "@/components/onboarding/CompanyDiscoveryStep";
import { DocumentUploadStep } from "@/components/onboarding/DocumentUploadStep";
import { UserProfileStep } from "@/components/onboarding/UserProfileStep";
import { WritingSampleStep } from "@/components/onboarding/WritingSampleStep";
import { EmailIntegrationStep } from "@/components/onboarding/EmailIntegrationStep";
import { IntegrationWizardStep } from "@/components/onboarding/IntegrationWizardStep";
import { FirstGoalStep } from "@/components/onboarding/FirstGoalStep";

export function OnboardingPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data, isLoading } = useOnboardingState();
  const completeMutation = useCompleteStep();
  const skipMutation = useSkipStep();
  const stepForQueries = data?.state?.current_step ?? "";
  const { data: injectedQuestions } = useInjectedQuestions(stepForQueries);

  const [viewingStep, setViewingStep] = useState<OnboardingStep | null>(null);

  const currentStep = data?.state?.current_step;
  const prevStepRef = useRef(currentStep);

  // Reset viewingStep when the server's current step advances
  if (currentStep !== prevStepRef.current) {
    prevStepRef.current = currentStep;
    if (viewingStep !== null) {
      setViewingStep(null);
    }
  }

  // Redirect to dashboard if onboarding is already complete
  useEffect(() => {
    if (data?.is_complete) {
      navigate("/dashboard", { replace: true });
    }
  }, [data?.is_complete, navigate]);

  if (isLoading || !data) {
    return <OnboardingSkeleton />;
  }

  const { state } = data;
  const serverStep = state.current_step;
  const displayStep = viewingStep ?? serverStep;
  const isRevisiting = viewingStep !== null;
  const isSkippable = SKIPPABLE_STEPS.has(serverStep);

  function handleComplete(companyData?: { company_name: string; website: string; email: string }) {
    if (isRevisiting) {
      setViewingStep(null);
      return;
    }
    completeMutation.mutate({ step: serverStep, stepData: companyData || {} });
  }

  function handleSkip() {
    if (isRevisiting) {
      setViewingStep(null);
      return;
    }
    skipMutation.mutate({ step: serverStep });
  }

  function handleStepClick(step: OnboardingStep) {
    if (step === serverStep) {
      setViewingStep(null);
    } else {
      setViewingStep(step);
    }
  }

  return (
    <div className="min-h-screen bg-primary">
      <div className="mx-auto max-w-[960px] px-6 py-12 md:py-16">
        {/* Header */}
        <div className="mb-12">
          <p className="font-sans text-xs font-medium text-secondary tracking-widest uppercase">
            Getting started
          </p>
        </div>

        <div className="flex flex-col md:flex-row gap-12 md:gap-16">
          {/* Left: Progress indicator */}
          <aside className="md:w-48 shrink-0">
            <OnboardingProgress
              currentStep={serverStep}
              activeStep={displayStep}
              completedSteps={state.completed_steps}
              skippedSteps={state.skipped_steps}
              onStepClick={handleStepClick}
            />
          </aside>

          {/* Right: Step content */}
          <main className="flex-1 min-w-0">
            {/* OODA-injected contextual questions (US-916) */}
            {!isRevisiting && injectedQuestions && injectedQuestions.length > 0 && (
              <div className="mb-6 space-y-3">
                {injectedQuestions.map((q, i) => (
                  <div
                    key={i}
                    className="rounded-xl border border-border bg-subtle px-5 py-4"
                  >
                    <p className="text-[13px] font-medium text-secondary mb-1">
                      {q.context}
                    </p>
                    <p className="text-[15px] text-content">{q.question}</p>
                  </div>
                ))}
              </div>
            )}

            {displayStep === "company_discovery" ? (
              <CompanyDiscoveryStep
                onComplete={(companyData) => handleComplete(companyData)}
              />
            ) : displayStep === "document_upload" ? (
              <DocumentUploadStep
                onComplete={() => handleComplete()}
                onSkip={handleSkip}
              />
            ) : displayStep === "user_profile" ? (
              <UserProfileStep
                onComplete={() => handleComplete()}
                onSkip={!isRevisiting && isSkippable ? handleSkip : undefined}
              />
            ) : displayStep === "writing_samples" ? (
              <WritingSampleStep
                onComplete={() => handleComplete()}
                onSkip={handleSkip}
              />
            ) : displayStep === "email_integration" ? (
              <EmailIntegrationStep
                onComplete={() => handleComplete()}
                onSkip={handleSkip}
              />
            ) : displayStep === "integration_wizard" ? (
              <IntegrationWizardStep
                onComplete={() => handleComplete()}
              />
            ) : displayStep === "first_goal" ? (
              <FirstGoalStep
                onComplete={() => {
                  if (isRevisiting) {
                    setViewingStep(null);
                    return;
                  }
                  queryClient.invalidateQueries({ queryKey: onboardingKeys.state() });
                }}
              />
            ) : (
              <OnboardingStepPlaceholder
                step={displayStep}
                onComplete={handleComplete}
                onSkip={!isRevisiting && isSkippable ? handleSkip : undefined}
                isCompleting={completeMutation.isPending}
                isSkipping={skipMutation.isPending}
              />
            )}
          </main>
        </div>
      </div>
    </div>
  );
}

const SKELETON_WIDTHS = [72, 84, 92, 88, 64, 96, 76, 80];

function OnboardingSkeleton() {
  return (
    <div className="min-h-screen bg-primary">
      <div className="mx-auto max-w-[960px] px-6 py-12 md:py-16">
        <div className="mb-12">
          <div className="h-4 w-28 rounded bg-border animate-pulse" />
        </div>
        <div className="flex flex-col md:flex-row gap-12 md:gap-16">
          <aside className="md:w-48 shrink-0">
            <div className="flex flex-col gap-2">
              {SKELETON_WIDTHS.map((w, i) => (
                <div key={i} className="flex items-center gap-3 px-3 py-2.5">
                  <div className="w-6 h-6 rounded-full bg-border animate-pulse" />
                  <div
                    className="h-3.5 rounded bg-border animate-pulse"
                    style={{ width: `${w}px` }}
                  />
                </div>
              ))}
            </div>
          </aside>
          <main className="flex-1 min-w-0">
            <div className="flex flex-col gap-6">
              <div className="h-10 w-48 rounded bg-border animate-pulse" />
              <div className="h-5 w-80 rounded bg-border animate-pulse" />
              <div className="h-20 w-full rounded-xl bg-subtle animate-pulse" />
              <div className="h-10 w-28 rounded-lg bg-border animate-pulse" />
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}
