import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createGoal,
  deleteGoal,
  getGoal,
  getGoalProgress,
  listGoals,
  pauseGoal,
  startGoal,
  updateGoal,
  getDashboard,
  createWithARIA,
  getTemplates,
  getGoalDetail,
  addMilestone,
  generateRetrospective,
  approveGoalProposal,
  type CreateGoalData,
  type GoalStatus,
  type GoalWithProgress,
  type UpdateGoalData,
  type GoalProposalApproval,
} from "@/api/goals";

// Query keys
export const goalKeys = {
  all: ["goals"] as const,
  lists: () => [...goalKeys.all, "list"] as const,
  list: (status?: GoalStatus) => [...goalKeys.lists(), { status }] as const,
  details: () => [...goalKeys.all, "detail"] as const,
  detail: (id: string) => [...goalKeys.details(), id] as const,
  progress: (id: string) => [...goalKeys.detail(id), "progress"] as const,
  dashboard: () => [...goalKeys.all, "dashboard"] as const,
  templates: (role?: string) => [...goalKeys.all, "templates", { role }] as const,
  goalDetail: (id: string) => [...goalKeys.details(), id, "full"] as const,
};

// List goals query
export function useGoals(status?: GoalStatus) {
  return useQuery({
    queryKey: goalKeys.list(status),
    queryFn: () => listGoals(status),
  });
}

// Single goal query
export function useGoal(goalId: string) {
  return useQuery({
    queryKey: goalKeys.detail(goalId),
    queryFn: () => getGoal(goalId),
    enabled: !!goalId,
  });
}

// Goal progress query (with polling for active goals)
export function useGoalProgress(goalId: string, enabled = true) {
  return useQuery({
    queryKey: goalKeys.progress(goalId),
    queryFn: () => getGoalProgress(goalId),
    enabled: enabled && !!goalId,
    refetchInterval: (query) => {
      const data = query.state.data as GoalWithProgress | undefined;
      // Poll every 5 seconds if goal is active
      return data?.status === "active" ? 5000 : false;
    },
  });
}

// Create goal mutation
export function useCreateGoal() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CreateGoalData) => createGoal(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: goalKeys.lists() });
    },
  });
}

// Update goal mutation
export function useUpdateGoal() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ goalId, data }: { goalId: string; data: UpdateGoalData }) =>
      updateGoal(goalId, data),
    onSuccess: (updatedGoal) => {
      queryClient.setQueryData(goalKeys.detail(updatedGoal.id), updatedGoal);
      queryClient.invalidateQueries({ queryKey: goalKeys.lists() });
    },
  });
}

// Delete goal mutation
export function useDeleteGoal() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (goalId: string) => deleteGoal(goalId),
    onSuccess: (_data, goalId) => {
      queryClient.removeQueries({ queryKey: goalKeys.detail(goalId) });
      queryClient.invalidateQueries({ queryKey: goalKeys.lists() });
    },
  });
}

// Start goal mutation
export function useStartGoal() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (goalId: string) => startGoal(goalId),
    onSuccess: (updatedGoal) => {
      queryClient.setQueryData(goalKeys.detail(updatedGoal.id), updatedGoal);
      queryClient.invalidateQueries({ queryKey: goalKeys.lists() });
    },
  });
}

// Pause goal mutation
export function usePauseGoal() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (goalId: string) => pauseGoal(goalId),
    onSuccess: (updatedGoal) => {
      queryClient.setQueryData(goalKeys.detail(updatedGoal.id), updatedGoal);
      queryClient.invalidateQueries({ queryKey: goalKeys.lists() });
    },
  });
}

// US-936: Lifecycle hooks

export function useGoalDashboard() {
  return useQuery({
    queryKey: goalKeys.dashboard(),
    queryFn: () => getDashboard(),
  });
}

export function useGoalTemplates(role?: string) {
  return useQuery({
    queryKey: goalKeys.templates(role),
    queryFn: () => getTemplates(role),
  });
}

export function useGoalDetail(goalId: string) {
  return useQuery({
    queryKey: goalKeys.goalDetail(goalId),
    queryFn: () => getGoalDetail(goalId),
    enabled: !!goalId,
  });
}

export function useCreateWithARIA() {
  return useMutation({
    mutationFn: ({ title, description }: { title: string; description?: string }) =>
      createWithARIA(title, description),
  });
}

export function useAddMilestone() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      goalId,
      data,
    }: {
      goalId: string;
      data: { title: string; description?: string; due_date?: string };
    }) => addMilestone(goalId, data),
    onSuccess: (_data, { goalId }) => {
      queryClient.invalidateQueries({ queryKey: goalKeys.goalDetail(goalId) });
      queryClient.invalidateQueries({ queryKey: goalKeys.dashboard() });
    },
  });
}

export function useGenerateRetrospective() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (goalId: string) => generateRetrospective(goalId),
    onSuccess: (_data, goalId) => {
      queryClient.invalidateQueries({ queryKey: goalKeys.goalDetail(goalId) });
    },
  });
}

export function useApproveGoalProposal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: GoalProposalApproval) => approveGoalProposal(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: goalKeys.lists() });
      queryClient.invalidateQueries({ queryKey: goalKeys.dashboard() });
    },
  });
}
