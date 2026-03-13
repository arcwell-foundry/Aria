/**
 * AvatarContainer — Left half of Dialogue Mode.
 *
 * Shows either:
 * - Tavus video via Daily.js SDK (when session active, room URL available)
 * - Static avatar fallback (aria-avatar.png) with animated border
 *
 * Background: dark radial gradient with subtle blue glow.
 * Renders WaveformBars below the avatar frame.
 */

import { forwardRef } from 'react';
import { useModalityStore } from '@/stores/modalityStore';
import { WaveformBars } from './WaveformBars';
import TavusAvatar, { type TavusAvatarHandle } from './TavusAvatar';
import ariaAvatarSrc from '@/assets/aria-avatar.png';

interface AvatarContainerProps {
  audioOnly?: boolean;
  isConnecting?: boolean;
  onAvatarConnected?: () => void;
  onAvatarDisconnected?: () => void;
  onAvatarError?: (error: string) => void;
}

export const AvatarContainer = forwardRef<TavusAvatarHandle, AvatarContainerProps>(
  ({ audioOnly = false, isConnecting = false, onAvatarConnected, onAvatarDisconnected, onAvatarError }, ref) => {
    const tavusSession = useModalityStore((s) => s.tavusSession);
    const hasActiveSession = !audioOnly && tavusSession.status === 'active' && tavusSession.roomUrl;

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
            className={`w-[280px] h-[280px] rounded-full overflow-hidden border-2 border-[#2E66FF] relative ${
              isConnecting ? 'animate-pulse' : ''
            }`}
            style={{
              boxShadow: isConnecting
                ? '0 0 40px rgba(46,102,255,0.3), 0 0 80px rgba(46,102,255,0.15)'
                : '0 0 40px rgba(46,102,255,0.15), 0 0 80px rgba(46,102,255,0.05)',
            }}
          >
            {hasActiveSession ? (
              <TavusAvatar
                ref={ref}
                conversationUrl={tavusSession.roomUrl!}
                onConnected={onAvatarConnected}
                onDisconnected={onAvatarDisconnected}
                onError={onAvatarError}
              />
            ) : isConnecting ? (
              <div className="absolute inset-0 flex flex-col items-center justify-center bg-[#0D1117]">
                <div className="w-8 h-8 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
                <span className="text-xs text-blue-400 mt-2">Connecting...</span>
              </div>
            ) : (
              <img
                src={ariaAvatarSrc}
                alt="ARIA"
                className="absolute inset-0 w-full h-full object-cover"
              />
            )}
          </div>

          {/* Waveform bars */}
          <WaveformBars />

          {/* Connection status */}
          {(isConnecting || tavusSession.status === 'connecting') && (
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-blue-400 animate-pulse" />
              <span className="font-mono text-[11px] text-blue-400">CONNECTING...</span>
            </div>
          )}
        </div>
      </div>
    );
  },
);

AvatarContainer.displayName = 'AvatarContainer';
