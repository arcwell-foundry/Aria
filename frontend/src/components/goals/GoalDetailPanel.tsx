import { useCallback, useEffect, useRef, useState } from "react";
import type { GoalDetail, GoalHealth, AgentStatus } from "@/api/goals";
import { GoalStatusBadge } from "./GoalStatusBadge";
import { ProgressRing } from "./ProgressRing";
import {
  useGoalDetail,
  useAddMilestone,
  useUpdateGoal,
  useGenerateRetrospective,
  useStartGoal,
  usePauseGoal,
} from "@/hooks/useGoals";
import {
  X,
  CheckCircle2,
  Circle,
  Plus,
  Clock,
  AlertTriangle,
  Sparkles,
  Loader2,
  Calendar,
  Users,
  Play,
  Pause,
} from "lucide-react";

interface GoalDetailPanelProps {
  goalId: string;
  isOpen: boolean;
  onClose: () => void;
}

type GoalDetailExtended = GoalDetail & {
  health?: GoalHealth;
  target_date?: string;
};

const healthConfig: Record<GoalHealth, { dotColor: string; label: string }> = {
  on_track: { dotColor: "bg-green-400", label: "On Track" },
  at_risk: { dotColor: "bg-amber-400", label: "At Risk" },
  behind: { dotColor: "bg-red-400", label: "Behind" },
  blocked: { dotColor: "bg-slate-400", label: "Blocked" },
};

const agentStatusConfig: Record<AgentStatus, { color: string; label: string }> = {
  pending: { color: "bg-slate-500/20 text-slate-400 border-slate-500/30", label: "Pending" },
  running: { color: "bg-green-500/20 text-green-400 border-green-500/30", label: "Running" },
  complete: { color: "bg-primary-500/20 text-primary-400 border-primary-500/30", label: "Complete" },
  failed: { color: "bg-red-500/20 text-red-400 border-red-500/30", label: "Failed" },
};

function getDaysRemaining(targetDate: string): number {
  const now = new Date();
  const target = new Date(targetDate);
  const diffMs = target.getTime() - now.getTime();
  return Math.ceil(diffMs / (1000 * 60 * 60 * 24));
}

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function GoalDetailPanel({ goalId, isOpen, onClose }: GoalDetailPanelProps) {
  const { data: goalData, isLoading, error } = useGoalDetail(goalId);
  const addMilestone = useAddMilestone();
  const updateGoal = useUpdateGoal();
  const generateRetrospective = useGenerateRetrospective();
  const startGoal = useStartGoal();
  const pauseGoal = usePauseGoal();

  const [newMilestoneTitle, setNewMilestoneTitle] = useState("");
  const [isEditingDescription, setIsEditingDescription] = useState(false);
  const [editedDescription, setEditedDescription] = useState("");

  // Cast to extended type to handle optional health/target_date fields
  const goal = goalData as GoalDetailExtended | undefined;

  // Track last seen description to sync editedDescription without useEffect + setState
  const lastDescriptionRef = useRef(goal?.description);
  if (goal?.description !== lastDescriptionRef.current) {
    lastDescriptionRef.current = goal?.description;
    if (goal?.description && !isEditingDescription) {
      setEditedDescription(goal.description);
    }
  }

  // ESC key handler
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    },
    [onClose]
  );

  useEffect(() => {
    if (isOpen) {
      document.addEventListener("keydown", handleKeyDown);
      return () => document.removeEventListener("keydown", handleKeyDown);
    }
  }, [isOpen, handleKeyDown]);

  const handleAddMilestone = () => {
    const trimmed = newMilestoneTitle.trim();
    if (!trimmed) return;
    addMilestone.mutate(
      { goalId, data: { title: trimmed } },
      { onSuccess: () => setNewMilestoneTitle("") }
    );
  };

  const handleSaveDescription = () => {
    const trimmed = editedDescription.trim();
    updateGoal.mutate(
      { goalId, data: { description: trimmed || undefined } },
      { onSuccess: () => setIsEditingDescription(false) }
    );
  };

  const handleDescriptionKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSaveDescription();
    }
    if (e.key === "Escape") {
      setIsEditingDescription(false);
      setEditedDescription(goal?.description ?? "");
    }
  };

  const canStart = goal?.status === "draft" || goal?.status === "paused";
  const canPause = goal?.status === "active";
  const showRetrospective = goal?.status === "complete" || goal?.status === "failed";

  return (
    <>
      {/* Backdrop */}
      <div
        className={`fixed inset-0 z-40 bg-black/40 backdrop-blur-sm transition-opacity duration-300 ${
          isOpen ? "opacity-100" : "opacity-0 pointer-events-none"
        }`}
        onClick={onClose}
      />

      {/* Slide-out panel */}
      <div
        className={`fixed top-0 right-0 z-50 h-full w-[480px] max-w-full bg-slate-800 border-l border-slate-700 shadow-2xl transition-transform duration-300 ${
          isOpen ? "translate-x-0" : "translate-x-full"
        }`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex h-full flex-col overflow-y-auto">
          <div className="space-y-6 p-6">
            {/* Header */}
            <div className="flex items-start justify-between gap-3">
              <h2 className="font-semibold text-xl text-white flex-1 min-w-0">
                {isLoading ? (
                  <span className="text-slate-500">Loading...</span>
                ) : (
                  goal?.title ?? "Goal not found"
                )}
              </h2>
              <button
                onClick={onClose}
                className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-700 rounded-lg transition-colors flex-shrink-0"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Error state */}
            {error && (
              <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
                <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0" />
                <p className="text-sm text-red-400">Failed to load goal details.</p>
              </div>
            )}

            {/* Loading state */}
            {isLoading && (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-6 h-6 text-primary-400 animate-spin" />
              </div>
            )}

            {goal && !isLoading && (
              <>
                {/* Status + Health row */}
                <div className="flex items-center gap-3 flex-wrap">
                  <GoalStatusBadge status={goal.status} size="md" />
                  {goal.health && (
                    <span className="inline-flex items-center gap-1.5">
                      <span className={`w-2 h-2 rounded-full ${healthConfig[goal.health].dotColor}`} />
                      <span className="text-sm text-slate-400">
                        {healthConfig[goal.health].label}
                      </span>
                    </span>
                  )}
                  <div className="ml-auto">
                    <ProgressRing progress={goal.progress} size={40} strokeWidth={3} />
                  </div>
                </div>

                {/* Lifecycle actions */}
                {(canStart || canPause) && (
                  <div className="flex items-center gap-2">
                    {canStart && (
                      <button
                        onClick={() => startGoal.mutate(goalId)}
                        disabled={startGoal.isPending}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-green-400 bg-green-500/10 hover:bg-green-500/20 border border-green-500/30 rounded-lg transition-colors disabled:opacity-50"
                      >
                        {startGoal.isPending ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <Play className="w-3.5 h-3.5" />
                        )}
                        Start
                      </button>
                    )}
                    {canPause && (
                      <button
                        onClick={() => pauseGoal.mutate(goalId)}
                        disabled={pauseGoal.isPending}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-amber-400 bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 rounded-lg transition-colors disabled:opacity-50"
                      >
                        {pauseGoal.isPending ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <Pause className="w-3.5 h-3.5" />
                        )}
                        Pause
                      </button>
                    )}
                  </div>
                )}

                {/* Description */}
                <div>
                  <h3 className="text-sm font-medium text-slate-400 uppercase tracking-wider mb-2">
                    Description
                  </h3>
                  {isEditingDescription ? (
                    <div className="space-y-2">
                      <textarea
                        value={editedDescription}
                        onChange={(e) => setEditedDescription(e.target.value)}
                        onKeyDown={handleDescriptionKeyDown}
                        className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-300 placeholder-slate-500 focus:outline-none focus:border-primary-500 resize-none"
                        rows={3}
                        autoFocus
                        placeholder="Add a description..."
                      />
                      <div className="flex items-center gap-2">
                        <button
                          onClick={handleSaveDescription}
                          disabled={updateGoal.isPending}
                          className="px-3 py-1 text-xs font-medium text-white bg-primary-600 hover:bg-primary-500 rounded transition-colors disabled:opacity-50"
                        >
                          {updateGoal.isPending ? "Saving..." : "Save"}
                        </button>
                        <button
                          onClick={() => {
                            setIsEditingDescription(false);
                            setEditedDescription(goal.description ?? "");
                          }}
                          className="px-3 py-1 text-xs font-medium text-slate-400 hover:text-white transition-colors"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <p
                      className="text-sm text-slate-400 cursor-pointer hover:text-slate-300 transition-colors"
                      onClick={() => {
                        setEditedDescription(goal.description ?? "");
                        setIsEditingDescription(true);
                      }}
                      title="Click to edit"
                    >
                      {goal.description || "No description. Click to add one."}
                    </p>
                  )}
                </div>

                {/* Target date */}
                {goal.target_date && (
                  <div>
                    <h3 className="text-sm font-medium text-slate-400 uppercase tracking-wider mb-2">
                      Target Date
                    </h3>
                    <div className="flex items-center gap-2">
                      <Calendar className="w-4 h-4 text-slate-500" />
                      <span className="text-sm text-slate-300">
                        {formatDate(goal.target_date)}
                      </span>
                      {(() => {
                        const daysLeft = getDaysRemaining(goal.target_date);
                        if (daysLeft > 0) {
                          return (
                            <span className="ml-2 text-xs text-slate-500">
                              {daysLeft} day{daysLeft !== 1 ? "s" : ""} left
                            </span>
                          );
                        }
                        return (
                          <span className="ml-2 inline-flex items-center gap-1 text-xs text-red-400">
                            <Clock className="w-3 h-3" />
                            Overdue
                          </span>
                        );
                      })()}
                    </div>
                  </div>
                )}

                {/* Agents section */}
                {goal.goal_agents && goal.goal_agents.length > 0 && (
                  <div>
                    <h3 className="text-sm font-medium text-slate-400 uppercase tracking-wider mb-3">
                      <span className="flex items-center gap-2">
                        <Users className="w-4 h-4" />
                        Agents ({goal.goal_agents.length})
                      </span>
                    </h3>
                    <div className="space-y-2">
                      {goal.goal_agents.map((agent) => (
                        <div
                          key={agent.id}
                          className="flex items-center justify-between px-3 py-2 bg-slate-900/50 rounded-lg"
                        >
                          <span className="text-sm text-slate-300 capitalize">
                            {agent.agent_type.replace(/_/g, " ")}
                          </span>
                          <span
                            className={`inline-flex items-center px-2 py-0.5 rounded-full border text-xs font-medium ${agentStatusConfig[agent.status].color}`}
                          >
                            {agentStatusConfig[agent.status].label}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Milestones section */}
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-medium text-slate-400 uppercase tracking-wider">
                      Milestones ({goal.milestones.length})
                    </h3>
                  </div>
                  <div className="space-y-2">
                    {goal.milestones.map((milestone) => (
                      <div
                        key={milestone.id}
                        className="flex items-start gap-2.5 px-3 py-2 bg-slate-900/50 rounded-lg"
                      >
                        <button className="mt-0.5 flex-shrink-0 text-slate-500">
                          {milestone.status === "complete" ? (
                            <CheckCircle2 className="w-[18px] h-[18px] text-primary-400" />
                          ) : (
                            <Circle className="w-[18px] h-[18px]" />
                          )}
                        </button>
                        <div className="flex-1 min-w-0">
                          <span
                            className={`text-sm ${
                              milestone.status === "complete"
                                ? "text-slate-500 line-through"
                                : "text-slate-300"
                            }`}
                          >
                            {milestone.title}
                          </span>
                          {milestone.due_date && (
                            <p className="text-xs text-slate-500 mt-0.5">
                              Due {formatDate(milestone.due_date)}
                            </p>
                          )}
                        </div>
                      </div>
                    ))}

                    {/* Add milestone input */}
                    <div className="flex items-center gap-2 px-3 py-2">
                      <Plus className="w-4 h-4 text-slate-500 flex-shrink-0" />
                      <input
                        type="text"
                        value={newMilestoneTitle}
                        onChange={(e) => setNewMilestoneTitle(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            e.preventDefault();
                            handleAddMilestone();
                          }
                        }}
                        placeholder="Add milestone..."
                        className="flex-1 bg-transparent text-sm text-slate-300 placeholder-slate-600 focus:outline-none"
                        disabled={addMilestone.isPending}
                      />
                      {addMilestone.isPending && (
                        <Loader2 className="w-3.5 h-3.5 text-slate-500 animate-spin" />
                      )}
                    </div>
                  </div>
                </div>

                {/* Retrospective section */}
                {showRetrospective && (
                  <div>
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-sm font-medium text-slate-400 uppercase tracking-wider">
                        Retrospective
                      </h3>
                      {!goal.retrospective && (
                        <button
                          onClick={() => generateRetrospective.mutate(goalId)}
                          disabled={generateRetrospective.isPending}
                          className="inline-flex items-center gap-1.5 px-3 py-1 text-xs font-medium text-primary-400 bg-primary-500/10 hover:bg-primary-500/20 border border-primary-500/30 rounded-lg transition-colors disabled:opacity-50"
                        >
                          {generateRetrospective.isPending ? (
                            <Loader2 className="w-3 h-3 animate-spin" />
                          ) : (
                            <Sparkles className="w-3 h-3" />
                          )}
                          Generate
                        </button>
                      )}
                    </div>

                    {generateRetrospective.isPending && !goal.retrospective && (
                      <div className="flex flex-col items-center gap-3 py-8 text-center">
                        <Loader2 className="w-6 h-6 text-primary-400 animate-spin" />
                        <p className="text-sm text-slate-400">
                          Generating retrospective analysis...
                        </p>
                      </div>
                    )}

                    {goal.retrospective && (
                      <div className="space-y-4">
                        {/* Summary */}
                        <div>
                          <p className="text-sm text-slate-300">{goal.retrospective.summary}</p>
                        </div>

                        {/* What worked */}
                        {goal.retrospective.what_worked.length > 0 && (
                          <div>
                            <h4 className="text-xs font-medium text-green-400 mb-1.5">
                              What Worked
                            </h4>
                            <ul className="space-y-1">
                              {goal.retrospective.what_worked.map((item, i) => (
                                <li
                                  key={i}
                                  className="flex items-start gap-2 text-sm text-slate-400"
                                >
                                  <span className="mt-1.5 w-1 h-1 rounded-full bg-green-400 flex-shrink-0" />
                                  {item}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {/* What didn't work */}
                        {goal.retrospective.what_didnt.length > 0 && (
                          <div>
                            <h4 className="text-xs font-medium text-red-400 mb-1.5">
                              What Didn&apos;t Work
                            </h4>
                            <ul className="space-y-1">
                              {goal.retrospective.what_didnt.map((item, i) => (
                                <li
                                  key={i}
                                  className="flex items-start gap-2 text-sm text-slate-400"
                                >
                                  <span className="mt-1.5 w-1 h-1 rounded-full bg-red-400 flex-shrink-0" />
                                  {item}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {/* Learnings */}
                        {goal.retrospective.learnings.length > 0 && (
                          <div>
                            <h4 className="text-xs font-medium text-amber-400 mb-1.5">
                              Key Learnings
                            </h4>
                            <ul className="space-y-1">
                              {goal.retrospective.learnings.map((item, i) => (
                                <li
                                  key={i}
                                  className="flex items-start gap-2 text-sm text-slate-400"
                                >
                                  <span className="mt-1.5 w-1 h-1 rounded-full bg-amber-400 flex-shrink-0" />
                                  {item}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
