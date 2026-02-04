import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  addNote,
  downloadCsv,
  exportLeads,
  getLead,
  listLeads,
  type Lead,
  type LeadFilters,
  type NoteCreate,
} from "@/api/leads";

// Query keys
export const leadKeys = {
  all: ["leads"] as const,
  lists: () => [...leadKeys.all, "list"] as const,
  list: (filters?: LeadFilters) => [...leadKeys.lists(), { filters }] as const,
  details: () => [...leadKeys.all, "detail"] as const,
  detail: (id: string) => [...leadKeys.details(), id] as const,
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

// Add note mutation
export function useAddNote() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ leadId, note }: { leadId: string; note: NoteCreate }) =>
      addNote(leadId, note),
    onSuccess: (_data, { leadId }) => {
      // Invalidate the specific lead and lists
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
