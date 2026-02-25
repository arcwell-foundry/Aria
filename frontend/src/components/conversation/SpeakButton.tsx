/**
 * SpeakButton — Button to have ARIA's message read aloud
 *
 * Shows a speaker/volume icon that toggles speech playback.
 * Visual feedback for speaking/paused states.
 */

import { memo, useCallback } from 'react';
import { Volume2, VolumeX, Play } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

interface SpeakButtonProps {
  text: string;
  isSpeaking: boolean;
  isPaused: boolean;
  onSpeak: (text: string) => void;
  onStop: () => void;
  onResume: () => void;
  isSupported: boolean;
}

export const SpeakButton = memo(function SpeakButton({
  text,
  isSpeaking,
  isPaused,
  onSpeak,
  onStop,
  onResume,
  isSupported,
}: SpeakButtonProps) {
  const handleClick = useCallback(() => {
    if (isSpeaking && !isPaused) {
      onStop();
    } else if (isPaused) {
      onResume();
    } else {
      onSpeak(text);
    }
  }, [text, isSpeaking, isPaused, onSpeak, onStop, onResume]);

  if (!isSupported) return null;

  return (
    <button
      type="button"
      onClick={handleClick}
      className={`
        p-1.5 rounded-md transition-all cursor-pointer
        ${isSpeaking
          ? 'text-accent bg-[var(--accent-muted)]'
          : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)]'
        }
        opacity-0 group-hover:opacity-100 focus:opacity-100
      `}
      aria-label={isSpeaking ? (isPaused ? 'Resume speaking' : 'Stop speaking') : 'Listen to message'}
      title={isSpeaking ? (isPaused ? 'Resume' : 'Stop') : 'Listen'}
    >
      <AnimatePresence mode="wait">
        {isSpeaking && !isPaused ? (
          <motion.div
            key="speaking"
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.8, opacity: 0 }}
            className="flex items-center gap-1"
          >
            <VolumeX size={14} />
            {/* Animated sound waves */}
            <div className="flex items-center gap-[2px] h-3">
              {[0, 1, 2].map((i) => (
                <motion.div
                  key={i}
                  className="w-[2px] bg-accent rounded-full"
                  animate={{
                    height: ['4px', '10px', '4px'],
                  }}
                  transition={{
                    duration: 0.4,
                    repeat: Infinity,
                    delay: i * 0.1,
                  }}
                />
              ))}
            </div>
          </motion.div>
        ) : isPaused ? (
          <motion.div
            key="paused"
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.8, opacity: 0 }}
          >
            <Play size={14} />
          </motion.div>
        ) : (
          <motion.div
            key="idle"
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.8, opacity: 0 }}
          >
            <Volume2 size={14} />
          </motion.div>
        )}
      </AnimatePresence>
    </button>
  );
});
