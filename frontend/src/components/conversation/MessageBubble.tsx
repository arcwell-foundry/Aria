import ReactMarkdown from 'react-markdown';
import type { Message } from '@/types/chat';

interface MessageBubbleProps {
  message: Message;
}

function formatTime(timestamp: string): string {
  const date = new Date(timestamp);
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isAria = message.role === 'aria';

  if (isAria) {
    return (
      <div className="flex justify-start animate-in" data-aria-id="message-aria">
        <div className="max-w-[85%] border-l-2 border-accent pl-4 py-2">
          <div className="prose-aria">
            <ReactMarkdown
              components={{
                h1: ({ children }) => (
                  <h1 className="font-display italic text-xl text-[var(--text-primary)] mb-2 mt-4 first:mt-0">
                    {children}
                  </h1>
                ),
                h2: ({ children }) => (
                  <h2 className="font-display italic text-lg text-[var(--text-primary)] mb-2 mt-3 first:mt-0">
                    {children}
                  </h2>
                ),
                h3: ({ children }) => (
                  <h3 className="font-display italic text-base text-[var(--text-primary)] mb-1 mt-3 first:mt-0">
                    {children}
                  </h3>
                ),
                p: ({ children }) => (
                  <p className="text-sm leading-relaxed text-[var(--text-primary)] mb-2 last:mb-0">
                    {children}
                  </p>
                ),
                ul: ({ children }) => (
                  <ul className="text-sm text-[var(--text-primary)] mb-2 ml-4 list-disc space-y-1">
                    {children}
                  </ul>
                ),
                ol: ({ children }) => (
                  <ol className="text-sm text-[var(--text-primary)] mb-2 ml-4 list-decimal space-y-1">
                    {children}
                  </ol>
                ),
                strong: ({ children }) => (
                  <strong className="font-semibold text-[var(--text-primary)]">{children}</strong>
                ),
                code: ({ children, className }) => {
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
              }}
            >
              {message.content}
            </ReactMarkdown>
          </div>

          {message.rich_content.length > 0 && (
            <div className="mt-3 space-y-2">
              {message.rich_content.map((rc, i) => (
                <div
                  key={i}
                  className="rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] px-3 py-2 text-xs text-[var(--text-secondary)]"
                  data-aria-id={`rich-content-${rc.type}`}
                >
                  <span className="font-mono uppercase tracking-wider text-[var(--accent)]">
                    {rc.type}
                  </span>
                </div>
              ))}
            </div>
          )}

          <span className="block mt-2 font-mono text-[10px] text-[var(--text-secondary)] opacity-60">
            {formatTime(message.timestamp)}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-end animate-in" data-aria-id="message-user">
      <div className="max-w-[75%] bg-[var(--bg-elevated)] rounded-2xl rounded-br-md px-4 py-3">
        <p className="text-sm text-[var(--text-primary)]">{message.content}</p>
        <span className="block mt-1.5 font-mono text-[10px] text-[var(--text-secondary)] opacity-60 text-right">
          {formatTime(message.timestamp)}
        </span>
      </div>
    </div>
  );
}
