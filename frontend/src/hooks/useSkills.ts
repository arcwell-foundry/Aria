import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  listAvailableSkills,
  listInstalledSkills,
  installSkill,
  uninstallSkill,
  getSkillAudit,
  getExecutionPlan,
  approveExecutionPlan,
  rejectExecutionPlan,
  listPendingPlans,
  approveSkillGlobally,
  getSkillPerformance,
  submitSkillFeedback,
  listCustomSkills,
  updateCustomSkill,
  deleteCustomSkill,
  getExecutionReplay,
  type AvailableSkillsFilters,
  type UpdateCustomSkillData,
} from "@/api/skills";

// Query keys
export const skillKeys = {
  all: ["skills"] as const,
  available: () => [...skillKeys.all, "available"] as const,
  availableFiltered: (filters?: AvailableSkillsFilters) =>
    [...skillKeys.available(), { filters }] as const,
  installed: () => [...skillKeys.all, "installed"] as const,
  audit: () => [...skillKeys.all, "audit"] as const,
  auditFiltered: (skillId?: string) =>
    [...skillKeys.audit(), { skillId }] as const,
  plans: () => [...skillKeys.all, "plans"] as const,
  pendingPlans: () => [...skillKeys.plans(), "pending"] as const,
  plan: (planId: string) => [...skillKeys.plans(), planId] as const,
  performance: (skillId: string) =>
    [...skillKeys.all, "performance", skillId] as const,
  custom: () => [...skillKeys.all, "custom"] as const,
  replay: (executionId: string) => [...skillKeys.all, "replay", executionId] as const,
};

// List available skills
export function useAvailableSkills(filters?: AvailableSkillsFilters) {
  return useQuery({
    queryKey: skillKeys.availableFiltered(filters),
    queryFn: () => listAvailableSkills(filters),
  });
}

// List installed skills
export function useInstalledSkills() {
  return useQuery({
    queryKey: skillKeys.installed(),
    queryFn: () => listInstalledSkills(),
  });
}

// Install skill mutation
export function useInstallSkill() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (skillId: string) => installSkill(skillId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: skillKeys.installed() });
      queryClient.invalidateQueries({ queryKey: skillKeys.available() });
    },
  });
}

// Uninstall skill mutation
export function useUninstallSkill() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (skillId: string) => uninstallSkill(skillId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: skillKeys.installed() });
      queryClient.invalidateQueries({ queryKey: skillKeys.available() });
    },
  });
}

// Skill audit log
export function useSkillAudit(skillId?: string) {
  return useQuery({
    queryKey: skillKeys.auditFiltered(skillId),
    queryFn: () => getSkillAudit(skillId),
  });
}

// Execution plan polling (2s when executing/pending_approval, stops otherwise)
export function useExecutionPlan(planId: string | null) {
  return useQuery({
    queryKey: skillKeys.plan(planId ?? ""),
    queryFn: () => getExecutionPlan(planId!),
    enabled: !!planId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "executing" || status === "pending_approval") return 2_000;
      return false;
    },
  });
}

// List pending execution plans (polls every 10s)
export function usePendingPlans() {
  return useQuery({
    queryKey: skillKeys.pendingPlans(),
    queryFn: () => listPendingPlans(),
    refetchInterval: 10_000,
  });
}

// Approve an execution plan
export function useApproveExecutionPlan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (planId: string) => approveExecutionPlan(planId),
    onSuccess: (plan) => {
      queryClient.setQueryData(skillKeys.plan(plan.id), plan);
      queryClient.invalidateQueries({ queryKey: skillKeys.pendingPlans() });
    },
  });
}

// Reject an execution plan
export function useRejectExecutionPlan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (planId: string) => rejectExecutionPlan(planId),
    onSuccess: (plan) => {
      queryClient.setQueryData(skillKeys.plan(plan.id), plan);
      queryClient.invalidateQueries({ queryKey: skillKeys.pendingPlans() });
    },
  });
}

// Approve a skill globally (skip future approval prompts)
export function useApproveSkillGlobally() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (skillId: string) => approveSkillGlobally(skillId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: skillKeys.all });
    },
  });
}

// Skill performance metrics
export function useSkillPerformance(skillId: string | null) {
  return useQuery({
    queryKey: skillKeys.performance(skillId ?? ""),
    queryFn: () => getSkillPerformance(skillId!),
    enabled: !!skillId,
  });
}

// Submit skill feedback (thumbs up/down)
export function useSubmitFeedback() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      executionId,
      feedback,
    }: {
      executionId: string;
      feedback: "positive" | "negative";
    }) => submitSkillFeedback(executionId, feedback),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: skillKeys.all });
    },
  });
}

// List custom skills
export function useCustomSkills() {
  return useQuery({
    queryKey: skillKeys.custom(),
    queryFn: () => listCustomSkills(),
  });
}

// Update custom skill
export function useUpdateCustomSkill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      skillId,
      data,
    }: {
      skillId: string;
      data: UpdateCustomSkillData;
    }) => updateCustomSkill(skillId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: skillKeys.custom() });
    },
  });
}

// Delete custom skill
export function useDeleteCustomSkill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (skillId: string) => deleteCustomSkill(skillId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: skillKeys.custom() });
    },
  });
}

// Execution replay
export function useExecutionReplay(executionId: string | null) {
  return useQuery({
    queryKey: skillKeys.replay(executionId ?? ""),
    queryFn: () => getExecutionReplay(executionId!),
    enabled: !!executionId,
  });
}
