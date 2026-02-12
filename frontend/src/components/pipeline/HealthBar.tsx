/**
 * HealthBar - Lead health score indicator
 *
 * Follows ARIA Design System v1.0:
 * - Uses CSS variables for theming
 * - Color coding: green >= 70, amber 40-70, red < 40
 * - Shows progress bar with optional percentage label
 *
 * @example
 * <HealthBar score={85} />
 * <HealthBar score={35} showLabel={false} size="sm" />
 */

import { cn } from '../../utils/cn';

export interface HealthBarProps {
  /** Health score (0-100) */
  score: number;
  /** Show percentage label */
  showLabel?: boolean;
  /** Size variant */
  size?: 'sm' | 'md';
  /** Additional CSS classes */
  className?: string;
}

type HealthLevel = 'green' | 'amber' | 'red';

function getHealthLevel(score: number): HealthLevel {
  if (score >= 70) return 'green';
  if (score >= 40) return 'amber';
  return 'red';
}

const healthColors: Record<HealthLevel, { bg: string; bar: string }> = {
  green: {
    bg: 'rgba(107, 143, 113, 0.15)',
    bar: 'var(--success)',
  },
  amber: {
    bg: 'rgba(184, 149, 106, 0.15)',
    bar: 'var(--warning)',
  },
  red: {
    bg: 'rgba(166, 107, 107, 0.15)',
    bar: 'var(--critical)',
  },
};

const sizeStyles = {
  sm: {
    container: 'h-1.5',
    label: 'text-xs',
  },
  md: {
    container: 'h-2.5',
    label: 'text-sm',
  },
};

export function HealthBar({
  score,
  showLabel = true,
  size = 'md',
  className = '',
}: HealthBarProps) {
  const clampedScore = Math.min(100, Math.max(0, score));
  const level = getHealthLevel(clampedScore);
  const colors = healthColors[level];

  return (
    <div className={cn('inline-flex items-center gap-2', className)}>
      {/* Progress Bar Container */}
      <div
        className={cn(
          'w-20 rounded-full overflow-hidden',
          sizeStyles[size].container
        )}
        style={{ backgroundColor: colors.bg }}
        role="progressbar"
        aria-valuenow={clampedScore}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`Health score: ${clampedScore}%`}
      >
        <div
          className="h-full rounded-full transition-all duration-300 ease-out"
          style={{
            width: `${clampedScore}%`,
            backgroundColor: colors.bar,
          }}
        />
      </div>

      {/* Percentage Label */}
      {showLabel && (
        <span
          className={cn('font-medium', sizeStyles[size].label)}
          style={{ color: colors.bar }}
        >
          {clampedScore}%
        </span>
      )}
    </div>
  );
}
