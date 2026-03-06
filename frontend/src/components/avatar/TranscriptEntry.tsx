/**
 * TranscriptEntry — Single message in the Dialogue Mode transcript.
 *
 * Always left-aligned. Speaker label + timestamp always visible.
 * ARIA messages: "ARIA" in electric blue, content in lighter weight.
 * User messages: "YOU" in muted gray, content in regular weight.
 * Active (latest) message at full opacity, older messages dimmed.
 *
 * Briefing messages (containing a 'briefing' rich_content item) are rendered
 * through BriefingTranscriptView with collapsible sections instead of
 * a flat card list.
 */

import ReactMarkdown from 'react-markdown';
import { MessageAvatar } from '@/components/conversation/MessageAvatar';
import { RichContentRenderer } from '@/components/rich/RichContentRenderer';
import { BriefingTranscriptView } from '@/components/briefing/BriefingTranscriptView';
import type { Message } from '@/types/chat';

interface TranscriptEntryProps {
  message: Message;
  isActive: boolean;
  isFirstInGroup: boolean;
}

function formatTranscriptTime(timestamp: string): string {
  const date = new Date(timestamp);
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

/** Detect whether a message is a text-only briefing delivery */
function isBriefingMessage(message: Message): boolean {
  return (
    message.role === 'aria' &&
    message.rich_content.some((rc) => rc.type === 'briefing')
  );
}

export function TranscriptEntry({ message, isActive, isFirstInGroup }: TranscriptEntryProps) {
  const isAria = message.role === 'aria';
  const isBriefing = isBriefingMessage(message);

  return (
    <div
      className={`flex items-start gap-3 transition-opacity duration-300 ${isActive ? 'opacity-100' : 'opacity-50'}`}
      data-message-id={message.id}
    >
      <MessageAvatar role={message.role} visible={isFirstInGroup} />

      <div className="flex-1 min-w-0">
        {isFirstInGroup && (
          <div className="flex items-center gap-2 mb-1">
            <span
              className={`font-mono text-[11px] tracking-wider ${isAria ? 'text-[#2E66FF]' : 'text-[#8B8FA3]'}`}
            >
              {isAria ? 'ARIA' : 'YOU'}
            </span>
            <span className="font-mono text-[11px] text-[#555770]">
              {formatTranscriptTime(message.timestamp)}
            </span>
          </div>
        )}

        {isBriefing ? (
          /* Organized sectioned briefing view */
          <div className="mt-1">
            <BriefingTranscriptView
              summary={message.content}
              richContent={message.rich_content}
            />
          </div>
        ) : (
          <>
            {isAria ? (
              <div className="prose-aria text-sm leading-relaxed text-[#E2E4E9] font-light">
                <ReactMarkdown>{message.content}</ReactMarkdown>
              </div>
            ) : (
              <p className="text-sm text-[#F8FAFC]">{message.content}</p>
            )}

            {/* Rich content cards */}
            {message.rich_content.length > 0 && (
              <RichContentRenderer items={message.rich_content} />
            )}
          </>
        )}
      </div>
    </div>
  );
}
