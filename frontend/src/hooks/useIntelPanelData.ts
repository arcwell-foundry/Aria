import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useLocation } from "react-router-dom";

// ---------------------------------------------------------------------------
// Utility: relative time formatting
// ---------------------------------------------------------------------------
export function formatRelativeTime(dateStr: string): string {
  const now = Date.now();
  const date = new Date(dateStr).getTime();
  const diffMs = now - date;
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHrs = Math.floor(diffMin / 60);
  if (diffHrs < 24) return `${diffHrs}h ago`;
  const diffDays = Math.floor(diffHrs / 24);
  if (diffDays < 7) return `${diffDays}d ago`;
  return new Date(dateStr).toLocaleDateString();
}

// ---------------------------------------------------------------------------
// Utility: extract IDs from current route
// ---------------------------------------------------------------------------
export function useRouteContext() {
  const location = useLocation();
  const pathname = location.pathname;

  const leadMatch = pathname.match(/^\/pipeline\/leads\/([^/]+)/);
  const draftMatch = pathname.match(/^\/communications\/drafts\/([^/]+)/);

  return {
    leadId: leadMatch?.[1] ?? "",
    draftId: draftMatch?.[1] ?? "",
    isLeadDetail: !!leadMatch,
    isDraftDetail: !!draftMatch,
  };
}
import { listSignals, markSignalRead, markAllRead, dismissSignal, getUnreadCount, type SignalFilters } from "@/api/signals";
import {
  listInsights,
  updateInsightFeedback,
  type InsightFilters,
} from "@/api/intelligence";
import { listBattleCards } from "@/api/battleCards";
import { listLeads, getLead, getLeadInsights } from "@/api/leads";
import { getDraft, listDrafts } from "@/api/drafts";
import { listGoals, getDashboard, type GoalStatus } from "@/api/goals";
import { getSyncStatus } from "@/api/deepSync";

// ---------------------------------------------------------------------------
// Query key factories
// ---------------------------------------------------------------------------
export const intelKeys = {
  all: ["intel-panel"] as const,
  signals: (filters?: SignalFilters) => [...intelKeys.all, "signals", filters] as const,
  insights: (filters?: InsightFilters) => [...intelKeys.all, "insights", filters] as const,
  battleCards: () => [...intelKeys.all, "battleCards"] as const,
  leads: () => [...intelKeys.all, "leads"] as const,
  lead: (id: string) => [...intelKeys.all, "lead", id] as const,
  leadInsights: (id: string) => [...intelKeys.all, "leadInsights", id] as const,
  draft: (id: string) => [...intelKeys.all, "draft", id] as const,
  drafts: () => [...intelKeys.all, "drafts"] as const,
  goals: (status?: GoalStatus) => [...intelKeys.all, "goals", status] as const,
  goalsDashboard: () => [...intelKeys.all, "goalsDashboard"] as const,
  syncStatus: () => [...intelKeys.all, "syncStatus"] as const,
};

// ---------------------------------------------------------------------------
// Signals hooks (AlertsModule, NewsAlertsModule, BuyingSignalsModule)
// ---------------------------------------------------------------------------
export function useSignals(filters?: SignalFilters) {
  return useQuery({
    queryKey: intelKeys.signals(filters),
    queryFn: () => listSignals(filters),
    staleTime: 1000 * 60 * 2, // 2 minutes
  });
}

// ---------------------------------------------------------------------------
// Signal mutation hooks (MarketSignalsFeed)
// ---------------------------------------------------------------------------
export function useUnreadSignalCount() {
  return useQuery({
    queryKey: [...intelKeys.all, "signalUnread"] as const,
    queryFn: () => getUnreadCount(),
    staleTime: 1000 * 60,
  });
}

export function useMarkSignalRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (signalId: string) => markSignalRead(signalId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: intelKeys.all });
    },
  });
}

export function useMarkAllSignalsRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => markAllRead(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: intelKeys.all });
    },
  });
}

export function useDismissSignal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (signalId: string) => dismissSignal(signalId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: intelKeys.all });
    },
  });
}

// ---------------------------------------------------------------------------
// Intelligence insights hooks (JarvisInsightsModule, NextBestActionModule,
// StrategicAdviceModule)
// ---------------------------------------------------------------------------
export function useIntelligenceInsights(filters?: InsightFilters) {
  return useQuery({
    queryKey: intelKeys.insights(filters),
    queryFn: () => listInsights(filters),
    staleTime: 1000 * 60 * 2,
  });
}

export function useInsightFeedback() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ insightId, feedback }: { insightId: string; feedback: string }) =>
      updateInsightFeedback(insightId, { feedback }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: intelKeys.all });
    },
  });
}

// ---------------------------------------------------------------------------
// Battle cards hooks (CompetitiveIntelModule, ObjectionsModule)
// ---------------------------------------------------------------------------
export function useIntelBattleCards() {
  return useQuery({
    queryKey: intelKeys.battleCards(),
    queryFn: () => listBattleCards(),
    staleTime: 1000 * 60 * 5, // 5 minutes
  });
}

// ---------------------------------------------------------------------------
// Lead hooks (BuyingSignalsModule, ObjectionsModule, StrategicAdviceModule,
// CRMSnapshotModule)
// ---------------------------------------------------------------------------
export function useIntelLeads() {
  return useQuery({
    queryKey: intelKeys.leads(),
    queryFn: () => listLeads({ status: "active", limit: 10 }),
    staleTime: 1000 * 60 * 2,
  });
}

export function useIntelLead(leadId: string) {
  return useQuery({
    queryKey: intelKeys.lead(leadId),
    queryFn: () => getLead(leadId),
    enabled: !!leadId,
    staleTime: 1000 * 60 * 2,
  });
}

export function useIntelLeadInsights(leadId: string) {
  return useQuery({
    queryKey: intelKeys.leadInsights(leadId),
    queryFn: () => getLeadInsights(leadId),
    enabled: !!leadId,
    staleTime: 1000 * 60 * 2,
  });
}

// ---------------------------------------------------------------------------
// Draft hooks (WhyIWroteThisModule, ToneModule, AnalysisModule)
// ---------------------------------------------------------------------------
export function useIntelDraft(draftId: string) {
  return useQuery({
    queryKey: intelKeys.draft(draftId),
    queryFn: () => getDraft(draftId),
    enabled: !!draftId,
    staleTime: 1000 * 60,
  });
}

export function useIntelDrafts() {
  return useQuery({
    queryKey: intelKeys.drafts(),
    queryFn: () => listDrafts(undefined, 20),
    staleTime: 1000 * 60 * 2,
  });
}

// ---------------------------------------------------------------------------
// Goals hooks (NextStepsModule, AgentStatusModule)
// ---------------------------------------------------------------------------
export function useIntelGoals(status?: GoalStatus) {
  return useQuery({
    queryKey: intelKeys.goals(status),
    queryFn: () => listGoals(status),
    staleTime: 1000 * 60,
  });
}

export function useIntelGoalsDashboard() {
  return useQuery({
    queryKey: intelKeys.goalsDashboard(),
    queryFn: () => getDashboard(),
    staleTime: 1000 * 60,
  });
}

// ---------------------------------------------------------------------------
// CRM/Sync hooks (CRMSnapshotModule)
// ---------------------------------------------------------------------------
export function useIntelSyncStatus() {
  return useQuery({
    queryKey: intelKeys.syncStatus(),
    queryFn: () => getSyncStatus(),
    staleTime: 1000 * 60 * 5,
  });
}
