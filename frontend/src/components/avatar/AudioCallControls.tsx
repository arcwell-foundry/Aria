/**
 * AudioCallControls — Call controls bar for audio-only sessions.
 *
 * Shows: mute/unmute toggle, end call button, elapsed time.
 * Rendered at the bottom of DialogueMode in audio-only layout.
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { Mic, MicOff, PhoneOff } from 'lucide-react';
import { modalityController } from '@/core/ModalityController';

interface AudioCallControlsProps {
  startedAt?: string | null;
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

export function AudioCallControls({ startedAt }: AudioCallControlsProps) {
  const [isMuted, setIsMuted] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const start = startedAt ? new Date(startedAt).getTime() : Date.now();
    const tick = () => setElapsed(Math.floor((Date.now() - start) / 1000));
    tick();
    intervalRef.current = setInterval(tick, 1000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [startedAt]);

  const handleMuteToggle = useCallback(() => {
    setIsMuted((prev) => !prev);
    // Daily.co mute/unmute would be handled by the iframe's own audio track.
    // For audio-only Tavus sessions, the Daily room handles mic state internally.
  }, []);

  const handleEndCall = useCallback(() => {
    modalityController.endSession();
  }, []);

  return (
    <div
      className="flex items-center justify-center gap-6 py-4 px-6"
      data-aria-id="audio-call-controls"
    >
      {/* Duration */}
      <span className="font-mono text-xs text-[#8B8FA3] min-w-[48px] text-center">
        {formatDuration(elapsed)}
      </span>

      {/* Mute toggle */}
      <button
        onClick={handleMuteToggle}
        className={`p-3 rounded-full transition-colors ${
          isMuted
            ? 'bg-red-500/20 text-red-400 hover:bg-red-500/30'
            : 'bg-[#1A1A2E] text-[#8B8FA3] hover:bg-[#252540] hover:text-white'
        }`}
        aria-label={isMuted ? 'Unmute microphone' : 'Mute microphone'}
      >
        {isMuted ? <MicOff size={20} /> : <Mic size={20} />}
      </button>

      {/* End call */}
      <button
        onClick={handleEndCall}
        className="p-3 rounded-full bg-red-500 text-white hover:bg-red-600 transition-colors"
        aria-label="End call"
      >
        <PhoneOff size={20} />
      </button>
    </div>
  );
}
