/**
 * TavusAvatar — Headless Daily.js video renderer for ARIA's Tavus CVI.
 *
 * Replaces the raw Daily.co iframe to eliminate all native UI chrome
 * (participant labels, mute buttons, permission prompts). Renders only
 * ARIA's video track in a plain <video> element.
 *
 * - audioSource: true  → user's mic (for speaking to ARIA)
 * - videoSource: false → never request camera permission
 */

import { useEffect, useRef, useState, forwardRef, useImperativeHandle } from 'react';
import type { DailyCall } from '@daily-co/daily-js';
import { useModalityStore } from '@/stores/modalityStore';

export interface TavusAvatarHandle {
  endCall: () => Promise<void>;
}

interface TavusAvatarProps {
  conversationUrl: string;
  onConnected?: () => void;
  onDisconnected?: () => void;
  onError?: (error: string) => void;
}

const TavusAvatar = forwardRef<TavusAvatarHandle, TavusAvatarProps>(
  ({ conversationUrl, onConnected, onDisconnected, onError }, ref) => {
    const videoRef = useRef<HTMLVideoElement>(null);
    const callRef = useRef<DailyCall | null>(null);
    const [connecting, setConnecting] = useState(true);
    const setTavusVideoTrack = useModalityStore((s) => s.setTavusVideoTrack);

    useImperativeHandle(ref, () => ({
      endCall: async () => {
        if (callRef.current) {
          try {
            await callRef.current.leave();
            callRef.current.destroy();
          } catch {
            // Already left or destroyed
          }
          callRef.current = null;
        }
        if (videoRef.current) {
          videoRef.current.srcObject = null;
        }
        setTavusVideoTrack(null);
        onDisconnected?.();
      },
    }));

    useEffect(() => {
      let call: DailyCall | null = null;
      let cancelled = false;

      const attachVideoTrack = (track: MediaStreamTrack) => {
        if (cancelled || !videoRef.current) return;
        if (videoRef.current.srcObject) return; // already attached
        console.log('[TavusAvatar] Attaching remote video track');
        const stream = new MediaStream([track]);
        videoRef.current.srcObject = stream;
        videoRef.current.play().catch(console.error);
        setTavusVideoTrack(track);
        setConnecting(false);
        onConnected?.();
      };

      const start = async () => {
        try {
          const Daily = (await import('@daily-co/daily-js')).default;
          call = Daily.createCallObject({
            audioSource: true,
            videoSource: false,
          });
          callRef.current = call;

          console.log('[TavusAvatar] Joining Daily room:', conversationUrl);

          // Attach ARIA's remote video track to our <video> element
          call.on('track-started', (event) => {
            if (cancelled) return;
            console.log('[TavusAvatar] track-started:', event.type, 'local:', event.participant?.local);
            if (!event.participant?.local && event.type === 'video') {
              attachVideoTrack(event.track);
            }
          });

          // Also attach remote audio tracks so we hear ARIA
          call.on('track-started', (event) => {
            if (cancelled) return;
            if (!event.participant?.local && event.type === 'audio') {
              const audio = new Audio();
              audio.srcObject = new MediaStream([event.track]);
              audio.play().catch(console.error);
            }
          });

          // Fallback: if track-started fires before our listener is ready,
          // participant-updated will catch the track once it appears
          call.on('participant-updated', (event) => {
            if (cancelled) return;
            if (event.participant.local) return;
            const videoTrack = event.participant.tracks?.video?.persistentTrack;
            if (videoTrack && videoRef.current && !videoRef.current.srcObject) {
              console.log('[TavusAvatar] participant-updated: found video persistentTrack');
              attachVideoTrack(videoTrack);
            }
          });

          call.on('left-meeting', () => {
            if (!cancelled) onDisconnected?.();
          });

          call.on('error', (e) => {
            if (cancelled) return;
            console.error('Daily call error:', e);
            const msg = e?.errorMsg || 'Connection error';
            if (msg.includes('mic') || msg.includes('audio') || msg.includes('NotAllowedError')) {
              onError?.('Microphone unavailable — you can listen but not speak');
            } else {
              onError?.(msg);
            }
            setConnecting(false);
          });

          await call.join({ url: conversationUrl });
          console.log('[TavusAvatar] Joined Daily room successfully');

          // Post-join fallback: check if remote participants already have tracks
          // (handles case where avatar was streaming before we joined)
          if (!cancelled && call) {
            const participants = call.participants();
            for (const [id, p] of Object.entries(participants)) {
              if (id === 'local') continue;
              const videoTrack = p.tracks?.video?.persistentTrack;
              if (videoTrack && videoRef.current && !videoRef.current.srcObject) {
                console.log('[TavusAvatar] Post-join: found existing video track from', id);
                attachVideoTrack(videoTrack);
                break;
              }
            }
          }
        } catch (err: unknown) {
          if (cancelled) return;
          const message = err instanceof Error ? err.message : 'Failed to connect';
          console.error('Failed to join Daily call:', err);
          onError?.(message);
          setConnecting(false);
        }
      };

      start();

      return () => {
        cancelled = true;
        setTavusVideoTrack(null);
        if (call) {
          call.leave().catch(console.error);
          call.destroy();
        }
      };
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [conversationUrl]);

    return (
      <div className="w-full h-full relative">
        {connecting && (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-[#0D1117] z-[1]">
            <div className="w-8 h-8 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
            <span className="text-xs text-blue-400 mt-2">Connecting...</span>
          </div>
        )}
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted={false}
          className="w-full h-full object-cover"
          style={{ display: connecting ? 'none' : 'block' }}
        />
      </div>
    );
  },
);

TavusAvatar.displayName = 'TavusAvatar';
export default TavusAvatar;
