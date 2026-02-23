import { useCallback, useState } from 'react';
import { Shield, Clock, AlertTriangle, Check, Loader2, ChevronRight } from 'lucide-react';
import { apiClient } from '@/api/client';
import { wsManager } from '@/core/WebSocketManager';
import { WS_EVENTS } from '@/types/chat';
import { useConversationStore } from '@/stores/conversationStore';
import { getAgentColor, resolveAgent } from '@/constants/agents';
import { AgentAvatar } from '@/components/common/AgentAvatar';
import { CollapsibleCard } from '@/components/conversation/CollapsibleCard';

// --- Types ---

interface TaskResource {
  tool: string;
  connected: boolean;
}

interface PlanTask {
  title: string;
  agent: string;
  dependencies: number[];
  tools_needed: string[];
  auth_required: string[];
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  estimated_minutes: number;
  auto_executable: boolean;
  resource_status?: TaskResource[];
}

export interface ExecutionPlanData {
  goal_id: string;
  title: string;
  // New resource-aware fields
  tasks?: PlanTask[];
  missing_integrations?: string[];
  approval_points?: string[];
  estimated_total_minutes?: number;
  // Legacy phase-based fields (backward compat)
  phases?: LegacyPhase[];
  autonomy?: {
    autonomous: string;
    requires_approval: string;
  };
}

interface LegacyPhase {
  name: string;
  timeline: string;
  agents: string[];
  output: string;
  status: 'pending' | 'active' | 'complete';
}

interface ExecutionPlanCardProps {
  data: ExecutionPlanData;
}

// --- Risk badge colors ---

const RISK_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  LOW: { bg: 'rgba(16, 185, 129, 0.1)', text: '#10B981', border: 'rgba(16, 185, 129, 0.3)' },
  MEDIUM: { bg: 'rgba(245, 158, 11, 0.1)', text: '#F59E0B', border: 'rgba(245, 158, 11, 0.3)' },
  HIGH: { bg: 'rgba(239, 68, 68, 0.1)', text: '#EF4444', border: 'rgba(239, 68, 68, 0.3)' },
  CRITICAL: { bg: 'rgba(220, 38, 38, 0.15)', text: '#DC2626', border: 'rgba(220, 38, 38, 0.4)' },
};

function RiskBadge({ level }: { level: string }) {
  const colors = RISK_COLORS[level] ?? RISK_COLORS.LOW;
  return (
    <span
      className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[9px] font-mono uppercase tracking-wider border"
      style={{ backgroundColor: colors.bg, color: colors.text, borderColor: colors.border }}
    >
      {level === 'HIGH' || level === 'CRITICAL' ? (
        <AlertTriangle className="w-2.5 h-2.5" />
      ) : (
        <Shield className="w-2.5 h-2.5" />
      )}
      {level}
    </span>
  );
}

function ResourceBadge({ resource }: { resource: TaskResource }) {
  if (resource.connected) {
    return (
      <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[9px] font-mono text-emerald-400 bg-emerald-500/10">
        <Check className="w-2.5 h-2.5" />
        {resource.tool}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[9px] font-mono text-amber-400 bg-amber-500/10">
      <AlertTriangle className="w-2.5 h-2.5" />
      {resource.tool}
    </span>
  );
}

function formatMinutes(minutes: number): string {
  if (minutes < 60) return `${minutes}m`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

// --- Legacy phase rendering (backward compat) ---

const PHASE_ICONS: Record<string, string> = {
  pending: '\u25CB',
  active: '\u25CF',
  complete: '\u2713',
};

function LegacyPlanView({ data }: { data: ExecutionPlanData }) {
  return (
    <>
      <div className="px-4 pb-3">
        <div className="space-y-0">
          {(data.phases ?? []).map((phase, i) => (
            <div key={phase.name} className="flex gap-3">
              <div className="flex flex-col items-center w-5 shrink-0">
                <span
                  className="text-sm leading-none mt-1"
                  style={{
                    color: phase.status === 'complete' ? '#10B981'
                      : phase.status === 'active' ? 'var(--accent)'
                      : 'var(--text-secondary)',
                  }}
                >
                  {PHASE_ICONS[phase.status]}
                </span>
                {i < (data.phases?.length ?? 0) - 1 && (
                  <div className="w-px flex-1 min-h-[24px] bg-[var(--border)]" />
                )}
              </div>
              <div className="pb-4 flex-1 min-w-0">
                <div className="flex items-baseline justify-between gap-2">
                  <p className="text-sm font-medium text-[var(--text-primary)]">
                    {phase.name}
                  </p>
                  <span className="text-[10px] font-mono text-[var(--text-secondary)] shrink-0">
                    {phase.timeline}
                  </span>
                </div>
                <p className="text-xs text-[var(--text-secondary)] mt-0.5 leading-relaxed">
                  {phase.output}
                </p>
                {phase.agents.length > 0 && (
                  <div className="flex gap-1.5 mt-1.5 items-center flex-wrap">
                    {phase.agents.map((agent) => {
                      const color = getAgentColor(agent);
                      return (
                        <span
                          key={agent}
                          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-mono uppercase tracking-wider"
                          style={{ backgroundColor: `${color}15`, color }}
                        >
                          <AgentAvatar agentKey={agent} size={14} />
                          {resolveAgent(agent).name}
                        </span>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {data.autonomy && (
        <div className="border-t border-[var(--border)] px-4 py-3 space-y-1.5">
          <div className="flex items-start gap-2">
            <span className="text-emerald-400 text-xs mt-0.5 shrink-0">AUTO</span>
            <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
              {data.autonomy.autonomous}
            </p>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-amber-400 text-xs mt-0.5 shrink-0">APPROVAL</span>
            <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
              {data.autonomy.requires_approval}
            </p>
          </div>
        </div>
      )}
    </>
  );
}

// --- Resource-aware task rendering ---

function TaskListView({ data }: { data: ExecutionPlanData }) {
  const tasks = data.tasks ?? [];

  return (
    <>
      <div className="px-4 pb-3">
        <div className="space-y-0">
          {tasks.map((task, i) => {
            const agentColor = getAgentColor(task.agent);
            const hasDeps = task.dependencies.length > 0;

            return (
              <div key={`${task.title}-${i}`} className="flex gap-3">
                {/* Vertical connector */}
                <div className="flex flex-col items-center w-5 shrink-0">
                  <span
                    className="w-4 h-4 rounded-full border-2 flex items-center justify-center text-[8px] font-mono mt-1"
                    style={{ borderColor: agentColor, color: agentColor }}
                  >
                    {i + 1}
                  </span>
                  {i < tasks.length - 1 && (
                    <div className="w-px flex-1 min-h-[20px] bg-[var(--border)]" />
                  )}
                </div>

                {/* Task content */}
                <div className="pb-4 flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-medium text-[var(--text-primary)]">
                      {task.title}
                    </p>
                    <div className="flex items-center gap-1.5 shrink-0">
                      <RiskBadge level={task.risk_level} />
                      <span className="inline-flex items-center gap-0.5 text-[10px] font-mono text-[var(--text-secondary)]">
                        <Clock className="w-2.5 h-2.5" />
                        {formatMinutes(task.estimated_minutes)}
                      </span>
                    </div>
                  </div>

                  {/* Agent badge */}
                  <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
                    <span
                      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-mono uppercase tracking-wider"
                      style={{ backgroundColor: `${agentColor}15`, color: agentColor }}
                    >
                      <AgentAvatar agentKey={task.agent} size={14} />
                      {resolveAgent(task.agent).name}
                    </span>

                    {task.auto_executable ? (
                      <span className="text-[9px] font-mono uppercase tracking-wider text-emerald-400">
                        Auto
                      </span>
                    ) : (
                      <span className="text-[9px] font-mono uppercase tracking-wider text-amber-400">
                        Approval
                      </span>
                    )}

                    {hasDeps && (
                      <span className="inline-flex items-center gap-0.5 text-[9px] font-mono text-[var(--text-secondary)]">
                        <ChevronRight className="w-2.5 h-2.5" />
                        after {task.dependencies.map(d => `#${d + 1}`).join(', ')}
                      </span>
                    )}
                  </div>

                  {/* Resource status badges */}
                  {task.resource_status && task.resource_status.length > 0 && (
                    <div className="flex gap-1 mt-1.5 flex-wrap">
                      {task.resource_status.map((r) => (
                        <ResourceBadge key={r.tool} resource={r} />
                      ))}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Summary footer */}
      <div className="border-t border-[var(--border)] px-4 py-3 space-y-2">
        {/* Timeline */}
        {data.estimated_total_minutes != null && data.estimated_total_minutes > 0 && (
          <div className="flex items-center gap-2">
            <Clock className="w-3.5 h-3.5 text-[var(--text-secondary)]" />
            <span className="text-xs text-[var(--text-secondary)]">
              Estimated total: <strong className="text-[var(--text-primary)]">{formatMinutes(data.estimated_total_minutes)}</strong>
            </span>
          </div>
        )}

        {/* Missing integrations */}
        {data.missing_integrations && data.missing_integrations.length > 0 && (
          <div className="flex items-start gap-2">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-400 mt-0.5 shrink-0" />
            <div className="text-xs text-[var(--text-secondary)]">
              <span className="text-amber-400 font-medium">Optional integrations: </span>
              {data.missing_integrations.join(', ')}
              <span className="text-[var(--text-secondary)]"> (plan works without these, some steps may be limited)</span>
            </div>
          </div>
        )}

        {/* Approval points */}
        {data.approval_points && data.approval_points.length > 0 && (
          <div className="flex items-start gap-2">
            <Shield className="w-3.5 h-3.5 text-[var(--accent)] mt-0.5 shrink-0" />
            <div className="text-xs text-[var(--text-secondary)]">
              <span className="text-[var(--accent)] font-medium">I'll check with you: </span>
              {data.approval_points.join(' | ')}
            </div>
          </div>
        )}
      </div>
    </>
  );
}

// --- Main component ---

export function ExecutionPlanCard({ data }: ExecutionPlanCardProps) {
  const [isApproved, setIsApproved] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const addMessage = useConversationStore((s) => s.addMessage);
  const activeConversationId = useConversationStore((s) => s.activeConversationId);

  const isResourceAware = Boolean(data.tasks && data.tasks.length > 0);

  const handleApprove = useCallback(async () => {
    setIsLoading(true);
    try {
      await apiClient.post(`/goals/${data.goal_id}/approve`);
      setIsApproved(true);
    } catch {
      // Error surfaced in conversation
    } finally {
      setIsLoading(false);
    }
  }, [data.goal_id]);

  const handleModify = useCallback(() => {
    const message = `I'd like to adjust the execution plan for "${data.title}"`;
    addMessage({
      role: 'user',
      content: message,
      rich_content: [],
      ui_commands: [],
      suggestions: [],
    });
    wsManager.send(WS_EVENTS.USER_MESSAGE, {
      message,
      conversation_id: activeConversationId,
    });
  }, [data.title, addMessage, activeConversationId]);

  const handleDiscuss = useCallback(() => {
    const message = `Tell me more about the execution plan for "${data.title}"`;
    addMessage({
      role: 'user',
      content: message,
      rich_content: [],
      ui_commands: [],
      suggestions: [],
    });
    wsManager.send(WS_EVENTS.USER_MESSAGE, {
      message,
      conversation_id: activeConversationId,
    });
  }, [data.title, addMessage, activeConversationId]);

  const approvalButtons = !isApproved ? (
    <div className="border-t border-[var(--border)] px-4 py-3 flex items-center gap-2">
      <button
        onClick={handleApprove}
        disabled={isLoading}
        className="px-3 py-1.5 rounded-md text-xs font-medium text-white transition-colors disabled:opacity-50"
        style={{ backgroundColor: 'var(--accent)' }}
      >
        {isLoading ? (
          <span className="inline-flex items-center gap-1">
            <Loader2 className="w-3 h-3 animate-spin" />
            Starting...
          </span>
        ) : (
          'Approve Plan'
        )}
      </button>
      <button
        onClick={handleModify}
        className="px-3 py-1.5 rounded-md text-xs font-medium border border-[var(--border)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
      >
        Modify
      </button>
      <button
        onClick={handleDiscuss}
        className="px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
      >
        Discuss
      </button>
    </div>
  ) : null;

  return (
    <div
      className="rounded-lg border border-[var(--border)] overflow-hidden"
      style={{ backgroundColor: 'var(--bg-elevated)' }}
      data-aria-id={`execution-plan-${data.goal_id}`}
    >
      <CollapsibleCard approvalSlot={approvalButtons}>
        {/* Header */}
        <div className="px-4 pt-4 pb-2 flex items-start justify-between">
          <div>
            <p className="text-[10px] font-mono uppercase tracking-wider text-[var(--accent)] mb-1">
              Execution Plan
            </p>
            <h3 className="font-display italic text-base text-[var(--text-primary)]">
              {data.title}
            </h3>
          </div>
          <div className="flex items-center gap-2">
            {isResourceAware && data.tasks && (
              <span className="text-[10px] font-mono text-[var(--text-secondary)]">
                {data.tasks.length} tasks
              </span>
            )}
            {isApproved && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono uppercase tracking-wider bg-emerald-500/20 text-emerald-400">
                <Check className="w-2.5 h-2.5" />
                Active
              </span>
            )}
          </div>
        </div>

        {/* Content — resource-aware or legacy */}
        {isResourceAware ? <TaskListView data={data} /> : <LegacyPlanView data={data} />}
      </CollapsibleCard>
    </div>
  );
}
