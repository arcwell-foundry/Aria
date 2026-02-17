/**
 * TerritoryOverviewBar - Territory stats bar for Pipeline page
 *
 * Horizontal stats bar showing territory health at a glance:
 * - Total Accounts count
 * - Pipeline Value (formatted as $X.XM)
 * - Avg Health (color-coded: green >70, amber 40-70, red <40)
 * - Stage breakdown as inline pill badges
 *
 * Follows ARIA Design System v1.0:
 * - LIGHT THEME (content page context)
 * - CSS variables for colors
 * - font-mono for data labels
 * - Skeleton loading state
 */

import { HealthBar } from './HealthBar';
import type { TerritoryResponse } from '@/api/accounts';

interface TerritoryOverviewBarProps {
  territory: TerritoryResponse | undefined;
  isLoading: boolean;
}

function formatCurrency(value: number): string {
  if (value >= 1_000_000) {
    return `$${(value / 1_000_000).toFixed(1)}M`;
  }
  if (value >= 1_000) {
    return `$${(value / 1_000).toFixed(0)}K`;
  }
  return `$${value.toFixed(0)}`;
}

const STAGE_COLORS: Record<string, string> = {
  lead: 'var(--text-secondary)',
  opportunity: 'var(--warning)',
  account: 'var(--success)',
};

function TerritoryOverviewBarSkeleton() {
  return (
    <div
      className="flex items-center gap-6 px-5 py-3 rounded-lg border mb-6 animate-pulse"
      style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)' }}
    >
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="flex items-center gap-2">
          <div className="h-3 w-16 rounded bg-[var(--border)]" />
          <div className="h-5 w-12 rounded bg-[var(--border)]" />
        </div>
      ))}
    </div>
  );
}

export function TerritoryOverviewBar({ territory, isLoading }: TerritoryOverviewBarProps) {
  if (isLoading) return <TerritoryOverviewBarSkeleton />;

  if (!territory) {
    return (
      <div
        className="px-5 py-3 rounded-lg border mb-6"
        style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)' }}
        data-aria-id="territory-overview-bar"
      >
        <p className="font-sans text-[12px]" style={{ color: 'var(--text-secondary)' }}>
          ARIA is mapping your territory.
        </p>
      </div>
    );
  }

  const { stats } = territory;

  return (
    <div
      className="flex items-center gap-6 px-5 py-3 rounded-lg border mb-6 flex-wrap"
      style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)' }}
      data-aria-id="territory-overview-bar"
    >
      {/* Total Accounts */}
      <div className="flex items-center gap-2">
        <span
          className="font-sans text-[11px] font-medium uppercase tracking-wider"
          style={{ color: 'var(--text-secondary)' }}
        >
          Accounts
        </span>
        <span
          className="font-mono text-[14px] font-semibold"
          style={{ color: 'var(--text-primary)' }}
        >
          {stats.total_accounts}
        </span>
      </div>

      {/* Divider */}
      <div className="w-px h-5" style={{ backgroundColor: 'var(--border)' }} />

      {/* Pipeline Value */}
      <div className="flex items-center gap-2">
        <span
          className="font-sans text-[11px] font-medium uppercase tracking-wider"
          style={{ color: 'var(--text-secondary)' }}
        >
          Pipeline
        </span>
        <span
          className="font-mono text-[14px] font-semibold"
          style={{ color: 'var(--text-primary)' }}
        >
          {formatCurrency(stats.total_value)}
        </span>
      </div>

      {/* Divider */}
      <div className="w-px h-5" style={{ backgroundColor: 'var(--border)' }} />

      {/* Avg Health */}
      <div className="flex items-center gap-2">
        <span
          className="font-sans text-[11px] font-medium uppercase tracking-wider"
          style={{ color: 'var(--text-secondary)' }}
        >
          Avg Health
        </span>
        <HealthBar score={stats.avg_health} size="sm" />
      </div>

      {/* Divider */}
      <div className="w-px h-5" style={{ backgroundColor: 'var(--border)' }} />

      {/* Stage Breakdown */}
      <div className="flex items-center gap-2">
        {Object.entries(stats.stage_counts).map(([stage, count]) => (
          <span
            key={stage}
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium"
            style={{
              backgroundColor: `color-mix(in srgb, ${STAGE_COLORS[stage] ?? 'var(--text-secondary)'} 12%, transparent)`,
              color: STAGE_COLORS[stage] ?? 'var(--text-secondary)',
            }}
          >
            {stage.charAt(0).toUpperCase() + stage.slice(1)}
            <span className="font-mono">{count}</span>
          </span>
        ))}
      </div>
    </div>
  );
}
