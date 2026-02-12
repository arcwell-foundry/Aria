/**
 * PerceptionSection - Perception and emotion detection settings
 */

import { Eye, Video, Info } from 'lucide-react';

export function PerceptionSection() {
  return (
    <div
      className="border rounded-lg p-6"
      style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)' }}
    >
      <div className="flex items-center gap-2 mb-6">
        <Eye className="w-4 h-4" style={{ color: 'var(--text-secondary)' }} />
        <h3
          className="font-medium"
          style={{ color: 'var(--text-primary)' }}
        >
          Perception
        </h3>
      </div>

      <div className="space-y-6">
        {/* Webcam opt-in */}
        <div
          className="flex items-start justify-between gap-4 p-4 rounded-lg border"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
        >
          <div className="flex items-start gap-3">
            <Video
              className="w-5 h-5 mt-0.5"
              style={{ color: 'var(--text-secondary)' }}
            />
            <div>
              <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                Emotion Detection
              </p>
              <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
                Allow ARIA to read your facial expressions during Dialogue Mode using Raven-0. This helps ARIA adapt responses to your engagement level.
              </p>
            </div>
          </div>

          <label className="relative inline-flex items-center cursor-pointer flex-shrink-0">
            <input type="checkbox" className="sr-only peer" />
            <div
              className="w-11 h-6 rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:rounded-full after:h-5 after:w-5 after:transition-all"
              style={{
                backgroundColor: 'var(--border)',
              }}
            >
              <div
                className="absolute top-[2px] left-[2px] w-5 h-5 rounded-full transition-transform"
                style={{
                  backgroundColor: 'white',
                }}
              />
            </div>
          </label>
        </div>

        {/* Info notice */}
        <div
          className="flex items-start gap-2 p-3 rounded-lg"
          style={{ backgroundColor: 'var(--bg-subtle)' }}
        >
          <Info
            className="w-4 h-4 mt-0.5 flex-shrink-0"
            style={{ color: 'var(--text-secondary)' }}
          />
          <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            Video data is processed locally and never stored. Emotion detection is optional and can be disabled at any time.
          </p>
        </div>
      </div>
    </div>
  );
}
