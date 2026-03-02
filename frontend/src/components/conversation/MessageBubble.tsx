import { memo, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import type { Message } from '@/types/chat';
import { MessageAvatar } from './MessageAvatar';
import { RichContentRenderer } from '@/components/rich/RichContentRenderer';
import { SpeakButton } from './SpeakButton';
import { useMessageSpeech } from '@/hooks/useMessageSpeech';
import { useThesys } from '@/contexts/ThesysContext';
import { C1MessageRenderer } from './C1MessageRenderer';
import { useConversationStore } from '@/stores/conversationStore';
import { wsManager } from '@/core/WebSocketManager';
import { WS_EVENTS } from '@/types/chat';

interface MessageBubbleProps {
  message: Message;
  isFirstInGroup?: boolean;
}

function formatTime(timestamp: string): string {
  const date = new Date(timestamp);
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

const markdownComponents = {
  h1: ({ children }: { children?: React.ReactNode }) => (
    <h1 className="font-display italic text-xl text-[var(--text-primary)] mb-2 mt-4 first:mt-0">
      {children}
    </h1>
  ),
  h2: ({ children }: { children?: React.ReactNode }) => (
    <h2 className="font-display italic text-lg text-[var(--text-primary)] mb-2 mt-3 first:mt-0">
      {children}
    </h2>
  ),
  h3: ({ children }: { children?: React.ReactNode }) => (
    <h3 className="font-display italic text-base text-[var(--text-primary)] mb-1 mt-3 first:mt-0">
      {children}
    </h3>
  ),
  p: ({ children }: { children?: React.ReactNode }) => (
    <p className="text-sm leading-relaxed text-[var(--text-primary)] mb-2 last:mb-0">
      {children}
    </p>
  ),
  ul: ({ children }: { children?: React.ReactNode }) => (
    <ul className="text-sm text-[var(--text-primary)] mb-2 ml-4 list-disc space-y-1">
      {children}
    </ul>
  ),
  ol: ({ children }: { children?: React.ReactNode }) => (
    <ol className="text-sm text-[var(--text-primary)] mb-2 ml-4 list-decimal space-y-1">
      {children}
    </ol>
  ),
  strong: ({ children }: { children?: React.ReactNode }) => (
    <strong className="font-semibold text-[var(--text-primary)]">{children}</strong>
  ),
  code: ({ children, className }: { children?: React.ReactNode; className?: string }) => {
    const isBlock = className?.includes('language-');
    if (isBlock) {
      return (
        <code className="block font-mono text-xs bg-[var(--bg-elevated)] rounded-md p-3 my-2 overflow-x-auto text-[var(--text-secondary)]">
          {children}
        </code>
      );
    }
    return (
      <code className="font-mono text-xs bg-[var(--bg-elevated)] rounded px-1.5 py-0.5 text-[var(--accent)]">
        {children}
      </code>
    );
  },
};

export const MessageBubble = memo(function MessageBubble({ message, isFirstInGroup = true }: MessageBubbleProps) {
  const isAria = message.role === 'aria';
  const { enabled: thesysEnabled } = useThesys();
  const addMessage = useConversationStore((s) => s.addMessage);

  const {
    speakMessage,
    stopSpeaking,
    togglePause,
    isThisMessageSpeaking,
    isThisMessagePaused,
    isSupported: isTTSSupported,
  } = useMessageSpeech();

  const isSpeaking = isThisMessageSpeaking(message.id);
  const isPaused = isThisMessagePaused(message.id);

  const handleSendMessage = useCallback((msg: string) => {
    // Add user message to store
    addMessage({
      role: 'user',
      content: msg,
      rich_content: [],
      ui_commands: [],
      suggestions: [],
    });

    // Send via WebSocket
    const activeConversationId = useConversationStore.getState().activeConversationId;

    wsManager.send(WS_EVENTS.USER_MESSAGE, {
      message: msg,
      conversation_id: activeConversationId,
    });
  }, [addMessage]);

  if (isAria) {
    // Check if we should render with C1
    const shouldUseC1 =
      thesysEnabled &&
      message.render_mode === 'c1' &&
      message.c1_response &&
      message.c1_response.trim() !== '';
    return (
      <div
        className={`group flex items-start gap-3 justify-start ${
          message.isStreaming
            ? 'aria-message-streaming'
            : 'motion-safe:animate-[slideInLeft_200ms_ease-out] aria-message-settle'
        }`}
        data-aria-id="message-aria"
        data-message-id={message.id}
      >
        <MessageAvatar role="aria" visible={isFirstInGroup} />

        <div className="relative max-w-[85%] border-l-2 border-accent pl-4 py-2">
          {shouldUseC1 ? (
            // C1 rendering mode
            <C1MessageRenderer
              c1Response={message.c1_response!}
              isStreaming={message.isStreaming || false}
              onSendMessage={handleSendMessage}
            />
          ) : (
            // Markdown rendering mode (fallback)
            <div className="prose-aria">
              <ReactMarkdown
                components={markdownComponents}
              >
                {message.content}
              </ReactMarkdown>
            </div>
          )}

          {/* Rich content renders after main content in both modes */}
          {message.rich_content.length > 0 && (
            <RichContentRenderer items={message.rich_content} />
          )}

          {/* Message actions: speak button + timestamp */}
          <div className="flex items-center gap-2 mt-1">
            <SpeakButton
              text={message.content}
              isSpeaking={isSpeaking}
              isPaused={isPaused}
              onSpeak={(text) => speakMessage(message.id, text)}
              onStop={stopSpeaking}
              onResume={togglePause}
              isSupported={isTTSSupported && !message.isStreaming}
            />
          </div>

          {/* Hover timestamp tooltip */}
          <span className="absolute -bottom-5 left-4 hidden group-hover:block font-mono text-[11px] text-[#555770] bg-[#111318] px-2 py-1 rounded whitespace-nowrap z-10">
            {formatTime(message.timestamp)}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div
      className="group flex items-start gap-3 justify-end motion-safe:animate-[slideInRight_200ms_ease-out]"
      data-aria-id="message-user"
      data-message-id={message.id}
    >
      <div className="relative max-w-[75%] bg-[var(--bg-elevated)] rounded-2xl rounded-br-md px-4 py-3">
        <p className="text-sm text-[var(--text-primary)]">{message.content}</p>

        {/* Hover timestamp tooltip */}
        <span className="absolute -bottom-5 right-4 hidden group-hover:block font-mono text-[11px] text-[#555770] bg-[#111318] px-2 py-1 rounded whitespace-nowrap z-10">
          {formatTime(message.timestamp)}
        </span>
      </div>

      <MessageAvatar role="user" visible={isFirstInGroup} />
    </div>
  );
});
