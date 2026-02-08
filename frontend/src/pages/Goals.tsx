import { useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { Goal, GoalDashboard, GoalHealth, GoalStatus } from "@/api/goals";
import { DashboardLayout } from "@/components/DashboardLayout";
import {
  DeleteGoalModal,
  EmptyGoals,
  GoalCard,
  GoalCreationWizard,
  GoalDetailPanel,
} from "@/components/goals";
import {
  useGoalDashboard,
  useDeleteGoal,
  useStartGoal,
  usePauseGoal,
  goalKeys,
} from "@/hooks/useGoals";
import { HelpTooltip } from "@/components/HelpTooltip";
import {
  Plus,
  LayoutGrid,
  List,
  Target,
  TrendingUp,
  CheckCircle2,
  AlertTriangle,
} from "lucide-react";

// ---------- Constants ----------

const statusFilters: { value: GoalStatus | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "active", label: "Active" },
  { value: "draft", label: "Draft" },
  { value: "paused", label: "Paused" },
  { value: "complete", label: "Complete" },
  { value: "failed", label: "Failed" },
];

type ViewMode = "grid" | "list";

// ---------- Summary Stat Card ----------

interface StatCardProps {
  label: string;
  value: number;
  icon: React.ReactNode;
  accent?: string;
}

function StatCard({ label, value, icon, accent = "text-slate-400" }: StatCardProps) {
  return (
    <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-4 flex items-center gap-3">
      <div className={`${accent}`}>{icon}</div>
      <div>
        <p className="text-2xl font-semibold text-white">{value}</p>
        <p className="text-sm text-slate-400">{label}</p>
      </div>
    </div>
  );
}

// ---------- GoalsPage ----------

export function GoalsPage() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<GoalStatus | "all">("all");
  const [isWizardOpen, setIsWizardOpen] = useState(false);
  const [goalToDelete, setGoalToDelete] = useState<Goal | null>(null);
  const [selectedGoalId, setSelectedGoalId] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("grid");

  // Queries — use dashboard hook for enriched data
  const { data: dashboardGoals, isLoading, error } = useGoalDashboard();

  // Mutations
  const deleteGoal = useDeleteGoal();
  const startGoal = useStartGoal();
  const pauseGoal = usePauseGoal();

  // Derived: filter goals by status tab
  const filteredGoals = useMemo(() => {
    if (!dashboardGoals) return [];
    if (statusFilter === "all") return dashboardGoals;
    return dashboardGoals.filter((g) => g.status === statusFilter);
  }, [dashboardGoals, statusFilter]);

  // Derived: summary stats
  const stats = useMemo(() => {
    const goals = dashboardGoals ?? [];
    const total = goals.length;
    const active = goals.filter((g) => g.status === "active").length;
    const completed = goals.filter((g) => g.status === "complete").length;
    // Count goals with at_risk health if the field is present
    const atRisk = goals.filter(
      (g) => (g as GoalDashboard & { health?: GoalHealth }).health === "at_risk"
    ).length;
    return { total, active, completed, atRisk };
  }, [dashboardGoals]);

  // Handlers
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

  const handleGoalCreated = () => {
    queryClient.invalidateQueries({ queryKey: goalKeys.dashboard() });
  };

  const handleCardClick = (goalId: string) => {
    setSelectedGoalId(goalId);
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
                <h1 className="text-3xl font-display text-white">Goals</h1>
                <HelpTooltip
                  content="Set objectives for ARIA to pursue. She'll track progress and suggest strategies."
                  placement="right"
                />
              </div>
              <p className="mt-1 text-slate-400">
                Manage your AI-powered pursuits and track agent progress
              </p>
            </div>

            <button
              onClick={() => setIsWizardOpen(true)}
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-primary-600 hover:bg-primary-500 text-white font-medium rounded-lg transition-colors shadow-lg shadow-primary-600/25"
            >
              <Plus className="w-5 h-5" />
              New Goal
            </button>
          </div>

          {/* Summary stats row */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
            <StatCard
              label="Total Goals"
              value={stats.total}
              icon={<Target className="w-5 h-5" />}
              accent="text-primary-400"
            />
            <StatCard
              label="Active"
              value={stats.active}
              icon={<TrendingUp className="w-5 h-5" />}
              accent="text-green-400"
            />
            <StatCard
              label="Completed"
              value={stats.completed}
              icon={<CheckCircle2 className="w-5 h-5" />}
              accent="text-blue-400"
            />
            <StatCard
              label="At Risk"
              value={stats.atRisk}
              icon={<AlertTriangle className="w-5 h-5" />}
              accent="text-amber-400"
            />
          </div>

          {/* Filter tabs + view toggle row */}
          <div className="flex items-center justify-between gap-4 mb-6">
            {/* Filter tabs */}
            <div className="flex gap-2 overflow-x-auto pb-2">
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

            {/* View toggle */}
            <div className="flex items-center gap-1 flex-shrink-0">
              <button
                onClick={() => setViewMode("grid")}
                className={`p-2 rounded-lg transition-colors ${
                  viewMode === "grid"
                    ? "bg-slate-700 text-white"
                    : "text-slate-500 hover:text-slate-300 hover:bg-slate-800"
                }`}
                title="Grid view"
              >
                <LayoutGrid className="w-4 h-4" />
              </button>
              <button
                onClick={() => setViewMode("list")}
                className={`p-2 rounded-lg transition-colors ${
                  viewMode === "list"
                    ? "bg-slate-700 text-white"
                    : "text-slate-500 hover:text-slate-300 hover:bg-slate-800"
                }`}
                title="List view"
              >
                <List className="w-4 h-4" />
              </button>
            </div>
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
          {!isLoading && filteredGoals.length === 0 && !error && (
            <EmptyGoals onCreateClick={() => setIsWizardOpen(true)} />
          )}

          {/* Goals grid */}
          {!isLoading && filteredGoals.length > 0 && (
            <div
              className={
                viewMode === "grid"
                  ? "grid gap-4 md:grid-cols-2"
                  : "flex flex-col gap-3"
              }
            >
              {filteredGoals.map((goal, index) => (
                <div
                  key={goal.id}
                  className="animate-in fade-in slide-in-from-bottom-4"
                  style={{ animationDelay: `${index * 50}ms`, animationFillMode: "both" }}
                >
                  <GoalCard
                    goal={goal}
                    onClick={() => handleCardClick(goal.id)}
                    onStart={() => handleStartGoal(goal.id)}
                    onPause={() => handlePauseGoal(goal.id)}
                    onDelete={() => setGoalToDelete(goal)}
                    isLoading={startGoal.isPending || pauseGoal.isPending}
                  />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* GoalCreationWizard modal */}
        <GoalCreationWizard
          isOpen={isWizardOpen}
          onClose={() => setIsWizardOpen(false)}
          onGoalCreated={handleGoalCreated}
        />

        {/* DeleteGoalModal */}
        <DeleteGoalModal
          goal={goalToDelete}
          isOpen={goalToDelete !== null}
          onClose={() => setGoalToDelete(null)}
          onConfirm={handleDeleteGoal}
          isLoading={deleteGoal.isPending}
        />

        {/* GoalDetailPanel slide-out */}
        {selectedGoalId && (
          <GoalDetailPanel
            goalId={selectedGoalId}
            isOpen={selectedGoalId !== null}
            onClose={() => setSelectedGoalId(null)}
          />
        )}
      </div>
    </DashboardLayout>
  );
}
