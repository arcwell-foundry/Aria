import { useCallback } from 'react';
import { wsManager } from '@/core/WebSocketManager';
import { WS_EVENTS } from '@/types/chat';
import { useConversationStore } from '@/stores/conversationStore';

export interface SignalCardData {
  id: string;
  company_name: string;
  signal_type: string;
  headline: string;
  health_score?: number;
  lifecycle_stage?: string;
}

interface SignalCardProps {
  data: SignalCardData;
}

const SIGNAL_TYPE_LABELS: Record<string, string> = {
  buying_signal: 'BUYING SIGNAL',
  engagement: 'ENGAGEMENT',
  champion_activity: 'CHAMPION',
};

export function SignalCard({ data }: SignalCardProps) {
  const addMessage = useConversationStore((s) => s.addMessage);
  const activeConversationId = useConversationStore((s) => s.activeConversationId);

  const handleDraftOutreach = useCallback(() => {
    if (!data) return;
    const message = `Draft outreach for ${data.company_name}`;
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
  }, [data, addMessage, activeConversationId]);

  if (!data) return null;

  return (
    <div
      className="rounded-lg border border-[var(--border)] px-4 py-3"
      style={{ backgroundColor: 'var(--bg-elevated)' }}
      data-aria-id={`signal-card-${data.id}`}
    >
      <div className="flex items-start justify-between gap-2 mb-1.5">
        <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-mono uppercase tracking-wider bg-emerald-500/15 text-emerald-400">
          {SIGNAL_TYPE_LABELS[data.signal_type] || data.signal_type?.toUpperCase() || 'SIGNAL'}
        </span>
        {data.health_score != null && (
          <span className={`text-xs font-mono ${data.health_score >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {data.health_score >= 0 ? '+' : ''}{data.health_score}pts
          </span>
        )}
      </div>
      <p className="text-sm text-[var(--text-primary)] leading-relaxed">
        {data.headline}
      </p>
      <div className="mt-2">
        <button
          onClick={handleDraftOutreach}
          className="px-2.5 py-1 rounded text-[10px] font-mono uppercase tracking-wider text-[var(--accent)] border border-[rgba(46,102,255,0.3)] hover:bg-[rgba(46,102,255,0.1)] transition-colors"
        >
          Draft Outreach
        </button>
      </div>
    </div>
  );
}
