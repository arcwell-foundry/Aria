/**
 * BattleCardPreview - Preview card for competitor battle cards
 *
 * Follows ARIA Design System v1.0:
 * - Uses CSS variables for theming
 * - Win rate color coding: green >60%, amber 40-60%, red <40%
 * - Market cap gap: green if negative (competitor smaller), red if positive (competitor larger)
 * - Click navigates to battle card detail
 * - data-aria-id for UICommandExecutor targeting
 *
 * @example
 * <BattleCardPreview
 *   card={battleCard}
 *   onClick={() => navigate(`/intelligence/battle-cards/${card.competitor_name}`)}
 * />
 */

import { useNavigate } from 'react-router-dom';
import { TrendingUp, TrendingDown, Minus, Clock } from 'lucide-react';
import { cn } from '@/utils/cn';
import type { BattleCard } from '@/api/battleCards';

export interface BattleCardPreviewProps {
  /** Battle card data */
  card: BattleCard;
  /** Optional market cap gap percentage (mock data for now) */
  marketCapGap?: number;
  /** Optional win rate percentage (mock data for now) */
  winRate?: number;
  /** Optional last signal timestamp (mock data for now) */
  lastSignalAt?: string | null;
  /** Additional CSS classes */
  className?: string;
}

// Get win rate color based on percentage
function getWinRateColor(winRate: number): string {
  if (winRate > 60) return 'var(--success)';
  if (winRate >= 40) return 'var(--warning)';
  return 'var(--error)';
}

// Get market cap gap color and icon
function getMarketCapGapStyle(gap: number): { color: string; icon: typeof TrendingUp } {
  // Negative gap means competitor is smaller (good for us)
  if (gap < 0) {
    return { color: 'var(--success)', icon: TrendingDown };
  }
  // Positive gap means competitor is larger
  if (gap > 0) {
    return { color: 'var(--error)', icon: TrendingUp };
  }
  // Equal size
  return { color: 'var(--text-secondary)', icon: Minus };
}

// Format relative time for last signal
function formatLastSignal(dateStr: string | null): string {
  if (!dateStr) return 'No signals';

  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays} days ago`;
  if (diffDays < 30) {
    const weeks = Math.floor(diffDays / 7);
    return `${weeks} ${weeks === 1 ? 'week' : 'weeks'} ago`;
  }
  if (diffDays < 365) {
    const months = Math.floor(diffDays / 30);
    return `${months} ${months === 1 ? 'month' : 'months'} ago`;
  }
  const years = Math.floor(diffDays / 365);
  return `${years} ${years === 1 ? 'year' : 'years'} ago`;
}

// Format market cap gap as string
function formatMarketCapGap(gap: number): string {
  const sign = gap > 0 ? '+' : '';
  return `${sign}${gap.toFixed(1)}%`;
}

// Skeleton for loading state
export function BattleCardPreviewSkeleton() {
  return (
    <div
      className={cn(
        'rounded-xl p-5 border border-[var(--border)]',
        'bg-[var(--bg-elevated)] animate-pulse'
      )}
    >
      {/* Competitor name skeleton */}
      <div className="h-5 w-32 bg-[var(--border)] rounded mb-4" />

      {/* Stats skeleton */}
      <div className="flex flex-col gap-3">
        <div className="h-4 w-24 bg-[var(--border)] rounded" />
        <div className="h-4 w-20 bg-[var(--border)] rounded" />
        <div className="h-4 w-28 bg-[var(--border)] rounded" />
      </div>
    </div>
  );
}

export function BattleCardPreview({
  card,
  marketCapGap = 0,
  winRate = 50,
  lastSignalAt = null,
  className = '',
}: BattleCardPreviewProps) {
  const navigate = useNavigate();

  const winRateColor = getWinRateColor(winRate);
  const { color: marketCapColor, icon: MarketCapIcon } = getMarketCapGapStyle(marketCapGap);

  const handleClick = () => {
    navigate(`/intelligence/battle-cards/${encodeURIComponent(card.competitor_name)}`);
  };

  return (
    <div
      onClick={handleClick}
      data-aria-id={`battle-card-${card.competitor_name}`}
      className={cn(
        'rounded-xl p-5 border border-[var(--border)]',
        'bg-[var(--bg-elevated)]',
        'cursor-pointer transition-all duration-200',
        'hover:border-[var(--accent)] hover:shadow-sm',
        'hover:bg-[var(--bg-subtle)]',
        className
      )}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          handleClick();
        }
      }}
    >
      {/* Competitor Name */}
      <h3
        className="text-lg font-medium mb-4 truncate"
        style={{ color: 'var(--text-primary)' }}
      >
        {card.competitor_name}
      </h3>

      {/* Stats */}
      <div className="flex flex-col gap-3">
        {/* Market Cap Gap */}
        <div className="flex items-center justify-between">
          <span
            className="text-xs uppercase tracking-wide"
            style={{ color: 'var(--text-secondary)' }}
          >
            Market Cap Gap
          </span>
          <div className="flex items-center gap-1.5">
            <MarketCapIcon className="w-4 h-4" style={{ color: marketCapColor }} />
            <span
              className="text-sm font-medium font-mono"
              style={{ color: marketCapColor }}
            >
              {formatMarketCapGap(marketCapGap)}
            </span>
          </div>
        </div>

        {/* Win Rate */}
        <div className="flex items-center justify-between">
          <span
            className="text-xs uppercase tracking-wide"
            style={{ color: 'var(--text-secondary)' }}
          >
            Win Rate
          </span>
          <span
            className="text-sm font-medium font-mono"
            style={{ color: winRateColor }}
          >
            {winRate}%
          </span>
        </div>

        {/* Last Signal */}
        <div className="flex items-center justify-between">
          <span
            className="text-xs uppercase tracking-wide"
            style={{ color: 'var(--text-secondary)' }}
          >
            Last Signal
          </span>
          <div className="flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5" style={{ color: 'var(--text-secondary)' }} />
            <span
              className="text-xs font-mono"
              style={{ color: 'var(--text-secondary)' }}
            >
              {formatLastSignal(lastSignalAt)}
            </span>
          </div>
        </div>
      </div>

      {/* Quick strengths preview (first 2) */}
      {card.strengths.length > 0 && (
        <div className="mt-4 pt-3 border-t border-[var(--border)]">
          <span
            className="text-xs uppercase tracking-wide mb-2 block"
            style={{ color: 'var(--text-secondary)' }}
          >
            Key Strengths
          </span>
          <ul className="space-y-1">
            {card.strengths.slice(0, 2).map((strength, index) => (
              <li
                key={index}
                className="text-xs truncate"
                style={{ color: 'var(--text-primary)' }}
              >
                {strength}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
