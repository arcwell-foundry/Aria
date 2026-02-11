/**
 * WaveformBars — Animated vertical bars that respond to ARIA's speech.
 *
 * Variants:
 * - 'default': 12 bars, used in AvatarContainer
 * - 'mini': 6 bars, used in CompactAvatar PiP
 */

import { useModalityStore } from '@/stores/modalityStore';

interface WaveformBarsProps {
  variant?: 'default' | 'mini';
}

export function WaveformBars({ variant = 'default' }: WaveformBarsProps) {
  const isSpeaking = useModalityStore((s) => s.isSpeaking);

  const barCount = variant === 'mini' ? 6 : 12;
  const barHeight = variant === 'mini' ? 20 : 40;
  const barWidth = variant === 'mini' ? 2 : 3;
  const gap = variant === 'mini' ? 4 : 8;

  return (
    <div
      className="flex items-end justify-center"
      style={{ gap: `${gap}px`, height: `${barHeight}px` }}
    >
      {Array.from({ length: barCount }).map((_, i) => (
        <div
          key={i}
          className="rounded-full transition-opacity duration-300"
          style={{
            width: `${barWidth}px`,
            height: '100%',
            backgroundColor: '#2E66FF',
            opacity: isSpeaking ? 1 : 0.3,
            animation: isSpeaking
              ? `waveform 1.2s ease-in-out ${i * 0.1}s infinite`
              : 'none',
            transform: isSpeaking ? undefined : 'scaleY(0.3)',
          }}
        />
      ))}
    </div>
  );
}
