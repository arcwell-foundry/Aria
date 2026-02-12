/**
 * VoiceIndicator — Shows listening state in the input bar.
 *
 * Idle: mic icon + "SPACE TO TALK" label
 * Listening: pulsing mic + waveform bars + "LISTENING..." label
 */

import { motion, AnimatePresence } from 'framer-motion';
import { Mic } from 'lucide-react';

interface VoiceIndicatorProps {
  isListening: boolean;
  isSupported: boolean;
  onToggle: () => void;
}

export function VoiceIndicator({ isListening, isSupported, onToggle }: VoiceIndicatorProps) {
  if (!isSupported) return null;

  return (
    <div className="flex items-center gap-2" data-aria-id="voice-indicator">
      <button
        type="button"
        onClick={onToggle}
        className={`
          flex-shrink-0 p-2 rounded-lg transition-all
          ${isListening
            ? 'text-accent bg-[var(--accent-muted)] shadow-[0_0_12px_rgba(46,102,255,0.3)]'
            : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)]'
          }
        `}
        aria-label={isListening ? 'Stop listening' : 'Start voice input'}
      >
        <Mic size={18} />
      </button>

      <AnimatePresence mode="wait">
        {isListening ? (
          <motion.div
            key="listening"
            initial={{ opacity: 0, width: 0 }}
            animate={{ opacity: 1, width: 'auto' }}
            exit={{ opacity: 0, width: 0 }}
            className="flex items-center gap-2 overflow-hidden"
          >
            <div className="flex items-center gap-[2px] h-4">
              {[0, 1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="w-[3px] bg-accent rounded-full"
                  style={{
                    animation: `waveform 0.6s ease-in-out ${i * 0.1}s infinite`,
                    height: '100%',
                  }}
                />
              ))}
            </div>

            <span className="font-mono text-[9px] tracking-widest uppercase text-accent whitespace-nowrap select-none">
              Listening...
            </span>
          </motion.div>
        ) : (
          <motion.span
            key="idle"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="hidden sm:block font-mono text-[9px] tracking-widest uppercase text-[var(--text-secondary)] opacity-50 select-none whitespace-nowrap"
          >
            Space to talk
          </motion.span>
        )}
      </AnimatePresence>
    </div>
  );
}
