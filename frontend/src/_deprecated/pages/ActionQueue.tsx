import { useMemo, useState } from "react";
import type { Action, ActionStatus } from "@/api/actionQueue";
import { DashboardLayout } from "@/components/DashboardLayout";
import { ActionCard, ActionDetailModal } from "@/components/actionQueue";
import { useActions, useApproveAction, useRejectAction, useBatchApprove } from "@/hooks/useActionQueue";
import { HelpTooltip } from "@/components/HelpTooltip";
import {
  ListChecks,
  CheckCircle2,
  XCircle,
  Clock,
  Zap,
  CheckSquare,
} from "lucide-react";

// ---------- Filter tabs ----------

interface StatusFilter {
  value: ActionStatus | "all";
  label: string;
  icon: typeof Clock;
}

const statusFilters: StatusFilter[] = [
  { value: "pending", label: "Pending", icon: Clock },
  { value: "all", label: "All", icon: ListChecks },
  { value: "approved", label: "Approved", icon: CheckCircle2 },
  { value: "completed", label: "Completed", icon: Zap },
  { value: "rejected", label: "Rejected", icon: XCircle },
];

// ---------- Stat Card ----------

interface StatCardProps {
  label: string;
  value: number;
  icon: React.ReactNode;
  accent?: string;
}

function StatCard({ label, value, icon, accent = "text-slate-400" }: StatCardProps) {
  return (
    <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-4 flex items-center gap-3">
      <div className={accent}>{icon}</div>
      <div>
        <p className="text-2xl font-semibold text-white">{value}</p>
        <p className="text-sm text-slate-400">{label}</p>
      </div>
    </div>
  );
}

// ---------- ActionQueuePage ----------

export function ActionQueuePage() {
  const [statusFilter, setStatusFilter] = useState<ActionStatus | "all">("pending");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [detailAction, setDetailAction] = useState<Action | null>(null);

  // Query — fetch all actions (client-side filter for speed)
  const { data: allActions, isLoading, error } = useActions();

  // Mutations
  const approveAction = useApproveAction();
  const rejectAction = useRejectAction();
  const batchApprove = useBatchApprove();

  // Derived: filter by status tab
  const filteredActions = useMemo(() => {
    if (!allActions) return [];
    if (statusFilter === "all") return allActions;
    return allActions.filter((a) => a.status === statusFilter);
  }, [allActions, statusFilter]);

  // Derived: stats
  const stats = useMemo(() => {
    const actions = allActions ?? [];
    return {
      pending: actions.filter((a) => a.status === "pending").length,
      approved: actions.filter((a) => a.status === "approved" || a.status === "auto_approved").length,
      completed: actions.filter((a) => a.status === "completed").length,
      rejected: actions.filter((a) => a.status === "rejected").length,
    };
  }, [allActions]);

  // Handlers
  const handleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleApprove = (id: string) => {
    approveAction.mutate(id, {
      onSuccess: () => {
        setSelectedIds((prev) => {
          const next = new Set(prev);
          next.delete(id);
          return next;
        });
        if (detailAction?.id === id) setDetailAction(null);
      },
    });
  };

  const handleReject = (id: string, reason?: string) => {
    rejectAction.mutate(
      { actionId: id, reason },
      {
        onSuccess: () => {
          setSelectedIds((prev) => {
            const next = new Set(prev);
            next.delete(id);
            return next;
          });
          if (detailAction?.id === id) setDetailAction(null);
        },
      }
    );
  };

  const handleBatchApprove = () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;
    batchApprove.mutate(ids, {
      onSuccess: () => setSelectedIds(new Set()),
    });
  };

  const handleViewDetail = (id: string) => {
    const action = allActions?.find((a) => a.id === id);
    if (action) setDetailAction(action);
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
                <h1 className="text-3xl font-display text-white">Action Queue</h1>
                <HelpTooltip
                  content="Review and approve actions ARIA wants to take on your behalf. Low-risk actions auto-execute; high-risk actions require your approval."
                  placement="right"
                />
              </div>
              <p className="mt-1 text-slate-400">
                Control ARIA&apos;s autonomous actions and maintain oversight
              </p>
            </div>

            {/* Batch approve button */}
            {selectedIds.size > 0 && (
              <button
                onClick={handleBatchApprove}
                disabled={batchApprove.isPending}
                className="inline-flex items-center gap-2 px-5 py-2.5 bg-green-600 hover:bg-green-500 disabled:opacity-50 text-white font-medium rounded-lg transition-colors shadow-lg shadow-green-600/25"
              >
                <CheckSquare className="w-5 h-5" />
                Approve Selected ({selectedIds.size})
              </button>
            )}
          </div>

          {/* Summary stats row */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
            <StatCard
              label="Pending"
              value={stats.pending}
              icon={<Clock className="w-5 h-5" />}
              accent="text-warning"
            />
            <StatCard
              label="Approved"
              value={stats.approved}
              icon={<CheckCircle2 className="w-5 h-5" />}
              accent="text-info"
            />
            <StatCard
              label="Completed"
              value={stats.completed}
              icon={<Zap className="w-5 h-5" />}
              accent="text-green-400"
            />
            <StatCard
              label="Rejected"
              value={stats.rejected}
              icon={<XCircle className="w-5 h-5" />}
              accent="text-critical"
            />
          </div>

          {/* Filter tabs */}
          <div className="flex gap-2 overflow-x-auto pb-2 mb-6">
            {statusFilters.map((filter) => {
              const FilterIcon = filter.icon;
              const count =
                filter.value === "pending"
                  ? stats.pending
                  : filter.value === "approved"
                    ? stats.approved
                    : filter.value === "completed"
                      ? stats.completed
                      : filter.value === "rejected"
                        ? stats.rejected
                        : (allActions ?? []).length;

              return (
                <button
                  key={filter.value}
                  onClick={() => setStatusFilter(filter.value)}
                  className={`inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg whitespace-nowrap transition-colors ${
                    statusFilter === filter.value
                      ? "bg-primary-600/20 text-primary-400 border border-primary-500/30"
                      : "text-slate-400 hover:text-white hover:bg-slate-800"
                  }`}
                >
                  <FilterIcon className="w-4 h-4" />
                  {filter.label}
                  {count > 0 && (
                    <span
                      className={`ml-1 px-1.5 py-0.5 text-xs rounded-full ${
                        statusFilter === filter.value
                          ? "bg-primary-500/20 text-primary-400"
                          : "bg-slate-700 text-slate-400"
                      }`}
                    >
                      {count}
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          {/* Error state */}
          {error && (
            <div className="bg-critical/10 border border-critical/30 rounded-xl p-4 mb-6">
              <p className="text-critical">Failed to load actions. Please try again.</p>
            </div>
          )}

          {/* Loading state */}
          {isLoading && (
            <div className="space-y-3">
              {[1, 2, 3, 4].map((i) => (
                <div
                  key={i}
                  className="bg-slate-800/50 border border-slate-700 rounded-xl p-4 animate-pulse"
                >
                  <div className="flex items-start gap-3">
                    <div className="w-5 h-5 bg-slate-700 rounded" />
                    <div className="flex-1 space-y-3">
                      <div className="flex gap-2">
                        <div className="h-4 bg-slate-700 rounded w-16" />
                        <div className="h-4 bg-slate-700 rounded w-20" />
                      </div>
                      <div className="h-5 bg-slate-700 rounded w-3/4" />
                      <div className="h-4 bg-slate-700 rounded w-1/2" />
                    </div>
                    <div className="flex flex-col gap-1.5">
                      <div className="h-5 bg-slate-700 rounded-full w-14" />
                      <div className="h-5 bg-slate-700 rounded-full w-16" />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Empty state */}
          {!isLoading && filteredActions.length === 0 && !error && (
            <div className="text-center py-16">
              <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-slate-800/80 border border-slate-700 mb-4">
                <ListChecks className="w-8 h-8 text-slate-500" />
              </div>
              <h3 className="text-lg font-medium text-white mb-2">
                {statusFilter === "pending"
                  ? "No pending actions"
                  : `No ${statusFilter === "all" ? "" : statusFilter + " "}actions`}
              </h3>
              <p className="text-sm text-slate-400 max-w-md mx-auto">
                {statusFilter === "pending"
                  ? "ARIA is working within her approved autonomy. Actions requiring your review will appear here."
                  : "Actions will appear here as ARIA works on your behalf."}
              </p>
            </div>
          )}

          {/* Actions list */}
          {!isLoading && filteredActions.length > 0 && (
            <div className="space-y-3">
              {filteredActions.map((action, index) => (
                <div
                  key={action.id}
                  className="animate-in fade-in slide-in-from-bottom-4"
                  style={{ animationDelay: `${index * 30}ms`, animationFillMode: "both" }}
                >
                  <ActionCard
                    action={action}
                    isSelected={selectedIds.has(action.id)}
                    onSelect={action.status === "pending" ? handleSelect : undefined}
                    onApprove={action.status === "pending" ? handleApprove : undefined}
                    onReject={action.status === "pending" ? (id) => handleReject(id) : undefined}
                    onViewDetail={handleViewDetail}
                  />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Action detail slide-out */}
        <ActionDetailModal
          action={detailAction}
          isOpen={detailAction !== null}
          onClose={() => setDetailAction(null)}
          onApprove={detailAction?.status === "pending" ? handleApprove : undefined}
          onReject={detailAction?.status === "pending" ? handleReject : undefined}
        />
      </div>
    </DashboardLayout>
  );
}
