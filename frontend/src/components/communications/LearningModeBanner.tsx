/**
 * LearningModeBanner - Shows learning mode status during first week
 *
 * Displays a subtle informational banner when ARIA is still learning
 * the user's writing style (first 7 days after email connection).
 * Renders nothing once learning mode has graduated.
 */

import { Sparkles } from 'lucide-react';
import { useEmailIntelligenceSettings } from '@/hooks/useEmailIntelligenceSettings';

export function LearningModeBanner() {
  const { data: settings } = useEmailIntelligenceSettings();

  if (!settings?.learning_mode_active || !settings.learning_mode_day) {
    return null;
  }

  const day = settings.learning_mode_day;
  const daysRemaining = 7 - day;
  const graduationDate = new Date();
  graduationDate.setDate(graduationDate.getDate() + daysRemaining);
  const formattedDate = graduationDate.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
  });

  return (
    <div
      className="rounded-lg p-4 mb-6 flex items-start gap-3"
      style={{
        backgroundColor: 'var(--bg-subtle)',
        borderLeftColor: 'var(--accent-muted)',
        borderLeftWidth: '3px',
        borderLeftStyle: 'solid',
      }}
    >
      <Sparkles
        className="w-5 h-5 flex-shrink-0 mt-0.5"
        style={{ color: 'var(--accent)' }}
      />
      <div>
        <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
          ARIA is learning your writing style (Day {day} of 7)
        </p>
        <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
          Drafting for all contacts. Confidence will improve as ARIA learns your style through {formattedDate}.
        </p>
      </div>
    </div>
  );
}
