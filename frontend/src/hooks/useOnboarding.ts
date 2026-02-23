import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useEffect, useCallback } from "react";
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
  submitCompanyDiscovery,
  analyzeWritingSamples,
  extractTextFromFile,
  getIntegrationWizardStatus,
  connectIntegration,
  disconnectIntegration,
  type OnboardingStep,
  type FirstGoalCreateRequest,
  type CompanyDiscoveryRequest,
  type IntegrationAppName,
} from "@/api/onboarding";
import {
  uploadDocument,
  getDocuments,
} from "@/api/documents";
import {
  connectEmail,
  getEmailStatus,
  getBootstrapStatus,
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
  bootstrapStatus: () => [...emailKeys.all, "bootstrap-status"] as const,
};

export const goalKeys = {
  all: ["goals"] as const,
  suggestions: () => [...goalKeys.all, "suggestions"] as const,
};

export const integrationKeys = {
  all: ["integrations"] as const,
  status: () => [...integrationKeys.all, "status"] as const,
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

export function useRoutingDecision(enabled = true) {
  // Only run if user is authenticated (token exists)
  const isAuthenticated = typeof window !== "undefined" && !!localStorage.getItem("access_token");

  return useQuery({
    queryKey: onboardingKeys.routing(),
    queryFn: getRoutingDecision,
    enabled: enabled && isAuthenticated,
    retry: (failureCount, error) => {
      // Don't retry on 401 - auth issue needs user action
      if (error instanceof Error && error.message.includes("401")) {
        return false;
      }
      return failureCount < 2;
    },
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

const MAX_EMAIL_STATUS_ATTEMPTS = 30; // Max 30 attempts (90 seconds at 3s interval)

export function useEmailStatus(enabled: boolean) {
  const attemptsRef = useRef(0);
  const queryClient = useQueryClient();

  // Reset attempts when enabled changes (step change)
  useEffect(() => {
    if (enabled) {
      attemptsRef.current = 0;
    }
  }, [enabled]);

  const query = useQuery({
    queryKey: emailKeys.status(),
    queryFn: getEmailStatus,
    enabled,
    refetchInterval: (query) => {
      const data = query.state.data;

      // Stop polling if connected
      if (data?.google?.connected || data?.microsoft?.connected) {
        return false;
      }

      // Stop polling after max attempts
      if (attemptsRef.current >= MAX_EMAIL_STATUS_ATTEMPTS) {
        return false;
      }

      // Increment attempt counter
      attemptsRef.current += 1;
      return 3000; // Poll every 3 seconds
    },
    staleTime: 3000,
    gcTime: 5 * 60 * 1000,
  });

  // Provide a method to reset attempts (useful for retry after OAuth)
  const resetAttempts = useCallback(() => {
    attemptsRef.current = 0;
    queryClient.invalidateQueries({ queryKey: emailKeys.status() });
  }, [queryClient]);

  return { ...query, resetAttempts };
}

/**
 * Hook for polling email bootstrap status.
 * Polls every 2 seconds while status is "not_started" or "processing".
 * Stops polling when status is "complete" or "error".
 */
export function useEmailBootstrapStatus(enabled: boolean) {
  return useQuery({
    queryKey: emailKeys.bootstrapStatus(),
    queryFn: getBootstrapStatus,
    enabled,
    refetchInterval: (query) => {
      const data = query.state.data;

      // Stop polling if complete or error
      if (data?.status === "complete" || data?.status === "error") {
        return false;
      }

      // Poll every 2 seconds while processing
      return 2000;
    },
    staleTime: 2000,
    gcTime: 5 * 60 * 1000,
    retry: 3,
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

// --- Writing Analysis hook ---

export function useAnalyzeWriting() {
  return useMutation({
    mutationFn: (samples: string[]) => analyzeWritingSamples(samples),
  });
}

export function useExtractTextFromFile() {
  return useMutation({
    mutationFn: (file: File) => extractTextFromFile(file),
  });
}

// --- Company Discovery hook ---

export function useCompanyDiscovery() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CompanyDiscoveryRequest) => submitCompanyDiscovery(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: onboardingKeys.state() });
    },
  });
}

// --- Integration Wizard hooks ---

export function useIntegrationWizardStatus(enabled: boolean) {
  return useQuery({
    queryKey: integrationKeys.status(),
    queryFn: getIntegrationWizardStatus,
    enabled,
    refetchInterval: (query) => {
      const data = query.state.data;
      const anyPending =
        [...(data?.crm ?? []), ...(data?.calendar ?? []), ...(data?.messaging ?? [])].some(
          (i) => !i.connected
        );
      return anyPending ? 3000 : false;
    },
  });
}

export function useConnectIntegration() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (appName: IntegrationAppName) => connectIntegration(appName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: integrationKeys.status() });
    },
  });
}

export function useDisconnectIntegration() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (appName: IntegrationAppName) => disconnectIntegration(appName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: integrationKeys.status() });
    },
  });
}

