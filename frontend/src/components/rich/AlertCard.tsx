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

const SEVERITY_STYLES: Record<string, { border: string; pillBg: string; pillText: string; label: string }> = {
  high: { border: 'rgb(239, 68, 68)', pillBg: 'bg-red-500/15', pillText: 'text-red-400', label: 'HIGH' },
  medium: { border: 'rgb(245, 158, 11)', pillBg: 'bg-amber-500/15', pillText: 'text-amber-400', label: 'MEDIUM' },
  low: { border: 'rgb(100, 116, 139)', pillBg: 'bg-blue-500/15', pillText: 'text-blue-400', label: 'LOW' },
};

/**
 * Parse a summary that may contain sub-tasks (newline-separated, dash-prefixed).
 * Used for grouped contact cards like "4 follow-ups - 3 days overdue\n- Task1\n- Task2"
 */
function parseSubTasks(summary: string): { subtitle: string; subTasks: string[] } {
  const lines = summary.split('\n');
  const subtitle = lines[0] || '';
  const subTasks = lines.slice(1)
    .filter(l => l.startsWith('- '))
    .map(l => l.slice(2).trim());
  return { subtitle, subTasks };
}

export function AlertCard({ data }: AlertCardProps) {
  const addMessage = useConversationStore((s) => s.addMessage);
  const activeConversationId = useConversationStore((s) => s.activeConversationId);

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

  const { subtitle, subTasks } = useMemo(() => parseSubTasks(data.summary || ''), [data.summary]);
  const hasSubTasks = subTasks.length > 0;

  if (!data) return null;

  const severity = SEVERITY_STYLES[data.severity] || SEVERITY_STYLES.medium;

  // Remove "Overdue: " prefix from headline (redundant in Priority Actions context)
  const displayHeadline = data.headline.startsWith('Overdue: ')
    ? data.headline.slice(9)
    : data.headline;

  return (
    <div
      className="rounded-r-lg pl-3 pr-4 py-3"
      style={{
        borderLeft: `3px solid ${severity.border}`,
        backgroundColor: 'rgba(30, 41, 59, 0.5)',
        fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
      }}
      data-aria-id={`alert-card-${data.id}`}
    >
      {/* Priority pill */}
      <div className="flex items-center gap-2 mb-1.5">
        <span
          className={`inline-flex items-center rounded-full px-2 py-0.5 text-[8px] font-medium tracking-wider ${severity.pillBg} ${severity.pillText}`}
          style={{ fontFamily: "var(--font-mono)" }}
        >
          {severity.label}
        </span>
        {data.company_name && (
          <span
            className="text-[11px] text-slate-500"
            style={{ fontFamily: "var(--font-mono)" }}
          >
            {data.company_name}
          </span>
        )}
      </div>

      {/* Headline */}
      <p className={`text-[var(--text-primary)] leading-snug ${hasSubTasks ? 'text-[15px] font-medium' : 'text-[14px]'}`}>
        {displayHeadline}
      </p>

      {/* Subtitle */}
      {subtitle && (
        <p className="text-[12px] font-light text-slate-400 mt-0.5">
          {subtitle}
        </p>
      )}

      {/* Sub-tasks for grouped cards */}
      {hasSubTasks && (
        <ul className="mt-2 space-y-0.5 pl-1">
          {subTasks.map((task, i) => (
            <li key={i} className="text-[12px] font-light text-slate-400 leading-snug flex">
              <span className="text-slate-500 mr-1.5 shrink-0">-</span>
              <span>{task}</span>
            </li>
          ))}
        </ul>
      )}

      {/* View Details */}
      <div className="mt-2.5">
        <button
          onClick={handleViewDetails}
          className="text-slate-500 hover:text-slate-300 transition-colors uppercase tracking-wider"
          style={{ fontFamily: "var(--font-mono)", fontSize: '10px' }}
        >
          View Details
        </button>
      </div>
    </div>
  );
}
