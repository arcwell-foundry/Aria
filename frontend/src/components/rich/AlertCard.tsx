import { useCallback, useMemo } from 'react';
import { wsManager } from '@/core/WebSocketManager';
import { WS_EVENTS } from '@/types/chat';
import { useConversationStore } from '@/stores/conversationStore';

export interface AlertCardData {
  id: string;
  company_name: string;
  headline: string;
  summary: string;
  severity: 'high' | 'medium' | 'low';
}

interface AlertCardProps {
  data: AlertCardData;
}

const SEVERITY_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  high: { bg: 'bg-red-500/15', text: 'text-red-400', label: 'HIGH' },
  medium: { bg: 'bg-amber-500/15', text: 'text-amber-400', label: 'MEDIUM' },
  low: { bg: 'bg-blue-500/15', text: 'text-blue-400', label: 'LOW' },
};

/**
 * Parse a backend-generated summary string like "Priority: medium. Due: 2026-03-02T02:39:42.764559+00:00"
 * Returns the extracted priority and a formatted due date string.
 */
function parseOverdueSummary(summary: string): { priority: string; dueDateDisplay: string } {
  // Default values
  let priority = 'high';
  let dueDateDisplay = '';

  // Try to parse "Priority: X. Due: Y" format
  const priorityMatch = summary.match(/Priority:\s*(\w+)/i);
  const dueMatch = summary.match(/Due:\s*(\S+)/i);

  if (priorityMatch) {
    priority = priorityMatch[1].toLowerCase();
  }

  if (dueMatch) {
    const dueDateStr = dueMatch[1];
    try {
      const dueDate = new Date(dueDateStr);
      const now = new Date();

      // Calculate days overdue (if in the past)
      const diffMs = now.getTime() - dueDate.getTime();
      const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

      if (diffDays > 0) {
        dueDateDisplay = `Overdue by ${diffDays} ${diffDays === 1 ? 'day' : 'days'}`;
      } else if (diffDays === 0) {
        dueDateDisplay = 'Due today';
      } else {
        // Future date - show as "Due: Feb 23"
        dueDateDisplay = `Due: ${dueDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}`;
      }
    } catch {
      // If date parsing fails, don't show the raw ISO
      dueDateDisplay = '';
    }
  }

  return { priority, dueDateDisplay };
}

export function AlertCard({ data }: AlertCardProps) {
  const addMessage = useConversationStore((s) => s.addMessage);
  const activeConversationId = useConversationStore((s) => s.activeConversationId);

  // Check if this is an overdue task card (has "Priority:" and "Due:" in summary)
  const isOverdueTask = data.summary?.includes('Priority:') && data.summary?.includes('Due:');

  // Parse the summary to extract actual priority and format the due date
  const { priority, dueDateDisplay } = useMemo(() => {
    if (isOverdueTask && data.summary) {
      return parseOverdueSummary(data.summary);
    }
    return { priority: data.severity, dueDateDisplay: '' };
  }, [isOverdueTask, data.summary, data.severity]);

  const handleViewDetails = useCallback(() => {
    if (!data) return;
    const label = data.company_name
      ? `Tell me more about the ${data.company_name} alert`
      : `Tell me more about "${data.headline}"`;
    addMessage({
      role: 'user',
      content: label,
      rich_content: [],
      ui_commands: [],
      suggestions: [],
    });
    wsManager.send(WS_EVENTS.USER_MESSAGE, {
      message: label,
      conversation_id: activeConversationId,
    });
  }, [data, addMessage, activeConversationId]);

  if (!data) return null;

  // Use actual priority for severity styling (not hardcoded backend value)
  const severity = SEVERITY_STYLES[priority] || SEVERITY_STYLES.medium;

  // For overdue tasks, remove "Overdue: " prefix from headline since badge conveys urgency
  const displayHeadline = isOverdueTask && data.headline.startsWith('Overdue: ')
    ? data.headline.slice(9) // Remove "Overdue: " prefix
    : data.headline;

  return (
    <div
      className="rounded-lg border border-[var(--border)] px-4 py-3"
      style={{ backgroundColor: 'var(--bg-elevated)' }}
      data-aria-id={`alert-card-${data.id}`}
    >
      <div className="flex items-start justify-between gap-2 mb-1.5">
        <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-mono uppercase tracking-wider ${severity.bg} ${severity.text}`}>
          {severity.label}
        </span>
        {data.company_name && (
          <span className="text-xs font-mono text-[var(--text-secondary)]">
            {data.company_name}
          </span>
        )}
      </div>
      <p className="text-sm text-[var(--text-primary)] leading-relaxed">
        {displayHeadline}
      </p>
      {/* For overdue tasks, show formatted due date instead of raw summary */}
      {isOverdueTask && dueDateDisplay && (
        <p className="text-xs text-[var(--text-secondary)] mt-1 leading-relaxed">
          {dueDateDisplay}
        </p>
      )}
      {/* For non-overdue alerts, show the summary as-is */}
      {!isOverdueTask && data.summary && (
        <p className="text-xs text-[var(--text-secondary)] mt-1 leading-relaxed">
          {data.summary}
        </p>
      )}
      <div className="mt-2">
        <button
          onClick={handleViewDetails}
          className="px-2.5 py-1 rounded text-[10px] font-mono uppercase tracking-wider text-[var(--accent)] border border-[rgba(46,102,255,0.3)] hover:bg-[rgba(46,102,255,0.1)] transition-colors"
        >
          View Details
        </button>
      </div>
    </div>
  );
}
