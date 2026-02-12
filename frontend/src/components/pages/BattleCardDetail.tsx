/**
 * BattleCardDetail - Detailed competitive analysis view
 *
 * Follows ARIA Design System v1.0:
 * - LIGHT THEME with dark accent sections
 * - Header with competitor dropdown selector
 * - Metrics bar: Market Cap Gap, Win Rate, Pricing Delta, Last Signal
 * - Sections: How to Win, Feature Gap Analysis, Critical Gaps, Objection Handling
 * - data-aria-id on all key elements
 *
 * All data sourced from the battle_cards API (analysis JSONB column).
 *
 * @example
 * <BattleCardDetail competitorId="Lonza" />
 */

import { useState, useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Zap,
  Target,
  Clock,
  Shield,
  CircleCheck,
  AlertCircle,
  CheckCircle2,
  XCircle,
  ChevronDown,
  ChevronRight,
  TrendingUp,
  TrendingDown,
  Minus,
  ArrowLeft,
} from 'lucide-react';
import { cn } from '@/utils/cn';
import { useBattleCard, useBattleCards } from '@/hooks/useBattleCards';
import { CopyButton } from '@/components/common/CopyButton';
import { EmptyState } from '@/components/common/EmptyState';
import type {
  BattleCard,
  BattleCardObjectionHandler,
  BattleCardStrategy,
  BattleCardFeatureGap,
  BattleCardCriticalGap,
} from '@/api/battleCards';

// ============================================================================
// ICON MAPPING
// ============================================================================

/** Map strategy icon strings from the API to Lucide icon components. */
const STRATEGY_ICON_MAP: Record<string, typeof Zap> = {
  zap: Zap,
  target: Target,
  clock: Clock,
  shield: Shield,
};


// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

function getWinRateColor(winRate: number): string {
  if (winRate > 60) return 'var(--success)';
  if (winRate >= 40) return 'var(--warning)';
  return 'var(--error)';
}

function getWinRateDotClass(winRate: number): string {
  if (winRate > 60) return 'bg-emerald-500';
  if (winRate >= 40) return 'bg-amber-500';
  return 'bg-red-500';
}

function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / (1000 * 60));
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays}d ago`;
  if (diffDays < 30) {
    const weeks = Math.floor(diffDays / 7);
    return `${weeks}w ago`;
  }
  const months = Math.floor(diffDays / 30);
  return `${months}mo ago`;
}

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
    return `${weeks}w ago`;
  }
  const months = Math.floor(diffDays / 30);
  return `${months}mo ago`;
}

/** Extract the win rate from a battle card's analysis, defaulting to 50. */
function getCardWinRate(card: BattleCard): number {
  return card.analysis?.metrics?.win_rate ?? 50;
}

// ============================================================================
// SUB-COMPONENTS
// ============================================================================

// Metric Card for top metrics bar
interface MetricCardProps {
  label: string;
  value: string | number;
  sublabel?: string;
  color?: string;
  icon?: typeof TrendingUp;
  iconColor?: string;
}

function MetricCard({ label, value, sublabel, color, icon: Icon, iconColor }: MetricCardProps) {
  return (
    <div
      className="flex flex-col p-4 rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)]"
      data-aria-id={`metric-${label.toLowerCase().replace(/\s+/g, '-')}`}
    >
      <span
        className="text-xs uppercase tracking-wide mb-1"
        style={{ color: 'var(--text-secondary)' }}
      >
        {label}
      </span>
      <div className="flex items-center gap-2">
        {Icon && <Icon className="w-4 h-4" style={{ color: iconColor || 'var(--text-secondary)' }} />}
        <span
          className="text-xl font-semibold font-mono"
          style={{ color: color || 'var(--text-primary)' }}
        >
          {value}
        </span>
      </div>
      {sublabel && (
        <span
          className="text-xs mt-1"
          style={{ color: 'var(--text-secondary)' }}
        >
          {sublabel}
        </span>
      )}
    </div>
  );
}

// Section wrapper with timestamp
interface SectionProps {
  title: string;
  agent?: string;
  updatedAt?: string;
  children: React.ReactNode;
  className?: string;
  dark?: boolean;
}

function Section({ title, agent, updatedAt, children, className = '', dark = false }: SectionProps) {
  return (
    <section
      className={cn(
        'rounded-xl border border-[var(--border)] overflow-hidden',
        dark ? 'bg-[#0A0A0B]' : 'bg-[var(--bg-elevated)]',
        className
      )}
      data-aria-id={`section-${title.toLowerCase().replace(/\s+/g, '-')}`}
    >
      {/* Section Header */}
      <div
        className={cn(
          'px-5 py-4 border-b border-[var(--border)]',
          dark ? 'bg-[#111113]' : 'bg-[var(--bg-subtle)]'
        )}
      >
        <div className="flex items-center justify-between">
          <h2
            className="text-base font-medium"
            style={{ color: dark ? '#F8FAFC' : 'var(--text-primary)' }}
          >
            {title}
          </h2>
          {agent && updatedAt && (
            <span
              className="text-xs font-mono"
              style={{ color: dark ? '#64748B' : 'var(--text-secondary)' }}
            >
              Updated by {agent}, {formatRelativeTime(updatedAt)}
            </span>
          )}
        </div>
      </div>
      {/* Section Content */}
      <div className="p-5">{children}</div>
    </section>
  );
}

// Strategy Card for How to Win section
interface StrategyCardProps {
  strategy: BattleCardStrategy;
  index: number;
}

function StrategyCard({ strategy, index }: StrategyCardProps) {
  const StrategyIcon = STRATEGY_ICON_MAP[strategy.icon] ?? Zap;

  return (
    <div
      className="rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] p-4 hover:border-[var(--accent)] transition-colors duration-200"
      data-aria-id={`strategy-${index}`}
    >
      <div className="flex items-start gap-3">
        <div
          className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0"
          style={{ backgroundColor: 'var(--bg-subtle)' }}
        >
          <StrategyIcon className="w-5 h-5" style={{ color: 'var(--accent)' }} />
        </div>
        <div className="flex-1 min-w-0">
          <h3
            className="text-sm font-medium mb-1"
            style={{ color: 'var(--text-primary)' }}
          >
            {strategy.title}
          </h3>
          <p
            className="text-xs leading-relaxed"
            style={{ color: 'var(--text-secondary)' }}
          >
            {strategy.description}
          </p>
        </div>
      </div>
    </div>
  );
}

// Feature Gap Bar
interface FeatureGapBarProps {
  gap: BattleCardFeatureGap;
}

function FeatureGapBar({ gap }: FeatureGapBarProps) {
  const [isHovered, setIsHovered] = useState(false);
  const ariaLeads = gap.aria_score >= gap.competitor_score;
  const delta = gap.aria_score - gap.competitor_score;

  return (
    <div
      className="py-3"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      data-aria-id={`feature-gap-${gap.feature.toLowerCase().replace(/\s+/g, '-')}`}
    >
      {/* Feature name and icons */}
      <div className="flex items-center justify-between mb-2">
        <span
          className="text-sm font-medium"
          style={{ color: 'var(--text-primary)' }}
        >
          {gap.feature}
        </span>
        {ariaLeads ? (
          <CircleCheck className="w-4 h-4 text-emerald-500" />
        ) : (
          <AlertCircle className="w-4 h-4 text-amber-500" />
        )}
      </div>

      {/* Side-by-side bars */}
      <div className="space-y-1.5">
        {/* ARIA bar */}
        <div className="flex items-center gap-2">
          <span
            className="text-xs w-12 flex-shrink-0"
            style={{ color: 'var(--text-secondary)' }}
          >
            ARIA
          </span>
          <div className="flex-1 h-2 rounded-full bg-[var(--border)] overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-300"
              style={{
                width: `${gap.aria_score}%`,
                backgroundColor: '#2E66FF',
              }}
            />
          </div>
          <span
            className="text-xs w-8 text-right font-mono"
            style={{ color: 'var(--text-secondary)' }}
          >
            {gap.aria_score}
          </span>
        </div>

        {/* Competitor bar */}
        <div className="flex items-center gap-2">
          <span
            className="text-xs w-12 flex-shrink-0 truncate"
            style={{ color: 'var(--text-secondary)' }}
          >
            Comp.
          </span>
          <div className="flex-1 h-2 rounded-full bg-[var(--border)] overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-300"
              style={{
                width: `${gap.competitor_score}%`,
                backgroundColor: '#64748B',
              }}
            />
          </div>
          <span
            className="text-xs w-8 text-right font-mono"
            style={{ color: 'var(--text-secondary)' }}
          >
            {gap.competitor_score}
          </span>
        </div>
      </div>

      {/* Delta on hover */}
      {isHovered && (
        <div
          className="mt-2 text-xs font-mono"
          style={{
            color: delta >= 0 ? 'var(--success)' : 'var(--warning)',
          }}
        >
          {delta >= 0 ? '+' : ''}{delta} point{Math.abs(delta) !== 1 ? 's' : ''} {delta >= 0 ? 'advantage' : 'gap'}
        </div>
      )}
    </div>
  );
}

// Critical Gap Item
interface CriticalGapItemProps {
  gap: BattleCardCriticalGap;
  index: number;
}

function CriticalGapItem({ gap, index }: CriticalGapItemProps) {
  return (
    <div
      className="flex items-start gap-3 py-2"
      data-aria-id={`critical-gap-${index}`}
    >
      {gap.is_advantage ? (
        <CheckCircle2 className="w-4 h-4 text-emerald-500 flex-shrink-0 mt-0.5" />
      ) : (
        <XCircle className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" />
      )}
      <span
        className="text-sm leading-relaxed"
        style={{ color: 'var(--text-primary)' }}
      >
        {gap.description}
      </span>
    </div>
  );
}

// Objection Accordion Item
interface ObjectionAccordionProps {
  handler: BattleCardObjectionHandler;
  isExpanded: boolean;
  onToggle: () => void;
}

function ObjectionAccordion({ handler, isExpanded, onToggle }: ObjectionAccordionProps) {
  return (
    <div
      className={cn(
        'rounded-lg border border-[var(--border)] overflow-hidden',
        isExpanded && 'border-[var(--accent)]'
      )}
      data-aria-id={`objection-${handler.objection.toLowerCase().slice(0, 30).replace(/\s+/g, '-')}`}
    >
      {/* Header - clickable */}
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between p-4 text-left hover:bg-[var(--bg-subtle)] transition-colors duration-200"
      >
        <span
          className="text-sm font-medium pr-4"
          style={{ color: 'var(--text-primary)' }}
        >
          {handler.objection}
        </span>
        {isExpanded ? (
          <ChevronDown className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--text-secondary)' }} />
        ) : (
          <ChevronRight className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--text-secondary)' }} />
        )}
      </button>

      {/* Expanded content */}
      {isExpanded && (
        <div className="px-4 pb-4">
          <div
            className="p-4 rounded-lg relative"
            style={{ backgroundColor: 'var(--bg-subtle)' }}
          >
            {/* Copy button in top-right */}
            <div className="absolute top-2 right-2">
              <CopyButton text={handler.response} />
            </div>

            {/* Response text */}
            <p
              className="text-sm leading-relaxed pr-16"
              style={{ color: 'var(--text-primary)' }}
            >
              {handler.response}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

// Competitor Dropdown Selector
interface CompetitorDropdownProps {
  competitors: BattleCard[];
  selectedName: string;
  onSelect: (name: string) => void;
}

function CompetitorDropdown({ competitors, selectedName, onSelect }: CompetitorDropdownProps) {
  const [isOpen, setIsOpen] = useState(false);

  const selectedCard = competitors.find(c => c.competitor_name === selectedName);
  const selectedWinRate = selectedCard ? getCardWinRate(selectedCard) : 50;

  return (
    <div className="relative" data-aria-id="competitor-dropdown">
      {/* Trigger button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-3 py-2 rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] hover:border-[var(--accent)] transition-colors duration-200"
      >
        <div className={cn('w-2 h-2 rounded-full', getWinRateDotClass(selectedWinRate))} />
        <span
          className="text-sm font-medium"
          style={{ color: 'var(--text-primary)' }}
        >
          {selectedName}
        </span>
        <ChevronDown
          className={cn('w-4 h-4 transition-transform duration-200', isOpen && 'rotate-180')}
          style={{ color: 'var(--text-secondary)' }}
        />
      </button>

      {/* Dropdown menu */}
      {isOpen && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-10"
            onClick={() => setIsOpen(false)}
          />
          {/* Menu */}
          <div
            className="absolute top-full left-0 mt-1 w-64 rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] shadow-lg z-20 py-1"
          >
            {competitors.map((comp) => {
              const winRate = getCardWinRate(comp);
              const isSelected = comp.competitor_name === selectedName;
              return (
                <button
                  key={comp.id}
                  onClick={() => {
                    onSelect(comp.competitor_name);
                    setIsOpen(false);
                  }}
                  className={cn(
                    'w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-[var(--bg-subtle)] transition-colors duration-150',
                    isSelected && 'bg-[var(--bg-subtle)]'
                  )}
                >
                  <div className={cn('w-2 h-2 rounded-full', getWinRateDotClass(winRate))} />
                  <span
                    className="text-sm flex-1"
                    style={{ color: 'var(--text-primary)' }}
                  >
                    {comp.competitor_name}
                  </span>
                  <span
                    className="text-xs font-mono"
                    style={{ color: getWinRateColor(winRate) }}
                  >
                    {winRate}%
                  </span>
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

// Loading Skeleton
function BattleCardDetailSkeleton() {
  return (
    <div className="flex-1 overflow-y-auto p-8 animate-pulse">
      {/* Header skeleton */}
      <div className="mb-6">
        <div className="h-4 w-32 bg-[var(--border)] rounded mb-4" />
        <div className="flex items-center gap-4 mb-4">
          <div className="h-8 w-48 bg-[var(--border)] rounded" />
          <div className="h-8 w-40 bg-[var(--border)] rounded" />
        </div>
        <div className="h-6 w-64 bg-[var(--border)] rounded" />
      </div>

      {/* Metrics skeleton */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-24 bg-[var(--border)] rounded-lg" />
        ))}
      </div>

      {/* Sections skeleton */}
      <div className="space-y-6">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-48 bg-[var(--border)] rounded-xl" />
        ))}
      </div>
    </div>
  );
}

// ============================================================================
// MAIN COMPONENT
// ============================================================================

export interface BattleCardDetailProps {
  competitorId?: string;
}

export function BattleCardDetail({ competitorId: propCompetitorId }: BattleCardDetailProps) {
  const navigate = useNavigate();
  const params = useParams<{ competitorId: string }>();
  const competitorId = propCompetitorId || params.competitorId;

  // Fetch all battle cards for the dropdown
  const { data: allBattleCards, isLoading: isLoadingList } = useBattleCards();

  // Decode competitor name from URL
  const decodedName = competitorId ? decodeURIComponent(competitorId) : '';

  // Fetch the selected battle card
  const { data: battleCard, isLoading: isLoadingCard, error } = useBattleCard(decodedName);

  // Extract analysis data from the API response
  const metrics = useMemo(() => {
    const m = battleCard?.analysis?.metrics;
    return {
      marketCapGap: m?.market_cap_gap ?? 0,
      winRate: m?.win_rate ?? 50,
      pricingDelta: m?.pricing_delta ?? 0,
      lastSignalAt: m?.last_signal_at ?? null,
    };
  }, [battleCard]);

  const strategies = useMemo(() => {
    return battleCard?.analysis?.strategies ?? [];
  }, [battleCard]);

  const featureGaps = useMemo(() => {
    return battleCard?.analysis?.feature_gaps ?? [];
  }, [battleCard]);

  const criticalGaps = useMemo(() => {
    return battleCard?.analysis?.critical_gaps ?? [];
  }, [battleCard]);

  // Separate advantages and gaps
  const advantages = criticalGaps.filter(g => g.is_advantage);
  const disadvantages = criticalGaps.filter(g => !g.is_advantage);

  // Handle competitor selection
  const handleCompetitorSelect = (name: string) => {
    navigate(`/intelligence/battle-cards/${encodeURIComponent(name)}`);
  };

  // Handle back navigation
  const handleBack = () => {
    navigate('/intelligence');
  };

  // Loading state
  if (isLoadingList || isLoadingCard) {
    return (
      <div
        className="flex-1 flex flex-col h-full"
        style={{ backgroundColor: 'var(--bg-primary)' }}
      >
        <BattleCardDetailSkeleton />
      </div>
    );
  }

  // Error or not found state
  if (error || !battleCard) {
    return (
      <div
        className="flex-1 flex flex-col h-full"
        style={{ backgroundColor: 'var(--bg-primary)' }}
      >
        <div className="flex-1 overflow-y-auto p-8">
          <button
            onClick={handleBack}
            className="flex items-center gap-2 text-sm mb-6 hover:underline"
            style={{ color: 'var(--accent)' }}
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Intelligence
          </button>
          <EmptyState
            title="Battle card not found"
            description="ARIA hasn't researched this competitor yet. Start a conversation to begin competitive analysis."
            suggestion="Return to Intelligence"
            onSuggestion={handleBack}
            icon={<AlertCircle className="w-8 h-8" />}
          />
        </div>
      </div>
    );
  }

  // Get market cap gap style
  const getMarketCapGapStyle = (gap: number) => {
    if (gap < 0) {
      return { color: 'var(--success)', icon: TrendingDown, text: 'Competitor smaller' };
    }
    if (gap > 0) {
      return { color: 'var(--error)', icon: TrendingUp, text: 'Competitor larger' };
    }
    return { color: 'var(--text-secondary)', icon: Minus, text: 'Equal size' };
  };

  const marketCapStyle = getMarketCapGapStyle(metrics.marketCapGap);
  const MarketCapIcon = marketCapStyle.icon;

  // Get pricing delta style
  const getPricingDeltaStyle = (delta: number) => {
    if (delta < 0) {
      return { color: 'var(--success)', text: 'We are cheaper' };
    }
    if (delta > 0) {
      return { color: 'var(--warning)', text: 'We are pricier' };
    }
    return { color: 'var(--text-secondary)', text: 'Price parity' };
  };

  const pricingStyle = getPricingDeltaStyle(metrics.pricingDelta);

  return (
    <div
      className="flex-1 flex flex-col h-full"
      style={{ backgroundColor: 'var(--bg-primary)' }}
    >
      <div className="flex-1 overflow-y-auto p-8">
        {/* Back button */}
        <button
          onClick={handleBack}
          className="flex items-center gap-2 text-sm mb-6 hover:underline"
          style={{ color: 'var(--accent)' }}
          data-aria-id="back-to-intelligence"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Intelligence
        </button>

        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-4 mb-4">
            {/* Competitor dropdown */}
            {allBattleCards && allBattleCards.length > 0 && (
              <CompetitorDropdown
                competitors={allBattleCards}
                selectedName={battleCard.competitor_name}
                onSelect={handleCompetitorSelect}
              />
            )}
          </div>

          <div className="flex items-center gap-3">
            <h1
              className="font-display text-2xl italic"
              style={{ color: 'var(--text-primary)' }}
              data-aria-id="battle-card-title"
            >
              Battle Cards: Competitor Analysis
            </h1>
          </div>
        </div>

        {/* Metrics Bar */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8" data-aria-id="metrics-bar">
          <MetricCard
            label="Market Cap Gap"
            value={`${metrics.marketCapGap > 0 ? '+' : ''}${metrics.marketCapGap.toFixed(1)}%`}
            sublabel={marketCapStyle.text}
            color={marketCapStyle.color}
            icon={MarketCapIcon}
            iconColor={marketCapStyle.color}
          />
          <MetricCard
            label="Win Rate"
            value={`${metrics.winRate}%`}
            sublabel="vs this competitor"
            color={getWinRateColor(metrics.winRate)}
          />
          <MetricCard
            label="Pricing Delta"
            value={`${metrics.pricingDelta > 0 ? '+' : ''}${metrics.pricingDelta.toFixed(1)}%`}
            sublabel={pricingStyle.text}
            color={pricingStyle.color}
          />
          <MetricCard
            label="Last Signal"
            value={formatLastSignal(metrics.lastSignalAt)}
            sublabel="intelligence detected"
          />
        </div>

        {/* Sections */}
        <div className="space-y-6">
          {/* How to Win */}
          {strategies.length > 0 && (
            <Section
              title="How to Win"
              agent={strategies[0]?.agent ?? 'Hunter'}
              updatedAt={battleCard.last_updated}
            >
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {strategies.map((strategy, index) => (
                  <StrategyCard key={index} strategy={strategy} index={index} />
                ))}
              </div>
            </Section>
          )}

          {/* Feature Gap Analysis */}
          {featureGaps.length > 0 && (
            <Section
              title="Feature Gap Analysis"
              agent="Analyst"
              updatedAt={battleCard.last_updated}
            >
              <div className="space-y-4">
                {featureGaps.map((gap, index) => (
                  <FeatureGapBar key={index} gap={gap} />
                ))}
              </div>
            </Section>
          )}

          {/* Critical Gaps */}
          {criticalGaps.length > 0 && (
            <Section
              title="Critical Gaps"
              agent="Strategist"
              updatedAt={battleCard.last_updated}
            >
              {/* ARIA Advantages */}
              {advantages.length > 0 && (
                <div className="mb-6">
                  <h3
                    className="text-xs uppercase tracking-wide mb-3 flex items-center gap-2"
                    style={{ color: 'var(--success)' }}
                  >
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    ARIA Advantages ({advantages.length})
                  </h3>
                  <div className="space-y-1">
                    {advantages.map((gap, index) => (
                      <CriticalGapItem key={index} gap={gap} index={index} />
                    ))}
                  </div>
                </div>
              )}

              {/* Competitor Advantages */}
              {disadvantages.length > 0 && (
                <div>
                  <h3
                    className="text-xs uppercase tracking-wide mb-3 flex items-center gap-2"
                    style={{ color: 'var(--warning)' }}
                  >
                    <XCircle className="w-3.5 h-3.5" />
                    Competitor Advantages ({disadvantages.length})
                  </h3>
                  <div className="space-y-1">
                    {disadvantages.map((gap, index) => (
                      <CriticalGapItem key={index} gap={gap} index={advantages.length + index} />
                    ))}
                  </div>
                </div>
              )}
            </Section>
          )}

          {/* Objection Handling */}
          <Section
            title="Objection Handling"
            agent="Scribe"
            updatedAt={battleCard.last_updated}
            dark
          >
            <ObjectionHandlingContent handlers={battleCard.objection_handlers} />
          </Section>
        </div>
      </div>
    </div>
  );
}

// Separate component for objection handling to manage expanded state
interface ObjectionHandlingContentProps {
  handlers: BattleCardObjectionHandler[];
}

function ObjectionHandlingContent({ handlers }: ObjectionHandlingContentProps) {
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);

  if (handlers.length === 0) {
    return (
      <div className="text-center py-4">
        <p
          className="text-sm"
          style={{ color: '#94A3B8' }}
        >
          No objection handlers defined yet. ARIA will learn these from conversations.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {handlers.map((handler, index) => (
        <ObjectionAccordion
          key={index}
          handler={handler}
          isExpanded={expandedIndex === index}
          onToggle={() => setExpandedIndex(expandedIndex === index ? null : index)}
        />
      ))}
    </div>
  );
}

export default BattleCardDetail;
