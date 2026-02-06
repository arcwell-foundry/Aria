import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getOnboardingState,
  completeStep,
  skipStep,
  getRoutingDecision,
  getReadiness,
  type OnboardingStep,
} from "@/api/onboarding";

export const onboardingKeys = {
  all: ["onboarding"] as const,
  state: () => [...onboardingKeys.all, "state"] as const,
  routing: () => [...onboardingKeys.all, "routing"] as const,
  readiness: () => [...onboardingKeys.all, "readiness"] as const,
};

export function useOnboardingState() {
  return useQuery({
    queryKey: onboardingKeys.state(),
    queryFn: getOnboardingState,
  });
}

export function useCompleteStep() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      step,
      stepData,
    }: {
      step: OnboardingStep;
      stepData?: Record<string, unknown>;
    }) => completeStep(step, stepData),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: onboardingKeys.state() });
    },
  });
}

export function useSkipStep() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      step,
      reason,
    }: {
      step: OnboardingStep;
      reason?: string;
    }) => skipStep(step, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: onboardingKeys.state() });
    },
  });
}

export function useRoutingDecision() {
  return useQuery({
    queryKey: onboardingKeys.routing(),
    queryFn: getRoutingDecision,
  });
}

export function useReadiness() {
  return useQuery({
    queryKey: onboardingKeys.readiness(),
    queryFn: getReadiness,
    refetchInterval: 5 * 60 * 1000, // Refetch every 5 minutes
  });
}

