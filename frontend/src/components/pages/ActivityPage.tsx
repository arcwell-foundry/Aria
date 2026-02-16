/**
 * ActivityPage - Agent Activity Feed
 *
 * Follows ARIA Design System v1.0:
 * - LIGHT THEME (content pages use light background)
 * - Header: "Activity // Agent Feed" with status dot
 * - Search bar + agent filter chips + type filter chips
 * - Activity cards with agent avatars, timestamps, and entity navigation
 */

import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Search,
  Users,
  Shield,
  Mail,
  Calendar,
  Radio,
  Activity,
} from 'lucide-react';
import { cn } from '@/utils/cn';
import { useActivityFeed } from '@/hooks/useActivity';
import { EmptyState } from '@/components/common/EmptyState';
import { AgentAvatar } from '@/components/common/AgentAvatar';
import { resolveAgent } from '@/constants/agents';
import type { ActivityItem, ActivityFilters } from '@/api/activity';

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

function ActivitySkeleton() {
  return (
    <div className="space-y-3 animate-pulse">
      {Array.from({ length: 6 }).map((_, i) => (
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
// ActivityItemCard
// ---------------------------------------------------------------------------

function ActivityItemCard({
  item,
  onClick,
}: {
  item: ActivityItem;
  onClick?: () => void;
}) {
  const Icon = ACTIVITY_TYPE_ICONS[item.activity_type] ?? Activity;
  const agent = item.agent ? resolveAgent(item.agent) : null;

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!onClick}
      data-aria-id={`activity-item-${item.id}`}
      className={cn(
        'w-full text-left border border-[var(--border)] rounded-lg p-4 transition-colors duration-150',
        onClick && 'cursor-pointer hover:border-[var(--accent)]',
      )}
      style={{ backgroundColor: 'var(--bg-elevated)' }}
    >
      <div className="flex items-start gap-3">
        {/* Icon */}
        <div
          className="w-8 h-8 rounded-full flex items-center justify-center shrink-0"
          style={{
            backgroundColor: agent?.color ? `${agent.color}15` : 'var(--bg-subtle)',
            color: agent?.color ?? 'var(--text-secondary)',
          }}
        >
          <Icon className="w-4 h-4" />
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <p
            className="text-sm font-medium truncate"
            style={{ color: 'var(--text-primary)' }}
          >
            {item.title}
          </p>
          <p
            className="text-xs mt-0.5 line-clamp-2"
            style={{ color: 'var(--text-secondary)' }}
          >
            {item.description}
          </p>

          {/* Agent badge */}
          {agent && (
            <div className="flex items-center gap-1.5 mt-2">
              <AgentAvatar agentKey={agent.type} size={16} />
              <span
                className="text-xs font-medium"
                style={{ color: agent.color }}
              >
                {agent.name}
              </span>
            </div>
          )}
        </div>

        {/* Timestamp */}
        <span
          className="font-mono text-xs shrink-0"
          style={{ color: 'var(--text-secondary)' }}
        >
          {formatRelativeTime(item.created_at)}
        </span>
      </div>
    </button>
  );
}

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
      style={
        active
          ? undefined
          : { backgroundColor: 'var(--bg-subtle)' }
      }
    >
      {label}
    </button>
  );
}

// ---------------------------------------------------------------------------
// ActivityFeed (internal)
// ---------------------------------------------------------------------------

function ActivityFeed() {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [agentFilter, setAgentFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState('');

  const filters = useMemo<ActivityFilters>(() => {
    const f: ActivityFilters = { limit: 50 };
    if (agentFilter) f.agent = agentFilter;
    if (typeFilter) f.activity_type = typeFilter;
    if (search.trim()) f.search = search.trim();
    return f;
  }, [agentFilter, typeFilter, search]);

  const { data, isLoading, error } = useActivityFeed(filters);

  const handleItemClick = (item: ActivityItem) => {
    if (item.related_entity_type && item.related_entity_id) {
      const routeBuilder = ENTITY_ROUTES[item.related_entity_type];
      if (routeBuilder) {
        navigate(routeBuilder(item.related_entity_id));
      }
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
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

      {/* Agent filter chips */}
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

      {/* Type filter chips */}
      <div className="flex flex-wrap gap-2">
        {TYPE_FILTERS.map((f) => (
          <FilterChip
            key={f.value}
            label={f.label}
            active={typeFilter === f.value}
            onClick={() => setTypeFilter(f.value)}
          />
        ))}
      </div>

      {/* Content */}
      {isLoading && <ActivitySkeleton />}

      {error && (
        <p className="text-sm" style={{ color: 'var(--critical)' }}>
          Failed to load activity feed. Please try again.
        </p>
      )}

      {!isLoading && !error && (!data?.activities || data.activities.length === 0) && (
        <EmptyState
          title="ARIA hasn't taken any actions yet."
          description="Once ARIA begins working on your behalf, autonomous actions and intelligence operations will appear here."
          suggestion="Talk to ARIA"
          onSuggestion={() => navigate('/')}
        />
      )}

      {!isLoading && !error && data?.activities && data.activities.length > 0 && (
        <div className="space-y-3">
          {data.activities.map((item) => (
            <ActivityItemCard
              key={item.id}
              item={item}
              onClick={
                item.related_entity_type && item.related_entity_id
                  ? () => handleItemClick(item)
                  : undefined
              }
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ActivityPage (exported wrapper)
// ---------------------------------------------------------------------------

export function ActivityPage() {
  return (
    <div
      className="flex-1 flex flex-col h-full"
      style={{ backgroundColor: 'var(--bg-primary)' }}
      data-aria-id="activity-page"
    >
      <div className="flex-1 overflow-y-auto p-8">
        <ActivityFeed />
      </div>
    </div>
  );
}
