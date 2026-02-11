import { useEffect, useRef } from 'react';
import { useConversationStore } from '@/stores/conversationStore';
import { MessageBubble } from './MessageBubble';

export function ConversationThread() {
  const messages = useConversationStore((s) => s.messages);
  const isStreaming = useConversationStore((s) => s.isStreaming);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length, isStreaming]);

  return (
    <div
      className="flex-1 overflow-y-auto px-6 py-4 space-y-4"
      data-aria-id="conversation-thread"
    >
      {messages.length === 0 && (
        <div className="flex flex-col items-center justify-center h-full opacity-60">
          <div className="w-12 h-12 rounded-full bg-[var(--accent-muted)] flex items-center justify-center mb-4">
            <div className="w-3 h-3 rounded-full bg-accent aria-pulse-dot" />
          </div>
          <p className="font-display italic text-lg text-[var(--text-primary)]">ARIA</p>
          <p className="text-xs text-[var(--text-secondary)] mt-1">Your AI colleague is ready</p>
        </div>
      )}

      {messages.map((message) => (
        <MessageBubble key={message.id} message={message} />
      ))}

      {isStreaming && (
        <div className="flex justify-start" data-aria-id="streaming-indicator">
          <div className="border-l-2 border-accent pl-4 py-2">
            <div className="flex items-center gap-1.5">
              <div className="w-1.5 h-1.5 rounded-full bg-accent animate-bounce [animation-delay:0ms]" />
              <div className="w-1.5 h-1.5 rounded-full bg-accent animate-bounce [animation-delay:150ms]" />
              <div className="w-1.5 h-1.5 rounded-full bg-accent animate-bounce [animation-delay:300ms]" />
            </div>
          </div>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  );
}
