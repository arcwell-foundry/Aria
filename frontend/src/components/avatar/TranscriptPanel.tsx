/**
 * TranscriptPanel — Right half of Dialogue Mode.
 *
 * Renders conversation messages as a call transcript aesthetic.
 * Reads from conversationStore (same data as ConversationThread).
 * Timestamps always visible. Active message full opacity, rest dimmed.
 */

import { useEffect, useRef, useMemo } from 'react';
import { Share2, Download } from 'lucide-react';
import { useConversationStore } from '@/stores/conversationStore';
import { TranscriptEntry } from './TranscriptEntry';
import { ChatContextSection } from './ChatContextSection';
import { useModalityStore } from '@/stores/modalityStore';
import { InputBar } from '@/components/conversation/InputBar';
import { SuggestionChips } from '@/components/conversation/SuggestionChips';
import { TimeDivider } from '@/components/conversation/TimeDivider';

interface TranscriptPanelProps {
  onSend: (message: string) => void;
}

function shouldShowTimeDivider(current: string, previous: string): boolean {
  const gap = new Date(current).getTime() - new Date(previous).getTime();
  return gap > 30 * 60 * 1000; // 30 minutes
}

export function TranscriptPanel({ onSend }: TranscriptPanelProps) {
  const messages = useConversationStore((s) => s.messages);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Load chat context when video started from an active conversation
  const conversationId = useModalityStore((s) => s.tavusSession.id);
  const allMessages = useConversationStore((s) => s.messages);
  const chatContextMessages = useMemo(() => {
    // Show last 8 messages that existed before video started
    // (messages already in store when TranscriptPanel mounts)
    return allMessages.slice(-8);
  }, []); // Empty deps: capture messages at mount time only

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length]);

  return (
    <div
      className="flex-1 flex flex-col h-full"
      style={{ backgroundColor: '#0F1117' }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-[#1A1A2E]">
        <h2
          className="text-lg text-[#F8FAFC] italic"
          style={{ fontFamily: "'Instrument Serif', Georgia, serif" }}
        >
          Transcript &amp; Analysis
        </h2>
        <div className="flex items-center gap-2">
          <button
            className="p-2 rounded-lg text-[#8B8FA3] hover:text-[#F8FAFC] hover:bg-[#1A1A2E] transition-colors"
            aria-label="Share transcript"
          >
            <Share2 size={16} />
          </button>
          <button
            className="p-2 rounded-lg text-[#8B8FA3] hover:text-[#F8FAFC] hover:bg-[#1A1A2E] transition-colors"
            aria-label="Download transcript"
          >
            <Download size={16} />
          </button>
        </div>
      </div>

      {/* Chat context from linked conversation */}
      {chatContextMessages.length > 0 && (
        <ChatContextSection messages={chatContextMessages} />
      )}

      {/* Transcript messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {messages.map((message, index) => {
          const prevMessage = messages[index - 1];
          const isFirstInGroup = !prevMessage || prevMessage.role !== message.role;
          const showDivider = prevMessage && shouldShowTimeDivider(message.timestamp, prevMessage.timestamp);
          const isActive = index === messages.length - 1;

          return (
            <div key={message.id}>
              {showDivider && <TimeDivider timestamp={message.timestamp} />}
              <TranscriptEntry
                message={message}
                isActive={isActive}
                isFirstInGroup={isFirstInGroup}
              />
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <SuggestionChips onSelect={onSend} />
      <InputBar onSend={onSend} placeholder="Interrupt to ask a question..." />
    </div>
  );
}
