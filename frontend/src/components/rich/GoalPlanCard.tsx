import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  Check,
  Clock,
  Loader2,
  MessageSquare,
  Pencil,
  Plug,
  Search,
  Send,
  FlaskConical,
  Target,
  X,
} from 'lucide-react';
import { wsManager } from '@/core/WebSocketManager';
import { WS_EVENTS } from '@/types/chat';
import { useConversationStore } from '@/stores/conversationStore';
import { approveGoalProposal } from '@/api/goals';
import { getAgentColor, resolveAgent } from '@/constants/agents';
import { AgentAvatar } from '@/components/common/AgentAvatar';
import { CollapsibleCard } from '@/components/conversation/CollapsibleCard';

// --- Types ---

export interface ResourceStatus {
  tool: string;
  connected: boolean;
  display_name?: string;
  description?: string;
  toolkit?: string;
  setup_instruction?: string;
}

export interface GoalPlanPhase {
  name: string;
  description: string;
  agent: string;
  deliverable?: string;
  resource_status?: ResourceStatus[];
}

export interface GoalPlanData {
  id: string;
  title: string;
  rationale: string;
  approach: string;
  phases?: GoalPlanPhase[];
  agents: string[];
  timeline: string;
  goal_type: string;
  status: 'proposed' | 'approved' | 'rejected';
}

interface GoalPlanCardProps {
  data: GoalPlanData;
}

// --- Helpers ---

/** Map phase name keywords to Lucide icons. */
function PhaseIcon({ name, color }: { name: string; color: string }) {
  const lower = name.toLowerCase();
  const cls = 'w-3 h-3';
  const style = { color };
  if (lower.includes('discover') || lower.includes('search') || lower.includes('scan'))
    return <Search className={cls} style={style} />;
  if (lower.includes('analy') || lower.includes('research') || lower.includes('qualif'))
    return <FlaskConical className={cls} style={style} />;
  if (lower.includes('draft') || lower.includes('action') || lower.includes('write') || lower.includes('outreach'))
    return <Pencil className={cls} style={style} />;
  return <Target className={cls} style={style} />;
}

/** Render tool connection status indicator. */
function ToolStatusIndicator({ resource }: { resource: ResourceStatus }) {
  const displayName = resource.display_name || resource.tool;
  const isConnected = resource.connected;

  return (
    <div className="flex items-center gap-1 text-[10px]">
      {isConnected ? (
        <>
          <Check className="w-2.5 h-2.5 text-emerald-400" />
          <span className="text-emerald-400">{displayName}</span>
        </>
      ) : (
        <>
          <AlertTriangle className="w-2.5 h-2.5 text-amber-400" />
          <span className="text-amber-400">{displayName}</span>
          <span className="text-[var(--text-secondary)] opacity-70 ml-1">
            Connect in Settings
          </span>
        </>
      )}
    </div>
  );
}

// --- Component ---

export function GoalPlanCard({ data }: GoalPlanCardProps) {
  const [status, setStatus] = useState(data.status);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [modifyMode, setModifyMode] = useState(false);
  const [modifyText, setModifyText] = useState('');
  const modifyInputRef = useRef<HTMLTextAreaElement>(null);
  const addMessage = useConversationStore((s) => s.addMessage);
  const activeConversationId = useConversationStore((s) => s.activeConversationId);

  const phases = useMemo(() => data.phases ?? [], [data.phases]);
  const isApproved = status === 'approved';

  // Focus the modify textarea when it opens
  useEffect(() => {
    if (modifyMode) modifyInputRef.current?.focus();
  }, [modifyMode]);

  // --- Handlers ---

  const handleApprove = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      await approveGoalProposal({
        title: data.title,
        description: data.rationale,
        goal_type: data.goal_type,
        rationale: data.rationale,
        approach: data.approach,
        agents: data.agents,
        timeline: data.timeline,
      });
      setStatus('approved');
    } catch {
      setError('Approval failed — try again');
    } finally {
      setIsLoading(false);
    }
  }, [data]);

  const sendMessage = useCallback(
    (content: string) => {
      addMessage({
        role: 'user',
        content,
        rich_content: [],
        ui_commands: [],
        suggestions: [],
      });
      wsManager.send(WS_EVENTS.USER_MESSAGE, {
        message: content,
        conversation_id: activeConversationId,
      });
    },
    [addMessage, activeConversationId],
  );

  const handleDiscuss = useCallback(() => {
    const phaseSummary = phases.length > 0
      ? ` The plan has ${phases.length} phases: ${phases.map((p) => p.name).join(', ')}.`
      : '';
    sendMessage(
      `I'd like to discuss the plan for "${data.title}".${phaseSummary} ${data.rationale}`,
    );
  }, [data.title, data.rationale, phases, sendMessage]);

  const handleModifyOpen = useCallback(() => {
    setModifyMode(true);
    setModifyText('');
  }, []);

  const handleModifyCancel = useCallback(() => {
    setModifyMode(false);
    setModifyText('');
  }, []);

  const handleModifySubmit = useCallback(() => {
    const text = modifyText.trim();
    if (!text) return;
    sendMessage(
      `Regarding the plan for "${data.title}" — I'd like to change: ${text}`,
    );
    setModifyMode(false);
    setModifyText('');
  }, [data.title, modifyText, sendMessage]);

  // --- Approval slot ---

  const approvalSlot = (() => {
    if (isApproved) return null;

    // Inline modify input
    if (modifyMode) {
      return (
        <div className="border-t border-[var(--border)] px-4 py-3">
          <div className="flex gap-2">
            <textarea
              ref={modifyInputRef}
              value={modifyText}
              onChange={(e) => setModifyText(e.target.value)}
              placeholder="What would you like to change?"
              className="flex-1 bg-[var(--bg-primary)] border border-[var(--border)] rounded-md px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-secondary)] resize-none focus:outline-none focus:border-[var(--accent)] transition-colors"
              rows={2}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleModifySubmit();
                }
                if (e.key === 'Escape') {
                  handleModifyCancel();
                }
              }}
            />
            <div className="flex flex-col gap-1.5">
              <button
                type="button"
                onClick={handleModifySubmit}
                disabled={!modifyText.trim()}
                className="p-1.5 rounded-md text-white transition-colors disabled:opacity-30"
                style={{ backgroundColor: 'var(--accent)' }}
                aria-label="Send modification"
              >
                <Send className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                onClick={handleModifyCancel}
                className="p-1.5 rounded-md text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
                aria-label="Cancel"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      );
    }

    // Default buttons
    return (
      <div className="border-t border-[var(--border)] px-4 py-3 flex items-center gap-2">
        <button
          type="button"
          onClick={handleApprove}
          disabled={isLoading}
          className="px-3 py-1.5 rounded-md text-xs font-medium text-white transition-colors disabled:opacity-50"
          style={{ backgroundColor: 'var(--accent)' }}
        >
          {isLoading ? (
            <span className="inline-flex items-center gap-1">
              <Loader2 className="w-3 h-3 animate-spin" />
              Approving...
            </span>
          ) : (
            'Approve'
          )}
        </button>
        <button
          type="button"
          onClick={handleModifyOpen}
          className="px-3 py-1.5 rounded-md text-xs font-medium border border-[var(--border)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
        >
          Modify
        </button>
        <button
          type="button"
          onClick={handleDiscuss}
          className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
        >
          <MessageSquare className="w-3 h-3" />
          Discuss
        </button>
      </div>
    );
  })();

  // --- Render ---

  return (
    <div
      className="rounded-lg border border-[var(--border)] overflow-hidden"
      style={{ backgroundColor: 'var(--bg-elevated)' }}
      data-aria-id={`goal-plan-${data.id}`}
    >
      <CollapsibleCard approvalSlot={approvalSlot}>
        {/* Header */}
        <div className="px-4 pt-4 pb-2">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-[10px] font-mono uppercase tracking-wider text-[var(--accent)] mb-1">
                Goal Plan
              </p>
              <h3 className="font-display italic text-base text-[var(--text-primary)] leading-snug">
                {data.title}
              </h3>
            </div>
            {isApproved && (
              <span className="shrink-0 inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono uppercase tracking-wider bg-emerald-500/20 text-emerald-400">
                <Check className="w-2.5 h-2.5" />
                Approved
              </span>
            )}
          </div>
        </div>

        {/* Rationale */}
        <div className="px-4 pb-3">
          <p className="text-sm leading-relaxed text-[var(--text-secondary)]">
            {data.rationale}
          </p>
        </div>

        {/* Phases timeline */}
        {phases.length > 0 && (
          <div className="px-4 pb-3">
            <div className="space-y-0">
              {phases.map((phase, i) => {
                const agentColor = getAgentColor(phase.agent);
                return (
                  <div key={`${phase.name}-${i}`} className="flex gap-3">
                    {/* Vertical connector + phase icon */}
                    <div className="flex flex-col items-center w-5 shrink-0">
                      <span
                        className="w-5 h-5 rounded-full flex items-center justify-center mt-0.5"
                        style={{ backgroundColor: `${agentColor}20` }}
                      >
                        <PhaseIcon name={phase.name} color={agentColor} />
                      </span>
                      {i < phases.length - 1 && (
                        <div className="w-px flex-1 min-h-[16px] bg-[var(--border)]" />
                      )}
                    </div>

                    {/* Phase content */}
                    <div className="pb-3 flex-1 min-w-0">
                      <div className="flex items-baseline gap-2 flex-wrap">
                        <p className="text-sm font-medium text-[var(--text-primary)]">
                          {phase.name}
                        </p>
                        <span
                          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-mono uppercase tracking-wider"
                          style={{ backgroundColor: `${agentColor}15`, color: agentColor }}
                        >
                          <AgentAvatar agentKey={phase.agent} size={12} />
                          {resolveAgent(phase.agent).name}
                        </span>
                      </div>
                      <p className="text-xs text-[var(--text-secondary)] mt-0.5 leading-relaxed">
                        {phase.description}
                      </p>
                      {phase.deliverable && (
                        <p className="text-[10px] font-mono text-[var(--text-secondary)] mt-1 opacity-70">
                          Deliverable: {phase.deliverable}
                        </p>
                      )}
                      {/* Tool connection status */}
                      {phase.resource_status && phase.resource_status.length > 0 && (
                        <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 mt-1.5 pt-1.5 border-t border-[var(--border)]/50">
                          <Plug className="w-2.5 h-2.5 text-[var(--text-secondary)] opacity-50" />
                          {phase.resource_status.map((resource) => (
                            <ToolStatusIndicator key={resource.tool} resource={resource} />
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Fallback: approach text when no structured phases */}
        {phases.length === 0 && data.approach && (
          <div className="px-4 pb-2">
            <p className="text-xs font-mono uppercase tracking-wider text-[var(--text-secondary)] mb-1 opacity-60">
              Approach
            </p>
            <p className="text-sm text-[var(--text-primary)] leading-relaxed">
              {data.approach}
            </p>
          </div>
        )}

        {/* Footer: agent badges + timeline */}
        <div className="px-4 pb-3 flex items-center justify-between">
          <div className="flex items-center gap-1.5 flex-wrap">
            {(data.agents ?? []).map((agent) => {
              const color = getAgentColor(agent);
              return (
                <span
                  key={agent}
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono uppercase tracking-wider"
                  style={{ backgroundColor: `${color}20`, color }}
                >
                  <AgentAvatar agentKey={agent} size={16} />
                  {resolveAgent(agent).name}
                </span>
              );
            })}
          </div>
          <span className="inline-flex items-center gap-1 text-xs font-mono text-[var(--text-secondary)]">
            <Clock className="w-3 h-3" />
            {data.timeline}
          </span>
        </div>

        {/* Executing indicator (shown after approval) */}
        {isApproved && (
          <div className="px-4 pb-3">
            <div className="flex items-center gap-2 px-3 py-2 rounded-md" style={{ backgroundColor: 'rgba(46, 102, 255, 0.1)' }}>
              <Loader2 className="w-3.5 h-3.5 animate-spin" style={{ color: 'var(--accent)' }} />
              <span className="text-xs font-medium" style={{ color: 'var(--accent)' }}>
                ARIA is executing this plan...
              </span>
            </div>
          </div>
        )}

        {/* Error state */}
        {error && (
          <div className="px-4 pb-2">
            <p className="text-xs text-red-400">{error}</p>
          </div>
        )}
      </CollapsibleCard>
    </div>
  );
}
