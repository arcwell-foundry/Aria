import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getTerritory,
  getAccountPlan,
  updateAccountPlan,
  getForecast,
  getQuotas,
  setQuota,
} from "@/api/accounts";

export const accountKeys = {
  all: ["accounts"] as const,
  territory: (stage?: string) =>
    [...accountKeys.all, "territory", { stage }] as const,
  plan: (leadId: string) => [...accountKeys.all, "plan", leadId] as const,
  forecast: () => [...accountKeys.all, "forecast"] as const,
  quotas: (period?: string) =>
    [...accountKeys.all, "quotas", { period }] as const,
};

export function useTerritory(stage?: string) {
  return useQuery({
    queryKey: accountKeys.territory(stage),
    queryFn: () => getTerritory(stage),
  });
}

export function useAccountPlan(leadId: string) {
  return useQuery({
    queryKey: accountKeys.plan(leadId),
    queryFn: () => getAccountPlan(leadId),
    enabled: !!leadId,
  });
}

export function useUpdateAccountPlan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ leadId, strategy }: { leadId: string; strategy: string }) =>
      updateAccountPlan(leadId, strategy),
    onSuccess: (data) => {
      queryClient.setQueryData(
        accountKeys.plan(data.lead_memory_id),
        data
      );
      queryClient.invalidateQueries({ queryKey: accountKeys.territory() });
    },
  });
}

export function useForecast() {
  return useQuery({
    queryKey: accountKeys.forecast(),
    queryFn: () => getForecast(),
  });
}

export function useQuotas(period?: string) {
  return useQuery({
    queryKey: accountKeys.quotas(period),
    queryFn: () => getQuotas(period),
  });
}

export function useSetQuota() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      period,
      targetValue,
    }: {
      period: string;
      targetValue: number;
    }) => setQuota(period, targetValue),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: accountKeys.quotas() });
    },
  });
}
