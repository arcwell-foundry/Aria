import { useCallback } from 'react';
import type { FormEvent, KeyboardEvent } from 'react';
import { Mic, Send } from 'lucide-react';
import { useConversationStore } from '@/stores/conversationStore';

interface InputBarProps {
  onSend: (message: string) => void;
  disabled?: boolean;
}

export function InputBar({ onSend, disabled = false }: InputBarProps) {
  const inputValue = useConversationStore((s) => s.inputValue);
  const setInputValue = useConversationStore((s) => s.setInputValue);
  const isStreaming = useConversationStore((s) => s.isStreaming);

  const canSend = inputValue.trim().length > 0 && !disabled && !isStreaming;

  const handleSubmit = useCallback(
    (e?: FormEvent) => {
      e?.preventDefault();
      if (!canSend) return;
      onSend(inputValue.trim());
      setInputValue('');
    },
    [canSend, inputValue, onSend, setInputValue],
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  return (
    <div className="relative px-6 pb-4 pt-2" data-aria-id="input-bar">
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background: 'linear-gradient(to top, rgba(46,102,255,0.06) 0%, transparent 100%)',
        }}
      />

      <form
        onSubmit={handleSubmit}
        className="relative flex items-end gap-2 rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated)] px-3 py-2"
        style={{
          boxShadow: '0 -8px 40px rgba(46,102,255,0.08), 0 0 0 1px rgba(46,102,255,0.05)',
        }}
      >
        <button
          type="button"
          className="flex-shrink-0 p-2 rounded-lg text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] transition-colors"
          aria-label="Voice input"
        >
          <Mic size={18} />
        </button>

        <textarea
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask ARIA anything..."
          rows={1}
          disabled={disabled}
          className="flex-1 resize-none bg-transparent text-sm text-[var(--text-primary)] placeholder:text-[var(--text-secondary)] outline-none min-h-[36px] max-h-[120px] py-1.5"
          style={{ fontFamily: 'var(--font-sans)' }}
          data-aria-id="message-input"
        />

        <div className="flex-shrink-0 hidden sm:flex items-center">
          <span className="font-mono text-[9px] tracking-widest uppercase text-[var(--text-secondary)] opacity-50 mr-2 select-none">
            Space to talk
          </span>
        </div>

        <button
          type="submit"
          disabled={!canSend}
          className="flex-shrink-0 p-2 rounded-lg bg-accent text-white transition-all hover:bg-[var(--accent-hover)] disabled:opacity-30 disabled:cursor-not-allowed"
          aria-label="Send message"
          data-aria-id="send-button"
        >
          <Send size={16} />
        </button>
      </form>
    </div>
  );
}
