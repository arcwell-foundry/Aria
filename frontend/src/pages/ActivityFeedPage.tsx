/** Activity Feed page - ARIA command center showing agent activity (US-940). */

import { useState, useMemo, useCallback } from "react";
import { Link } from "react-router-dom";
import { DashboardLayout } from "@/components/DashboardLayout";
import { useActivityFeed, useAgentStatus } from "@/hooks/useActivity";
import type {
  ActivityItem,
  ActivityFilters,
  AgentStatusItem,
} from "@/api/activity";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const AGENTS = ["hunter", "analyst", "strategist", "scribe", "operator", "scout"] as const;
type AgentName = (typeof AGENTS)[number];

const ACTIVITY_TYPES = [
  "research_complete",
  "email_drafted",
  "signal_detected",
  "goal_progressed",
  "agent_activated",
  "crm_synced",
] as const;

const AGENT_COLORS: Record<AgentName, string> = {
  hunter: "emerald",
  analyst: "blue",
  strategist: "violet",
  scribe: "amber",
  operator: "rose",
  scout: "cyan",
};

const ACTIVITY_TYPE_LABELS: Record<string, string> = {
  research_complete: "Research",
  email_drafted: "Email",
  signal_detected: "Signal",
  goal_progressed: "Goal",
  agent_activated: "Agent",
  crm_synced: "CRM",
};

const PAGE_SIZE = 20;

// ---------------------------------------------------------------------------
// Utility helpers
// ---------------------------------------------------------------------------

function relativeTime(dateStr: string | null): string {
  if (!dateStr) return "\u2014";
  const diff = Date.now() - new Date(dateStr).getTime();
  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return `${Math.floor(days / 30)}mo ago`;
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function isRecentActivity(dateStr: string | null): boolean {
  if (!dateStr) return false;
  const diff = Date.now() - new Date(dateStr).getTime();
  return diff < 5 * 60 * 1000; // 5 minutes
}

function agentBadgeClasses(agent: string): string {
  const color = AGENT_COLORS[agent as AgentName];
  switch (color) {
    case "emerald":
      return "bg-emerald-500 text-white";
    case "blue":
      return "bg-blue-500 text-white";
    case "violet":
      return "bg-violet-500 text-white";
    case "amber":
      return "bg-amber-500 text-white";
    case "rose":
      return "bg-rose-500 text-white";
    case "cyan":
      return "bg-cyan-500 text-white";
    default:
      return "bg-slate-500 text-white";
  }
}

function agentCardBorderClass(agent: string, isRecent: boolean): string {
  if (!isRecent) return "border-slate-700";
  const color = AGENT_COLORS[agent as AgentName];
  switch (color) {
    case "emerald":
      return "border-emerald-500/50";
    case "blue":
      return "border-blue-500/50";
    case "violet":
      return "border-violet-500/50";
    case "amber":
      return "border-amber-500/50";
    case "rose":
      return "border-rose-500/50";
    case "cyan":
      return "border-cyan-500/50";
    default:
      return "border-slate-700";
  }
}

function agentCardGlowClass(agent: string, isRecent: boolean): string {
  if (!isRecent) return "";
  const color = AGENT_COLORS[agent as AgentName];
  switch (color) {
    case "emerald":
      return "shadow-emerald-500/20 shadow-lg";
    case "blue":
      return "shadow-blue-500/20 shadow-lg";
    case "violet":
      return "shadow-violet-500/20 shadow-lg";
    case "amber":
      return "shadow-amber-500/20 shadow-lg";
    case "rose":
      return "shadow-rose-500/20 shadow-lg";
    case "cyan":
      return "shadow-cyan-500/20 shadow-lg";
    default:
      return "";
  }
}

function typeBadgeClasses(activityType: string): string {
  switch (activityType) {
    case "research_complete":
      return "bg-blue-500/20 text-blue-400 border-blue-500/30";
    case "email_drafted":
      return "bg-amber-500/20 text-amber-400 border-amber-500/30";
    case "signal_detected":
      return "bg-yellow-500/20 text-yellow-400 border-yellow-500/30";
    case "goal_progressed":
      return "bg-emerald-500/20 text-emerald-400 border-emerald-500/30";
    case "agent_activated":
      return "bg-violet-500/20 text-violet-400 border-violet-500/30";
    case "crm_synced":
      return "bg-cyan-500/20 text-cyan-400 border-cyan-500/30";
    default:
      return "bg-slate-500/20 text-slate-400 border-slate-500/30";
  }
}

function confidenceDotColor(confidence: number): string {
  if (confidence > 0.8) return "bg-emerald-400";
  if (confidence > 0.5) return "bg-amber-400";
  return "bg-red-400";
}

function entityPath(entityType: string, entityId: string): string | null {
  switch (entityType) {
    case "lead":
      return `/dashboard/leads/${entityId}`;
    case "goal":
      return "/goals";
    case "contact":
    case "company":
      return `/dashboard/leads/${entityId}`;
    default:
      return null;
  }
}

function confidenceLabel(confidence: number): string {
  if (confidence >= 0.95) return "Stated as fact";
  if (confidence >= 0.8) return "High confidence";
  if (confidence >= 0.6) return "Moderate confidence";
  if (confidence >= 0.4) return "Low confidence";
  return "Needs confirmation";
}

// ---------------------------------------------------------------------------
// Inline SVG icons
// ---------------------------------------------------------------------------

function SearchIcon({ className = "w-5 h-5" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  );
}

function MagnifyingGlassIcon({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  );
}

function EnvelopeIcon({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="4" width="20" height="16" rx="2" />
      <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7" />
    </svg>
  );
}

function LightningBoltIcon({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
    </svg>
  );
}

function TargetIcon({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <circle cx="12" cy="12" r="6" />
      <circle cx="12" cy="12" r="2" />
    </svg>
  );
}

function PlayIcon({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="5 3 19 12 5 21 5 3" />
    </svg>
  );
}

function RefreshIcon({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 2v6h-6" />
      <path d="M3 12a9 9 0 0 1 15-6.7L21 8" />
      <path d="M3 22v-6h6" />
      <path d="M21 12a9 9 0 0 1-15 6.7L3 16" />
    </svg>
  );
}

function ChevronDownIcon({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

function ChevronUpIcon({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="18 15 12 9 6 15" />
    </svg>
  );
}

function ActivityEmptyIcon({ className = "w-12 h-12" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
    </svg>
  );
}

function activityTypeIcon(activityType: string): React.ReactNode {
  switch (activityType) {
    case "research_complete":
      return <MagnifyingGlassIcon />;
    case "email_drafted":
      return <EnvelopeIcon />;
    case "signal_detected":
      return <LightningBoltIcon />;
    case "goal_progressed":
      return <TargetIcon />;
    case "agent_activated":
      return <PlayIcon />;
    case "crm_synced":
      return <RefreshIcon />;
    default:
      return <ActivityEmptyIcon className="w-4 h-4" />;
  }
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function FilterBar({
  agentFilter,
  typeFilter,
  searchQuery,
  dateStart,
  dateEnd,
  onAgentChange,
  onTypeChange,
  onSearchChange,
  onDateStartChange,
  onDateEndChange,
}: {
  agentFilter: string;
  typeFilter: string;
  searchQuery: string;
  dateStart: string;
  dateEnd: string;
  onAgentChange: (v: string) => void;
  onTypeChange: (v: string) => void;
  onSearchChange: (v: string) => void;
  onDateStartChange: (v: string) => void;
  onDateEndChange: (v: string) => void;
}) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col sm:flex-row gap-3">
        {/* Agent dropdown */}
        <div className="relative">
          <select
            value={agentFilter}
            onChange={(e) => onAgentChange(e.target.value)}
            className="appearance-none bg-slate-800 border border-slate-700 rounded-lg px-4 py-2 pr-8 text-sm text-white focus:outline-none focus:ring-2 focus:ring-violet-500 focus:border-transparent cursor-pointer"
          >
            <option value="">All Agents</option>
            {AGENTS.map((a) => (
              <option key={a} value={a}>
                {capitalize(a)}
              </option>
            ))}
          </select>
          <ChevronDownIcon className="w-4 h-4 text-slate-400 absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none" />
        </div>

        {/* Type dropdown */}
        <div className="relative">
          <select
            value={typeFilter}
            onChange={(e) => onTypeChange(e.target.value)}
            className="appearance-none bg-slate-800 border border-slate-700 rounded-lg px-4 py-2 pr-8 text-sm text-white focus:outline-none focus:ring-2 focus:ring-violet-500 focus:border-transparent cursor-pointer"
          >
            <option value="">All Types</option>
            {ACTIVITY_TYPES.map((t) => (
              <option key={t} value={t}>
                {ACTIVITY_TYPE_LABELS[t]}
              </option>
            ))}
          </select>
          <ChevronDownIcon className="w-4 h-4 text-slate-400 absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none" />
        </div>

        {/* Date range */}
        <input
          type="date"
          value={dateStart}
          onChange={(e) => onDateStartChange(e.target.value)}
          className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-violet-500 focus:border-transparent [color-scheme:dark]"
          placeholder="Start date"
        />
        <input
          type="date"
          value={dateEnd}
          onChange={(e) => onDateEndChange(e.target.value)}
          className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-violet-500 focus:border-transparent [color-scheme:dark]"
          placeholder="End date"
        />

        {/* Search input */}
        <div className="relative flex-1 min-w-0">
          <SearchIcon className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search activity..."
            className="w-full bg-slate-800 border border-slate-700 rounded-lg pl-9 pr-4 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-violet-500 focus:border-transparent"
          />
        </div>
      </div>
    </div>
  );
}

function AgentCard({
  name,
  status,
}: {
  name: AgentName;
  status: AgentStatusItem | undefined;
}) {
  const lastDesc = status?.last_activity ?? "Idle";
  const lastTime = status?.last_time ?? null;
  const recent = isRecentActivity(lastTime);

  return (
    <div
      className={`bg-slate-800 border rounded-xl p-4 min-w-[160px] flex-shrink-0 transition-all ${agentCardBorderClass(name, recent)} ${agentCardGlowClass(name, recent)}`}
    >
      <div className="flex items-center gap-3 mb-2">
        {/* Agent avatar */}
        <div
          className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${agentBadgeClasses(name)}`}
        >
          {name.charAt(0).toUpperCase()}
        </div>
        <div className="min-w-0">
          <p className="text-white text-sm font-medium">{capitalize(name)}</p>
        </div>
      </div>
      <p className="text-slate-400 text-xs truncate">{lastDesc}</p>
      <p className="font-mono text-xs text-slate-500 mt-1">
        {lastTime ? relativeTime(lastTime) : "\u2014"}
      </p>
    </div>
  );
}

function ActivityListItem({
  item,
  isExpanded,
  onToggle,
}: {
  item: ActivityItem;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  const agentName = item.agent ?? "unknown";

  return (
    <div
      className="bg-slate-800/50 border border-slate-700 rounded-xl transition-colors hover:bg-slate-700/50 cursor-pointer"
      onClick={onToggle}
    >
      <div className="p-4 flex items-start gap-3">
        {/* Agent badge */}
        <div
          className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold flex-shrink-0 ${agentBadgeClasses(agentName)}`}
        >
          {agentName.charAt(0).toUpperCase()}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-white text-sm font-medium">{item.title}</h3>
            {/* Type badge */}
            <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded border ${typeBadgeClasses(item.activity_type)}`}>
              {activityTypeIcon(item.activity_type)}
              {ACTIVITY_TYPE_LABELS[item.activity_type] ?? item.activity_type}
            </span>
          </div>
          <p className="text-slate-400 text-sm mt-1 line-clamp-2">
            {item.description}
          </p>
        </div>

        {/* Right column: timestamp + confidence + expand */}
        <div className="flex items-center gap-3 flex-shrink-0">
          <span className="font-mono text-xs text-slate-500">
            {relativeTime(item.created_at)}
          </span>
          <span
            className={`w-2 h-2 rounded-full flex-shrink-0 ${confidenceDotColor(item.confidence)}`}
            title={`Confidence: ${Math.round(item.confidence * 100)}%`}
          />
          {isExpanded ? (
            <ChevronUpIcon className="w-4 h-4 text-slate-500" />
          ) : (
            <ChevronDownIcon className="w-4 h-4 text-slate-500" />
          )}
        </div>
      </div>

      {/* Expanded detail */}
      {isExpanded && (
        <div className="border-t border-slate-700 px-4 py-4 space-y-3">
          {/* Reasoning */}
          {item.reasoning && (
            <div>
              <p className="text-xs text-slate-500 uppercase tracking-wide mb-1">
                Reasoning
              </p>
              <p className="text-slate-300 text-sm whitespace-pre-wrap">
                {item.reasoning}
              </p>
            </div>
          )}

          {/* Related entity */}
          {item.related_entity_type && item.related_entity_id && (
            <div>
              <p className="text-xs text-slate-500 uppercase tracking-wide mb-1">
                Related Entity
              </p>
              {(() => {
                const path = entityPath(item.related_entity_type, item.related_entity_id);
                const content = (
                  <span className="inline-flex items-center gap-1 text-violet-400 text-sm hover:text-violet-300 transition-colors">
                    <span className="font-medium">
                      {capitalize(item.related_entity_type)}
                    </span>
                    <span className="text-slate-500">#</span>
                    <span className="font-mono text-xs">
                      {item.related_entity_id.slice(0, 8)}
                    </span>
                  </span>
                );
                return path ? (
                  <Link to={path} onClick={(e) => e.stopPropagation()}>
                    {content}
                  </Link>
                ) : (
                  content
                );
              })()}
            </div>
          )}

          {/* Confidence detail */}
          <div>
            <p className="text-xs text-slate-500 uppercase tracking-wide mb-1">
              Confidence
            </p>
            <div className="flex items-center gap-2">
              <span
                className={`w-2 h-2 rounded-full ${confidenceDotColor(item.confidence)}`}
              />
              <span className="text-slate-300 text-sm">
                {confidenceLabel(item.confidence)}
              </span>
            </div>
          </div>

          {/* Timestamp full */}
          <div>
            <p className="text-xs text-slate-500 uppercase tracking-wide mb-1">
              Timestamp
            </p>
            <p className="font-mono text-xs text-slate-400">
              {new Date(item.created_at).toLocaleString()}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function ActivityFeedPage() {
  const [agentFilter, setAgentFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [dateStart, setDateStart] = useState("");
  const [dateEnd, setDateEnd] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);

  // Build stable filters object
  const filters: ActivityFilters = useMemo(
    () => ({
      agent: agentFilter || undefined,
      activity_type: typeFilter || undefined,
      search: searchQuery || undefined,
      date_start: dateStart ? `${dateStart}T00:00:00Z` : undefined,
      date_end: dateEnd ? `${dateEnd}T23:59:59Z` : undefined,
      limit: PAGE_SIZE,
      offset,
    }),
    [agentFilter, typeFilter, searchQuery, dateStart, dateEnd, offset],
  );

  const { data: feedData, isLoading: feedLoading } = useActivityFeed(filters);
  const { data: agentStatusData, isLoading: agentStatusLoading } =
    useAgentStatus();

  const activities = feedData?.activities ?? [];
  const hasMore = activities.length === PAGE_SIZE;

  const handleToggleExpand = useCallback((id: string) => {
    setExpandedId((prev) => (prev === id ? null : id));
  }, []);

  // Reset offset when filters change
  const handleAgentChange = useCallback((v: string) => {
    setAgentFilter(v);
    setOffset(0);
  }, []);

  const handleTypeChange = useCallback((v: string) => {
    setTypeFilter(v);
    setOffset(0);
  }, []);

  const handleSearchChange = useCallback((v: string) => {
    setSearchQuery(v);
    setOffset(0);
  }, []);

  const handleDateStartChange = useCallback((v: string) => {
    setDateStart(v);
    setOffset(0);
  }, []);

  const handleDateEndChange = useCallback((v: string) => {
    setDateEnd(v);
    setOffset(0);
  }, []);

  return (
    <DashboardLayout>
      <div className="p-4 lg:p-8 min-h-screen bg-slate-900">
        <div className="max-w-7xl mx-auto space-y-8">
          {/* ---- Header ---- */}
          <div>
            <h1 className="text-3xl font-display text-white">
              ARIA Activity
            </h1>
            <p className="mt-1 text-slate-400">
              Real-time feed of agent actions, research, and intelligence
              updates
            </p>
          </div>

          {/* ---- Filter Bar ---- */}
          <FilterBar
            agentFilter={agentFilter}
            typeFilter={typeFilter}
            searchQuery={searchQuery}
            dateStart={dateStart}
            dateEnd={dateEnd}
            onAgentChange={handleAgentChange}
            onTypeChange={handleTypeChange}
            onSearchChange={handleSearchChange}
            onDateStartChange={handleDateStartChange}
            onDateEndChange={handleDateEndChange}
          />

          {/* ---- Agent Status Strip ---- */}
          <div className="overflow-x-auto pb-2">
            <div className="flex gap-4 min-w-min">
              {agentStatusLoading
                ? AGENTS.map((a) => (
                    <div
                      key={a}
                      className="bg-slate-800 border border-slate-700 rounded-xl p-4 min-w-[160px] flex-shrink-0"
                    >
                      <div className="flex items-center gap-3 mb-2">
                        <div className="w-8 h-8 bg-slate-700 rounded-full animate-pulse" />
                        <div className="h-4 bg-slate-700 rounded animate-pulse w-16" />
                      </div>
                      <div className="h-3 bg-slate-700 rounded animate-pulse w-24 mt-2" />
                      <div className="h-3 bg-slate-700 rounded animate-pulse w-12 mt-1" />
                    </div>
                  ))
                : AGENTS.map((a) => (
                    <AgentCard
                      key={a}
                      name={a}
                      status={agentStatusData?.agents[a]}
                    />
                  ))}
            </div>
          </div>

          {/* ---- Activity Stream ---- */}
          <div className="space-y-3">
            {feedLoading ? (
              // Loading skeletons
              Array.from({ length: 5 }).map((_, i) => (
                <div
                  key={i}
                  className="bg-slate-800/50 border border-slate-700 rounded-xl p-4 flex items-start gap-3"
                >
                  <div className="w-8 h-8 bg-slate-700 rounded-full animate-pulse flex-shrink-0" />
                  <div className="flex-1 space-y-2">
                    <div className="h-4 bg-slate-700 rounded animate-pulse w-1/3" />
                    <div className="h-3 bg-slate-700 rounded animate-pulse w-2/3" />
                  </div>
                  <div className="h-3 bg-slate-700 rounded animate-pulse w-16 flex-shrink-0" />
                </div>
              ))
            ) : activities.length === 0 ? (
              // Empty state
              <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-12 text-center">
                <ActivityEmptyIcon className="w-12 h-12 text-slate-600 mx-auto mb-4" />
                <p className="text-slate-400 text-sm">
                  ARIA is getting to work. Activity will appear here as she
                  completes tasks.
                </p>
              </div>
            ) : (
              // Activity items
              <>
                {activities.map((item) => (
                  <ActivityListItem
                    key={item.id}
                    item={item}
                    isExpanded={expandedId === item.id}
                    onToggle={() => handleToggleExpand(item.id)}
                  />
                ))}

                {/* Load more */}
                {hasMore && (
                  <div className="flex justify-center pt-4">
                    <button
                      onClick={() => setOffset((o) => o + PAGE_SIZE)}
                      className="px-6 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-300 font-medium hover:bg-slate-700 hover:text-white transition-colors"
                    >
                      Load More
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
