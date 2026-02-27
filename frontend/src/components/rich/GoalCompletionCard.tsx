/**
 * GoalCompletionCard — Summarizes a completed goal's deliverables in conversation.
 *
 * Shows goal title, success status, per-agent result summaries, and CTAs
 * to view the full report or start a follow-up goal.
 */

import { CheckCircle2, XCircle, ChevronRight, Lightbulb, ExternalLink } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { wsManager } from '@/core/WebSocketManager';
import { WS_EVENTS } from '@/types/chat';
import { useConversationStore } from '@/stores/conversationStore';

interface AgentResult {
  agent_type: string;
  success: boolean;
  summary: string;
}

export interface GoalCompletionData {
  goal_id: string;
  goal_title: string;
  success_count: number;
  total_agents: number;
  agent_results: AgentResult[];
  strategic_recommendation?: string;
  key_findings?: string[];
  deliverable_link?: string;
}

const AGENT_LABELS: Record<string, string> = {
  hunter: 'Hunter',
  analyst: 'Analyst',
  scribe: 'Scribe',
  scout: 'Scout',
  strategist: 'Strategist',
  operator: 'Operator',
  verifier: 'Verifier',
};

export function GoalCompletionCard({ data }: { data: GoalCompletionData }) {
  const navigate = useNavigate();
  const addMessage = useConversationStore((s) => s.addMessage);
  const activeConversationId = useConversationStore((s) => s.activeConversationId);

  if (!data) return null;

  const allSuccess = data.success_count === data.total_agents;

  const handleViewReport = () => {
    navigate(data.deliverable_link ?? `/goals/${data.goal_id}`);
  };

  const handleWhatsNext = () => {
    const message = "What should I focus on next?";
    addMessage({
      role: 'user',
      content: message,
      rich_content: [],
      ui_commands: [],
      suggestions: [],
    });
    wsManager.send(WS_EVENTS.USER_MESSAGE, {
      message,
      conversation_id: activeConversationId ?? undefined,
    });
  };

  return (
    <div
      className="rounded-lg border overflow-hidden"
      style={{
        borderColor: allSuccess ? 'var(--success)' : 'var(--border)',
        backgroundColor: 'var(--bg-elevated)',
      }}
      data-aria-id="goal-completion-card"
    >
      {/* Header */}
      <div
        className="flex items-center gap-2 px-4 py-2.5"
        style={{
          backgroundColor: allSuccess
            ? 'rgba(34,197,94,0.06)'
            : 'var(--bg-subtle)',
          borderBottom: '1px solid var(--border)',
        }}
      >
        {allSuccess ? (
          <CheckCircle2 className="w-3.5 h-3.5" style={{ color: 'var(--success)' }} />
        ) : (
          <CheckCircle2 className="w-3.5 h-3.5" style={{ color: '#F59E0B' }} />
        )}
        <span className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
          Goal Complete
        </span>
        <span className="ml-auto text-[11px]" style={{ color: 'var(--text-secondary)' }}>
          {data.success_count}/{data.total_agents} agents
        </span>
      </div>

      {/* Goal title */}
      <div className="px-4 pt-3 pb-1">
        <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
          {data.goal_title}
        </p>
      </div>

      {/* Agent results */}
      <div className="px-4 py-2 space-y-1.5">
        {(data.agent_results ?? []).map((result, i) => (
          <div
            key={`${result.agent_type}-${i}`}
            className="flex items-start gap-2 text-xs"
          >
            {result.success ? (
              <CheckCircle2
                className="w-3 h-3 mt-0.5 shrink-0"
                style={{ color: 'var(--success)' }}
              />
            ) : (
              <XCircle
                className="w-3 h-3 mt-0.5 shrink-0"
                style={{ color: '#EF4444' }}
              />
            )}
            <span style={{ color: 'var(--text-secondary)' }}>
              <span className="font-medium" style={{ color: 'var(--text-primary)' }}>
                {AGENT_LABELS[result.agent_type] ?? result.agent_type}
              </span>
              {result.summary && result.summary !== 'Completed' && result.summary !== 'Failed' && (
                <> — {result.summary}</>
              )}
            </span>
          </div>
        ))}
      </div>

      {/* Key Findings */}
      {data.key_findings && data.key_findings.length > 0 && (
        <div className="px-4 py-2" style={{ borderTop: '1px solid var(--border)' }}>
          <p className="text-[11px] font-medium mb-1.5" style={{ color: 'var(--text-secondary)' }}>
            Key Findings
          </p>
          <ul className="space-y-1">
            {data.key_findings.map((finding, i) => (
              <li
                key={i}
                className="flex items-start gap-2 text-xs"
                style={{ color: 'var(--text-primary)' }}
              >
                <span
                  className="mt-1.5 w-1.5 h-1.5 rounded-full shrink-0"
                  style={{ backgroundColor: 'var(--accent)' }}
                />
                {finding}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Strategic Recommendation */}
      {data.strategic_recommendation && (
        <div className="mx-4 my-2 rounded-md px-3 py-2" style={{ backgroundColor: 'rgba(var(--accent-rgb, 99,102,241), 0.08)' }}>
          <div className="flex items-start gap-2">
            <Lightbulb className="w-3.5 h-3.5 mt-0.5 shrink-0" style={{ color: 'var(--accent)' }} />
            <div>
              <p className="text-[11px] font-medium mb-0.5" style={{ color: 'var(--accent)' }}>
                Recommendation
              </p>
              <p className="text-xs" style={{ color: 'var(--text-primary)' }}>
                {data.strategic_recommendation}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Actions */}
      <div
        className="flex items-center gap-2 px-4 py-2.5"
        style={{ borderTop: '1px solid var(--border)' }}
      >
        <button
          type="button"
          onClick={handleViewReport}
          className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-medium text-white transition-opacity hover:opacity-90"
          style={{ backgroundColor: 'var(--accent)' }}
        >
          View Full Report
          {data.deliverable_link ? (
            <ExternalLink className="w-3 h-3" />
          ) : (
            <ChevronRight className="w-3 h-3" />
          )}
        </button>
        <button
          type="button"
          onClick={handleWhatsNext}
          className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-medium border transition-opacity hover:opacity-90"
          style={{
            borderColor: 'var(--border)',
            color: 'var(--text-secondary)',
            backgroundColor: 'transparent',
          }}
        >
          What's Next?
        </button>
      </div>
    </div>
  );
}
