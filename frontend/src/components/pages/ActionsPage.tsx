/**
 * ActionsPage - Goals and Activity View
 *
 * Follows ARIA Design System v1.0:
 * - LIGHT THEME (content pages use light background)
 * - Header: "Actions & Goals" with status dot
 * - Active Goals section with progress bars
 * - Completed Goals section with "Show how ARIA did this" delegation tree drawer
 * - Agent Activity grid (6 agent status cards)
 * - Action Queue with pending approvals
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Target,
  CheckCircle,
  XCircle,
  Clock,
  Loader2,
  AlertCircle,
  GitBranch,
} from 'lucide-react';
import { cn } from '@/utils/cn';
import { UpcomingMeetings } from '@/components/actions/UpcomingMeetings';
import { useGoalDashboard } from '@/hooks/useGoals';
import { useActions, useApproveAction, useRejectAction } from '@/hooks/useActionQueue';
import { EmptyState } from '@/components/common/EmptyState';
import { AgentAvatar } from '@/components/common/AgentAvatar';
import { AGENT_REGISTRY, AGENT_TYPES, resolveAgent } from '@/constants/agents';
import type { AgentType } from '@/constants/agents';
import type { GoalStatus, GoalDashboard } from '@/api/goals';
import type { Action, ActionStatus, RiskLevel } from '@/api/actionQueue';
import { DelegationTreeDrawer } from '@/components/traces/DelegationTreeDrawer';

// Status colors
const GOAL_STATUS_COLORS: Record<GoalStatus, string> = {
  draft: 'var(--text-secondary)',
  active: 'var(--success)',
  paused: 'var(--warning)',
  complete: 'var(--success)',
  failed: 'var(--critical)',
};

const RISK_COLORS: Record<RiskLevel, string> = {
  low: 'var(--success)',
  medium: 'var(--warning)',
  high: 'var(--critical)',
  critical: 'var(--critical)',
};

const ACTION_STATUS_COLORS: Record<ActionStatus, string> = {
  pending: 'var(--warning)',
  approved: 'var(--success)',
  auto_approved: 'var(--success)',
  executing: 'var(--accent)',
  completed: 'var(--success)',
  rejected: 'var(--text-secondary)',
  failed: 'var(--critical)',
};

// Format relative time
function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

// Skeleton components
function GoalsSkeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      {Array.from({ length: 3 }).map((_, i) => (
        <div
          key={i}
          className="border border-[var(--border)] rounded-lg p-4"
          style={{ backgroundColor: 'var(--bg-elevated)' }}
        >
          <div className="flex items-center justify-between mb-3">
            <div className="h-4 w-48 bg-[var(--border)] rounded" />
            <div className="h-5 w-16 bg-[var(--border)] rounded-full" />
          </div>
          <div className="h-2 w-full bg-[var(--border)] rounded-full" />
        </div>
      ))}
    </div>
  );
}

function ActionsSkeleton() {
  return (
    <div className="space-y-3 animate-pulse">
      {Array.from({ length: 4 }).map((_, i) => (
        <div
          key={i}
          className="border border-[var(--border)] rounded-lg p-4"
          style={{ backgroundColor: 'var(--bg-elevated)' }}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-full bg-[var(--border)]" />
              <div className="space-y-2">
                <div className="h-4 w-40 bg-[var(--border)] rounded" />
                <div className="h-3 w-24 bg-[var(--border)] rounded" />
              </div>
            </div>
            <div className="flex gap-2">
              <div className="w-8 h-8 rounded bg-[var(--border)]" />
              <div className="w-8 h-8 rounded bg-[var(--border)]" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// Goal Card Component
function GoalCard({ goal, onClick }: { goal: GoalDashboard; onClick?: () => void }) {
  const progress = goal.progress ?? 0;
  const statusColor = GOAL_STATUS_COLORS[goal.status];

  return (
    <button
      onClick={onClick}
      className={cn(
        'w-full text-left border rounded-lg p-4 transition-all duration-200',
        'hover:border-[var(--accent)]/50 hover:shadow-sm'
      )}
      style={{
        borderColor: 'var(--border)',
        backgroundColor: 'var(--bg-elevated)',
      }}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <Target className="w-4 h-4 flex-shrink-0" style={{ color: statusColor }} />
          <span
            className="font-medium text-sm truncate"
            style={{ color: 'var(--text-primary)' }}
          >
            {goal.title}
          </span>
        </div>
        <span
          className="px-2 py-0.5 rounded-full text-xs font-medium flex-shrink-0"
          style={{
            backgroundColor: `${statusColor}20`,
            color: statusColor,
          }}
        >
          {goal.status.toUpperCase()}
        </span>
      </div>

      {/* Progress bar */}
      <div className="flex items-center gap-3">
        <div
          className="flex-1 h-2 rounded-full overflow-hidden"
          style={{ backgroundColor: 'var(--bg-subtle)' }}
        >
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{
              width: `${progress}%`,
              backgroundColor: statusColor,
            }}
          />
        </div>
        <span
          className="font-mono text-xs flex-shrink-0"
          style={{ color: 'var(--text-secondary)' }}
        >
          {progress}%
        </span>
      </div>

      {/* Milestones indicator */}
      {goal.milestone_total > 0 && (
        <div className="flex items-center gap-2 mt-2">
          <span
            className="font-mono text-xs"
            style={{ color: 'var(--text-secondary)' }}
          >
            {goal.milestone_complete}/{goal.milestone_total} milestones
          </span>
        </div>
      )}
    </button>
  );
}

// Agent Status Card Component
function AgentCard({ agent }: { agent: AgentType }) {
  const info = AGENT_REGISTRY[agent];

  return (
    <div
      className="border rounded-lg p-3 text-center"
      style={{
        borderColor: 'var(--border)',
        backgroundColor: 'var(--bg-elevated)',
      }}
    >
      <div className="mx-auto mb-2 w-10 h-10">
        <AgentAvatar agentKey={agent} size={40} />
      </div>
      <p
        className="font-medium text-sm mb-1"
        style={{ color: 'var(--text-primary)' }}
      >
        {info.name}
      </p>
      <p
        className="text-xs leading-tight"
        style={{ color: 'var(--text-secondary)' }}
      >
        {info.description}
      </p>
    </div>
  );
}

// Action Item Component
function ActionItem({
  action,
  onApprove,
  onReject,
  isApproving,
  isRejecting,
}: {
  action: Action;
  onApprove: () => void;
  onReject: () => void;
  isApproving: boolean;
  isRejecting: boolean;
}) {
  const riskColor = RISK_COLORS[action.risk_level];
  const agentInfo = resolveAgent(action.agent);

  return (
    <div
      className="border rounded-lg p-4"
      style={{
        borderColor: 'var(--border)',
        backgroundColor: 'var(--bg-elevated)',
      }}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3 min-w-0 flex-1">
          <div className="flex-shrink-0">
            <AgentAvatar agentKey={action.agent} size={32} />
          </div>
          <div className="min-w-0 flex-1">
            <p
              className="font-medium text-sm truncate"
              style={{ color: 'var(--text-primary)' }}
            >
              {action.title}
            </p>
            <div className="flex items-center gap-2 mt-1">
              <span
                className="font-mono text-xs"
                style={{ color: 'var(--text-secondary)' }}
              >
                {agentInfo.name}
              </span>
              <span
                className="px-1.5 py-0.5 rounded text-xs font-medium"
                style={{
                  backgroundColor: `${riskColor}20`,
                  color: riskColor,
                }}
              >
                {action.risk_level.toUpperCase()}
              </span>
              <span
                className="font-mono text-xs"
                style={{ color: 'var(--text-secondary)' }}
              >
                {formatRelativeTime(action.created_at)}
              </span>
            </div>
          </div>
        </div>

        {/* Action buttons for pending items */}
        {action.status === 'pending' && (
          <div className="flex items-center gap-2 flex-shrink-0">
            <button
              onClick={onReject}
              disabled={isRejecting || isApproving}
              className={cn(
                'p-2 rounded-lg transition-colors',
                'border border-[var(--border)] hover:bg-[var(--bg-subtle)]',
                (isRejecting || isApproving) && 'opacity-50 cursor-not-allowed'
              )}
              style={{ color: 'var(--critical)' }}
              title="Reject"
            >
              {isRejecting ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <XCircle className="w-4 h-4" />
              )}
            </button>
            <button
              onClick={onApprove}
              disabled={isApproving || isRejecting}
              className={cn(
                'p-2 rounded-lg transition-colors',
                (isApproving || isRejecting) && 'opacity-50 cursor-not-allowed'
              )}
              style={{
                backgroundColor: 'var(--success)',
                color: 'white',
              }}
              title="Approve"
            >
              {isApproving ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <CheckCircle className="w-4 h-4" />
              )}
            </button>
          </div>
        )}

        {/* Status indicator for non-pending */}
        {action.status !== 'pending' && (
          <div className="flex items-center gap-2 flex-shrink-0">
            <span
              className="flex items-center gap-1 text-xs"
              style={{ color: ACTION_STATUS_COLORS[action.status] }}
            >
              {action.status === 'completed' && <CheckCircle className="w-3.5 h-3.5" />}
              {action.status === 'rejected' && <XCircle className="w-3.5 h-3.5" />}
              {action.status === 'failed' && <AlertCircle className="w-3.5 h-3.5" />}
              {action.status === 'executing' && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              {action.status.replace('_', ' ').toUpperCase()}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

// Completed Goal Card Component
function CompletedGoalCard({
  goal,
  onShowTree,
}: {
  goal: GoalDashboard;
  onShowTree: () => void;
}) {
  return (
    <div
      className="border rounded-lg p-4"
      style={{
        borderColor: 'var(--border)',
        backgroundColor: 'var(--bg-elevated)',
      }}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <CheckCircle className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--success)' }} />
          <span
            className="font-medium text-sm truncate"
            style={{ color: 'var(--text-primary)' }}
          >
            {goal.title}
          </span>
          <span
            className="px-2 py-0.5 rounded-full text-[10px] font-medium flex-shrink-0"
            style={{
              backgroundColor: 'rgba(16, 185, 129, 0.15)',
              color: 'var(--success)',
            }}
          >
            COMPLETE
          </span>
        </div>
        {goal.completed_at && (
          <span
            className="font-mono text-xs flex-shrink-0 mr-3"
            style={{ color: 'var(--text-secondary)' }}
          >
            {formatRelativeTime(goal.completed_at)}
          </span>
        )}
      </div>
      <button
        type="button"
        onClick={onShowTree}
        className="flex items-center gap-1.5 mt-2 ml-6 text-xs font-medium transition-colors hover:opacity-80"
        style={{ color: 'var(--accent)' }}
      >
        <GitBranch className="w-3.5 h-3.5" />
        Show how ARIA did this
      </button>
    </div>
  );
}

// Main ActionsPage Component
export function ActionsPage() {
  const navigate = useNavigate();
  const [traceGoalId, setTraceGoalId] = useState<string | null>(null);
  const [traceGoalTitle, setTraceGoalTitle] = useState('');

  // Fetch data
  const { data: goals, isLoading: goalsLoading, error: goalsError } = useGoalDashboard();
  const { data: allActions, isLoading: actionsLoading, error: actionsError } = useActions();

  // Mutations
  const approveMutation = useApproveAction();
  const rejectMutation = useRejectAction();

  // Separate pending and completed actions
  const pendingActions = allActions?.filter((a) => a.status === 'pending') ?? [];
  const completedActions = allActions
    ?.filter((a) => ['completed', 'rejected', 'failed'].includes(a.status))
    .slice(0, 5) ?? [];

  const activeGoals = goals?.filter((g) => g.status === 'active' || g.status === 'paused') ?? [];
  const completedGoals = goals?.filter((g) => g.status === 'complete').slice(0, 5) ?? [];
  const hasGoals = activeGoals.length > 0;
  const hasPending = pendingActions.length > 0;

  return (
    <div
      className="flex-1 flex flex-col h-full"
      style={{ backgroundColor: 'var(--bg-primary)' }}
    >
      <div className="flex-1 overflow-y-auto p-8">
        {/* Header */}
        <div className="mb-6">
          <div className="flex items-center gap-3 mb-1">
            <div
              className="w-2 h-2 rounded-full"
              style={{ backgroundColor: 'var(--success)' }}
            />
            <h1
              className="font-display text-2xl italic"
              style={{ color: 'var(--text-primary)' }}
            >
              Actions & Goals
            </h1>
          </div>
          <p
            className="text-sm ml-5"
            style={{ color: 'var(--text-secondary)' }}
          >
            Monitor goals, agent activity, and approve pending actions.
          </p>
        </div>

        {/* Upcoming Meetings Section */}
        <UpcomingMeetings />

        {/* Active Goals Section */}
        <section className="mb-8">
          <h2
            className="font-sans text-sm font-medium mb-4"
            style={{ color: 'var(--text-primary)' }}
          >
            Active Goals
          </h2>

          {goalsLoading ? (
            <GoalsSkeleton />
          ) : goalsError ? (
            <div
              className="text-center py-6"
              style={{ color: 'var(--text-secondary)' }}
            >
              Error loading goals.
            </div>
          ) : !hasGoals ? (
            <EmptyState
              title="No active goals."
              description="Start a conversation with ARIA to create and activate goals."
              suggestion="Create a goal"
              onSuggestion={() => navigate('/')}
              icon={<Target className="w-8 h-8" />}
            />
          ) : (
            <div className="space-y-3">
              {activeGoals.map((goal) => (
                <GoalCard
                  key={goal.id}
                  goal={goal}
                  onClick={() => navigate(`/actions/goals/${goal.id}`)}
                />
              ))}
            </div>
          )}
        </section>

        {/* Completed Goals Section */}
        {completedGoals.length > 0 && (
          <section className="mb-8">
            <h2
              className="font-sans text-sm font-medium mb-4"
              style={{ color: 'var(--text-primary)' }}
            >
              Completed Goals
            </h2>
            <div className="space-y-3">
              {completedGoals.map((goal) => (
                <CompletedGoalCard
                  key={goal.id}
                  goal={goal}
                  onShowTree={() => {
                    setTraceGoalId(goal.id);
                    setTraceGoalTitle(goal.title);
                  }}
                />
              ))}
            </div>
          </section>
        )}

        {/* Agent Activity Section */}
        <section className="mb-8">
          <h2
            className="font-sans text-sm font-medium mb-4"
            style={{ color: 'var(--text-primary)' }}
          >
            Agent Activity
          </h2>

          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            {AGENT_TYPES.map((agent) => (
              <AgentCard key={agent} agent={agent} />
            ))}
          </div>
        </section>

        {/* Action Queue Section */}
        <section>
          <div className="flex items-center justify-between mb-4">
            <h2
              className="font-sans text-sm font-medium"
              style={{ color: 'var(--text-primary)' }}
            >
              Action Queue
            </h2>
            {hasPending && (
              <span
                className="px-2 py-0.5 rounded-full text-xs font-medium"
                style={{
                  backgroundColor: 'var(--warning)',
                  color: 'white',
                }}
              >
                {pendingActions.length} pending
              </span>
            )}
          </div>

          {actionsLoading ? (
            <ActionsSkeleton />
          ) : actionsError ? (
            <div
              className="text-center py-6"
              style={{ color: 'var(--text-secondary)' }}
            >
              Error loading actions.
            </div>
          ) : (
            <div className="space-y-6">
              {/* Pending Approvals */}
              {hasPending && (
                <div>
                  <p
                    className="text-xs font-medium mb-3 uppercase tracking-wider"
                    style={{ color: 'var(--text-secondary)' }}
                  >
                    Pending Approval
                  </p>
                  <div className="space-y-3">
                    {pendingActions.map((action) => (
                      <ActionItem
                        key={action.id}
                        action={action}
                        onApprove={() => approveMutation.mutate(action.id)}
                        onReject={() => rejectMutation.mutate({ actionId: action.id })}
                        isApproving={approveMutation.isPending}
                        isRejecting={rejectMutation.isPending}
                      />
                    ))}
                  </div>
                </div>
              )}

              {/* Recent Completions */}
              {completedActions.length > 0 && (
                <div>
                  <p
                    className="text-xs font-medium mb-3 uppercase tracking-wider"
                    style={{ color: 'var(--text-secondary)' }}
                  >
                    Recent Completions
                  </p>
                  <div className="space-y-3">
                    {completedActions.map((action) => (
                      <ActionItem
                        key={action.id}
                        action={action}
                        onApprove={() => {}}
                        onReject={() => {}}
                        isApproving={false}
                        isRejecting={false}
                      />
                    ))}
                  </div>
                </div>
              )}

              {/* Empty state */}
              {!hasPending && completedActions.length === 0 && (
                <div
                  className="text-center py-8"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  <Clock className="w-8 h-8 mx-auto mb-2 opacity-50" />
                  <p className="text-sm">No actions in the queue.</p>
                  <p className="text-xs mt-1">
                    Actions will appear here when agents have tasks to execute.
                  </p>
                </div>
              )}
            </div>
          )}
        </section>
      </div>

      <DelegationTreeDrawer
        goalId={traceGoalId}
        goalTitle={traceGoalTitle}
        onClose={() => setTraceGoalId(null)}
      />
    </div>
  );
}
