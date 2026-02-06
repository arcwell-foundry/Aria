import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  useOnboardingState,
  useCompleteStep,
  useSkipStep,
} from "@/hooks/useOnboarding";
import { SKIPPABLE_STEPS } from "@/api/onboarding";
import { OnboardingProgress } from "@/components/onboarding/OnboardingProgress";
import { OnboardingStepPlaceholder } from "@/components/onboarding/OnboardingStepPlaceholder";
import { CompanyDiscoveryStep } from "@/components/onboarding/CompanyDiscoveryStep";
import { DocumentUploadStep } from "@/components/onboarding/DocumentUploadStep";

export function OnboardingPage() {
  const navigate = useNavigate();
  const { data, isLoading } = useOnboardingState();
  const completeMutation = useCompleteStep();
  const skipMutation = useSkipStep();

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
  const currentStep = state.current_step;
  const isSkippable = SKIPPABLE_STEPS.has(currentStep);

  function handleComplete(companyData?: { company_name: string; website: string; email: string }) {
    completeMutation.mutate({ step: currentStep, stepData: companyData || {} });
  }

  function handleSkip() {
    skipMutation.mutate({ step: currentStep });
  }

  return (
    <div className="min-h-screen bg-[#FAFAF9]">
      <div className="mx-auto max-w-[960px] px-6 py-12 md:py-16">
        {/* Header */}
        <div className="mb-12">
          <p className="font-sans text-[13px] font-medium text-[#6B7280] tracking-wide uppercase">
            Getting started
          </p>
        </div>

        <div className="flex flex-col md:flex-row gap-12 md:gap-16">
          {/* Left: Progress indicator */}
          <aside className="md:w-48 shrink-0">
            <OnboardingProgress
              currentStep={currentStep}
              completedSteps={state.completed_steps}
              skippedSteps={state.skipped_steps}
            />
          </aside>

          {/* Right: Step content */}
          <main className="flex-1 min-w-0">
            {currentStep === "company_discovery" ? (
              <CompanyDiscoveryStep
                onComplete={(companyData) => handleComplete(companyData)}
              />
            ) : currentStep === "document_upload" ? (
              <DocumentUploadStep
                onComplete={() => handleComplete()}
                onSkip={handleSkip}
              />
            ) : (
              <OnboardingStepPlaceholder
                step={currentStep}
                onComplete={handleComplete}
                onSkip={isSkippable ? handleSkip : undefined}
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
    <div className="min-h-screen bg-[#FAFAF9]">
      <div className="mx-auto max-w-[960px] px-6 py-12 md:py-16">
        <div className="mb-12">
          <div className="h-4 w-28 rounded bg-[#E2E0DC] animate-pulse" />
        </div>
        <div className="flex flex-col md:flex-row gap-12 md:gap-16">
          <aside className="md:w-48 shrink-0">
            <div className="flex flex-col gap-2">
              {SKELETON_WIDTHS.map((w, i) => (
                <div key={i} className="flex items-center gap-3 px-3 py-2.5">
                  <div className="w-6 h-6 rounded-full bg-[#E2E0DC] animate-pulse" />
                  <div
                    className="h-3.5 rounded bg-[#E2E0DC] animate-pulse"
                    style={{ width: `${w}px` }}
                  />
                </div>
              ))}
            </div>
          </aside>
          <main className="flex-1 min-w-0">
            <div className="flex flex-col gap-6">
              <div className="h-10 w-48 rounded bg-[#E2E0DC] animate-pulse" />
              <div className="h-5 w-80 rounded bg-[#E2E0DC] animate-pulse" />
              <div className="h-20 w-full rounded-xl bg-[#F5F5F0] animate-pulse" />
              <div className="h-10 w-28 rounded-lg bg-[#E2E0DC] animate-pulse" />
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}
