import { useState } from "react";
import type { Goal, GoalStatus, GoalType } from "@/api/goals";
import { DashboardLayout } from "@/components/DashboardLayout";
import {
  CreateGoalModal,
  DeleteGoalModal,
  EmptyGoals,
  GoalCard,
} from "@/components/goals";
import {
  useGoals,
  useCreateGoal,
  useDeleteGoal,
  useStartGoal,
  usePauseGoal,
} from "@/hooks/useGoals";
import { HelpTooltip } from "@/components/HelpTooltip";

const statusFilters: { value: GoalStatus | "all"; label: string }[] = [
  { value: "all", label: "All Goals" },
  { value: "draft", label: "Draft" },
  { value: "active", label: "Active" },
  { value: "paused", label: "Paused" },
  { value: "complete", label: "Complete" },
  { value: "failed", label: "Failed" },
];

export function GoalsPage() {
  const [statusFilter, setStatusFilter] = useState<GoalStatus | "all">("all");
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [goalToDelete, setGoalToDelete] = useState<Goal | null>(null);

  // Queries
  const { data: goals, isLoading, error } = useGoals(
    statusFilter === "all" ? undefined : statusFilter
  );

  // Mutations
  const createGoal = useCreateGoal();
  const deleteGoal = useDeleteGoal();
  const startGoal = useStartGoal();
  const pauseGoal = usePauseGoal();

  const handleCreateGoal = (data: {
    title: string;
    description?: string;
    goal_type: GoalType;
  }) => {
    createGoal.mutate(data, {
      onSuccess: () => {
        setIsCreateModalOpen(false);
      },
    });
  };

  const handleDeleteGoal = () => {
    if (!goalToDelete) return;
    deleteGoal.mutate(goalToDelete.id, {
      onSuccess: () => {
        setGoalToDelete(null);
      },
    });
  };

  const handleStartGoal = (goalId: string) => {
    startGoal.mutate(goalId);
  };

  const handlePauseGoal = (goalId: string) => {
    pauseGoal.mutate(goalId);
  };

  return (
    <DashboardLayout>
      <div className="relative">
        {/* Background pattern */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-800 via-slate-900 to-slate-900 pointer-events-none" />

        <div className="relative max-w-6xl mx-auto px-4 py-8 lg:px-8">
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-3xl font-bold text-white">Goals</h1>
                <HelpTooltip content="Set objectives for ARIA to pursue. She'll track progress and suggest strategies." placement="right" />
              </div>
              <p className="mt-1 text-slate-400">
                Manage your AI-powered pursuits and track agent progress
              </p>
            </div>

            <button
              onClick={() => setIsCreateModalOpen(true)}
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-primary-600 hover:bg-primary-500 text-white font-medium rounded-lg transition-colors shadow-lg shadow-primary-600/25"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 4v16m8-8H4"
                />
              </svg>
              New Goal
            </button>
          </div>

          {/* Filters */}
          <div className="flex gap-2 mb-6 overflow-x-auto pb-2">
            {statusFilters.map((filter) => (
              <button
                key={filter.value}
                onClick={() => setStatusFilter(filter.value)}
                className={`px-4 py-2 text-sm font-medium rounded-lg whitespace-nowrap transition-colors ${
                  statusFilter === filter.value
                    ? "bg-primary-600/20 text-primary-400 border border-primary-500/30"
                    : "text-slate-400 hover:text-white hover:bg-slate-800"
                }`}
              >
                {filter.label}
              </button>
            ))}
          </div>

          {/* Error state */}
          {error && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 mb-6">
              <p className="text-red-400">Failed to load goals. Please try again.</p>
            </div>
          )}

          {/* Loading state */}
          {isLoading && (
            <div className="grid gap-4 md:grid-cols-2">
              {[1, 2, 3, 4].map((i) => (
                <div
                  key={i}
                  className="bg-slate-800/50 border border-slate-700 rounded-xl p-5 animate-pulse"
                >
                  <div className="flex items-start gap-4">
                    <div className="w-14 h-14 bg-slate-700 rounded-full" />
                    <div className="flex-1 space-y-3">
                      <div className="h-5 bg-slate-700 rounded w-3/4" />
                      <div className="h-4 bg-slate-700 rounded w-1/2" />
                      <div className="flex gap-2">
                        <div className="h-6 bg-slate-700 rounded-full w-20" />
                        <div className="h-6 bg-slate-700 rounded-full w-16" />
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Empty state */}
          {!isLoading && goals && goals.length === 0 && (
            <EmptyGoals onCreateClick={() => setIsCreateModalOpen(true)} />
          )}

          {/* Goals grid */}
          {!isLoading && goals && goals.length > 0 && (
            <div className="grid gap-4 md:grid-cols-2">
              {goals.map((goal, index) => (
                <div
                  key={goal.id}
                  className="animate-in fade-in slide-in-from-bottom-4"
                  style={{ animationDelay: `${index * 50}ms`, animationFillMode: "both" }}
                >
                  <GoalCard
                    goal={goal}
                    onStart={() => handleStartGoal(goal.id)}
                    onPause={() => handlePauseGoal(goal.id)}
                    onDelete={() => setGoalToDelete(goal)}
                    isLoading={
                      startGoal.isPending || pauseGoal.isPending
                    }
                  />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Modals */}
        <CreateGoalModal
          isOpen={isCreateModalOpen}
          onClose={() => setIsCreateModalOpen(false)}
          onSubmit={handleCreateGoal}
          isLoading={createGoal.isPending}
        />

        <DeleteGoalModal
          goal={goalToDelete}
          isOpen={goalToDelete !== null}
          onClose={() => setGoalToDelete(null)}
          onConfirm={handleDeleteGoal}
          isLoading={deleteGoal.isPending}
        />
      </div>
    </DashboardLayout>
  );
}
