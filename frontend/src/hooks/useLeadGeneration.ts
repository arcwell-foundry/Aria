import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  discoverLeads,
  getICP,
  getPipeline,
  getScoreExplanation,
  initiateOutreach,
  listDiscoveredLeads,
  reviewLead,
  saveICP,
  type DiscoveredLead,
  type ICPDefinition,
  type ICPResponse,
  type LeadScoreBreakdown,
  type OutreachRequest,
  type OutreachResponse,
  type PipelineSummary,
  type ReviewStatus,
} from "@/api/leadGeneration";

// Query keys
export const leadGenKeys = {
  all: ["leadGen"] as const,
  icp: () => [...leadGenKeys.all, "icp"] as const,
  discovered: () => [...leadGenKeys.all, "discovered"] as const,
  discoveredList: (status?: ReviewStatus) =>
    [...leadGenKeys.discovered(), { status }] as const,
  score: (id: string) => [...leadGenKeys.all, "score", id] as const,
  pipeline: () => [...leadGenKeys.all, "pipeline"] as const,
};

// ICP queries
export function useICP() {
  return useQuery({
    queryKey: leadGenKeys.icp(),
    queryFn: getICP,
    staleTime: 1000 * 60 * 5,
  });
}

export function useSaveICP() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (icp: ICPDefinition) => saveICP(icp),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: leadGenKeys.icp() });
    },
  });
}

// Discovery
export function useDiscoverLeads() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (targetCount?: number) => discoverLeads(targetCount),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: leadGenKeys.discovered(),
      });
    },
  });
}

export function useDiscoveredLeads(statusFilter?: ReviewStatus) {
  return useQuery({
    queryKey: leadGenKeys.discoveredList(statusFilter),
    queryFn: () => listDiscoveredLeads(statusFilter),
    staleTime: 1000 * 60 * 2,
  });
}

// Review
export function useReviewLead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      leadId,
      action,
    }: {
      leadId: string;
      action: ReviewStatus;
    }) => reviewLead(leadId, action),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: leadGenKeys.discovered(),
      });
      queryClient.invalidateQueries({
        queryKey: leadGenKeys.pipeline(),
      });
    },
  });
}

// Score explanation
export function useScoreExplanation(leadId: string) {
  return useQuery({
    queryKey: leadGenKeys.score(leadId),
    queryFn: () => getScoreExplanation(leadId),
    enabled: !!leadId,
  });
}

// Pipeline
export function usePipeline() {
  return useQuery({
    queryKey: leadGenKeys.pipeline(),
    queryFn: getPipeline,
    staleTime: 1000 * 60 * 2,
  });
}

// Outreach
export function useInitiateOutreach() {
  return useMutation({
    mutationFn: ({
      leadId,
      outreach,
    }: {
      leadId: string;
      outreach: OutreachRequest;
    }) => initiateOutreach(leadId, outreach),
  });
}

// Re-export types
export type {
  DiscoveredLead,
  ICPDefinition,
  ICPResponse,
  LeadScoreBreakdown,
  OutreachRequest,
  OutreachResponse,
  PipelineSummary,
  ReviewStatus,
};
