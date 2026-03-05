import { useCallback } from 'react';
import { wsManager } from '@/core/WebSocketManager';
import { WS_EVENTS } from '@/types/chat';
import { useConversationStore } from '@/stores/conversationStore';

export interface MeetingCardData {
  id: string;
  title: string;
  time: string;
  start_time?: string;
  date?: string;
  attendees: string[];
  company: string;
  has_brief: boolean;
}

interface MeetingCardProps {
  data: MeetingCardData;
}

export function MeetingCard({ data }: MeetingCardProps) {
  const addMessage = useConversationStore((s) => s.addMessage);
  const activeConversationId = useConversationStore((s) => s.activeConversationId);

  const handleViewBrief = useCallback(() => {
    if (!data) return;
    const label = data.company || data.title;
    const message = `Show me the meeting brief for ${label}`;
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

  // Backend sends time pre-formatted (e.g. "11:00 AM"), so display directly.
  // Fall back to parsing start_time ISO string if available.
  let formattedTime = '';
  if (data.time) {
    formattedTime = data.time;
  } else if (data.start_time) {
    const parsed = new Date(data.start_time);
    formattedTime = isNaN(parsed.getTime())
      ? ''
      : parsed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  return (
    <div
      className="rounded-lg border border-[var(--border)] px-4 py-3 flex items-center gap-3"
      style={{ backgroundColor: 'var(--bg-elevated)' }}
      data-aria-id={`meeting-card-${data.id}`}
    >
      <div className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0" style={{ backgroundColor: 'rgba(46, 102, 255, 0.1)' }}>
        <span className="text-[var(--accent)] text-sm font-mono">{formattedTime || '--:--'}</span>
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-[var(--text-primary)] truncate">
          {data.company || data.title}
        </p>
        <p className="text-xs text-[var(--text-secondary)]">
          {(data.attendees ?? []).length > 0
            ? `${(data.attendees ?? []).length} attendee${(data.attendees ?? []).length > 1 ? 's' : ''}`
            : data.title}
        </p>
      </div>
      {data.has_brief && (
        <button
          onClick={handleViewBrief}
          className="shrink-0 px-2.5 py-1 rounded text-[10px] font-mono uppercase tracking-wider text-[var(--accent)] border border-[rgba(46,102,255,0.3)] hover:bg-[rgba(46,102,255,0.1)] transition-colors"
        >
          View Brief
        </button>
      )}
    </div>
  );
}
