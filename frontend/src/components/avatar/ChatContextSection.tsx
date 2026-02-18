import { useState, useEffect, useRef } from 'react';
import { ChevronDown, ChevronUp, MessageSquare } from 'lucide-react';
import type { Message } from '@/types/chat';

interface ChatContextSectionProps {
  messages: Message[];
}

export function ChatContextSection({ messages }: ChatContextSectionProps) {
  const [expanded, setExpanded] = useState(true);
  const autoCollapsedRef = useRef(false);

  // Auto-collapse after 10 seconds
  useEffect(() => {
    if (autoCollapsedRef.current) return;
    const timer = setTimeout(() => {
      autoCollapsedRef.current = true;
      setExpanded(false);
    }, 10_000);
    return () => clearTimeout(timer);
  }, []);

  if (messages.length === 0) return null;

  return (
    <div
      className="border-b border-[#1A1A2E]"
      style={{ backgroundColor: 'rgba(255,255,255,0.03)' }}
      data-aria-id="chat-context-section"
    >
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between px-6 py-2.5 text-left hover:bg-[rgba(255,255,255,0.02)] transition-colors"
      >
        <div className="flex items-center gap-2">
          <MessageSquare size={14} className="text-[#2E66FF]" />
          <span className="text-xs font-medium text-[#F8FAFC]">
            Continuing from chat
          </span>
          <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-[#1A1A2E] text-[#8B8FA3]">
            {messages.length} message{messages.length !== 1 ? 's' : ''}
          </span>
        </div>
        {expanded ? (
          <ChevronUp size={14} className="text-[#8B8FA3]" />
        ) : (
          <ChevronDown size={14} className="text-[#8B8FA3]" />
        )}
      </button>

      {expanded && (
        <div className="px-6 pb-3 space-y-1.5">
          {messages.map((msg) => (
            <ChatContextMessage key={msg.id} message={msg} />
          ))}
        </div>
      )}
    </div>
  );
}

function ChatContextMessage({ message }: { message: Message }) {
  const [showFull, setShowFull] = useState(false);
  const isLong = message.content.length > 120;
  const displayText = isLong && !showFull
    ? message.content.slice(0, 120) + '...'
    : message.content;

  return (
    <div
      className="flex gap-2 text-xs cursor-pointer"
      onClick={() => isLong && setShowFull((v) => !v)}
    >
      <span
        className="font-semibold flex-shrink-0"
        style={{
          color: message.role === 'aria' ? '#2E66FF' : '#8B8FA3',
        }}
      >
        {message.role === 'aria' ? 'ARIA' : 'You'}:
      </span>
      <span className="text-[#C0C4D0] leading-relaxed">{displayText}</span>
    </div>
  );
}
