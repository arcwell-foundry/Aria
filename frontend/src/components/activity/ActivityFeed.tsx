/**
 * ActivityFeed — Reusable activity feed with infinite scroll, filtering, and polling.
 *
 * Modes:
 *   - Full (default): Header, search, agent/type filter chips, date range, infinite scroll.
 *   - Compact (compact=true): Slim cards, no header/search, limited height, "View all" link.
 *
 * Real-time: Polls /activity/poll every 10s. Shows a "New activity" banner when new items
 * arrive — clicking it prepends the items and resets the poll cursor.
 */

import { memo, useState, useMemo, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Virtuoso } from 'react-virtuoso';
import {
  Search,
  Users,
  Shield,
  Mail,
  Calendar,
  Radio,
  Activity,
  ChevronDown,
  ArrowUp,
  GitBranch,
} from 'lucide-react';
import { cn } from '@/utils/cn';
import { useActivityFeed, useActivityPoll } from '@/hooks/useActivity';
import { EmptyState } from '@/components/common/EmptyState';
import { AgentAvatar } from '@/components/common/AgentAvatar';
import { resolveAgent } from '@/constants/agents';
import type { ActivityItem, ActivityFilters } from '@/api/activity';
import { DelegationTreeDrawer } from '@/components/traces/DelegationTreeDrawer';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const AGENT_FILTERS = [
  { label: 'All Agents', value: '' },
  { label: 'Hunter', value: 'hunter' },
  { label: 'Analyst', value: 'analyst' },
  { label: 'Strategist', value: 'strategist' },
  { label: 'Scribe', value: 'scribe' },
  { label: 'Operator', value: 'operator' },
  { label: 'Scout', value: 'scout' },
];

const TYPE_FILTERS = [
  { label: 'All Types', value: '' },
  { label: 'Lead Found', value: 'lead_discovered' },
  { label: 'Battle Card', value: 'battle_card_updated' },
  { label: 'Email Drafted', value: 'email_drafted' },
  { label: 'Meeting Prepped', value: 'meeting_prepped' },
  { label: 'Signal Detected', value: 'signal_detected' },
];

const ACTIVITY_TYPE_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  lead_discovered: Users,
  battle_card_updated: Shield,
  email_drafted: Mail,
  meeting_prepped: Calendar,
  signal_detected: Radio,
};

const ENTITY_ROUTES: Record<string, (id: string) => string> = {
  lead: (id) => `/pipeline/leads/${id}`,
  draft: (id) => `/communications/drafts/${id}`,
  goal: (id) => `/actions/goals/${id}`,
  battle_card: (id) => `/intelligence/battle-cards/${id}`,
  contact: (id) => `/pipeline/leads/${id}`,
  company: (id) => `/pipeline/leads/${id}`,
};

const ENTITY_LABELS: Record<string, string> = {
  lead: 'Lead',
  draft: 'Draft',
  goal: 'Goal',
  battle_card: 'Battle Card',
  contact: 'Contact',
  company: 'Company',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

function ActivitySkeleton({ count = 6 }: { count?: number }) {
  return (
    <div className="space-y-3 animate-pulse">
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="border border-[var(--border)] rounded-lg p-4"
          style={{ backgroundColor: 'var(--bg-elevated)' }}
        >
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-full bg-[var(--border)]" />
            <div className="flex-1 space-y-2">
              <div className="h-4 w-48 bg-[var(--border)] rounded" />
              <div className="h-3 w-72 bg-[var(--border)] rounded" />
            </div>
            <div className="h-3 w-16 bg-[var(--border)] rounded" />
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// EntityBadge
// ---------------------------------------------------------------------------

function EntityBadge({
  entityType,
  entityId,
  onClick,
}: {
  entityType: string;
  entityId: string;
  onClick: () => void;
}) {
  const label = ENTITY_LABELS[entityType] ?? entityType;

  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      className={cn(
        'inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-mono',
        'border border-[var(--accent)]/20 text-[var(--accent)]',
        'hover:bg-[var(--accent)]/10 transition-colors duration-150',
      )}
    >
      {label}
      <span className="opacity-60">{entityId.slice(0, 6)}</span>
    </button>
  );
}

// ---------------------------------------------------------------------------
// ActivityItemCard
// ---------------------------------------------------------------------------

const ActivityItemCard = memo(function ActivityItemCard({
  item,
  compact,
  onNavigate,
  onViewTree,
}: {
  item: ActivityItem;
  compact?: boolean;
  onNavigate?: (route: string) => void;
  onViewTree?: (goalId: string, title: string) => void;
}) {
  const Icon = ACTIVITY_TYPE_ICONS[item.activity_type] ?? Activity;
  const agent = item.agent ? resolveAgent(item.agent) : null;

  const handleEntityClick = () => {
    if (item.related_entity_type && item.related_entity_id && onNavigate) {
      const routeBuilder = ENTITY_ROUTES[item.related_entity_type];
      if (routeBuilder) {
        onNavigate(routeBuilder(item.related_entity_id));
      }
    }
  };

  const hasEntity = item.related_entity_type && item.related_entity_id;

  return (
    <div
      data-aria-id={`activity-item-${item.id}`}
      className={cn(
        'border border-[var(--border)] rounded-lg transition-colors duration-150',
        compact ? 'p-3' : 'p-4',
      )}
      style={{ backgroundColor: 'var(--bg-elevated)' }}
    >
      <div className="flex items-start gap-3">
        {/* Agent avatar / Icon */}
        <div
          className={cn(
            'rounded-full flex items-center justify-center shrink-0',
            compact ? 'w-7 h-7' : 'w-8 h-8',
          )}
          style={{
            backgroundColor: agent?.color ? `${agent.color}15` : 'var(--bg-subtle)',
            color: agent?.color ?? 'var(--text-secondary)',
          }}
        >
          {agent ? (
            <AgentAvatar agentKey={agent.type} size={compact ? 20 : 24} />
          ) : (
            <Icon className={compact ? 'w-3.5 h-3.5' : 'w-4 h-4'} />
          )}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <p
              className={cn(
                'font-medium truncate',
                compact ? 'text-xs' : 'text-sm',
              )}
              style={{ color: 'var(--text-primary)' }}
            >
              {item.title}
            </p>
            {agent && !compact && (
              <span
                className="text-[10px] font-medium px-1.5 py-0.5 rounded"
                style={{
                  backgroundColor: `${agent.color}15`,
                  color: agent.color,
                }}
              >
                {agent.name}
              </span>
            )}
          </div>

          {!compact && (
            <p
              className="text-xs mt-0.5 line-clamp-2"
              style={{ color: 'var(--text-secondary)' }}
            >
              {item.description}
            </p>
          )}

          {/* Entity badge */}
          {hasEntity && (
            <div className="mt-1.5">
              <EntityBadge
                entityType={item.related_entity_type!}
                entityId={item.related_entity_id!}
                onClick={handleEntityClick}
              />
            </div>
          )}

          {/* Delegation tree link for goal-related items */}
          {item.related_entity_type === 'goal' && item.related_entity_id && onViewTree && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onViewTree(item.related_entity_id!, item.title);
              }}
              className="flex items-center gap-1 mt-1 text-[11px] font-medium transition-colors hover:opacity-80"
              style={{ color: 'var(--accent)' }}
            >
              <GitBranch className="w-3 h-3" />
              View delegation tree
            </button>
          )}
        </div>

        {/* Timestamp */}
        <span
          className={cn(
            'font-mono shrink-0',
            compact ? 'text-[10px]' : 'text-xs',
          )}
          style={{ color: 'var(--text-secondary)' }}
        >
          {formatRelativeTime(item.created_at)}
        </span>
      </div>
    </div>
  );
});

// ---------------------------------------------------------------------------
// FilterChip
// ---------------------------------------------------------------------------

function FilterChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'px-3 py-1.5 rounded-full text-xs font-medium transition-colors duration-150',
        active
          ? 'bg-[var(--accent)] text-white'
          : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]',
      )}
      style={active ? undefined : { backgroundColor: 'var(--bg-subtle)' }}
    >
      {label}
    </button>
  );
}

// ---------------------------------------------------------------------------
// NewActivityBanner
// ---------------------------------------------------------------------------

function NewActivityBanner({
  count,
  onClick,
}: {
  count: number;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'w-full flex items-center justify-center gap-2 py-2.5 rounded-lg',
        'bg-[var(--accent)] text-white text-sm font-medium',
        'hover:bg-[var(--accent)]/90 transition-colors duration-150',
        'animate-in slide-in-from-top-2 fade-in duration-300',
      )}
    >
      <ArrowUp className="w-4 h-4" />
      {count} new activit{count === 1 ? 'y' : 'ies'}
    </button>
  );
}

// ---------------------------------------------------------------------------
// ActivityFeed (exported)
// ---------------------------------------------------------------------------

export interface ActivityFeedProps {
  /** Compact mode for dashboard widget embedding. */
  compact?: boolean;
  /** Max items to display in compact mode (default 5). */
  compactLimit?: number;
  /** Pre-applied filter (e.g., show only a specific agent's activity). */
  initialAgent?: string;
  /** Pre-applied type filter. */
  initialType?: string;
}

export function ActivityFeed({
  compact = false,
  compactLimit = 5,
  initialAgent = '',
  initialType = '',
}: ActivityFeedProps) {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [agentFilter, setAgentFilter] = useState(initialAgent);
  const [typeFilter, setTypeFilter] = useState(initialType);
  const [dateStart, setDateStart] = useState('');
  const [dateEnd, setDateEnd] = useState('');
  const [pendingItems, setPendingItems] = useState<ActivityItem[]>([]);
  const [treeGoalId, setTreeGoalId] = useState<string | null>(null);
  const [treeGoalTitle, setTreeGoalTitle] = useState('');

  // Build filters (excluding page/page_size — handled by infinite query)
  const filters = useMemo<Omit<ActivityFilters, 'page' | 'page_size'>>(() => {
    const f: Omit<ActivityFilters, 'page' | 'page_size'> = {};
    if (agentFilter) f.agent = agentFilter;
    if (typeFilter) f.type = typeFilter;
    if (dateStart) f.since = dateStart;
    return f;
  }, [agentFilter, typeFilter, dateStart]);

  const {
    data,
    isLoading,
    error,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useActivityFeed(filters);

  // Flatten pages into single list
  const allItems = useMemo(() => {
    if (!data?.pages) return [];
    return data.pages.flatMap((page) => page.items);
  }, [data]);

  // Track the latest created_at for polling cursor
  const latestTimestamp = useMemo(() => {
    if (pendingItems.length > 0) return pendingItems[0].created_at;
    if (allItems.length > 0) return allItems[0].created_at;
    return null;
  }, [allItems, pendingItems]);

  // Poll for new items
  const { data: pollData } = useActivityPoll(latestTimestamp);

  // When poll returns new items, stash them in pendingItems
  useEffect(() => {
    if (pollData && pollData.count > 0) {
      setPendingItems((prev) => {
        const existingIds = new Set(prev.map((i) => i.id));
        const newItems = pollData.items.filter((i) => !existingIds.has(i.id));
        if (newItems.length === 0) return prev;
        return [...newItems, ...prev];
      });
    }
  }, [pollData]);

  // Flush pending items into the feed
  const flushPending = useCallback(() => {
    setPendingItems([]);
    // Refetch to get latest data merged in
    // The query will re-fetch page 1 which includes the new items
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, []);

  const handleNavigate = useCallback((route: string) => navigate(route), [navigate]);

  const handleViewTree = useCallback((goalId: string, title: string) => {
    setTreeGoalId(goalId);
    setTreeGoalTitle(title);
  }, []);

  // Virtuoso endReached callback for infinite scroll (full mode only)
  const handleEndReached = useCallback(() => {
    if (hasNextPage && !isFetchingNextPage) {
      fetchNextPage();
    }
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  // In compact mode, only show compactLimit items
  const displayItems = compact ? allItems.slice(0, compactLimit) : allItems;

  // -------------------------------------------------------------------------
  // Compact mode render
  // -------------------------------------------------------------------------

  if (compact) {
    return (
      <div data-aria-id="activity-feed-compact">
        {isLoading && <ActivitySkeleton count={3} />}

        {!isLoading && displayItems.length === 0 && (
          <p
            className="text-xs text-center py-4"
            style={{ color: 'var(--text-secondary)' }}
          >
            No recent activity.
          </p>
        )}

        {!isLoading && displayItems.length > 0 && (
          <div className="space-y-2">
            {pendingItems.length > 0 && (
              <NewActivityBanner count={pendingItems.length} onClick={flushPending} />
            )}
            {displayItems.map((item) => (
              <ActivityItemCard
                key={item.id}
                item={item}
                compact
                onNavigate={handleNavigate}
                onViewTree={handleViewTree}
              />
            ))}
            {allItems.length > compactLimit && (
              <button
                type="button"
                onClick={() => navigate('/activity')}
                className="w-full text-center text-xs font-medium py-2 rounded-lg hover:bg-[var(--bg-subtle)] transition-colors"
                style={{ color: 'var(--accent)' }}
              >
                View all activity
              </button>
            )}
          </div>
        )}

        <DelegationTreeDrawer
          goalId={treeGoalId}
          goalTitle={treeGoalTitle}
          onClose={() => setTreeGoalId(null)}
        />
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // Full mode render
  // -------------------------------------------------------------------------

  return (
    <div
      className="max-w-4xl mx-auto space-y-6"
      data-aria-id="activity-feed"
    >
      {/* Header */}
      <div className="flex items-center gap-3">
        <span
          className="w-3 h-3 rounded-full shrink-0"
          style={{ backgroundColor: 'var(--success)' }}
        />
        <div>
          <p
            className="font-mono text-xs uppercase tracking-wider"
            style={{ color: 'var(--text-secondary)' }}
          >
            Activity
          </p>
          <h1
            className="font-display text-2xl italic"
            style={{ color: 'var(--text-primary)' }}
          >
            Agent Feed
          </h1>
        </div>
      </div>

      <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
        ARIA's autonomous actions and intelligence operations.
      </p>

      {/* Search bar */}
      <div
        className="flex items-center gap-2 px-3 py-2 rounded-lg border border-[var(--border)]"
        style={{ backgroundColor: 'var(--bg-elevated)' }}
      >
        <Search className="w-4 h-4 shrink-0" style={{ color: 'var(--text-secondary)' }} />
        <input
          type="text"
          placeholder="Search activity..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 bg-transparent text-sm outline-none placeholder:text-[var(--text-secondary)]"
          style={{ color: 'var(--text-primary)' }}
        />
      </div>

      {/* Filter bar */}
      <div className="space-y-3">
        {/* Agent chips */}
        <div className="flex flex-wrap gap-2">
          {AGENT_FILTERS.map((f) => (
            <FilterChip
              key={f.value}
              label={f.label}
              active={agentFilter === f.value}
              onClick={() => setAgentFilter(f.value)}
            />
          ))}
        </div>

        {/* Type dropdown + date range */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Type dropdown */}
          <div className="relative">
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className={cn(
                'appearance-none pl-3 pr-8 py-1.5 rounded-lg text-xs font-medium',
                'border border-[var(--border)] outline-none cursor-pointer',
              )}
              style={{
                backgroundColor: 'var(--bg-elevated)',
                color: typeFilter ? 'var(--accent)' : 'var(--text-secondary)',
              }}
            >
              {TYPE_FILTERS.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}
                </option>
              ))}
            </select>
            <ChevronDown
              className="absolute right-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 pointer-events-none"
              style={{ color: 'var(--text-secondary)' }}
            />
          </div>

          {/* Date range */}
          <div className="flex items-center gap-2">
            <input
              type="date"
              value={dateStart}
              onChange={(e) => setDateStart(e.target.value)}
              className={cn(
                'px-2 py-1.5 rounded-lg text-xs border border-[var(--border)] outline-none',
              )}
              style={{
                backgroundColor: 'var(--bg-elevated)',
                color: 'var(--text-secondary)',
              }}
            />
            <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
              to
            </span>
            <input
              type="date"
              value={dateEnd}
              onChange={(e) => setDateEnd(e.target.value)}
              className={cn(
                'px-2 py-1.5 rounded-lg text-xs border border-[var(--border)] outline-none',
              )}
              style={{
                backgroundColor: 'var(--bg-elevated)',
                color: 'var(--text-secondary)',
              }}
            />
          </div>

          {/* Clear filters */}
          {(agentFilter || typeFilter || dateStart || dateEnd || search) && (
            <button
              type="button"
              onClick={() => {
                setAgentFilter('');
                setTypeFilter('');
                setDateStart('');
                setDateEnd('');
                setSearch('');
              }}
              className="text-xs underline"
              style={{ color: 'var(--text-secondary)' }}
            >
              Clear filters
            </button>
          )}
        </div>
      </div>

      {/* New activity banner */}
      {pendingItems.length > 0 && (
        <NewActivityBanner count={pendingItems.length} onClick={flushPending} />
      )}

      {/* Content */}
      {isLoading && <ActivitySkeleton />}

      {error && (
        <p className="text-sm" style={{ color: 'var(--critical)' }}>
          Failed to load activity feed. Please try again.
        </p>
      )}

      {!isLoading && !error && displayItems.length === 0 && (
        <EmptyState
          title="ARIA hasn't taken any actions yet."
          description="Once ARIA begins working on your behalf, autonomous actions and intelligence operations will appear here."
          suggestion="Talk to ARIA"
          onSuggestion={() => navigate('/')}
        />
      )}

      {!isLoading && !error && displayItems.length > 0 && (
        <Virtuoso
          useWindowScroll
          totalCount={displayItems.length}
          endReached={handleEndReached}
          overscan={200}
          itemContent={(index) => (
            <div className="pb-3">
              <ActivityItemCard
                item={displayItems[index]}
                onNavigate={handleNavigate}
                onViewTree={handleViewTree}
              />
            </div>
          )}
          components={{
            Footer: () => (
              <>
                {isFetchingNextPage && (
                  <div className="flex justify-center py-4">
                    <div className="w-5 h-5 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin" />
                  </div>
                )}
                {!hasNextPage && displayItems.length > 0 && (
                  <p
                    className="text-xs text-center py-4"
                    style={{ color: 'var(--text-secondary)' }}
                  >
                    All activity loaded.
                  </p>
                )}
              </>
            ),
          }}
        />
      )}

      <DelegationTreeDrawer
        goalId={treeGoalId}
        goalTitle={treeGoalTitle}
        onClose={() => setTreeGoalId(null)}
      />
    </div>
  );
}
