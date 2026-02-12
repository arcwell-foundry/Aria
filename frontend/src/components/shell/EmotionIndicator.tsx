/**
 * EmotionIndicator — Subtle perception readout in ARIA workspace
 *
 * Shows the current detected emotion as a minimal text indicator.
 * Designed to be noticed by observant investors without cluttering the UI.
 */

import { motion, AnimatePresence } from 'framer-motion';
import { usePerceptionStore } from '@/stores/perceptionStore';

const EMOTION_LABELS: Record<string, string> = {
  neutral: 'Neutral',
  engaged: 'Engaged',
  frustrated: 'Needs attention',
  confused: 'Processing',
  excited: 'Energized',
  distracted: 'Distracted',
  focused: 'Deep focus',
};

const ENGAGEMENT_COLORS: Record<string, string> = {
  high: 'var(--success)',
  medium: 'var(--accent)',
  low: 'var(--warning)',
  unknown: 'var(--text-secondary)',
};

export function EmotionIndicator() {
  const currentEmotion = usePerceptionStore((s) => s.currentEmotion);
  const engagementLevel = usePerceptionStore((s) => s.engagementLevel);

  if (!currentEmotion) return null;

  const label = EMOTION_LABELS[currentEmotion.emotion] ?? currentEmotion.emotion;
  const color = ENGAGEMENT_COLORS[engagementLevel];

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: -4 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -4 }}
        transition={{ duration: 0.3 }}
        className="flex items-center gap-1.5"
        data-aria-id="emotion-indicator"
      >
        <div
          className="w-1.5 h-1.5 rounded-full"
          style={{ backgroundColor: color }}
        />
        <span
          className="font-mono text-[9px] tracking-widest uppercase select-none"
          style={{ color }}
        >
          {label}
        </span>
        {currentEmotion.confidence > 0.8 && (
          <span className="font-mono text-[8px] text-[var(--text-secondary)] opacity-40">
            {Math.round(currentEmotion.confidence * 100)}%
          </span>
        )}
      </motion.div>
    </AnimatePresence>
  );
}
