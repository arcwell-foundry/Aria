import { useEffect, useRef } from 'react';
import { useConversationStore } from '@/stores/conversationStore';
import { MessageBubble } from './MessageBubble';
import { TimeDivider } from './TimeDivider';
import { TypingIndicator } from './TypingIndicator';
import { UnreadIndicator } from './UnreadIndicator';
import type { Message } from '@/types/chat';

const THIRTY_MINUTES_MS = 30 * 60 * 1000;

function shouldShowTimeDivider(prev: Message | undefined, current: Message): boolean {
  if (!prev) return false;
  const prevTime = new Date(prev.timestamp).getTime();
  const currTime = new Date(current.timestamp).getTime();
  return currTime - prevTime >= THIRTY_MINUTES_MS;
}

function isFirstInGroup(messages: Message[], index: number): boolean {
  if (index === 0) return true;
  const prev = messages[index - 1];
  const curr = messages[index];
  if (prev.role !== curr.role) return true;
  const gap = new Date(curr.timestamp).getTime() - new Date(prev.timestamp).getTime();
  return gap >= THIRTY_MINUTES_MS;
}

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
      <UnreadIndicator />

      {messages.length === 0 && (
        <div className="flex flex-col items-center justify-center h-full opacity-60">
          <div className="w-12 h-12 rounded-full bg-[var(--accent-muted)] flex items-center justify-center mb-4">
            <div className="w-3 h-3 rounded-full bg-accent aria-pulse-dot" />
          </div>
          <p className="font-display italic text-lg text-[var(--text-primary)]">ARIA</p>
          <p className="text-xs text-[var(--text-secondary)] mt-1">Your AI colleague is ready</p>
        </div>
      )}

      {messages.map((message, index) => (
        <div key={message.id}>
          {shouldShowTimeDivider(messages[index - 1], message) && (
            <TimeDivider timestamp={message.timestamp} />
          )}
          <MessageBubble
            message={message}
            isFirstInGroup={isFirstInGroup(messages, index)}
          />
        </div>
      ))}

      {isStreaming && <TypingIndicator />}

      <div ref={bottomRef} />
    </div>
  );
}
