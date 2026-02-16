/**
 * IntelligencePage - Competitive intelligence overview and battle card views
 *
 * Follows ARIA Design System v1.0:
 * - LIGHT THEME (content pages use light background)
 * - Header: "Competitive Intelligence" with subtitle
 * - Battle Cards section: Grid of competitor cards
 * - Market Signals section: Empty state (no API yet)
 * - Empty state drives to ARIA conversation
 *
 * All data sourced from the battle_cards API (analysis JSONB column).
 *
 * Routes:
 * - /intelligence -> IntelligenceOverview
 * - /intelligence/battle-cards/:competitorId -> BattleCardDetail
 */

import { useParams } from 'react-router-dom';
import { Newspaper, TrendingUp } from 'lucide-react';
import { useBattleCards } from '@/hooks/useBattleCards';
import { BattleCardPreview, BattleCardPreviewSkeleton, MarketSignalsFeed } from '@/components/intelligence';
import { EmptyState } from '@/components/common/EmptyState';
import { useUnreadSignalCount } from '@/hooks/useIntelPanelData';
import { BattleCardDetail } from '@/components/pages/BattleCardDetail';
import type { BattleCard } from '@/api/battleCards';

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
          {Array.from({ length: 6 }).map((_, i) => (
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


// Intelligence Overview Component
function IntelligenceOverview() {
  const { data: battleCards, isLoading, error } = useBattleCards();
  const { data: unreadCount } = useUnreadSignalCount();

  // Extract analysis data from each battle card
  const getCardData = (card: BattleCard) => ({
    marketCapGap: card.analysis?.metrics?.market_cap_gap ?? 0,
    winRate: card.analysis?.metrics?.win_rate ?? 50,
    lastSignalAt: card.analysis?.metrics?.last_signal_at ?? card.last_updated,
  });

  const hasBattleCards = battleCards && battleCards.length > 0;

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
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {battleCards.map((card) => {
                  const cardData = getCardData(card);
                  return (
                    <BattleCardPreview
                      key={card.id}
                      card={card}
                      marketCapGap={cardData.marketCapGap}
                      winRate={cardData.winRate}
                      lastSignalAt={cardData.lastSignalAt}
                    />
                  );
                })}
              </div>
            )}
          </section>

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
    </div>
  );
}

// Main IntelligencePage component
export function IntelligencePage() {
  const { competitorId } = useParams<{ competitorId: string }>();

  // Show detail view if competitorId is present
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
