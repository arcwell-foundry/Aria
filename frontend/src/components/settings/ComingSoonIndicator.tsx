/**
 * ComingSoonIndicator - Reusable component for features not yet available
 *
 * Used in Settings page to show planned features with disabled state.
 */

import { Lock } from 'lucide-react';

export interface ComingSoonIndicatorProps {
  title: string;
  description: string;
  availableDate: string;
}

export function ComingSoonIndicator({
  title,
  description,
  availableDate,
}: ComingSoonIndicatorProps) {
  return (
    <div
      className="border border-dashed rounded-lg p-4 opacity-60"
      style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
    >
      <div className="flex items-start gap-3">
        <Lock
          className="w-4 h-4 mt-0.5 flex-shrink-0"
          style={{ color: 'var(--text-secondary)' }}
        />
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span
              className="font-medium text-sm"
              style={{ color: 'var(--text-primary)' }}
            >
              {title}
            </span>
            <span
              className="px-1.5 py-0.5 rounded text-xs font-medium"
              style={{
                backgroundColor: 'var(--bg-elevated)',
                color: 'var(--text-secondary)',
              }}
            >
              Coming {availableDate}
            </span>
          </div>
          <p
            className="text-xs"
            style={{ color: 'var(--text-secondary)' }}
          >
            {description}
          </p>
        </div>
      </div>
    </div>
  );
}
