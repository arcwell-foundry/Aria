import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getOnboardingState,
  completeStep,
  skipStep,
  getRoutingDecision,
  getReadiness,
  getInjectedQuestions,
  getEnrichmentDelta,
  getFirstGoalSuggestions,
  createFirstGoal,
  activateAria,
  type OnboardingStep,
  type FirstGoalCreateRequest,
} from "@/api/onboarding";
import {
  uploadDocument,
  getDocuments,
} from "@/api/documents";
import {
  connectEmail,
  getEmailStatus,
  type EmailProvider,
} from "@/api/emailIntegration";

export const onboardingKeys = {
  all: ["onboarding"] as const,
  state: () => [...onboardingKeys.all, "state"] as const,
  routing: () => [...onboardingKeys.all, "routing"] as const,
  readiness: () => [...onboardingKeys.all, "readiness"] as const,
  injectedQuestions: (step: string) =>
    [...onboardingKeys.all, "injected-questions", step] as const,
  enrichmentDelta: () => [...onboardingKeys.all, "enrichment-delta"] as const,
};

export const documentKeys = {
  all: ["documents"] as const,
  list: () => [...documentKeys.all, "list"] as const,
};

export const emailKeys = {
  all: ["email"] as const,
  status: () => [...emailKeys.all, "status"] as const,
};

export const goalKeys = {
  all: ["goals"] as const,
  suggestions: () => [...goalKeys.all, "suggestions"] as const,
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

export function useInjectedQuestions(step: string) {
  return useQuery({
    queryKey: onboardingKeys.injectedQuestions(step),
    queryFn: () => getInjectedQuestions(step),
    enabled: !!step,
  });
}

export function useEnrichmentDelta() {
  return useQuery({
    queryKey: onboardingKeys.enrichmentDelta(),
    queryFn: getEnrichmentDelta,
  });
}

// --- Document hooks ---

export function useDocumentUpload() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (file: File) => uploadDocument(file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: documentKeys.list() });
    },
  });
}

export function useDocuments(enabled: boolean) {
  return useQuery({
    queryKey: documentKeys.list(),
    queryFn: getDocuments,
    enabled,
  });
}

// --- Email hooks ---

export function useEmailConnect() {
  return useMutation({
    mutationFn: (provider: EmailProvider) => connectEmail(provider),
  });
}

export function useEmailStatus(enabled: boolean) {
  return useQuery({
    queryKey: emailKeys.status(),
    queryFn: getEmailStatus,
    enabled,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (data?.google?.connected || data?.microsoft?.connected) {
        return false;
      }
      return 3000;
    },
  });
}

// --- First goal hooks ---

export function useFirstGoalSuggestions(enabled: boolean) {
  return useQuery({
    queryKey: goalKeys.suggestions(),
    queryFn: getFirstGoalSuggestions,
    enabled,
  });
}

export function useCreateFirstGoal() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: FirstGoalCreateRequest) => createFirstGoal(request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: onboardingKeys.state() });
    },
  });
}

// --- Activation hook ---

export function useActivateAria() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => activateAria(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: onboardingKeys.state() });
    },
  });
}

