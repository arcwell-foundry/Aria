import { useCallback } from 'react';
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

export function AlertCard({ data }: AlertCardProps) {
  const addMessage = useConversationStore((s) => s.addMessage);
  const activeConversationId = useConversationStore((s) => s.activeConversationId);
  const severity = SEVERITY_STYLES[data.severity] || SEVERITY_STYLES.medium;

  const handleViewDetails = useCallback(() => {
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
  }, [data.company_name, data.headline, addMessage, activeConversationId]);

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
        {data.headline}
      </p>
      {data.summary && (
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
