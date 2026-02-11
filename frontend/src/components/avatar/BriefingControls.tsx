import { useState } from 'react';
import { Play, Pause, SkipBack, SkipForward } from 'lucide-react';
import { useModalityStore } from '@/stores/modalityStore';

interface BriefingControlsProps {
  progress: number;
  isPlaying: boolean;
  onPlayPause: () => void;
  onRewind: () => void;
  onForward: () => void;
}

const SPEED_OPTIONS = [0.75, 1.0, 1.25, 1.5];

export function BriefingControls({
  progress,
  isPlaying,
  onPlayPause,
  onRewind,
  onForward,
}: BriefingControlsProps) {
  const playbackSpeed = useModalityStore((s) => s.playbackSpeed);
  const setPlaybackSpeed = useModalityStore((s) => s.setPlaybackSpeed);
  const captionsEnabled = useModalityStore((s) => s.captionsEnabled);
  const setCaptionsEnabled = useModalityStore((s) => s.setCaptionsEnabled);

  const [speedIndex, setSpeedIndex] = useState(SPEED_OPTIONS.indexOf(playbackSpeed));

  const cycleSpeed = () => {
    const next = (speedIndex + 1) % SPEED_OPTIONS.length;
    setSpeedIndex(next);
    setPlaybackSpeed(SPEED_OPTIONS[next]);
  };

  return (
    <div className="w-full max-w-xs flex flex-col items-center gap-3">
      <div className="w-full h-1 rounded-full bg-[#1A1A2E] overflow-hidden">
        <div
          className="h-full bg-[#2E66FF] rounded-full transition-all duration-300"
          style={{ width: `${progress}%` }}
        />
      </div>

      <div className="flex items-center gap-4">
        <button
          onClick={onRewind}
          className="p-2 text-[#8B8FA3] hover:text-white transition-colors"
          aria-label="Rewind 10 seconds"
        >
          <SkipBack size={18} />
        </button>

        <button
          onClick={onPlayPause}
          className="p-3 rounded-full bg-[#1A1A2E] text-white hover:bg-[#2E66FF] transition-colors"
          aria-label={isPlaying ? 'Pause' : 'Play'}
        >
          {isPlaying ? <Pause size={20} /> : <Play size={20} />}
        </button>

        <button
          onClick={onForward}
          className="p-2 text-[#8B8FA3] hover:text-white transition-colors"
          aria-label="Forward 10 seconds"
        >
          <SkipForward size={18} />
        </button>
      </div>

      <div className="flex items-center gap-4">
        <button
          onClick={() => setCaptionsEnabled(!captionsEnabled)}
          className={`font-mono text-[11px] tracking-wider transition-colors ${captionsEnabled ? 'text-[#F8FAFC]' : 'text-[#555770]'}`}
        >
          CAPTIONS {captionsEnabled ? 'ON' : 'OFF'}
        </button>

        <button
          onClick={cycleSpeed}
          className="font-mono text-[11px] text-[#8B8FA3] hover:text-white transition-colors"
        >
          {playbackSpeed}x
        </button>
      </div>

      <div className="flex items-center gap-2">
        <div className="w-1.5 h-1.5 rounded-full bg-[#2E66FF] animate-pulse" />
        <span className="font-mono text-[11px] text-[#8B8FA3] tracking-wider">
          BRIEFING IN PROGRESS
        </span>
      </div>
    </div>
  );
}
