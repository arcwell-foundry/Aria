/**
 * ExecutionSummaryCard — Structured summary of a completed goal execution.
 *
 * Shows goal title, status, duration, per-agent results with findings,
 * suggested actions, and feedback affordance (thumbs up/down).
 */

import { useState, useCallback } from 'react';
import {
  CheckCircle2,
  XCircle,
  Clock,
  ThumbsUp,
  ThumbsDown,
  ChevronRight,
  Loader2,
} from 'lucide-react';
import { resolveAgent } from '@/constants/agents';
import { AgentAvatar } from '@/components/common/AgentAvatar';
import { submitGoalFeedback } from '@/api/goals';

// --- Types ---

export interface ExecutionAgentResult {
  agent_name: string;
  findings: string[];
  items_count: number;
  success: boolean;
}

export interface ExecutionSummaryData {
  goal_id: string;
  goal_title: string;
  status: 'completed' | 'failed' | 'partial';
  duration_ms: number;
  agent_results: ExecutionAgentResult[];
  suggested_actions: string[];
  feedback_affordance: boolean;
}

interface ExecutionSummaryCardProps {
  data: ExecutionSummaryData;
}

// --- Helpers ---

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  const minutes = Math.floor(ms / 60000);
  const seconds = Math.round((ms % 60000) / 1000);
  return `${minutes}m ${seconds}s`;
}

function getStatusConfig(status: ExecutionSummaryData['status']) {
  switch (status) {
    case 'completed':
      return {
        icon: CheckCircle2,
        label: 'Completed',
        color: 'var(--success)',
        bgColor: 'rgba(34,197,94,0.06)',
      };
    case 'failed':
      return {
        icon: XCircle,
        label: 'Failed',
        color: '#EF4444',
        bgColor: 'rgba(239,68,68,0.06)',
      };
    case 'partial':
      return {
        icon: CheckCircle2,
        label: 'Partially Completed',
        color: '#F59E0B',
        bgColor: 'rgba(245,158,11,0.06)',
      };
  }
}

// --- Component ---

export function ExecutionSummaryCard({ data }: ExecutionSummaryCardProps) {
  const [feedbackSubmitting, setFeedbackSubmitting] = useState(false);
  const [feedbackSubmitted, setFeedbackSubmitted] = useState<'up' | 'down' | null>(null);
  const [feedbackError, setFeedbackError] = useState<string | null>(null);

  const statusConfig = getStatusConfig(data.status);
  const StatusIcon = statusConfig.icon;

  const handleFeedback = useCallback(
    async (rating: 'up' | 'down') => {
      if (feedbackSubmitting || feedbackSubmitted) return;

      setFeedbackSubmitting(true);
      setFeedbackError(null);

      try {
        await submitGoalFeedback(data.goal_id, { rating });
        setFeedbackSubmitted(rating);
      } catch {
        setFeedbackError('Failed to submit feedback');
      } finally {
        setFeedbackSubmitting(false);
      }
    },
    [data.goal_id, feedbackSubmitting, feedbackSubmitted]
  );

  return (
    <div
      className="rounded-lg border overflow-hidden"
      style={{
        borderColor: statusConfig.color,
        backgroundColor: 'var(--bg-elevated)',
      }}
      data-aria-id="execution-summary-card"
    >
      {/* Header: Title + Status + Duration */}
      <div
        className="flex items-center gap-3 px-4 py-3"
        style={{
          backgroundColor: statusConfig.bgColor,
          borderBottom: '1px solid var(--border)',
        }}
      >
        <StatusIcon className="w-4 h-4 shrink-0" style={{ color: statusConfig.color }} />
        <div className="flex-1 min-w-0">
          <p className="text-[10px] font-mono uppercase tracking-wider text-[var(--accent)] mb-0.5">
            Execution Summary
          </p>
          <h3 className="font-display italic text-sm text-[var(--text-primary)] leading-snug truncate">
            {data.goal_title}
          </h3>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <span
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono uppercase tracking-wider"
            style={{
              backgroundColor: `${statusConfig.color}20`,
              color: statusConfig.color,
            }}
          >
            {statusConfig.label}
          </span>
          <span className="inline-flex items-center gap-1 text-xs font-mono text-[var(--text-secondary)]">
            <Clock className="w-3 h-3" />
            {formatDuration(data.duration_ms)}
          </span>
        </div>
      </div>

      {/* Agent Results Section */}
      {data.agent_results.length > 0 && (
        <div className="px-4 py-3 space-y-3">
          <p className="text-[11px] font-medium text-[var(--text-secondary)]">
            Agent Results
          </p>
          {data.agent_results.map((result, i) => {
            const agent = resolveAgent(result.agent_name);
            return (
              <div
                key={`${result.agent_name}-${i}`}
                className="flex gap-3"
              >
                {/* Agent avatar */}
                <div
                  className="shrink-0 w-8 h-8 rounded-full flex items-center justify-center"
                  style={{ backgroundColor: `${agent.color}15` }}
                >
                  <AgentAvatar agentKey={result.agent_name} size={24} />
                </div>

                {/* Agent findings */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-medium text-[var(--text-primary)]">
                      {agent.name}
                    </span>
                    {result.success ? (
                      <CheckCircle2 className="w-3 h-3" style={{ color: 'var(--success)' }} />
                    ) : (
                      <XCircle className="w-3 h-3" style={{ color: '#EF4444' }} />
                    )}
                    {result.items_count > 0 && (
                      <span className="text-[10px] font-mono text-[var(--text-secondary)] bg-[var(--bg-subtle)] px-1.5 py-0.5 rounded">
                        {result.items_count} items
                      </span>
                    )}
                  </div>
                  {result.findings.length > 0 && (
                    <ul className="space-y-0.5">
                      {result.findings.slice(0, 3).map((finding, j) => (
                        <li
                          key={j}
                          className="flex items-start gap-2 text-xs text-[var(--text-secondary)]"
                        >
                          <span
                            className="mt-1.5 w-1 h-1 rounded-full shrink-0"
                            style={{ backgroundColor: agent.color }}
                          />
                          <span className="leading-relaxed">{finding}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Suggested Actions Section */}
      {data.suggested_actions.length > 0 && (
        <div
          className="px-4 py-3"
          style={{ borderTop: '1px solid var(--border)' }}
        >
          <p className="text-[11px] font-medium text-[var(--text-secondary)] mb-2">
            Suggested Next Steps
          </p>
          <ul className="space-y-1.5">
            {data.suggested_actions.map((action, i) => (
              <li
                key={i}
                className="flex items-start gap-2 text-xs text-[var(--text-primary)]"
              >
                <ChevronRight className="w-3 h-3 mt-0.5 shrink-0" style={{ color: 'var(--accent)' }} />
                <span>{action}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Feedback Row */}
      {data.feedback_affordance && (
        <div
          className="flex items-center justify-between px-4 py-2.5"
          style={{ borderTop: '1px solid var(--border)' }}
        >
          <span className="text-xs text-[var(--text-secondary)]">
            Was this execution helpful?
          </span>
          <div className="flex items-center gap-2">
            {feedbackError && (
              <span className="text-xs text-red-400">{feedbackError}</span>
            )}
            {feedbackSubmitted ? (
              <span className="text-xs text-[var(--success)] flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3" />
                Thanks for your feedback
              </span>
            ) : (
              <>
                <button
                  type="button"
                  onClick={() => handleFeedback('up')}
                  disabled={feedbackSubmitting}
                  className={`p-1.5 rounded transition-colors ${
                    feedbackSubmitted === 'up'
                      ? 'bg-emerald-500/20 text-emerald-400'
                      : 'text-[var(--text-secondary)] hover:text-emerald-400 hover:bg-emerald-500/10'
                  } disabled:opacity-50`}
                  aria-label="Thumbs up"
                >
                  {feedbackSubmitting ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <ThumbsUp className="w-4 h-4" />
                  )}
                </button>
                <button
                  type="button"
                  onClick={() => handleFeedback('down')}
                  disabled={feedbackSubmitting}
                  className={`p-1.5 rounded transition-colors ${
                    feedbackSubmitted === 'down'
                      ? 'bg-red-500/20 text-red-400'
                      : 'text-[var(--text-secondary)] hover:text-red-400 hover:bg-red-500/10'
                  } disabled:opacity-50`}
                  aria-label="Thumbs down"
                >
                  {feedbackSubmitting ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <ThumbsDown className="w-4 h-4" />
                  )}
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
