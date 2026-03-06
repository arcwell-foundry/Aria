/**
 * BattleCardPreview - Preview card for competitor battle cards
 *
 * Follows ARIA Design System v1.0:
 * - Uses CSS variables for theming
 * - Shows threat level, momentum, signal count, pricing, and differentiation
 * - All data sourced from battle_cards analysis JSONB field
 * - Click navigates to battle card detail
 * - data-aria-id for UICommandExecutor targeting
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowUp, ArrowDown, ArrowRight, Activity } from 'lucide-react';
import { cn } from '@/utils/cn';
import type { BattleCard } from '@/api/battleCards';

export interface BattleCardPreviewProps {
  card: BattleCard;
  className?: string;
}

// Threat level colors
const THREAT_COLORS = {
  high: { dot: '#EF4444', glow: 'rgba(239, 68, 68, 0.35)' },
  medium: { dot: '#F59E0B', glow: 'rgba(245, 158, 11, 0.3)' },
  low: { dot: '#22C55E', glow: 'rgba(34, 197, 94, 0.3)' },
} as const;

// Momentum config
const MOMENTUM_CONFIG = {
  increasing: { icon: ArrowUp, color: '#22C55E', label: 'Increasing' },
  declining: { icon: ArrowDown, color: '#EF4444', label: 'Declining' },
  stable: { icon: ArrowRight, color: '#94A3B8', label: 'Stable' },
} as const;

// Format relative time for last signal
function formatRelativeDate(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return '1d ago';
  if (diffDays < 7) return `${diffDays}d ago`;
  if (diffDays < 30) {
    const weeks = Math.floor(diffDays / 7);
    return `${weeks}w ago`;
  }
  if (diffDays < 365) {
    const months = Math.floor(diffDays / 30);
    return `${months}mo ago`;
  }
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

// Tooltip component
function Tooltip({ text, children }: { text: string; children: React.ReactNode }) {
  const [show, setShow] = useState(false);

  return (
    <span
      className="relative inline-flex"
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
    >
      {children}
      {show && (
        <span
          className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 rounded-lg text-xs leading-relaxed whitespace-normal max-w-[280px] w-max pointer-events-none"
          style={{
            backgroundColor: '#1E293B',
            color: '#F1F5F9',
            boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
          }}
        >
          {text}
          <span
            className="absolute top-full left-1/2 -translate-x-1/2 -mt-px"
            style={{
              width: 0,
              height: 0,
              borderLeft: '5px solid transparent',
              borderRight: '5px solid transparent',
              borderTop: '5px solid #1E293B',
            }}
          />
        </span>
      )}
    </span>
  );
}

// Skeleton for loading state
export function BattleCardPreviewSkeleton() {
  return (
    <div
      className={cn(
        'rounded-xl p-5 border animate-pulse'
      )}
      style={{
        backgroundColor: '#FFFFFF',
        borderColor: '#E2E8F0',
      }}
    >
      <div className="flex items-start justify-between mb-3">
        <div className="h-5 w-32 rounded" style={{ backgroundColor: '#E2E8F0' }} />
        <div className="h-3 w-3 rounded-full" style={{ backgroundColor: '#E2E8F0' }} />
      </div>
      <div className="h-4 w-full rounded mb-4" style={{ backgroundColor: '#E2E8F0' }} />
      <div className="flex gap-3 mb-4">
        <div className="h-4 w-20 rounded" style={{ backgroundColor: '#E2E8F0' }} />
        <div className="h-4 w-24 rounded" style={{ backgroundColor: '#E2E8F0' }} />
        <div className="h-4 w-16 rounded" style={{ backgroundColor: '#E2E8F0' }} />
      </div>
      <div className="h-4 w-28 rounded mb-2" style={{ backgroundColor: '#E2E8F0' }} />
      <div className="h-4 w-full rounded mb-4" style={{ backgroundColor: '#E2E8F0' }} />
      <div className="space-y-2">
        <div className="h-3 w-full rounded" style={{ backgroundColor: '#E2E8F0' }} />
        <div className="h-3 w-4/5 rounded" style={{ backgroundColor: '#E2E8F0' }} />
      </div>
    </div>
  );
}

export function BattleCardPreview({ card, className = '' }: BattleCardPreviewProps) {
  const navigate = useNavigate();
  const analysis = card.analysis;

  const threatLevel = analysis?.threat_level;
  const momentum = analysis?.momentum;
  const momentumDetail = analysis?.momentum_detail;
  const signalCount30d = analysis?.signal_count_30d;
  const lastSignalAt = analysis?.last_signal_at;
  const highImpactSignals = analysis?.high_impact_signals;
  const threatColors = threatLevel ? THREAT_COLORS[threatLevel] : null;
  const momentumConfig = momentum ? MOMENTUM_CONFIG[momentum] : null;

  // Determine "How We Win" content: differentiation first, fallback to strengths
  const howWeWin: string[] = card.differentiation?.length > 0
    ? card.differentiation.slice(0, 2).map(d => d.our_advantage)
    : (card.strengths ?? []).slice(0, 2);

  const handleClick = () => {
    navigate(`/intelligence/battle-cards/${encodeURIComponent(card.competitor_name)}`);
  };

  // Build threat tooltip
  const threatTooltip = threatLevel
    ? `${threatLevel.charAt(0).toUpperCase() + threatLevel.slice(1)} Threat: ${signalCount30d ?? 0} signals in 30 days, ${highImpactSignals ?? 0} high-impact signals. Threat is calculated from signal volume, impact types (product launches, funding, FDA approvals), and recency of activity.`
    : '';

  // Build momentum tooltip
  const momentumTooltip = momentumDetail
    ? `Momentum compares signal volume in the current 30-day window vs the previous 30-day window. Current: ${momentumDetail.signals_current_30d} signals, Previous: ${momentumDetail.signals_previous_30d} signals.`
    : '';

  return (
    <div
      onClick={handleClick}
      data-aria-id={`battle-card-${card.competitor_name}`}
      className={cn(
        'rounded-xl border cursor-pointer',
        'transition-all duration-200 ease-out',
        'hover:-translate-y-0.5',
        'group',
        className
      )}
      style={{
        backgroundColor: '#FFFFFF',
        borderColor: '#E2E8F0',
        padding: '20px',
        boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.boxShadow = '0 8px 24px rgba(0,0,0,0.08), 0 2px 8px rgba(0,0,0,0.04)';
        e.currentTarget.style.borderColor = '#CBD5E1';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.boxShadow = '0 1px 3px rgba(0,0,0,0.04)';
        e.currentTarget.style.borderColor = '#E2E8F0';
      }}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          handleClick();
        }
      }}
    >
      {/* Row 1: Competitor Name + Threat Dot */}
      <div className="flex items-start justify-between mb-1">
        <h3
          className="text-[15px] font-semibold tracking-tight truncate pr-3"
          style={{ color: '#1E293B', fontFamily: 'var(--font-display, system-ui)', lineHeight: '1.3' }}
        >
          {card.competitor_name}
        </h3>
        {threatColors && (
          <Tooltip text={threatTooltip}>
            <span
              className="inline-block w-2.5 h-2.5 rounded-full flex-shrink-0 mt-1"
              style={{
                backgroundColor: threatColors.dot,
                boxShadow: `0 0 6px ${threatColors.glow}`,
              }}
            />
          </Tooltip>
        )}
      </div>

      {/* Row 2: Overview */}
      {card.overview && (
        <p
          className="text-xs truncate mb-3"
          style={{ color: '#5B6E8A', lineHeight: '1.5' }}
        >
          {card.overview}
        </p>
      )}

      {/* Row 3: Momentum | Signal Count | Last Signal */}
      <div className="flex items-center gap-2 flex-wrap mb-4">
        {momentumConfig && (
          <Tooltip text={momentumTooltip}>
            <span
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium"
              style={{
                color: momentumConfig.color,
                backgroundColor: `${momentumConfig.color}10`,
              }}
            >
              <momentumConfig.icon className="w-3 h-3" />
              {momentumConfig.label}
            </span>
          </Tooltip>
        )}

        {signalCount30d != null && (
          <span
            className="inline-flex items-center gap-1 text-[11px]"
            style={{ color: '#5B6E8A' }}
          >
            <Activity className="w-3 h-3" />
            {signalCount30d} signals / 30d
          </span>
        )}

        {lastSignalAt && (
          <span
            className="text-[11px]"
            style={{ color: '#94A3B8' }}
          >
            {formatRelativeDate(lastSignalAt)}
          </span>
        )}
      </div>

      {/* Row 4: Pricing Range */}
      {card.pricing?.range && (
        <div className="mb-4">
          <span
            className="block text-[10px] uppercase tracking-widest font-semibold mb-1"
            style={{ color: '#94A3B8' }}
          >
            Pricing
          </span>
          <span
            className="text-xs"
            style={{ color: '#1E293B' }}
          >
            {card.pricing.range}
          </span>
        </div>
      )}

      {/* Row 5: How We Win */}
      {howWeWin.length > 0 && (
        <div className="mb-4">
          <span
            className="block text-[10px] uppercase tracking-widest font-semibold mb-1.5"
            style={{ color: '#94A3B8' }}
          >
            How We Win
          </span>
          <ul className="space-y-1">
            {howWeWin.map((item, i) => (
              <li
                key={i}
                className="text-xs truncate flex items-start gap-1.5"
                style={{ color: '#334155' }}
              >
                <span className="text-[8px] mt-1 flex-shrink-0" style={{ color: '#94A3B8' }}>&#9679;</span>
                <span className="truncate">{item}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Divider + Win Rate CRM Hint */}
      <div
        className="pt-3 mt-auto"
        style={{ borderTop: '1px solid #F1F5F9' }}
      >
        <span
          className="text-[11px] flex items-center gap-1"
          style={{ color: '#CBD5E1' }}
        >
          Win Rate: Connect CRM
          <span style={{ fontSize: '10px' }}>&nearr;</span>
        </span>
      </div>
    </div>
  );
}
