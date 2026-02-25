import { useCallback, useRef, useEffect } from 'react';
import type { FormEvent, KeyboardEvent } from 'react';
import { Send, Phone, Video } from 'lucide-react';
import { useConversationStore } from '@/stores/conversationStore';
import { useVoiceInput } from '@/hooks/useVoiceInput';
import { useVoiceMode, setListeningTrigger } from '@/hooks/useVoiceMode';
import { VoiceIndicator } from './VoiceIndicator';
import { VoiceModeToggle } from './VoiceModeToggle';
import { modalityController } from '@/core/ModalityController';
import { useModalityStore } from '@/stores/modalityStore';

interface InputBarProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

export function InputBar({ onSend, disabled = false, placeholder = 'Ask ARIA anything...' }: InputBarProps) {
  const inputValue = useConversationStore((s) => s.inputValue);
  const setInputValue = useConversationStore((s) => s.setInputValue);
  const isStreaming = useConversationStore((s) => s.isStreaming);

  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const canSend = inputValue.trim().length > 0 && !disabled && !isStreaming;

  // Voice mode hook - auto-speak responses, auto-listen after speaking
  const { voiceModeEnabled, toggleVoiceMode } = useVoiceMode();

  // Auto-resize textarea based on content
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  }, [inputValue]);

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

  const handleAudioCall = useCallback(() => {
    modalityController.switchToAudioCall('chat');
  }, []);

  const handleVideoCall = useCallback(() => {
    modalityController.switchTo('avatar', 'chat');
  }, []);

  const tavusStatus = useModalityStore((s) => s.tavusSession.status);
  const hasActiveSession = tavusStatus === 'active' || tavusStatus === 'connecting';

  const { isListening, isSupported, toggleListening, startListening } = useVoiceInput({
    onTranscript: (text) => {
      // In voice mode, send immediately. Otherwise, populate input for editing.
      if (voiceModeEnabled) {
        onSend(text);
      } else {
        setInputValue(text);
        // Focus the textarea so user can edit
        textareaRef.current?.focus();
      }
    },
  });

  // Register the listening trigger for voice mode auto-listen
  useEffect(() => {
    setListeningTrigger(startListening);
    return () => setListeningTrigger(null);
  }, [startListening]);

  // Check if TTS is supported (for voice mode toggle visibility)
  const isTTSSupported = typeof window !== 'undefined' && 'speechSynthesis' in window;

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
          boxShadow: isListening
            ? '0 0 20px rgba(46,102,255,0.15), 0 0 0 1px rgba(46,102,255,0.2)'
            : '0 -8px 40px rgba(46,102,255,0.08), 0 0 0 1px rgba(46,102,255,0.05)',
          transition: 'box-shadow 0.3s ease',
        }}
      >
        <VoiceIndicator
          isListening={isListening}
          isSupported={isSupported}
          onToggle={toggleListening}
        />

        <VoiceModeToggle
          voiceModeEnabled={voiceModeEnabled}
          onToggle={toggleVoiceMode}
          isSupported={isSupported && isTTSSupported}
        />

        <button
          type="button"
          onClick={handleAudioCall}
          disabled={hasActiveSession}
          className="flex-shrink-0 p-2 rounded-lg text-[var(--text-secondary)] transition-colors hover:text-[#2E66FF] hover:bg-[rgba(46,102,255,0.1)] disabled:opacity-30 disabled:cursor-not-allowed"
          aria-label="Call ARIA (audio only)"
          data-aria-id="audio-call-button"
          title={hasActiveSession ? 'Already in a call' : 'Call ARIA'}
        >
          <Phone size={16} />
        </button>

        <button
          type="button"
          onClick={handleVideoCall}
          disabled={hasActiveSession}
          className="flex-shrink-0 p-2 rounded-lg text-[var(--text-secondary)] transition-colors hover:text-[#2E66FF] hover:bg-[rgba(46,102,255,0.1)] disabled:opacity-30 disabled:cursor-not-allowed"
          aria-label="Video call ARIA"
          data-aria-id="video-call-button"
          title={hasActiveSession ? 'Already in a call' : 'Video call'}
        >
          <Video size={16} />
        </button>

        <textarea
          ref={textareaRef}
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={isListening ? 'Listening...' : placeholder}
          rows={1}
          disabled={disabled || isListening}
          className="flex-1 resize-none bg-transparent text-sm text-[var(--text-primary)] placeholder:text-[var(--text-secondary)] outline-none min-h-[36px] max-h-[120px] py-1.5 overflow-y-auto"
          style={{ fontFamily: 'var(--font-sans)' }}
          data-aria-id="message-input"
        />

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
