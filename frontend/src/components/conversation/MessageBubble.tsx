import { memo } from 'react';
import ReactMarkdown from 'react-markdown';
import type { Message } from '@/types/chat';
import { MessageAvatar } from './MessageAvatar';
import { RichContentRenderer } from '@/components/rich/RichContentRenderer';

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

  if (isAria) {
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
          <div className="prose-aria">
            <ReactMarkdown
              components={markdownComponents}
            >
              {message.content}
            </ReactMarkdown>
          </div>

          {message.rich_content.length > 0 && (
            <RichContentRenderer items={message.rich_content} />
          )}

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
