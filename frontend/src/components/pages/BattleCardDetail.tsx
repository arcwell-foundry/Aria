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
import type { BattleCard, BattleCardObjectionHandler } from '@/api/battleCards';

// ============================================================================
// MOCK DATA (Will be replaced by enhanced API in future)
// ============================================================================

interface MockMetrics {
  marketCapGap: number;
  winRate: number;
  pricingDelta: number;
  lastSignalDays: number;
}

interface MockStrategy {
  id: string;
  title: string;
  description: string;
  icon: typeof Zap;
  agent: string;
  updatedAt: string;
}

interface MockFeatureGap {
  feature: string;
  ariaScore: number; // 0-100
  competitorScore: number; // 0-100
  ariaLeads: boolean;
}

interface MockCriticalGap {
  id: string;
  description: string;
  isAdvantage: boolean; // true = ARIA advantage, false = competitor advantage
}

const MOCK_METRICS: Record<string, MockMetrics> = {
  'Lonza': { marketCapGap: 12.5, winRate: 42, pricingDelta: 8.3, lastSignalDays: 2 },
  'Catalent': { marketCapGap: -8.2, winRate: 58, pricingDelta: -3.1, lastSignalDays: 1 },
  'Thermo Fisher': { marketCapGap: 45.3, winRate: 35, pricingDelta: 15.2, lastSignalDays: 6 },
  'WuXi AppTec': { marketCapGap: -3.1, winRate: 68, pricingDelta: -5.7, lastSignalDays: 0 },
  'Samsung Biologics': { marketCapGap: 22.8, winRate: 51, pricingDelta: 12.0, lastSignalDays: 14 },
  'Eurofins': { marketCapGap: -15.6, winRate: 72, pricingDelta: -8.9, lastSignalDays: 2 },
};

const MOCK_STRATEGIES: Record<string, MockStrategy[]> = {
  'Lonza': [
    { id: '1', title: 'Emphasize Speed', description: 'Highlight our 40% faster turnaround for small batches', icon: Zap, agent: 'Hunter', updatedAt: '2026-02-10T14:30:00Z' },
    { id: '2', title: 'Target Emerging Biotech', description: 'Focus on Series A-C companies underserved by Lonza\'s enterprise focus', icon: Target, agent: 'Strategist', updatedAt: '2026-02-09T10:15:00Z' },
    { id: '3', title: 'Quick Win: Pricing', description: 'Offer 15% discount on first project to dislodge incumbent', icon: Clock, agent: 'Operator', updatedAt: '2026-02-08T16:45:00Z' },
    { id: '4', title: 'Defend on Quality', description: 'Prepare case studies showing superior analytical capabilities', icon: Shield, agent: 'Analyst', updatedAt: '2026-02-07T09:00:00Z' },
  ],
  'Catalent': [
    { id: '1', title: 'Lead with Agility', description: 'Our decision-making is 3x faster for scope changes', icon: Zap, agent: 'Hunter', updatedAt: '2026-02-10T11:20:00Z' },
    { id: '2', title: 'Target Gene Therapy', description: 'Position strongly in cell/gene where Catalent is weak', icon: Target, agent: 'Strategist', updatedAt: '2026-02-09T15:30:00Z' },
    { id: '3', title: 'Quick Win: Capacity', description: 'Offer immediate slot availability for Q2 projects', icon: Clock, agent: 'Operator', updatedAt: '2026-02-08T10:00:00Z' },
    { id: '4', title: 'Defend on Scale', description: 'Show successful large-scale production track record', icon: Shield, agent: 'Analyst', updatedAt: '2026-02-07T14:15:00Z' },
  ],
  'Thermo Fisher': [
    { id: '1', title: 'Highlight Partnership', description: 'We act as partners, not vendors - dedicated teams', icon: Zap, agent: 'Hunter', updatedAt: '2026-02-09T09:00:00Z' },
    { id: '2', title: 'Target Mid-Market', description: 'Focus on companies too small for Thermo\'s attention', icon: Target, agent: 'Strategist', updatedAt: '2026-02-08T12:30:00Z' },
    { id: '3', title: 'Quick Win: Responsiveness', description: 'Guarantee 24-hour response on all inquiries', icon: Clock, agent: 'Operator', updatedAt: '2026-02-07T16:00:00Z' },
    { id: '4', title: 'Defend on Integration', description: 'Show seamless end-to-end process management', icon: Shield, agent: 'Analyst', updatedAt: '2026-02-06T10:45:00Z' },
  ],
};

const DEFAULT_STRATEGIES: MockStrategy[] = [
  { id: '1', title: 'Lead with Value', description: 'Focus on unique value propositions', icon: Zap, agent: 'Hunter', updatedAt: new Date().toISOString() },
  { id: '2', title: 'Strategic Positioning', description: 'Identify and target underserved market segments', icon: Target, agent: 'Strategist', updatedAt: new Date().toISOString() },
  { id: '3', title: 'Quick Win Available', description: 'Leverage immediate competitive advantages', icon: Clock, agent: 'Operator', updatedAt: new Date().toISOString() },
  { id: '4', title: 'Defensive Strategy', description: 'Prepare responses to common objections', icon: Shield, agent: 'Analyst', updatedAt: new Date().toISOString() },
];

const MOCK_FEATURE_GAPS: Record<string, MockFeatureGap[]> = {
  'Lonza': [
    { feature: 'Analytical Capabilities', ariaScore: 85, competitorScore: 75, ariaLeads: true },
    { feature: 'Small Batch Speed', ariaScore: 92, competitorScore: 65, ariaLeads: true },
    { feature: 'Global Footprint', ariaScore: 45, competitorScore: 88, ariaLeads: false },
    { feature: 'Regulatory Expertise', ariaScore: 78, competitorScore: 82, ariaLeads: false },
    { feature: 'Cost Competitiveness', ariaScore: 70, competitorScore: 72, ariaLeads: false },
    { feature: 'Technology Platform', ariaScore: 80, competitorScore: 78, ariaLeads: true },
  ],
  'Catalent': [
    { feature: 'Project Management', ariaScore: 88, competitorScore: 72, ariaLeads: true },
    { feature: 'Gene Therapy Expertise', ariaScore: 75, competitorScore: 60, ariaLeads: true },
    { feature: 'Manufacturing Scale', ariaScore: 55, competitorScore: 90, ariaLeads: false },
    { feature: 'Supply Chain', ariaScore: 65, competitorScore: 85, ariaLeads: false },
    { feature: 'Pricing Flexibility', ariaScore: 82, competitorScore: 68, ariaLeads: true },
    { feature: 'Client Communication', ariaScore: 90, competitorScore: 70, ariaLeads: true },
  ],
  'Thermo Fisher': [
    { feature: 'Personalized Service', ariaScore: 92, competitorScore: 55, ariaLeads: true },
    { feature: 'Mid-Market Focus', ariaScore: 88, competitorScore: 45, ariaLeads: true },
    { feature: 'Product Breadth', ariaScore: 40, competitorScore: 95, ariaLeads: false },
    { feature: 'Brand Recognition', ariaScore: 50, competitorScore: 92, ariaLeads: false },
    { feature: 'Technical Expertise', ariaScore: 78, competitorScore: 80, ariaLeads: false },
    { feature: 'Responsiveness', ariaScore: 85, competitorScore: 65, ariaLeads: true },
  ],
};

const DEFAULT_FEATURE_GAPS: MockFeatureGap[] = [
  { feature: 'Core Competency', ariaScore: 75, competitorScore: 75, ariaLeads: false },
  { feature: 'Market Position', ariaScore: 70, competitorScore: 70, ariaLeads: false },
  { feature: 'Service Quality', ariaScore: 80, competitorScore: 75, ariaLeads: true },
  { feature: 'Pricing', ariaScore: 65, competitorScore: 70, ariaLeads: false },
];

const MOCK_CRITICAL_GAPS: Record<string, MockCriticalGap[]> = {
  'Lonza': [
    { id: '1', description: 'Faster turnaround on small batch projects (avg. 4 weeks vs 6 weeks)', isAdvantage: true },
    { id: '2', description: 'More flexible contract terms for early-stage companies', isAdvantage: true },
    { id: '3', description: 'Dedicated project manager assigned to each client', isAdvantage: true },
    { id: '4', description: 'Competitor has larger global manufacturing footprint (6 sites vs 3)', isAdvantage: false },
    { id: '5', description: 'Competitor offers integrated supply chain services', isAdvantage: false },
  ],
  'Catalent': [
    { id: '1', description: 'Stronger gene therapy and cell therapy capabilities', isAdvantage: true },
    { id: '2', description: 'More responsive to scope changes (avg. 2 days vs 7 days)', isAdvantage: true },
    { id: '3', description: 'Better pricing transparency and predictability', isAdvantage: true },
    { id: '4', description: 'Competitor has significantly larger manufacturing capacity', isAdvantage: false },
    { id: '5', description: 'Competitor offers broader range of dosage forms', isAdvantage: false },
  ],
  'Thermo Fisher': [
    { id: '1', description: 'Higher touch, more personalized client experience', isAdvantage: true },
    { id: '2', description: 'Faster decision-making on scope changes', isAdvantage: true },
    { id: '3', description: 'More attention given to mid-market clients', isAdvantage: true },
    { id: '4', description: 'Competitor has vastly superior product portfolio breadth', isAdvantage: false },
    { id: '5', description: 'Competitor has stronger brand recognition globally', isAdvantage: false },
  ],
};

const DEFAULT_CRITICAL_GAPS: MockCriticalGap[] = [
  { id: '1', description: 'Personalized client service approach', isAdvantage: true },
  { id: '2', description: 'Flexible engagement models', isAdvantage: true },
  { id: '3', description: 'Competitor may have broader market presence', isAdvantage: false },
];

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

function formatLastSignal(days: number): string {
  if (days === 0) return 'Today';
  if (days === 1) return 'Yesterday';
  if (days < 7) return `${days} days ago`;
  if (days < 30) {
    const weeks = Math.floor(days / 7);
    return `${weeks}w ago`;
  }
  const months = Math.floor(days / 30);
  return `${months}mo ago`;
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
  strategy: MockStrategy;
}

function StrategyCard({ strategy }: StrategyCardProps) {
  const Icon = strategy.icon;

  return (
    <div
      className="rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] p-4 hover:border-[var(--accent)] transition-colors duration-200"
      data-aria-id={`strategy-${strategy.id}`}
    >
      <div className="flex items-start gap-3">
        <div
          className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0"
          style={{ backgroundColor: 'var(--bg-subtle)' }}
        >
          <Icon className="w-5 h-5" style={{ color: 'var(--accent)' }} />
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
  gap: MockFeatureGap;
}

function FeatureGapBar({ gap }: FeatureGapBarProps) {
  const [isHovered, setIsHovered] = useState(false);
  const delta = gap.ariaScore - gap.competitorScore;

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
        {gap.ariaLeads ? (
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
                width: `${gap.ariaScore}%`,
                backgroundColor: '#2E66FF',
              }}
            />
          </div>
          <span
            className="text-xs w-8 text-right font-mono"
            style={{ color: 'var(--text-secondary)' }}
          >
            {gap.ariaScore}
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
                width: `${gap.competitorScore}%`,
                backgroundColor: '#64748B',
              }}
            />
          </div>
          <span
            className="text-xs w-8 text-right font-mono"
            style={{ color: 'var(--text-secondary)' }}
          >
            {gap.competitorScore}
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
  gap: MockCriticalGap;
}

function CriticalGapItem({ gap }: CriticalGapItemProps) {
  return (
    <div
      className="flex items-start gap-3 py-2"
      data-aria-id={`critical-gap-${gap.id}`}
    >
      {gap.isAdvantage ? (
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
  getWinRate: (name: string) => number;
}

function CompetitorDropdown({ competitors, selectedName, onSelect, getWinRate }: CompetitorDropdownProps) {
  const [isOpen, setIsOpen] = useState(false);

  const selectedWinRate = getWinRate(selectedName);

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
              const winRate = getWinRate(comp.competitor_name);
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

  // Get mock data
  const metrics = useMemo(() => {
    if (!decodedName) return { marketCapGap: 0, winRate: 50, pricingDelta: 0, lastSignalDays: 7 };
    return MOCK_METRICS[decodedName] || { marketCapGap: 0, winRate: 50, pricingDelta: 0, lastSignalDays: 7 };
  }, [decodedName]);

  const strategies = useMemo(() => {
    if (!decodedName) return DEFAULT_STRATEGIES;
    return MOCK_STRATEGIES[decodedName] || DEFAULT_STRATEGIES;
  }, [decodedName]);

  const featureGaps = useMemo(() => {
    if (!decodedName) return DEFAULT_FEATURE_GAPS;
    return MOCK_FEATURE_GAPS[decodedName] || DEFAULT_FEATURE_GAPS;
  }, [decodedName]);

  const criticalGaps = useMemo(() => {
    if (!decodedName) return DEFAULT_CRITICAL_GAPS;
    return MOCK_CRITICAL_GAPS[decodedName] || DEFAULT_CRITICAL_GAPS;
  }, [decodedName]);

  // Separate advantages and gaps
  const advantages = criticalGaps.filter(g => g.isAdvantage);
  const gaps = criticalGaps.filter(g => !g.isAdvantage);

  // Get win rate for a competitor
  const getWinRateForCompetitor = (name: string): number => {
    return MOCK_METRICS[name]?.winRate ?? 50;
  };

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
                getWinRate={getWinRateForCompetitor}
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
            value={formatLastSignal(metrics.lastSignalDays)}
            sublabel="intelligence detected"
          />
        </div>

        {/* Sections */}
        <div className="space-y-6">
          {/* How to Win */}
          <Section
            title="How to Win"
            agent="Hunter"
            updatedAt={strategies[0]?.updatedAt || new Date().toISOString()}
          >
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {strategies.map((strategy) => (
                <StrategyCard key={strategy.id} strategy={strategy} />
              ))}
            </div>
          </Section>

          {/* Feature Gap Analysis */}
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

          {/* Critical Gaps */}
          <Section
            title="Critical Gaps"
            agent="Strategist"
            updatedAt={battleCard.last_updated}
          >
            {/* ARIA Advantages */}
            <div className="mb-6">
              <h3
                className="text-xs uppercase tracking-wide mb-3 flex items-center gap-2"
                style={{ color: 'var(--success)' }}
              >
                <CheckCircle2 className="w-3.5 h-3.5" />
                ARIA Advantages ({advantages.length})
              </h3>
              <div className="space-y-1">
                {advantages.map((gap) => (
                  <CriticalGapItem key={gap.id} gap={gap} />
                ))}
              </div>
            </div>

            {/* Competitor Advantages */}
            <div>
              <h3
                className="text-xs uppercase tracking-wide mb-3 flex items-center gap-2"
                style={{ color: 'var(--warning)' }}
              >
                <XCircle className="w-3.5 h-3.5" />
                Competitor Advantages ({gaps.length})
              </h3>
              <div className="space-y-1">
                {gaps.map((gap) => (
                  <CriticalGapItem key={gap.id} gap={gap} />
                ))}
              </div>
            </div>
          </Section>

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
