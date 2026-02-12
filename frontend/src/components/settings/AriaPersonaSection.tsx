/**
 * AriaPersonaSection - ARIA persona and communication preferences
 */

import { Bot, Clock, MessageSquare } from 'lucide-react';
import { cn } from '@/utils/cn';
import type { DefaultTone } from '@/api/preferences';

const TONE_OPTIONS: { value: DefaultTone; label: string; description: string }[] = [
  { value: 'formal', label: 'Professional', description: 'Structured and precise communication' },
  { value: 'friendly', label: 'Conversational', description: 'Warm and approachable tone' },
  { value: 'urgent', label: 'Direct', description: 'Concise and action-oriented' },
];

const BRIEFING_TIMES = [
  { value: '07:00', label: '7:00 AM' },
  { value: '08:00', label: '8:00 AM' },
  { value: '09:00', label: '9:00 AM' },
];

export function AriaPersonaSection() {
  return (
    <div
      className="border rounded-lg p-6"
      style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)' }}
    >
      <div className="flex items-center gap-2 mb-6">
        <Bot className="w-4 h-4" style={{ color: 'var(--text-secondary)' }} />
        <h3
          className="font-medium"
          style={{ color: 'var(--text-primary)' }}
        >
          ARIA Persona
        </h3>
      </div>

      <div className="space-y-6">
        {/* Name preference */}
        <div>
          <label
            className="block text-sm font-medium mb-1.5"
            style={{ color: 'var(--text-primary)' }}
          >
            How should ARIA address you?
          </label>
          <input
            type="text"
            placeholder="Your preferred name"
            className={cn(
              'w-full px-3 py-2 rounded-lg border text-sm',
              'border-[var(--border)] bg-[var(--bg-subtle)]',
              'focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/30'
            )}
            style={{ color: 'var(--text-primary)' }}
          />
        </div>

        {/* Communication style */}
        <div>
          <label
            className="block text-sm font-medium mb-3"
            style={{ color: 'var(--text-primary)' }}
          >
            <MessageSquare className="w-4 h-4 inline-block mr-2" />
            Communication Style
          </label>
          <div className="space-y-2">
            {TONE_OPTIONS.map((option) => (
              <label
                key={option.value}
                className="flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors hover:border-[var(--accent)]/50"
                style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
              >
                <input
                  type="radio"
                  name="tone"
                  value={option.value}
                  className="mt-1"
                />
                <div>
                  <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                    {option.label}
                  </p>
                  <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                    {option.description}
                  </p>
                </div>
              </label>
            ))}
          </div>
        </div>

        {/* Briefing time */}
        <div>
          <label
            className="block text-sm font-medium mb-1.5"
            style={{ color: 'var(--text-primary)' }}
          >
            <Clock className="w-4 h-4 inline-block mr-2" />
            Daily Briefing Time
          </label>
          <select
            className={cn(
              'w-full px-3 py-2 rounded-lg border text-sm',
              'border-[var(--border)] bg-[var(--bg-subtle)]',
              'focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/30'
            )}
            style={{ color: 'var(--text-primary)' }}
          >
            {BRIEFING_TIMES.map((time) => (
              <option key={time.value} value={time.value}>
                {time.label}
              </option>
            ))}
          </select>
          <p className="text-xs mt-1.5" style={{ color: 'var(--text-secondary)' }}>
            ARIA will prepare your daily briefing at this time.
          </p>
        </div>
      </div>
    </div>
  );
}
