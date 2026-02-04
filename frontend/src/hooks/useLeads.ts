import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  addNote,
  addLeadEvent,
  addStakeholder,
  downloadCsv,
  exportLeads,
  getLead,
  getLeadInsights,
  getLeadStakeholders,
  getLeadTimeline,
  listLeads,
  transitionLeadStage,
  updateStakeholder,
  type Insight,
  type Lead,
  type LeadEvent,
  type LeadFilters,
  type NoteCreate,
  type Stakeholder,
  type StakeholderCreate,
  type StakeholderUpdate,
  type StageTransition,
} from "@/api/leads";

// Query keys
export const leadKeys = {
  all: ["leads"] as const,
  lists: () => [...leadKeys.all, "list"] as const,
  list: (filters?: LeadFilters) => [...leadKeys.lists(), { filters }] as const,
  details: () => [...leadKeys.all, "detail"] as const,
  detail: (id: string) => [...leadKeys.details(), id] as const,
  timeline: (id: string) => [...leadKeys.detail(id), "timeline"] as const,
  stakeholders: (id: string) => [...leadKeys.detail(id), "stakeholders"] as const,
  insights: (id: string) => [...leadKeys.detail(id), "insights"] as const,
};

// List leads query
export function useLeads(filters?: LeadFilters) {
  return useQuery({
    queryKey: leadKeys.list(filters),
    queryFn: () => listLeads(filters),
    staleTime: 1000 * 60 * 2, // 2 minutes
  });
}

// Single lead query
export function useLead(leadId: string) {
  return useQuery({
    queryKey: leadKeys.detail(leadId),
    queryFn: () => getLead(leadId),
    enabled: !!leadId,
  });
}

// Lead timeline query
export function useLeadTimeline(leadId: string) {
  return useQuery({
    queryKey: leadKeys.timeline(leadId),
    queryFn: () => getLeadTimeline(leadId),
    enabled: !!leadId,
  });
}

// Lead stakeholders query
export function useLeadStakeholders(leadId: string) {
  return useQuery({
    queryKey: leadKeys.stakeholders(leadId),
    queryFn: () => getLeadStakeholders(leadId),
    enabled: !!leadId,
  });
}

// Lead insights query
export function useLeadInsights(leadId: string) {
  return useQuery({
    queryKey: leadKeys.insights(leadId),
    queryFn: () => getLeadInsights(leadId),
    enabled: !!leadId,
  });
}

// Add note mutation
export function useAddNote() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ leadId, note }: { leadId: string; note: NoteCreate }) =>
      addNote(leadId, note),
    onSuccess: (_data, { leadId }) => {
      // Invalidate the specific lead and lists
      queryClient.invalidateQueries({ queryKey: leadKeys.detail(leadId) });
      queryClient.invalidateQueries({ queryKey: leadKeys.timeline(leadId) });
      queryClient.invalidateQueries({ queryKey: leadKeys.lists() });
    },
  });
}

// Add event mutation
export function useAddEvent() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      leadId,
      event,
    }: {
      leadId: string;
      event: Omit<LeadEvent, "id" | "lead_memory_id" | "created_at">;
    }) => addLeadEvent(leadId, event),
    onSuccess: (_data, { leadId }) => {
      queryClient.invalidateQueries({ queryKey: leadKeys.timeline(leadId) });
      queryClient.invalidateQueries({ queryKey: leadKeys.detail(leadId) });
    },
  });
}

// Add stakeholder mutation
export function useAddStakeholder() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      leadId,
      stakeholder,
    }: {
      leadId: string;
      stakeholder: StakeholderCreate;
    }) => addStakeholder(leadId, stakeholder),
    onSuccess: (_data, { leadId }) => {
      queryClient.invalidateQueries({ queryKey: leadKeys.stakeholders(leadId) });
    },
  });
}

// Update stakeholder mutation
export function useUpdateStakeholder() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      leadId,
      stakeholderId,
      updates,
    }: {
      leadId: string;
      stakeholderId: string;
      updates: StakeholderUpdate;
    }) => updateStakeholder(leadId, stakeholderId, updates),
    onSuccess: (_data, { leadId }) => {
      queryClient.invalidateQueries({ queryKey: leadKeys.stakeholders(leadId) });
    },
  });
}

// Transition stage mutation
export function useTransitionStage() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      leadId,
      transition,
    }: {
      leadId: string;
      transition: StageTransition;
    }) => transitionLeadStage(leadId, transition),
    onSuccess: (_data, { leadId }) => {
      queryClient.invalidateQueries({ queryKey: leadKeys.detail(leadId) });
      queryClient.invalidateQueries({ queryKey: leadKeys.lists() });
    },
  });
}

// Export leads mutation
export function useExportLeads() {
  return useMutation({
    mutationFn: (leadIds: string[]) => exportLeads(leadIds),
    onSuccess: (result) => {
      // Trigger download
      downloadCsv(result);
    },
  });
}

// Helper hook for selected leads management
export function useLeadSelection() {
  const queryClient = useQueryClient();

  const getSelectedLeads = (): Set<string> => {
    return queryClient.getQueryData(["leads", "selection"]) || new Set();
  };

  const setSelectedLeads = (ids: Set<string>) => {
    queryClient.setQueryData(["leads", "selection"], ids);
  };

  const toggleLead = (id: string) => {
    const current = getSelectedLeads();
    const next = new Set(current);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    setSelectedLeads(next);
  };

  const selectAll = (leads: Lead[]) => {
    setSelectedLeads(new Set(leads.map((l) => l.id)));
  };

  const clearSelection = () => {
    setSelectedLeads(new Set());
  };

  return {
    getSelectedLeads,
    setSelectedLeads,
    toggleLead,
    selectAll,
    clearSelection,
  };
}

// Re-export types for convenience
export type { Insight, Lead, LeadEvent, Stakeholder };
