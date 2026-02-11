import { useState, useCallback } from 'react';
import { Send } from 'lucide-react';
import { wsManager } from '@/core/WebSocketManager';
import { WS_EVENTS } from '@/types/chat';
import { useConversationStore } from '@/stores/conversationStore';

export interface ChatInputModuleProps {
  context?: string;
  placeholder?: string;
}

export function ChatInputModule({
  context,
  placeholder = 'Ask ARIA about this...',
}: ChatInputModuleProps) {
  const [value, setValue] = useState('');

  const handleSend = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed) return;

    const store = useConversationStore.getState();

    // Add message to conversation thread so it's visible
    store.addMessage({
      role: 'user',
      content: trimmed,
      rich_content: [],
      ui_commands: [],
      suggestions: [],
    });

    // Send via WebSocket with conversation context
    wsManager.send(WS_EVENTS.USER_MESSAGE, {
      message: trimmed,
      conversation_id: store.activeConversationId,
      context_hint: context,
    });
    setValue('');
  }, [value, context]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  return (
    <div data-aria-id="intel-chat-input" className="pt-3 mt-3 border-t" style={{ borderColor: 'var(--border)' }}>
      <div
        className="flex items-center gap-2 rounded-lg border px-3 py-2"
        style={{
          borderColor: 'var(--border)',
          backgroundColor: 'var(--bg-subtle)',
        }}
      >
        <input
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          className="flex-1 bg-transparent text-[12px] font-sans outline-none"
          style={{ color: 'var(--text-primary)' }}
        />
        <button
          onClick={handleSend}
          disabled={!value.trim()}
          className="p-1 rounded transition-colors cursor-pointer disabled:opacity-30 disabled:cursor-default"
          style={{ color: 'var(--accent)' }}
        >
          <Send size={14} />
        </button>
      </div>
    </div>
  );
}
