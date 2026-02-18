import { useCallback, useMemo } from 'react';
import { Virtuoso } from 'react-virtuoso';
import { useConversationStore } from '@/stores/conversationStore';
import { MessageBubble } from './MessageBubble';
import { TimeDivider } from './TimeDivider';
import { TypingIndicator } from './TypingIndicator';
import { UnreadIndicator } from './UnreadIndicator';
import { WelcomeCTAs } from './WelcomeCTAs';
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

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-full opacity-60">
      <div className="w-12 h-12 rounded-full bg-[var(--accent-muted)] flex items-center justify-center mb-4">
        <div className="w-3 h-3 rounded-full bg-accent aria-pulse-dot" />
      </div>
      <p className="font-display italic text-lg text-[var(--text-primary)]">ARIA</p>
      <p className="text-xs text-[var(--text-secondary)] mt-1">Your AI colleague is ready</p>
    </div>
  );
}

interface ConversationThreadProps {
  onStartTyping?: () => void;
}

export function ConversationThread({ onStartTyping }: ConversationThreadProps) {
  const messages = useConversationStore((s) => s.messages);
  const isStreaming = useConversationStore((s) => s.isStreaming);

  // Memoize time divider and grouping computations
  const messageMeta = useMemo(() => {
    return messages.map((message, index) => ({
      showTimeDivider: shouldShowTimeDivider(messages[index - 1], message),
      isFirstInGroup: isFirstInGroup(messages, index),
    }));
  }, [messages]);

  const itemContent = useCallback(
    (index: number) => {
      const message = messages[index];
      const meta = messageMeta[index];
      return (
        <div className="pb-4">
          {meta.showTimeDivider && (
            <TimeDivider timestamp={message.timestamp} />
          )}
          <MessageBubble
            message={message}
            isFirstInGroup={meta.isFirstInGroup}
          />
        </div>
      );
    },
    [messages, messageMeta],
  );

  const footer = useCallback(() => {
    if (!isStreaming) return null;
    return (
      <div className="pb-4">
        <TypingIndicator />
      </div>
    );
  }, [isStreaming]);

  if (messages.length === 0) {
    return (
      <div
        className={`flex-1 overflow-y-auto px-6 py-4 relative ${isStreaming ? 'aria-arrival-sweep' : ''}`}
        data-aria-id="conversation-thread"
      >
        <UnreadIndicator />
        {onStartTyping ? <WelcomeCTAs onStartTyping={onStartTyping} /> : <EmptyState />}
      </div>
    );
  }

  return (
    <div
      className={`flex-1 relative ${isStreaming ? 'aria-arrival-sweep' : ''}`}
      data-aria-id="conversation-thread"
    >
      <UnreadIndicator />
      <Virtuoso
        style={{ height: '100%' }}
        className="px-6 py-4"
        totalCount={messages.length}
        itemContent={itemContent}
        followOutput="smooth"
        initialTopMostItemIndex={messages.length - 1}
        components={{ Footer: footer }}
      />
    </div>
  );
}
