import type { Goal, GoalHealth } from "@/api/goals";
import { GoalStatusBadge } from "./GoalStatusBadge";
import { GoalTypeBadge } from "./GoalTypeBadge";
import { ProgressRing } from "./ProgressRing";

interface GoalCardProps {
  goal: Goal & {
    milestone_total?: number;
    milestone_complete?: number;
    health?: GoalHealth;
    target_date?: string;
  };
  onClick?: () => void;
  onStart?: () => void;
  onPause?: () => void;
  onDelete?: () => void;
  isLoading?: boolean;
}

const healthConfig: Record<GoalHealth, { color: string; label: string }> = {
  on_track: { color: "bg-green-400", label: "On Track" },
  at_risk: { color: "bg-warning", label: "At Risk" },
  behind: { color: "bg-critical", label: "Behind" },
  blocked: { color: "bg-slate-400", label: "Blocked" },
};

export function GoalCard({
  goal,
  onClick,
  onStart,
  onPause,
  onDelete,
  isLoading = false,
}: GoalCardProps) {
  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  };

  const getDaysRemaining = (targetDate: string): number => {
    const now = new Date();
    const target = new Date(targetDate);
    const diffMs = target.getTime() - now.getTime();
    return Math.ceil(diffMs / (1000 * 60 * 60 * 24));
  };

  const canStart = goal.status === "draft" || goal.status === "paused";
  const canPause = goal.status === "active";

  return (
    <div
      className={`group relative bg-slate-800/50 border border-slate-700 rounded-xl p-5 transition-all duration-200 hover:bg-slate-800/80 hover:border-slate-600 hover:shadow-lg hover:shadow-slate-900/50 ${
        onClick ? "cursor-pointer" : ""
      } ${isLoading ? "opacity-60 pointer-events-none" : ""}`}
      onClick={onClick}
    >
      {/* Gradient border effect on hover */}
      <div className="absolute inset-0 rounded-xl bg-gradient-to-r from-primary-500/0 via-primary-500/10 to-accent-500/0 opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />

      <div className="relative flex items-start gap-4">
        {/* Progress ring */}
        <ProgressRing progress={goal.progress} size={56} strokeWidth={5} />

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1 min-w-0">
              <h3 className="text-lg font-semibold text-white truncate group-hover:text-primary-400 transition-colors">
                {goal.title}
              </h3>
              {goal.description && (
                <p className="mt-1 text-sm text-slate-400 line-clamp-2">{goal.description}</p>
              )}
            </div>

            {/* Actions menu */}
            <div
              className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity"
              onClick={(e) => e.stopPropagation()}
            >
              {canStart && onStart && (
                <button
                  onClick={onStart}
                  className="p-2 text-slate-400 hover:text-green-400 hover:bg-green-500/10 rounded-lg transition-colors"
                  title="Start goal"
                >
                  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M8 5v14l11-7z" />
                  </svg>
                </button>
              )}
              {canPause && onPause && (
                <button
                  onClick={onPause}
                  className="p-2 text-slate-400 hover:text-warning hover:bg-warning/10 rounded-lg transition-colors"
                  title="Pause goal"
                >
                  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z" />
                  </svg>
                </button>
              )}
              {onDelete && (
                <button
                  onClick={onDelete}
                  className="p-2 text-slate-400 hover:text-critical hover:bg-critical/10 rounded-lg transition-colors"
                  title="Delete goal"
                >
                  <svg
                    className="w-4 h-4"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                    />
                  </svg>
                </button>
              )}
            </div>
          </div>

          {/* Badges and meta */}
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <GoalTypeBadge type={goal.goal_type} size="sm" />
            <GoalStatusBadge status={goal.status} size="sm" />
            {goal.health && (
              <span className="inline-flex items-center gap-1.5">
                <span className={`w-2 h-2 rounded-full ${healthConfig[goal.health].color}`} />
                <span className="text-xs text-slate-400">{healthConfig[goal.health].label}</span>
              </span>
            )}
            <span className="text-xs text-slate-500">Created {formatDate(goal.created_at)}</span>
            {goal.target_date && (() => {
              const daysLeft = getDaysRemaining(goal.target_date);
              return daysLeft > 0 ? (
                <span className="text-xs text-slate-500">&middot; {daysLeft} days left</span>
              ) : (
                <span className="text-xs text-critical">&middot; Overdue</span>
              );
            })()}
          </div>

          {/* Milestone progress bar */}
          {goal.milestone_total != null && goal.milestone_total > 0 && (
            <div className="mt-3">
              <div className="bg-slate-700 h-1 rounded-full">
                <div
                  className="h-1 rounded-full bg-primary-500"
                  style={{
                    width: `${((goal.milestone_complete ?? 0) / goal.milestone_total) * 100}%`,
                  }}
                />
              </div>
              <p className="mt-1 text-xs text-slate-500">
                {goal.milestone_complete ?? 0} of {goal.milestone_total} milestones
              </p>
            </div>
          )}

          {/* Agent count if available */}
          {goal.goal_agents && goal.goal_agents.length > 0 && (
            <div className="mt-3 flex items-center gap-2 text-xs text-slate-500">
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z"
                />
              </svg>
              <span>
                {goal.goal_agents.length} agent{goal.goal_agents.length !== 1 ? "s" : ""} assigned
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
