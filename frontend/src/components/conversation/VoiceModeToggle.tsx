/**
 * VoiceModeToggle — Toggle for continuous voice conversation mode
 *
 * When enabled:
 * - ARIA's responses are spoken automatically
 * - Listening auto-starts after ARIA finishes speaking
 * - Creates a hands-free conversation experience
 */

import { memo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Headphones, HeadphoneOff } from 'lucide-react';

interface VoiceModeToggleProps {
  voiceModeEnabled: boolean;
  onToggle: () => void;
  isSupported: boolean;
}

export const VoiceModeToggle = memo(function VoiceModeToggle({
  voiceModeEnabled,
  onToggle,
  isSupported,
}: VoiceModeToggleProps) {
  if (!isSupported) return null;

  return (
    <button
      type="button"
      onClick={onToggle}
      className={`
        relative flex items-center gap-1.5 px-2 py-1.5 rounded-lg
        text-[10px] font-mono uppercase tracking-wider
        transition-all cursor-pointer
        ${voiceModeEnabled
          ? 'text-accent bg-[var(--accent-muted)]'
          : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)]'
        }
      `}
      aria-label={voiceModeEnabled ? 'Disable voice mode' : 'Enable voice mode'}
      title={voiceModeEnabled ? 'Voice mode on - click to disable' : 'Voice mode - continuous voice conversation'}
      data-aria-id="voice-mode-toggle"
    >
      <AnimatePresence mode="wait">
        {voiceModeEnabled ? (
          <motion.div
            key="on"
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.8, opacity: 0 }}
            className="flex items-center gap-1.5"
          >
            <Headphones size={12} />
            <span>Voice Mode</span>
            {/* Pulsing indicator */}
            <motion.div
              className="w-1.5 h-1.5 rounded-full bg-accent"
              animate={{
                opacity: [1, 0.4, 1],
                scale: [1, 1.2, 1],
              }}
              transition={{
                duration: 1.5,
                repeat: Infinity,
                ease: 'easeInOut',
              }}
            />
          </motion.div>
        ) : (
          <motion.div
            key="off"
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.8, opacity: 0 }}
            className="flex items-center gap-1.5"
          >
            <HeadphoneOff size={12} />
            <span className="hidden sm:inline">Voice</span>
          </motion.div>
        )}
      </AnimatePresence>
    </button>
  );
});
