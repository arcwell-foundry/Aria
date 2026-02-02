import { useState, useRef, useCallback, useEffect, type KeyboardEvent } from "react";

interface ChatInputProps {
  onSend: (content: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

export function ChatInput({
  onSend,
  disabled = false,
  placeholder = "Message ARIA...",
}: ChatInputProps) {
  const [content, setContent] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea
  const adjustHeight = useCallback(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = "auto";
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
    }
  }, []);

  useEffect(() => {
    adjustHeight();
  }, [content, adjustHeight]);

  const handleSubmit = useCallback(() => {
    const trimmed = content.trim();
    if (trimmed && !disabled) {
      onSend(trimmed);
      setContent("");
      // Reset height
      if (textareaRef.current) {
        textareaRef.current.style.height = "auto";
      }
    }
  }, [content, disabled, onSend]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit]
  );

  return (
    <div className="relative">
      {/* Outer container with glass effect */}
      <div className="relative bg-slate-800/60 backdrop-blur-xl rounded-2xl border border-white/10 shadow-2xl shadow-black/20 overflow-hidden">
        {/* Subtle gradient overlay */}
        <div className="absolute inset-0 bg-gradient-to-b from-white/5 to-transparent pointer-events-none" />

        {/* Input area */}
        <div className="relative flex items-end gap-3 p-4">
          {/* Textarea */}
          <div className="flex-1 relative">
            <textarea
              ref={textareaRef}
              value={content}
              onChange={(e) => setContent(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={placeholder}
              disabled={disabled}
              rows={1}
              className="w-full bg-transparent text-white placeholder-slate-400 resize-none outline-none text-base leading-relaxed disabled:opacity-50 disabled:cursor-not-allowed"
              style={{ fontFamily: "var(--font-sans)" }}
            />
          </div>

          {/* Send button */}
          <button
            onClick={handleSubmit}
            disabled={disabled || !content.trim()}
            className="relative flex-shrink-0 w-11 h-11 rounded-xl bg-gradient-to-br from-primary-500 to-primary-600 text-white flex items-center justify-center transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed hover:from-primary-400 hover:to-primary-500 hover:shadow-lg hover:shadow-primary-500/30 active:scale-95"
          >
            {/* Button glow */}
            {content.trim() && !disabled && (
              <div className="absolute inset-0 rounded-xl bg-primary-400 blur-md opacity-30" />
            )}

            {/* Icon */}
            <svg
              className="relative w-5 h-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 19V5m0 0l-7 7m7-7l7 7"
              />
            </svg>
          </button>
        </div>

        {/* Keyboard hint */}
        <div className="px-4 pb-3 flex items-center justify-between text-xs text-slate-500">
          <span>
            Press <kbd className="px-1.5 py-0.5 rounded bg-slate-700/50 font-mono text-slate-400">Enter</kbd> to send
          </span>
          <span>
            <kbd className="px-1.5 py-0.5 rounded bg-slate-700/50 font-mono text-slate-400">Shift + Enter</kbd> for new line
          </span>
        </div>
      </div>
    </div>
  );
}
