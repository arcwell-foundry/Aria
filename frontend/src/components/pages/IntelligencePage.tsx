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
 * Routes:
 * - /intelligence -> IntelligenceOverview
 * - /intelligence/battle-cards/:competitorId -> BattleCardDetail
 */

import { useParams } from 'react-router-dom';
import { Newspaper, TrendingUp } from 'lucide-react';
import { cn } from '@/utils/cn';
import { useBattleCards } from '@/hooks/useBattleCards';
import { BattleCardPreview, BattleCardPreviewSkeleton } from '@/components/intelligence';
import { EmptyState } from '@/components/common/EmptyState';
import { BattleCardDetail } from '@/components/pages/BattleCardDetail';
import type { BattleCard } from '@/api/battleCards';

// Mock data for market cap gaps (would come from enhanced API in future)
const MOCK_MARKET_CAP_GAPS: Record<string, number> = {
  'Lonza': 12.5,
  'Catalent': -8.2,
  'Thermo Fisher': 45.3,
  'WuXi AppTec': -3.1,
  'Samsung Biologics': 22.8,
  'Eurofins': -15.6,
};

// Mock data for win rates (would come from analytics in future)
const MOCK_WIN_RATES: Record<string, number> = {
  'Lonza': 42,
  'Catalent': 58,
  'Thermo Fisher': 35,
  'WuXi AppTec': 68,
  'Samsung Biologics': 51,
  'Eurofins': 72,
};

// Mock data for last signals (would come from signal detection API)
const MOCK_LAST_SIGNALS: Record<string, string | null> = {
  'Lonza': '2026-02-08T14:30:00Z',
  'Catalent': '2026-02-10T09:15:00Z',
  'Thermo Fisher': '2026-02-05T16:45:00Z',
  'WuXi AppTec': null,
  'Samsung Biologics': '2026-01-28T11:20:00Z',
  'Eurofins': '2026-02-09T08:00:00Z',
};

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

  // Get mock data for a battle card
  const getMockData = (card: BattleCard) => ({
    marketCapGap: MOCK_MARKET_CAP_GAPS[card.competitor_name] ?? 0,
    winRate: MOCK_WIN_RATES[card.competitor_name] ?? 50,
    lastSignalAt: MOCK_LAST_SIGNALS[card.competitor_name] ?? card.last_updated,
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
                  const mockData = getMockData(card);
                  return (
                    <BattleCardPreview
                      key={card.id}
                      card={card}
                      marketCapGap={mockData.marketCapGap}
                      winRate={mockData.winRate}
                      lastSignalAt={mockData.lastSignalAt}
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
            </h2>

            <div
              className={cn(
                'rounded-xl p-6 border border-[var(--border)]',
                'bg-[var(--bg-elevated)]'
              )}
            >
              <EmptyState
                title="Market signal detection coming soon"
                description="ARIA will automatically detect competitor pricing changes, product launches, and strategic moves."
                icon={<TrendingUp className="w-8 h-8" />}
              />
            </div>
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
