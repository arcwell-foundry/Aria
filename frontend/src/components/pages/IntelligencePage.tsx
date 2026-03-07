/**
 * IntelligencePage - Competitive intelligence overview and battle card views
 *
 * V2 Overhaul:
 * - Battle cards open a modal dossier on click (not navigate to detail page)
 * - Flexible grid (no empty cells)
 * - Competitor Activity Timeline (after battle cards)
 * - Therapeutic Trends with narratives + goal alignment
 * - Watch Topics section
 * - Market Signals with priority signals, deduplication, ARIA analysis
 * - Conference section with reasons on card, expandable details
 *
 * Routes:
 * - /intelligence -> IntelligenceOverview (V2)
 * - /intelligence/battle-cards/:competitorId -> BattleCardDetail (kept for deep links)
 */

import { useParams } from 'react-router-dom';
import { useState, useMemo } from 'react';
import { Newspaper, TrendingUp, FlaskConical, ChevronDown, ChevronUp, Target } from 'lucide-react';
import { useBattleCards } from '@/hooks/useBattleCards';
import { BattleCardPreview, BattleCardPreviewSkeleton, MarketSignalsFeed, ConferenceSection } from '@/components/intelligence';
import { BattleCardModal } from '@/components/intelligence/BattleCardModal';
import { WatchTopicsSection } from '@/components/intelligence/WatchTopicsSection';
import { CompetitorActivityTimeline } from '@/components/intelligence/CompetitorActivityTimeline';
import { EmptyState } from '@/components/common/EmptyState';
import {
  useUnreadSignalCount,
  useTherapeuticTrendsV2,
  useReturnBriefing,
} from '@/hooks/useIntelPanelData';
import { useIntelGoals } from '@/hooks/useIntelPanelData';
import { BattleCardDetail } from '@/components/pages/BattleCardDetail';

// Skeleton grid for loading state
function IntelligenceSkeleton() {
  return (
    <div className="space-y-8 animate-pulse">
      {/* Header skeleton */}
      <div>
        <div className="h-7 w-48 bg-[var(--border)] rounded mb-2" />
        <div className="h-4 w-64 bg-[var(--border)] rounded" />
      </div>

      {/* Battle cards grid skeleton */}
      <div>
        <div className="h-5 w-28 bg-[var(--border)] rounded mb-4" />
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 5 }).map((_, i) => (
            <BattleCardPreviewSkeleton key={i} />
          ))}
        </div>
      </div>

      {/* Market signals skeleton */}
      <div>
        <div className="h-5 w-32 bg-[var(--border)] rounded mb-4" />
        <div className="h-32 bg-[var(--border)] rounded-xl" />
      </div>
    </div>
  );
}


// Return Briefing Banner
function ReturnBriefingBanner() {
  const { data: briefing } = useReturnBriefing();
  const [dismissed, setDismissed] = useState(() => {
    return sessionStorage.getItem("aria_briefing_dismissed") === "true";
  });

  if (!briefing || dismissed) return null;

  const handleDismiss = () => {
    setDismissed(true);
    sessionStorage.setItem("aria_briefing_dismissed", "true");
  };

  const hoursAway = Math.round(briefing.hours_away);
  const daysAway = hoursAway >= 24 ? Math.round(hoursAway / 24) : null;
  const awayText = daysAway
    ? `${daysAway} day${daysAway > 1 ? "s" : ""}`
    : `${hoursAway} hours`;

  const signalCount = briefing.changes?.new_signals?.count ?? 0;
  const companyCount = briefing.changes?.new_signals?.by_company
    ? Object.keys(briefing.changes.new_signals.by_company).length
    : 0;
  const insightCount = briefing.changes?.new_insights?.count ?? 0;

  return (
    <div
      className="rounded-lg p-5 mb-6"
      style={{
        backgroundColor: "#EFF6FF",
        borderLeft: "4px solid #3B82F6",
      }}
    >
      <div className="flex items-start justify-between mb-2">
        <h3 className="text-sm font-semibold" style={{ color: "#1E40AF" }}>
          Welcome back! Here&apos;s what changed while you were away:
        </h3>
        <button
          onClick={handleDismiss}
          className="text-xs font-medium px-2 py-1 rounded hover:bg-blue-100 transition-colors"
          style={{ color: "#3B82F6" }}
        >
          Dismiss
        </button>
      </div>

      <p className="text-sm mb-3" style={{ color: "#1E40AF" }}>
        You were away for {awayText}.
        {signalCount > 0 &&
          ` ${signalCount} new market signal${signalCount !== 1 ? "s" : ""}`}
        {companyCount > 0 &&
          ` across ${companyCount} compan${companyCount !== 1 ? "ies" : "y"}`}
        {signalCount > 0 && "."}
        {insightCount > 0 &&
          ` ${insightCount} new intelligence insight${insightCount !== 1 ? "s" : ""}.`}
      </p>

      {briefing.priority_items && briefing.priority_items.length > 0 && (
        <div className="space-y-1.5">
          <span
            className="text-xs font-semibold uppercase tracking-wider"
            style={{ color: "#1E40AF" }}
          >
            Priority items:
          </span>
          {briefing.priority_items.map((item, i) => (
            <p key={i} className="text-sm" style={{ color: "#334155" }}>
              <span
                className="font-mono text-[10px] px-1 py-0.5 rounded mr-1.5"
                style={{ backgroundColor: "#DBEAFE", color: "#1E40AF" }}
              >
                {item.type?.toUpperCase()}
              </span>
              {item.company && (
                <span className="font-medium">{item.company}: </span>
              )}
              {item.text}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

// Therapeutic & Manufacturing Trends (V2 with narratives + goal alignment)
function TherapeuticTrendsSection() {
  const { data: trendsData } = useTherapeuticTrendsV2();
  const { data: goals } = useIntelGoals('active');
  const [expandedTrend, setExpandedTrend] = useState<string | null>(null);

  const trends = trendsData?.trends ?? [];

  // Match trends to goals by keyword overlap - MUST be before any early returns (React hooks rule)
  const goalMatches = useMemo(() => {
    const matches: Record<string, string> = {};
    if (!goals || trends.length === 0) return matches;
    for (const trend of trends) {
      const trendWords = trend.name.toLowerCase().split(/\s+/);
      for (const goal of goals) {
        const goalTitle = ((goal as { title?: string }).title ?? '').toLowerCase();
        if (trendWords.some((w) => w.length > 3 && goalTitle.includes(w))) {
          matches[trend.name] = (goal as { title?: string }).title ?? '';
          break;
        }
      }
      // Use backend-provided alignment if available
      if (trend.aligned_goal) {
        matches[trend.name] = trend.aligned_goal;
      }
    }
    return matches;
  }, [trends, goals]);

  if (trends.length === 0) return null;

  return (
    <section>
      <h2
        className="text-base font-medium mb-4 flex items-center gap-2"
        style={{ color: 'var(--text-primary)' }}
      >
        <FlaskConical className="w-4 h-4" style={{ color: 'var(--text-secondary)' }} />
        Therapeutic & Manufacturing Trends
      </h2>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {trends.map((trend) => {
          const isExpanded = expandedTrend === trend.name;
          const maxSignals = Math.max(...trends.map(t => t.signal_count));
          const barWidth = maxSignals > 0 ? (trend.signal_count / maxSignals) * 100 : 0;
          const matchedGoal = goalMatches[trend.name];

          return (
            <div
              key={trend.name}
              onClick={() => setExpandedTrend(isExpanded ? null : trend.name)}
              className="rounded-xl border p-4 cursor-pointer transition-all hover:-translate-y-0.5"
              style={{
                backgroundColor: '#FFFFFF',
                borderColor: isExpanded ? 'var(--accent)' : '#E2E8F0',
                boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
              }}
            >
              <div className="flex items-start justify-between mb-2">
                <h3 className="text-sm font-semibold" style={{ color: '#1E293B' }}>
                  {trend.name}
                </h3>
                {isExpanded ? (
                  <ChevronUp className="w-4 h-4" style={{ color: '#94A3B8' }} />
                ) : (
                  <ChevronDown className="w-4 h-4" style={{ color: '#94A3B8' }} />
                )}
              </div>
              <div className="flex items-center gap-4 text-xs mb-2" style={{ color: '#5B6E8A' }}>
                <span>{trend.signal_count} signals</span>
                <span>{trend.company_count} companies</span>
              </div>

              {/* Narrative line */}
              {trend.narrative && (
                <p className="text-xs mb-2 italic" style={{ color: '#5B6E8A' }}>
                  {trend.narrative}
                </p>
              )}

              {/* Goal alignment badge */}
              {matchedGoal && (
                <div
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium mb-2"
                  style={{ backgroundColor: '#EFF6FF', color: '#1E40AF' }}
                >
                  <Target className="w-3 h-3" />
                  Aligns with: {matchedGoal.length > 50 ? matchedGoal.slice(0, 50) + '...' : matchedGoal}
                </div>
              )}

              {/* Strength bar */}
              <div className="h-1.5 rounded-full overflow-hidden" style={{ backgroundColor: '#F1F5F9' }}>
                <div
                  className="h-full rounded-full transition-all"
                  style={{
                    width: `${barWidth}%`,
                    backgroundColor: trend.trend_type === 'therapeutic_area' ? '#a855f7' : '#06b6d4',
                  }}
                />
              </div>
              {/* Expanded: description */}
              {isExpanded && (
                <div className="mt-3 pt-3" style={{ borderTop: '1px solid #F1F5F9' }}>
                  <p className="text-xs leading-relaxed" style={{ color: '#5B6E8A' }}>
                    {trend.description}
                  </p>
                  {trend.companies_involved.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {trend.companies_involved.map((co) => (
                        <span
                          key={co}
                          className="text-[10px] px-1.5 py-0.5 rounded"
                          style={{ backgroundColor: '#F1F5F9', color: '#475569' }}
                        >
                          {co}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Market sizing coming soon note */}
      <p
        className="text-xs mt-3 text-center"
        style={{ color: '#94A3B8' }}
      >
        Market sizing estimates coming soon
      </p>
    </section>
  );
}

// Intelligence Overview Component (V2)
function IntelligenceOverview() {
  const { data: battleCards, isLoading, error } = useBattleCards();
  const { data: unreadCount } = useUnreadSignalCount();
  const [modalCompetitor, setModalCompetitor] = useState<string | null>(null);

  // Sort battle cards by threat_score descending (highest threat first)
  const sortedCards = useMemo(() => {
    if (!battleCards) return [];
    return [...battleCards].sort((a, b) => {
      const scoreA = a.analysis?.threat_score ?? 0;
      const scoreB = b.analysis?.threat_score ?? 0;
      return scoreB - scoreA;
    });
  }, [battleCards]);

  const hasBattleCards = sortedCards.length > 0;

  return (
    <div className="flex-1 overflow-y-auto p-8">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-1">
          {/* Status dot */}
          <div
            className="w-2 h-2 rounded-full"
            style={{ backgroundColor: 'var(--accent)' }}
          />
          <h1
            className="font-display text-2xl italic"
            style={{ color: 'var(--text-primary)' }}
          >
            Competitive Intelligence
          </h1>
        </div>
        <p
          className="text-sm ml-5"
          style={{ color: 'var(--text-secondary)' }}
        >
          Battle cards and market signals to win competitive deals.
        </p>
      </div>

      {/* Return Briefing */}
      <ReturnBriefingBanner />

      {/* Loading State */}
      {isLoading && <IntelligenceSkeleton />}

      {/* Error State */}
      {error && (
        <div
          className="text-center py-8"
          style={{ color: 'var(--text-secondary)' }}
        >
          Error loading battle cards. Please try again.
        </div>
      )}

      {/* Content */}
      {!isLoading && !error && (
        <div className="space-y-8">
          {/* Battle Cards Section */}
          <section>
            <h2
              className="text-base font-medium mb-4 flex items-center gap-2"
              style={{ color: 'var(--text-primary)' }}
            >
              <Newspaper className="w-4 h-4" style={{ color: 'var(--text-secondary)' }} />
              Battle Cards
            </h2>

            {!hasBattleCards ? (
              <EmptyState
                title="ARIA hasn't researched any competitors yet."
                description="Approve a competitive monitoring goal to start building battle cards automatically."
                suggestion="Set up competitor monitoring"
                onSuggestion={() => window.location.href = '/'}
                icon={<TrendingUp className="w-8 h-8" />}
              />
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                {sortedCards.map((card) => (
                  <div
                    key={card.id}
                    onClick={(e) => {
                      e.preventDefault();
                      setModalCompetitor(card.competitor_name);
                    }}
                  >
                    <BattleCardPreview
                      card={card}
                    />
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Competitor Activity Timeline */}
          <CompetitorActivityTimeline />

          {/* Therapeutic Trends Section */}
          <TherapeuticTrendsSection />

          {/* Watch Topics Section */}
          <WatchTopicsSection />

          {/* Conference Recommendations Section */}
          <ConferenceSection />

          {/* Market Signals Section */}
          <section>
            <h2
              className="text-base font-medium mb-4 flex items-center gap-2"
              style={{ color: 'var(--text-primary)' }}
            >
              <TrendingUp className="w-4 h-4" style={{ color: 'var(--text-secondary)' }} />
              Market Signals
              {(unreadCount?.count ?? 0) > 0 && (
                <span
                  className="px-2 py-0.5 rounded-full text-xs font-medium"
                  style={{ backgroundColor: 'var(--accent)', color: 'white' }}
                >
                  {unreadCount?.count} new
                </span>
              )}
            </h2>
            <MarketSignalsFeed />
          </section>
        </div>
      )}

      {/* Battle Card Modal */}
      {modalCompetitor && (
        <BattleCardModal
          competitorName={modalCompetitor}
          onClose={() => setModalCompetitor(null)}
        />
      )}
    </div>
  );
}

// Main IntelligencePage component
export function IntelligencePage() {
  const { competitorId } = useParams<{ competitorId: string }>();

  // Show detail view if competitorId is present (for deep links)
  if (competitorId) {
    return <BattleCardDetail competitorId={competitorId} />;
  }

  // Show overview
  return (
    <div
      className="flex-1 flex flex-col h-full"
      style={{ backgroundColor: 'var(--bg-primary)' }}
    >
      <IntelligenceOverview />
    </div>
  );
}
