/**
 * TavusAvatar — Headless Daily.js video renderer for ARIA's Tavus CVI.
 *
 * Replaces the raw Daily.co iframe to eliminate all native UI chrome
 * (participant labels, mute buttons, permission prompts). Renders only
 * ARIA's video track in a plain <video> element.
 *
 * - audioSource: true → must join with audio so Tavus detects a participant
 *   (muted via updateParticipant after join — briefing is one-way delivery)
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
    const audioElRef = useRef<HTMLAudioElement | null>(null);
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
        audioElRef.current?.remove();
        audioElRef.current = null;
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

          // Attach remote audio track to a DOM element so the browser plays it
          call.on('track-started', (event) => {
            if (cancelled) return;
            if (!event.participant?.local && event.type === 'audio') {
              console.log('[TavusAvatar] Attaching remote audio track');
              const audioEl = document.createElement('audio');
              audioEl.autoplay = true;
              audioEl.srcObject = new MediaStream([event.track]);
              audioEl.style.display = 'none';
              document.body.appendChild(audioEl);
              audioElRef.current = audioEl;
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

          call.on('left-meeting', (e) => {
            console.log('[TavusAvatar] left-meeting:', e);
            if (!cancelled) onDisconnected?.();
          });

          call.on('error', (e) => {
            if (cancelled) return;
            console.error('[TavusAvatar] Daily error:', e);
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

          // Mute local audio without disrupting WebRTC negotiation.
          // setLocalAudio(false) blocks remote track delivery, so use
          // updateParticipant instead which mutes at the track level.
          try {
            call.updateParticipant('local', { setAudio: false });
            console.log('[TavusAvatar] Local audio muted via updateParticipant');
          } catch (muteErr) {
            console.warn('[TavusAvatar] Could not mute local audio:', muteErr);
          }

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
        audioElRef.current?.remove();
        audioElRef.current = null;
        if (call) {
          call.leave().catch(console.error);
          call.destroy();
        }
      };
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [conversationUrl]);

    return (
      <div className="absolute inset-0 w-full h-full">
        {connecting && (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-[#0D1117] z-[2]">
            <div className="w-8 h-8 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
            <span className="text-xs text-blue-400 mt-2">Connecting...</span>
          </div>
        )}
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted={false}
          className="absolute inset-0 w-full h-full object-cover z-[1]"
        />
      </div>
    );
  },
);

TavusAvatar.displayName = 'TavusAvatar';
export default TavusAvatar;
