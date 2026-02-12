import { useCallback, useState } from 'react';
import { wsManager } from '@/core/WebSocketManager';
import { WS_EVENTS } from '@/types/chat';
import { useConversationStore } from '@/stores/conversationStore';
import { apiClient } from '@/api/client';

interface GoalPlanData {
  id: string;
  title: string;
  rationale: string;
  approach: string;
  agents: string[];
  timeline: string;
  goal_type: string;
  status: 'proposed' | 'approved' | 'rejected';
}

interface GoalPlanCardProps {
  data: GoalPlanData;
}

const AGENT_COLORS: Record<string, string> = {
  Hunter: '#2E66FF',
  Analyst: '#8B5CF6',
  Strategist: '#F59E0B',
  Scribe: '#10B981',
  Operator: '#EF4444',
  Scout: '#06B6D4',
};

export function GoalPlanCard({ data }: GoalPlanCardProps) {
  const [status, setStatus] = useState(data.status);
  const [isLoading, setIsLoading] = useState(false);
  const addMessage = useConversationStore((s) => s.addMessage);
  const activeConversationId = useConversationStore((s) => s.activeConversationId);

  const handleApprove = useCallback(async () => {
    setIsLoading(true);
    try {
      await apiClient.post('/goals/approve-proposal', {
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
      // Error handled by WebSocket response
    } finally {
      setIsLoading(false);
    }
  }, [data]);

  const handleDiscuss = useCallback(() => {
    const message = `Tell me more about "${data.title}"`;
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

  const handleModify = useCallback(() => {
    const message = `I'd like to adjust the goal "${data.title}"`;
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

  const isApproved = status === 'approved';

  return (
    <div
      className="rounded-lg border border-[var(--border)] overflow-hidden"
      style={{ backgroundColor: 'var(--bg-elevated)' }}
      data-aria-id={`goal-plan-${data.id}`}
    >
      <div className="px-4 pt-4 pb-2">
        <div className="flex items-start justify-between gap-3">
          <h3 className="font-display italic text-base text-[var(--text-primary)] leading-snug">
            {data.title}
          </h3>
          {isApproved && (
            <span className="shrink-0 inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono uppercase tracking-wider bg-emerald-500/20 text-emerald-400">
              Approved
            </span>
          )}
        </div>
      </div>

      <div className="px-4 pb-2">
        <p className="text-sm leading-relaxed text-[var(--text-secondary)]">
          {data.rationale}
        </p>
      </div>

      <div className="px-4 pb-2">
        <p className="text-xs font-mono uppercase tracking-wider text-[var(--text-secondary)] mb-1 opacity-60">
          Approach
        </p>
        <p className="text-sm text-[var(--text-primary)] leading-relaxed">
          {data.approach}
        </p>
      </div>

      <div className="px-4 pb-3 flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          {data.agents.map((agent) => (
            <span
              key={agent}
              className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono uppercase tracking-wider"
              style={{
                backgroundColor: `${AGENT_COLORS[agent] || '#6B7280'}20`,
                color: AGENT_COLORS[agent] || '#6B7280',
              }}
            >
              {agent}
            </span>
          ))}
        </div>
        <span className="text-xs font-mono text-[var(--text-secondary)]">
          {data.timeline}
        </span>
      </div>

      {!isApproved && (
        <div className="border-t border-[var(--border)] px-4 py-3 flex items-center gap-2">
          <button
            onClick={handleApprove}
            disabled={isLoading}
            className="px-3 py-1.5 rounded-md text-xs font-medium text-white transition-colors disabled:opacity-50"
            style={{ backgroundColor: 'var(--accent)' }}
          >
            {isLoading ? 'Approving...' : 'Approve'}
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
      )}
    </div>
  );
}
