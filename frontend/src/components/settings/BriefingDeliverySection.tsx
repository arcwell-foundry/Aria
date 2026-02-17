/**
 * BriefingDeliverySection - Settings for video briefing preferences
 *
 * Part of ARIA Persona settings. Controls how ARIA delivers briefings.
 */

import { Video, FileText } from 'lucide-react';
import { cn } from '@/utils/cn';
import type { BriefingMode, BriefingDuration } from '@/api/preferences';

interface BriefingDeliverySectionProps {
  briefingMode: BriefingMode;
  briefingTime: string;
  briefingDuration: BriefingDuration;
  timezone: string;
  onChange: (field: string, value: string | number) => void;
}

const BRIEFING_TIMES = [
  { value: '06:00', label: '6:00 AM' },
  { value: '07:00', label: '7:00 AM' },
  { value: '08:00', label: '8:00 AM' },
  { value: '09:00', label: '9:00 AM' },
  { value: '10:00', label: '10:00 AM' },
];

const DURATION_OPTIONS: { value: BriefingDuration; label: string; description: string }[] = [
  { value: 2, label: 'Quick', description: '2 min' },
  { value: 5, label: 'Standard', description: '5 min' },
  { value: 10, label: 'Deep', description: '10 min' },
];

// Map timezone to abbreviation
function getTimezoneAbbr(timezone: string): string {
  try {
    const formatter = new Intl.DateTimeFormat('en-US', {
      timeZone: timezone,
      timeZoneName: 'short',
    });
    const parts = formatter.formatToParts(new Date());
    const tzPart = parts.find((p) => p.type === 'timeZoneName');
    return tzPart?.value || timezone;
  } catch {
    return timezone;
  }
}

export function BriefingDeliverySection({
  briefingMode,
  briefingTime,
  briefingDuration,
  timezone,
  onChange,
}: BriefingDeliverySectionProps) {
  const tzAbbr = getTimezoneAbbr(timezone);

  return (
    <div
      className="mt-6 pt-6 border-t"
      style={{ borderColor: 'var(--border)' }}
    >
      <h4
        className="text-sm font-medium mb-4"
        style={{ color: 'var(--text-primary)' }}
      >
        Briefing Delivery
      </h4>

      <div className="space-y-5">
        {/* Video vs Text toggle */}
        <div>
          <label
            className="flex items-center justify-between cursor-pointer"
          >
            <div className="flex items-center gap-2">
              {briefingMode === 'video' ? (
                <Video className="w-4 h-4" style={{ color: 'var(--accent)' }} />
              ) : (
                <FileText className="w-4 h-4" style={{ color: 'var(--text-secondary)' }} />
              )}
              <span className="text-sm" style={{ color: 'var(--text-primary)' }}>
                Receive briefings as video
              </span>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={briefingMode === 'video'}
              onClick={() => onChange('briefing_mode', briefingMode === 'video' ? 'text' : 'video')}
              className={cn(
                'relative inline-flex h-5 w-9 items-center rounded-full transition-colors',
                briefingMode === 'video' ? 'bg-[var(--accent)]' : 'bg-[var(--border)]'
              )}
            >
              <span
                className={cn(
                  'inline-block h-4 w-4 transform rounded-full bg-white transition-transform',
                  briefingMode === 'video' ? 'translate-x-4' : 'translate-x-0.5'
                )}
              />
            </button>
          </label>
          <p className="text-xs mt-1 ml-6" style={{ color: 'var(--text-secondary)' }}>
            {briefingMode === 'video'
              ? 'ARIA will deliver briefings via video avatar'
              : 'ARIA will deliver briefings as text in chat'}
          </p>
        </div>

        {/* Preferred briefing time */}
        <div>
          <label
            className="block text-sm font-medium mb-1.5"
            style={{ color: 'var(--text-primary)' }}
          >
            Preferred briefing time
          </label>
          <select
            value={briefingTime}
            onChange={(e) => onChange('briefing_time', e.target.value)}
            className={cn(
              'w-full px-3 py-2 rounded-lg border text-sm',
              'border-[var(--border)] bg-[var(--bg-subtle)]',
              'focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/30'
            )}
            style={{ color: 'var(--text-primary)' }}
          >
            {BRIEFING_TIMES.map((time) => (
              <option key={time.value} value={time.value}>
                {time.label} {tzAbbr}
              </option>
            ))}
          </select>
        </div>

        {/* Briefing duration */}
        <div>
          <label
            className="block text-sm font-medium mb-2"
            style={{ color: 'var(--text-primary)' }}
          >
            Briefing duration
          </label>
          <div className="flex gap-2">
            {DURATION_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => onChange('briefing_duration', option.value)}
                className={cn(
                  'flex-1 py-2 px-3 rounded-lg border text-sm transition-colors',
                  briefingDuration === option.value
                    ? 'border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent)]'
                    : 'border-[var(--border)] bg-[var(--bg-subtle)] text-[var(--text-primary)] hover:border-[var(--accent)]/50'
                )}
              >
                <div className="font-medium">{option.label}</div>
                <div className="text-xs opacity-70">{option.description}</div>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
