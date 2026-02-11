/**
 * CompactAvatar — Picture-in-picture floating avatar overlay.
 *
 * Renders a 120x120 circular Tavus iframe in the bottom-right corner
 * when the user navigates away from Dialogue Mode while a video session
 * is active. Clicking the circle switches back to full avatar mode.
 * A close button dismisses the PiP without ending the Tavus session.
 *
 * Portaled to document.body at z-50 so it floats above all page content.
 */

import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { useModalityStore } from '@/stores/modalityStore';
import { modalityController } from '@/core/ModalityController';
import { WaveformBars } from './WaveformBars';

export function CompactAvatar() {
  const tavusSession = useModalityStore((s) => s.tavusSession);
  const isPipVisible = useModalityStore((s) => s.isPipVisible);

  if (tavusSession.status !== 'active' || !isPipVisible || !tavusSession.roomUrl) {
    return null;
  }

  return createPortal(
    <div
      className="fixed bottom-6 right-6 z-50 group cursor-pointer"
      onClick={() => modalityController.switchTo('avatar')}
      data-aria-id="compact-avatar"
    >
      {/* Close button — visible on hover */}
      <button
        onClick={(e) => {
          e.stopPropagation();
          modalityController.dismissPip();
        }}
        className="absolute -top-2 -right-2 z-10 w-6 h-6 rounded-full bg-[#0A0A0B] border border-[#1A1A2E] flex items-center justify-center text-[#8B8FA3] hover:text-white opacity-0 group-hover:opacity-100 transition-opacity"
        aria-label="Dismiss avatar"
      >
        <X size={12} />
      </button>

      {/* Avatar circle */}
      <div
        className="w-[120px] h-[120px] rounded-full overflow-hidden border-2 border-[#2E66FF]"
        style={{
          boxShadow: '0 0 20px rgba(46,102,255,0.2), 0 4px 20px rgba(0,0,0,0.5)',
        }}
      >
        <iframe
          src={tavusSession.roomUrl}
          className="w-full h-full border-0"
          allow="camera; microphone; autoplay"
          title="ARIA Avatar (compact)"
        />
      </div>

      {/* Mini waveform indicator */}
      <div className="flex justify-center mt-2">
        <WaveformBars variant="mini" />
      </div>
    </div>,
    document.body,
  );
}
