/**
 * AvatarContainer — Left half of Dialogue Mode.
 *
 * Shows either:
 * - Tavus Daily.co iframe (when session active, room URL available)
 * - Static avatar fallback (aria-avatar.png) with animated border
 *
 * Background: dark radial gradient with subtle blue glow.
 * Renders WaveformBars below the avatar frame.
 */

import { useModalityStore } from '@/stores/modalityStore';
import { WaveformBars } from './WaveformBars';
import ariaAvatarSrc from '@/assets/aria-avatar.png';

export function AvatarContainer() {
  const tavusSession = useModalityStore((s) => s.tavusSession);
  const hasActiveSession = tavusSession.status === 'active' && tavusSession.roomUrl;

  return (
    <div
      className="flex-1 flex flex-col items-center justify-center relative overflow-hidden"
      style={{
        background: 'radial-gradient(circle at center, #0D1117 0%, #0A0A0B 100%)',
      }}
    >
      {/* Subtle blue glow behind avatar */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background: 'radial-gradient(circle at center, rgba(46,102,255,0.08) 0%, transparent 60%)',
        }}
      />

      {/* Avatar frame */}
      <div className="relative z-10 flex flex-col items-center gap-6">
        <div
          className="w-[280px] h-[280px] rounded-full overflow-hidden border-2 border-[#2E66FF]"
          style={{
            boxShadow: '0 0 40px rgba(46,102,255,0.15), 0 0 80px rgba(46,102,255,0.05)',
          }}
        >
          {hasActiveSession ? (
            <iframe
              src={tavusSession.roomUrl!}
              className="w-full h-full border-0"
              allow="camera; microphone; autoplay; display-capture"
              title="ARIA Avatar"
            />
          ) : (
            <img
              src={ariaAvatarSrc}
              alt="ARIA"
              className="w-full h-full object-cover"
            />
          )}
        </div>

        {/* Waveform bars */}
        <WaveformBars />

        {/* Connection status */}
        {tavusSession.status === 'connecting' && (
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
            <span className="font-mono text-[11px] text-[#8B8FA3]">CONNECTING...</span>
          </div>
        )}
      </div>
    </div>
  );
}
