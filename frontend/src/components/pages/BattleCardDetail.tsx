/**
 * BattleCardDetail - Comprehensive competitor intelligence detail view
 *
 * Surfaces ALL available data:
 * - Overview text
 * - Signal-derived metrics (threat, momentum, signal counts, last signal)
 * - Pricing intelligence
 * - How We Win (differentiation)
 * - Strengths & Weaknesses (side-by-side)
 * - Objection handlers (accordion)
 * - Recent news (curated) + live market signals
 * - Freshness footer
 *
 * Light theme: bg #F8FAFC, cards white, text #1E293B, muted #5B6E8A
 */

import { useState, useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ChevronDown,
  ChevronRight,
  ArrowLeft,
  AlertCircle,
  ExternalLink,
  Newspaper,
  Activity,
  DollarSign,
  Shield,
  FlaskConical,
  FileText,
  UserCog,
  TrendingUp,
  Handshake,
  Scale,
  Package,
  Users,
} from 'lucide-react';
import { cn } from '@/utils/cn';
import { useBattleCard, useBattleCards } from '@/hooks/useBattleCards';
import { CopyButton } from '@/components/common/CopyButton';
import { EmptyState } from '@/components/common/EmptyState';
import { sanitizeSignalText } from '@/utils/sanitizeSignalText';
import { formatSourceName } from '@/utils/sourceLabels';
import type {
  BattleCard,
  BattleCardObjectionHandler,
  BattleCardDifferentiation,
  BattleCardNewsItem,
  BattleCardSignal,
} from '@/api/battleCards';

// ============================================================================
// CONSTANTS
// ============================================================================

const SIGNAL_TYPE_ICONS: Record<string, typeof TrendingUp> = {
  funding: DollarSign,
  fda_approval: Shield,
  clinical_trial: FlaskConical,
  patent: FileText,
  leadership: UserCog,
  earnings: TrendingUp,
  partnership: Handshake,
  regulatory: Scale,
  product: Package,
  hiring: Users,
};

const SIGNAL_TYPE_LABELS: Record<string, string> = {
  funding: 'FUNDING',
  fda_approval: 'FDA',
  clinical_trial: 'CLINICAL',
  patent: 'PATENT',
  leadership: 'LEADERSHIP',
  earnings: 'EARNINGS',
  partnership: 'PARTNERSHIP',
  regulatory: 'REGULATORY',
  product: 'PRODUCT',
  hiring: 'HIRING',
};

const THREAT_CONFIG = {
  high: { color: '#DC2626', bg: 'rgba(220, 38, 38, 0.06)', label: 'High', dot: 'bg-red-500' },
  medium: { color: '#D97706', bg: 'rgba(217, 119, 6, 0.06)', label: 'Medium', dot: 'bg-amber-500' },
  low: { color: '#16A34A', bg: 'rgba(22, 163, 74, 0.06)', label: 'Low', dot: 'bg-emerald-500' },
} as const;

const MOMENTUM_CONFIG = {
  increasing: { color: '#DC2626', label: 'Increasing', arrow: '\u2191' },
  declining: { color: '#16A34A', label: 'Declining', arrow: '\u2193' },
  stable: { color: '#5B6E8A', label: 'Stable', arrow: '\u2192' },
} as const;

// ============================================================================
// HELPERS
// ============================================================================

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function formatRelativeTime(dateStr: string | null): string {
  if (!dateStr) return 'No data';
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays}d ago`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`;
  return `${Math.floor(diffDays / 30)}mo ago`;
}

// ============================================================================
// SUB-COMPONENTS
// ============================================================================

/** Metrics card with hover tooltip */
function MetricCard({
  label,
  value,
  sublabel,
  tooltip,
  tint,
}: {
  label: string;
  value: string;
  sublabel?: string;
  tooltip: string;
  tint?: string;
}) {
  const [showTooltip, setShowTooltip] = useState(false);

  return (
    <div
      className="relative flex flex-col p-4 rounded-lg border transition-shadow duration-200 hover:shadow-md cursor-default"
      style={{
        backgroundColor: tint || '#FFFFFF',
        borderColor: '#E2E8F0',
      }}
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
      data-aria-id={`metric-${label.toLowerCase().replace(/\s+/g, '-')}`}
    >
      <span className="text-[11px] uppercase tracking-wider font-medium" style={{ color: '#5B6E8A' }}>
        {label}
      </span>
      <span className="text-xl font-semibold mt-1 font-mono" style={{ color: '#1E293B' }}>
        {value}
      </span>
      {sublabel && (
        <span className="text-xs mt-0.5" style={{ color: '#5B6E8A' }}>
          {sublabel}
        </span>
      )}
      {showTooltip && (
        <div
          className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 rounded-lg text-xs leading-relaxed z-30 w-56 shadow-lg"
          style={{ backgroundColor: '#1E293B', color: '#F1F5F9' }}
        >
          {tooltip}
          <div
            className="absolute top-full left-1/2 -translate-x-1/2 w-2 h-2 rotate-45 -mt-1"
            style={{ backgroundColor: '#1E293B' }}
          />
        </div>
      )}
    </div>
  );
}

/** Competitor dropdown selector */
function CompetitorDropdown({
  competitors,
  selectedName,
  onSelect,
}: {
  competitors: BattleCard[];
  selectedName: string;
  onSelect: (name: string) => void;
}) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="relative" data-aria-id="competitor-dropdown">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-4 py-2.5 rounded-lg border transition-all duration-200 hover:shadow-sm"
        style={{ backgroundColor: '#FFFFFF', borderColor: '#E2E8F0', color: '#1E293B' }}
      >
        <span className="text-sm font-medium">{selectedName}</span>
        <ChevronDown
          className={cn('w-4 h-4 transition-transform duration-200', isOpen && 'rotate-180')}
          style={{ color: '#5B6E8A' }}
        />
      </button>
      {isOpen && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setIsOpen(false)} />
          <div
            className="absolute top-full left-0 mt-1 w-64 rounded-lg border shadow-lg z-20 py-1"
            style={{ backgroundColor: '#FFFFFF', borderColor: '#E2E8F0' }}
          >
            {competitors.map((comp) => {
              const isSelected = comp.competitor_name === selectedName;
              const threat = comp.analysis?.threat_level;
              const threatCfg = threat ? THREAT_CONFIG[threat] : null;
              return (
                <button
                  key={comp.id}
                  onClick={() => { onSelect(comp.competitor_name); setIsOpen(false); }}
                  className={cn(
                    'w-full flex items-center gap-2.5 px-3 py-2 text-left transition-colors duration-150',
                    isSelected ? 'bg-[#F1F5F9]' : 'hover:bg-[#F8FAFC]'
                  )}
                >
                  {threatCfg && (
                    <div className={cn('w-2 h-2 rounded-full flex-shrink-0', threatCfg.dot)} />
                  )}
                  <span className="text-sm flex-1" style={{ color: '#1E293B' }}>
                    {comp.competitor_name}
                  </span>
                  {threat && (
                    <span className="text-[10px] uppercase tracking-wider font-medium" style={{ color: threatCfg?.color }}>
                      {threatCfg?.label}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

/** Objection handler accordion */
function ObjectionAccordion({
  handler,
  isExpanded,
  onToggle,
}: {
  handler: BattleCardObjectionHandler;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  return (
    <div
      className={cn(
        'rounded-lg border overflow-hidden transition-colors duration-200',
        isExpanded ? 'border-[#2E66FF]' : 'border-[#E2E8F0]'
      )}
      style={{ backgroundColor: '#FFFFFF' }}
      data-aria-id={`objection-${handler.objection.toLowerCase().slice(0, 30).replace(/\s+/g, '-')}`}
    >
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between p-4 text-left hover:bg-[#F8FAFC] transition-colors duration-200"
      >
        <span className="text-sm font-medium pr-4" style={{ color: '#1E293B' }}>
          &ldquo;{handler.objection}&rdquo;
        </span>
        {isExpanded ? (
          <ChevronDown className="w-4 h-4 flex-shrink-0" style={{ color: '#5B6E8A' }} />
        ) : (
          <ChevronRight className="w-4 h-4 flex-shrink-0" style={{ color: '#5B6E8A' }} />
        )}
      </button>
      {isExpanded && (
        <div className="px-4 pb-4">
          <div className="p-4 rounded-lg relative" style={{ backgroundColor: '#F8FAFC' }}>
            <div className="absolute top-2 right-2">
              <CopyButton text={handler.response} />
            </div>
            <p className="text-sm leading-relaxed pr-16" style={{ color: '#1E293B' }}>
              {handler.response}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

/** Objection handling section */
function ObjectionHandlingContent({ handlers }: { handlers: BattleCardObjectionHandler[] }) {
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);

  if (handlers.length === 0) {
    return (
      <p className="text-sm text-center py-4" style={{ color: '#5B6E8A' }}>
        No objection handlers defined yet. ARIA will learn these from conversations.
      </p>
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

/** Differentiation card for "How We Win" */
function DifferentiationCard({ item }: { item: BattleCardDifferentiation | string }) {
  const text = typeof item === 'string'
    ? item
    : (item as { our_advantage?: string }).our_advantage || '';
  const area = typeof item === 'string' ? null : (item as { area?: string }).area;

  if (!text) return null;

  return (
    <div
      className="rounded-lg border p-4 hover:shadow-md transition-all duration-200 flex flex-col"
      style={{ backgroundColor: '#FFFFFF', borderColor: '#E2E8F0' }}
    >
      {area && (
        <span className="text-[11px] uppercase tracking-wider font-semibold mb-2" style={{ color: '#2E66FF' }}>
          {area}
        </span>
      )}
      <p className="text-sm leading-relaxed flex-1" style={{ color: '#1E293B' }}>
        {text}
      </p>
    </div>
  );
}

/** Signal type badge */
function SignalTypeBadge({ type }: { type: string }) {
  const label = SIGNAL_TYPE_LABELS[type] || type.toUpperCase();
  const Icon = SIGNAL_TYPE_ICONS[type] || Activity;

  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider"
      style={{ backgroundColor: '#F1F5F9', color: '#5B6E8A' }}
    >
      <Icon className="w-3 h-3" />
      {label}
    </span>
  );
}

/** Loading skeleton */
function BattleCardDetailSkeleton() {
  return (
    <div className="flex-1 overflow-y-auto p-8 animate-pulse" style={{ backgroundColor: '#F8FAFC' }}>
      <div className="h-4 w-32 bg-[#E2E8F0] rounded mb-6" />
      <div className="h-8 w-48 bg-[#E2E8F0] rounded mb-2" />
      <div className="h-5 w-96 bg-[#E2E8F0] rounded mb-8" />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-24 bg-[#E2E8F0] rounded-lg" />
        ))}
      </div>
      <div className="space-y-6">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-48 bg-[#E2E8F0] rounded-xl" />
        ))}
      </div>
    </div>
  );
}

// ============================================================================
// SECTION DIVIDER
// ============================================================================

function SectionDivider() {
  return <div className="border-t my-8" style={{ borderColor: '#E2E8F0' }} />;
}

function SectionHeader({ title }: { title: string }) {
  return (
    <h2
      className="text-[11px] uppercase tracking-wider font-semibold mb-4"
      style={{ color: '#5B6E8A' }}
      data-aria-id={`section-${title.toLowerCase().replace(/\s+/g, '-')}`}
    >
      {title}
    </h2>
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

  const { data: allBattleCards, isLoading: isLoadingList } = useBattleCards();
  const decodedName = competitorId ? decodeURIComponent(competitorId) : '';
  const { data: battleCard, isLoading: isLoadingCard, error } = useBattleCard(decodedName);

  // Extract analysis data
  const analysis = useMemo(() => battleCard?.analysis ?? {}, [battleCard]);
  const threatLevel = analysis.threat_level as keyof typeof THREAT_CONFIG | undefined;
  const momentum = analysis.momentum as keyof typeof MOMENTUM_CONFIG | undefined;

  const handleCompetitorSelect = (name: string) => {
    navigate(`/intelligence/battle-cards/${encodeURIComponent(name)}`);
  };

  const handleBack = () => {
    navigate('/intelligence');
  };

  // Loading
  if (isLoadingList || isLoadingCard) {
    return (
      <div className="flex-1 flex flex-col h-full" style={{ backgroundColor: '#F8FAFC' }}>
        <BattleCardDetailSkeleton />
      </div>
    );
  }

  // Not found
  if (error || !battleCard) {
    return (
      <div className="flex-1 flex flex-col h-full" style={{ backgroundColor: '#F8FAFC' }}>
        <div className="flex-1 overflow-y-auto p-8">
          <button
            onClick={handleBack}
            className="flex items-center gap-2 text-sm mb-6 hover:underline"
            style={{ color: '#2E66FF' }}
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

  // Prepare data
  const pricing = battleCard.pricing;
  const hasPricing = pricing && (pricing.model || pricing.range || pricing.strategy || pricing.notes);
  const differentiation = battleCard.differentiation ?? [];
  const recentNews = analysis.recent_news ?? [];
  const recentSignals = battleCard.recent_signals ?? [];
  const hasNewsOrSignals = recentNews.length > 0 || recentSignals.length > 0;

  const threatCfg = threatLevel ? THREAT_CONFIG[threatLevel] : null;
  const momentumCfg = momentum ? MOMENTUM_CONFIG[momentum] : null;

  const hasMetrics = threatLevel || momentum || analysis.signal_count_30d != null || analysis.last_signal_at;

  return (
    <div className="flex-1 flex flex-col h-full" style={{ backgroundColor: '#F8FAFC' }}>
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-5xl mx-auto px-8 py-8">

          {/* Back + Dropdown */}
          <div className="flex items-center justify-between mb-6">
            <button
              onClick={handleBack}
              className="flex items-center gap-2 text-sm hover:underline transition-colors"
              style={{ color: '#2E66FF' }}
              data-aria-id="back-to-intelligence"
            >
              <ArrowLeft className="w-4 h-4" />
              Back to Intelligence
            </button>
            {allBattleCards && allBattleCards.length > 1 && (
              <CompetitorDropdown
                competitors={allBattleCards}
                selectedName={battleCard.competitor_name}
                onSelect={handleCompetitorSelect}
              />
            )}
          </div>

          {/* Competitor Name + Overview */}
          <div className="mb-8">
            <h1
              className="text-3xl font-bold tracking-tight mb-3"
              style={{ color: '#1E293B' }}
              data-aria-id="battle-card-title"
            >
              {battleCard.competitor_name}
            </h1>
            {battleCard.overview && (
              <p className="text-base leading-relaxed max-w-3xl" style={{ color: '#475569' }}>
                {battleCard.overview}
              </p>
            )}
          </div>

          {/* Metrics Bar */}
          {hasMetrics && (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-2" data-aria-id="metrics-bar">
                {threatLevel && threatCfg && (
                  <MetricCard
                    label="Threat Level"
                    value={`\u25CF ${threatCfg.label}`}
                    sublabel={analysis.threat_score != null ? `Score: ${(analysis.threat_score * 100).toFixed(0)}%` : undefined}
                    tooltip={`Threat assessment based on competitive activity, market signals, and win/loss data. ${threatLevel === 'high' ? 'This competitor poses a significant threat.' : threatLevel === 'medium' ? 'Moderate competitive pressure detected.' : 'Lower competitive activity observed.'}`}
                    tint={threatCfg.bg}
                  />
                )}
                {momentum && momentumCfg && (
                  <MetricCard
                    label="Momentum"
                    value={`${momentumCfg.arrow} ${momentumCfg.label}`}
                    sublabel={analysis.momentum_detail ? `${analysis.momentum_detail.signals_current_30d} vs ${analysis.momentum_detail.signals_previous_30d} prev` : undefined}
                    tooltip={`Signal trend over time. Compares signal volume in the last 30 days vs the previous 30-day period to detect acceleration or deceleration in competitive activity.`}
                    tint={momentum === 'increasing' ? 'rgba(220, 38, 38, 0.04)' : momentum === 'declining' ? 'rgba(22, 163, 74, 0.04)' : undefined}
                  />
                )}
                {analysis.signal_count_30d != null && (
                  <MetricCard
                    label="Signals"
                    value={`${analysis.signal_count_30d}`}
                    sublabel={analysis.signal_count_total != null ? `${analysis.signal_count_total} total` : `last 30d`}
                    tooltip="Count of market signals (news, funding, product launches, regulatory events) detected for this competitor. Higher signal counts indicate more market activity."
                  />
                )}
                {analysis.last_signal_at && (
                  <MetricCard
                    label="Last Signal"
                    value={formatDate(analysis.last_signal_at)}
                    sublabel={formatRelativeTime(analysis.last_signal_at)}
                    tooltip="Most recent market signal detected for this competitor. Stale signals may indicate reduced competitive activity or gaps in monitoring coverage."
                  />
                )}
              </div>

              {/* Win rate CTA */}
              {!analysis.metrics?.win_rate && (
                <p className="text-xs mt-1 mb-0" style={{ color: '#94A3B8' }}>
                  Win Rate: Connect your CRM to track competitive win rates &rarr;
                </p>
              )}

              <SectionDivider />
            </>
          )}

          {/* Pricing Intelligence */}
          {hasPricing && (
            <>
              <SectionHeader title="Pricing Intelligence" />
              <div
                className="rounded-lg border p-5 mb-0"
                style={{ backgroundColor: '#FAFBFD', borderColor: '#E2E8F0' }}
                data-aria-id="pricing-intelligence"
              >
                <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-3">
                  {pricing.model && (
                    <div>
                      <span className="text-[11px] uppercase tracking-wider font-medium block mb-1" style={{ color: '#5B6E8A' }}>
                        Model
                      </span>
                      <span className="text-sm" style={{ color: '#1E293B' }}>{pricing.model}</span>
                    </div>
                  )}
                  {pricing.range && (
                    <div>
                      <span className="text-[11px] uppercase tracking-wider font-medium block mb-1" style={{ color: '#5B6E8A' }}>
                        Range
                      </span>
                      <span className="text-sm font-medium" style={{ color: '#1E293B' }}>{pricing.range}</span>
                    </div>
                  )}
                  {pricing.strategy && (
                    <div className="md:col-span-2">
                      <span className="text-[11px] uppercase tracking-wider font-medium block mb-1" style={{ color: '#5B6E8A' }}>
                        Strategy
                      </span>
                      <span className="text-sm leading-relaxed" style={{ color: '#1E293B' }}>{pricing.strategy}</span>
                    </div>
                  )}
                  {pricing.notes && (
                    <div className="md:col-span-2">
                      <span className="text-[11px] uppercase tracking-wider font-medium block mb-1" style={{ color: '#5B6E8A' }}>
                        Notes
                      </span>
                      <span className="text-sm leading-relaxed" style={{ color: '#475569' }}>{pricing.notes}</span>
                    </div>
                  )}
                </div>
              </div>
              <SectionDivider />
            </>
          )}

          {/* How We Win (Differentiation) */}
          {differentiation.length > 0 && (
            <>
              <SectionHeader title="How We Win" />
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {differentiation.map((item, i) => (
                  <DifferentiationCard key={i} item={item} />
                ))}
              </div>
              <SectionDivider />
            </>
          )}

          {/* Strengths & Weaknesses */}
          {(battleCard.strengths?.length > 0 || battleCard.weaknesses?.length > 0) && (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6" data-aria-id="strengths-weaknesses">
                {battleCard.strengths?.length > 0 && (
                  <div>
                    <SectionHeader title="Strengths" />
                    <ul className="space-y-2.5">
                      {battleCard.strengths.map((s, i) => (
                        <li key={i} className="flex items-start gap-2.5">
                          <span className="w-1.5 h-1.5 rounded-full mt-2 flex-shrink-0" style={{ backgroundColor: '#16A34A' }} />
                          <span className="text-sm leading-relaxed" style={{ color: '#1E293B' }}>{s}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {battleCard.weaknesses?.length > 0 && (
                  <div>
                    <SectionHeader title="Weaknesses" />
                    <ul className="space-y-2.5">
                      {battleCard.weaknesses.map((w, i) => (
                        <li key={i} className="flex items-start gap-2.5">
                          <span className="text-amber-500 flex-shrink-0 mt-0.5 text-sm">{'\u26A0'}</span>
                          <span className="text-sm leading-relaxed" style={{ color: '#1E293B' }}>{w}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
              <SectionDivider />
            </>
          )}

          {/* Objection Handlers */}
          {battleCard.objection_handlers?.length > 0 && (
            <>
              <SectionHeader title="Objection Handlers" />
              <ObjectionHandlingContent handlers={battleCard.objection_handlers} />
              <SectionDivider />
            </>
          )}

          {/* Recent News & Signals */}
          {hasNewsOrSignals && (
            <>
              <SectionHeader title="Recent News & Signals" />
              <div className="space-y-4">
                {/* Curated News */}
                {recentNews.length > 0 && (
                  <div className="space-y-3">
                    <span className="text-xs font-medium uppercase tracking-wider" style={{ color: '#5B6E8A' }}>
                      Curated News
                    </span>
                    {recentNews.map((news: BattleCardNewsItem, i: number) => (
                      <div
                        key={i}
                        className="rounded-lg border p-4 hover:shadow-sm transition-shadow duration-200"
                        style={{ backgroundColor: '#FFFFFF', borderColor: '#E2E8F0' }}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-1">
                              <Newspaper className="w-3.5 h-3.5 flex-shrink-0" style={{ color: '#5B6E8A' }} />
                              <h4 className="text-sm font-medium truncate" style={{ color: '#1E293B' }}>
                                {sanitizeSignalText(news.title, 200)}
                              </h4>
                            </div>
                            <div className="flex items-center gap-2 text-xs mb-2" style={{ color: '#5B6E8A' }}>
                              {news.source && <span>{news.source}</span>}
                              {news.source && news.date && <span>&middot;</span>}
                              {news.date && <span>{formatDate(news.date)}</span>}
                              {news.signal_type && (
                                <>
                                  <span>&middot;</span>
                                  <SignalTypeBadge type={news.signal_type} />
                                </>
                              )}
                            </div>
                            {news.relevance && (
                              <p className="text-xs leading-relaxed" style={{ color: '#475569' }}>
                                <span className="font-medium" style={{ color: '#5B6E8A' }}>Relevance: </span>
                                {news.relevance}
                              </p>
                            )}
                          </div>
                          {news.url && (
                            <a
                              href={news.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="flex-shrink-0 p-1.5 rounded hover:bg-[#F1F5F9] transition-colors"
                            >
                              <ExternalLink className="w-3.5 h-3.5" style={{ color: '#5B6E8A' }} />
                            </a>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Live Market Signals */}
                {recentSignals.length > 0 && (
                  <div className="space-y-2">
                    <span className="text-xs font-medium uppercase tracking-wider" style={{ color: '#5B6E8A' }}>
                      Live Market Signals
                    </span>
                    <div
                      className="rounded-lg border divide-y divide-[#F1F5F9]"
                      style={{ backgroundColor: '#FFFFFF', borderColor: '#E2E8F0' }}
                    >
                      {recentSignals.map((signal: BattleCardSignal) => (
                        <div
                          key={signal.id}
                          className="flex items-center gap-3 px-4 py-3 hover:bg-[#F8FAFC] transition-colors duration-150"
                        >
                          <SignalTypeBadge type={signal.signal_type} />
                          <span className="text-sm flex-1 min-w-0 truncate" style={{ color: '#1E293B' }}>
                            {sanitizeSignalText(signal.headline, 200)}
                          </span>
                          <span className="text-xs flex-shrink-0 font-mono" style={{ color: '#94A3B8' }}>
                            {formatDate(signal.detected_at)}
                          </span>
                          {signal.source_url && (
                            <a
                              href={signal.source_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="flex-shrink-0 p-1 rounded hover:bg-[#F1F5F9] transition-colors"
                            >
                              <ExternalLink className="w-3 h-3" style={{ color: '#94A3B8' }} />
                            </a>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
              <SectionDivider />
            </>
          )}

          {/* How to Win Strategies (from analysis.strategies) */}
          {(analysis.strategies?.length ?? 0) > 0 && (
            <>
              <SectionHeader title="Recommended Strategies" />
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {analysis.strategies!.map((strategy, index) => (
                  <div
                    key={index}
                    className="rounded-lg border p-4 hover:shadow-sm transition-all duration-200"
                    style={{ backgroundColor: '#FFFFFF', borderColor: '#E2E8F0' }}
                    data-aria-id={`strategy-${index}`}
                  >
                    <div className="flex items-start gap-3">
                      <div
                        className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0"
                        style={{ backgroundColor: '#F1F5F9' }}
                      >
                        {(() => {
                          const Icon = SIGNAL_TYPE_ICONS[strategy.icon] || Activity;
                          return <Icon className="w-4 h-4" style={{ color: '#2E66FF' }} />;
                        })()}
                      </div>
                      <div className="flex-1 min-w-0">
                        <h3 className="text-sm font-medium mb-1" style={{ color: '#1E293B' }}>
                          {strategy.title}
                        </h3>
                        <p className="text-xs leading-relaxed" style={{ color: '#5B6E8A' }}>
                          {strategy.description}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              <SectionDivider />
            </>
          )}

          {/* Feature Gap Analysis */}
          {(analysis.feature_gaps?.length ?? 0) > 0 && (
            <>
              <SectionHeader title="Feature Gap Analysis" />
              <div className="space-y-3">
                {analysis.feature_gaps!.map((gap, index) => {
                  const ariaLeads = gap.aria_score >= gap.competitor_score;
                  return (
                    <div key={index} className="py-1">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-sm font-medium" style={{ color: '#1E293B' }}>{gap.feature}</span>
                        <span
                          className="text-xs font-mono"
                          style={{ color: ariaLeads ? '#16A34A' : '#D97706' }}
                        >
                          {ariaLeads ? '+' : ''}{gap.aria_score - gap.competitor_score}
                        </span>
                      </div>
                      <div className="space-y-1.5">
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] w-10 flex-shrink-0 uppercase tracking-wider" style={{ color: '#5B6E8A' }}>Us</span>
                          <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ backgroundColor: '#E2E8F0' }}>
                            <div
                              className="h-full rounded-full transition-all duration-300"
                              style={{ width: `${gap.aria_score}%`, backgroundColor: '#2E66FF' }}
                            />
                          </div>
                          <span className="text-[10px] w-6 text-right font-mono" style={{ color: '#5B6E8A' }}>{gap.aria_score}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] w-10 flex-shrink-0 uppercase tracking-wider" style={{ color: '#5B6E8A' }}>Them</span>
                          <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ backgroundColor: '#E2E8F0' }}>
                            <div
                              className="h-full rounded-full transition-all duration-300"
                              style={{ width: `${gap.competitor_score}%`, backgroundColor: '#94A3B8' }}
                            />
                          </div>
                          <span className="text-[10px] w-6 text-right font-mono" style={{ color: '#5B6E8A' }}>{gap.competitor_score}</span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
              <SectionDivider />
            </>
          )}

          {/* Critical Gaps */}
          {(analysis.critical_gaps?.length ?? 0) > 0 && (() => {
            const advantages = analysis.critical_gaps!.filter(g => g.is_advantage);
            const disadvantages = analysis.critical_gaps!.filter(g => !g.is_advantage);
            return (
              <>
                <SectionHeader title="Critical Gaps" />
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {advantages.length > 0 && (
                    <div>
                      <span className="text-xs font-medium mb-3 block" style={{ color: '#16A34A' }}>
                        Our Advantages ({advantages.length})
                      </span>
                      <ul className="space-y-2">
                        {advantages.map((gap, i) => (
                          <li key={i} className="flex items-start gap-2">
                            <span className="text-emerald-500 mt-0.5 text-sm flex-shrink-0">{'\u2713'}</span>
                            <span className="text-sm leading-relaxed" style={{ color: '#1E293B' }}>{gap.description}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {disadvantages.length > 0 && (
                    <div>
                      <span className="text-xs font-medium mb-3 block" style={{ color: '#D97706' }}>
                        Competitor Advantages ({disadvantages.length})
                      </span>
                      <ul className="space-y-2">
                        {disadvantages.map((gap, i) => (
                          <li key={i} className="flex items-start gap-2">
                            <span className="text-amber-500 mt-0.5 text-sm flex-shrink-0">{'\u2717'}</span>
                            <span className="text-sm leading-relaxed" style={{ color: '#1E293B' }}>{gap.description}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
                <SectionDivider />
              </>
            );
          })()}

          {/* Freshness Footer */}
          <div className="flex items-center justify-between py-2" data-aria-id="freshness-footer">
            <span className="text-xs" style={{ color: '#94A3B8' }}>
              Last enriched: {formatDate(battleCard.last_updated)}
              {' \u00B7 '}
              Source: {formatSourceName(analysis.computation_method || battleCard.update_source)}
              {analysis.computation_method && analysis.computation_method !== battleCard.update_source && (
                <> + {formatSourceName(battleCard.update_source)}</>
              )}
            </span>
            {battleCard.signal_count != null && battleCard.signal_count > 0 && (
              <span className="text-xs" style={{ color: '#94A3B8' }}>
                {battleCard.signal_count} total signals tracked
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default BattleCardDetail;
