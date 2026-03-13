/**
 * MarketSignalsFeed - Real-time market signals from ARIA's intelligence engines
 *
 * Displays funding rounds, FDA approvals, clinical trials, patents, leadership
 * changes, earnings, partnerships, regulatory updates, product launches, and
 * hiring signals detected by ARIA's Scout and Analyst agents.
 *
 * V2 Enhancements:
 * - Priority Signals section at top (highest-relevance signals from last 48h)
 * - Signal deduplication (cluster_id grouping, primary-only display)
 * - ARIA analysis on expand (linked insight + recommended actions)
 * - "Watched" filter chip
 *
 * Light theme component (Intelligence page context).
 */

import { useState, useMemo } from "react";
import {
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
  Check,
  X,
  Eye,
  Filter,
  Zap,
  Layers,
} from "lucide-react";
import { cn } from "@/utils/cn";
import { sanitizeSignalText } from "@/utils/sanitizeSignalText";
import { formatSourceName } from "@/utils/sourceLabels";
import {
  useSignals,
  useUnreadSignalCount,
  useMarkSignalRead,
  useMarkAllSignalsRead,
  useDismissSignal,
  usePrioritySignals,
  useWatchTopics,
  formatRelativeTime,
} from "@/hooks/useIntelPanelData";
import { useIntelligenceInsights } from "@/hooks/useIntelPanelData";
import type { Signal } from "@/api/signals";

// ---------------------------------------------------------------------------
// Signal type configuration
// ---------------------------------------------------------------------------
interface SignalTypeConfig {
  label: string;
  icon: React.ComponentType<{ className?: string; style?: React.CSSProperties }>;
  color: string;
}

const SIGNAL_TYPE_MAP: Record<string, SignalTypeConfig> = {
  funding: { label: "Funding", icon: DollarSign, color: "#22c55e" },
  fda_approval: { label: "FDA", icon: Shield, color: "#3b82f6" },
  clinical_trial: { label: "Clinical Trial", icon: FlaskConical, color: "#a855f7" },
  patent: { label: "Patent", icon: FileText, color: "#f59e0b" },
  leadership: { label: "Leadership", icon: UserCog, color: "#64748b" },
  earnings: { label: "Earnings", icon: TrendingUp, color: "#10b981" },
  partnership: { label: "Partnership", icon: Handshake, color: "#6366f1" },
  regulatory: { label: "Regulatory", icon: Scale, color: "#f97316" },
  product: { label: "Product", icon: Package, color: "#06b6d4" },
  hiring: { label: "Hiring", icon: Users, color: "#ec4899" },
};

const ALL_SIGNAL_TYPES = Object.keys(SIGNAL_TYPE_MAP);

function getSignalConfig(signalType: string): SignalTypeConfig {
  return (
    SIGNAL_TYPE_MAP[signalType] ?? {
      label: signalType,
      icon: TrendingUp,
      color: "var(--text-secondary)",
    }
  );
}

// ---------------------------------------------------------------------------
// Filter Chips
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
      onClick={onClick}
      className={cn(
        "px-3 py-1.5 rounded-full text-xs font-medium transition-colors",
        "border whitespace-nowrap"
      )}
      style={{
        backgroundColor: active ? "var(--accent)" : "var(--bg-elevated)",
        color: active ? "white" : "var(--text-secondary)",
        borderColor: active ? "var(--accent)" : "var(--border)",
      }}
    >
      {label}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Priority Signal Card
// ---------------------------------------------------------------------------
function PrioritySignalCard({
  signal,
}: {
  signal: {
    id: string;
    headline: string;
    company_name: string;
    signal_type: string;
    relevance_score: number;
    linked_insight_id: string | null;
    linked_action_summary: string | null;
  };
}) {
  const config = getSignalConfig(signal.signal_type);
  const Icon = config.icon;

  return (
    <div
      className="rounded-lg border p-4"
      style={{
        backgroundColor: "#FFFBEB",
        borderColor: "#FDE68A",
        borderLeftWidth: "3px",
        borderLeftColor: config.color,
      }}
    >
      <div className="flex items-start gap-3">
        <div
          className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center"
          style={{ backgroundColor: `${config.color}18` }}
        >
          <Icon className="w-4 h-4" style={{ color: config.color }} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span
              className="px-1.5 py-0.5 rounded text-[10px] font-medium uppercase tracking-wide"
              style={{
                backgroundColor: `${config.color}18`,
                color: config.color,
              }}
            >
              {config.label}
            </span>
            <span
              className="inline-flex items-center gap-1 text-[10px] font-semibold"
              style={{ color: "#DC2626" }}
            >
              <span
                className="w-1.5 h-1.5 rounded-full"
                style={{ backgroundColor: "#DC2626" }}
              />
              High
            </span>
          </div>
          <p
            className="text-sm font-medium leading-relaxed"
            style={{ color: "var(--text-primary)" }}
          >
            {sanitizeSignalText(signal.headline, 300) || `${signal.company_name} — new activity detected`}
          </p>
          {signal.company_name && (
            <span
              className="inline-block mt-1 px-1.5 py-0.5 rounded text-[10px] font-medium"
              style={{ backgroundColor: "#F1F5F9", color: "#5B6E8A" }}
            >
              {signal.company_name}
            </span>
          )}
          {signal.linked_action_summary && (
            <div
              className="mt-2 flex items-start gap-1.5 text-xs"
              style={{ color: "var(--accent, #2E66FF)" }}
            >
              <Zap className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
              <span>ARIA insight: {signal.linked_action_summary}</span>
            </div>
          )}
          {!signal.linked_action_summary && signal.linked_insight_id && (
            <div
              className="mt-2 flex items-start gap-1.5 text-xs"
              style={{ color: "#94A3B8" }}
            >
              <Zap className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
              <span>ARIA is analyzing...</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Signal Card (with dedup badge and ARIA analysis)
// ---------------------------------------------------------------------------
function SignalCard({
  signal,
  clusterCount,
  onMarkRead,
  onDismiss,
  linkedInsight,
}: {
  signal: Signal;
  clusterCount: number;
  onMarkRead: (id: string) => void;
  onDismiss: (id: string) => void;
  linkedInsight?: {
    content: string;
    recommended_actions: string[];
    classification: string;
  } | null;
}) {
  const [expanded, setExpanded] = useState(false);
  const config = getSignalConfig(signal.signal_type);
  const Icon = config.icon;
  const isUnread = !signal.read_at;
  const relevance = signal.relevance_score ?? 0;

  return (
    <div
      onClick={() => setExpanded(!expanded)}
      className={cn(
        "flex items-start gap-3 p-4 rounded-lg border transition-all cursor-pointer",
        "hover:bg-[var(--bg-subtle)]"
      )}
      style={{
        backgroundColor: "var(--bg-elevated)",
        borderColor: expanded ? "var(--accent)" : "var(--border)",
        borderLeftWidth: isUnread ? "3px" : "1px",
        borderLeftColor: isUnread ? config.color : "var(--border)",
      }}
    >
      {/* Icon */}
      <div
        className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center mt-0.5"
        style={{ backgroundColor: `${config.color}18` }}
      >
        <Icon className="w-4 h-4" style={{ color: config.color }} />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span
            className="px-1.5 py-0.5 rounded text-[10px] font-medium uppercase tracking-wide"
            style={{
              backgroundColor: `${config.color}18`,
              color: config.color,
            }}
          >
            {config.label}
          </span>
          {/* Cluster/dedup badge */}
          {clusterCount > 1 && (
            <span
              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium"
              style={{ backgroundColor: "#F1F5F9", color: "#5B6E8A" }}
            >
              <Layers className="w-3 h-3" />
              {clusterCount} sources
            </span>
          )}
          {/* Relevance indicator */}
          {relevance >= 0.9 && (
            <span
              className="inline-flex items-center gap-1 text-[10px] font-medium"
              style={{ color: "#3b82f6" }}
            >
              <span
                className="w-1.5 h-1.5 rounded-full"
                style={{ backgroundColor: "#3b82f6" }}
              />
              High
            </span>
          )}
          {relevance >= 0.7 && relevance < 0.9 && (
            <span
              className="w-1.5 h-1.5 rounded-full"
              style={{ backgroundColor: "#22c55e" }}
            />
          )}
          {isUnread && (
            <span
              className="w-2 h-2 rounded-full flex-shrink-0"
              style={{ backgroundColor: "var(--accent)" }}
            />
          )}
        </div>

        {/* Headline as primary text */}
        <p
          className="text-sm font-medium leading-relaxed"
          style={{ color: "var(--text-primary)" }}
        >
          {sanitizeSignalText(signal.headline || signal.content, 300) || `${signal.company_name} — new activity detected`}
        </p>
        {signal.company_name && (
          <span
            className="inline-block mt-1 px-1.5 py-0.5 rounded text-[10px] font-medium"
            style={{ backgroundColor: "#F1F5F9", color: "#5B6E8A" }}
          >
            {signal.company_name}
          </span>
        )}

        {/* Content body (collapsed: 2-line clamp) */}
        {signal.content && signal.content !== signal.headline && (
          <p
            className={cn("text-sm leading-relaxed mt-1", !expanded && "line-clamp-2")}
            style={{ color: "var(--text-secondary)" }}
          >
            {sanitizeSignalText(signal.content, expanded ? 2000 : 300)}
          </p>
        )}

        {/* Expanded details */}
        {expanded && (
          <div className="mt-3 space-y-2">
            {signal.summary && (
              <p
                className="text-sm leading-relaxed"
                style={{ color: "var(--text-secondary)" }}
              >
                {sanitizeSignalText(signal.summary, 1000)}
              </p>
            )}

            {/* ARIA Analysis (from linked insight) */}
            {linkedInsight && (
              <div
                className="rounded-lg p-3 mt-2"
                style={{
                  backgroundColor: linkedInsight.classification === 'threat' ? '#FEF2F210' : '#F0FDF410',
                  border: `1px solid ${linkedInsight.classification === 'threat' ? '#FECACA' : '#BBF7D0'}`,
                }}
              >
                <div className="flex items-center gap-1.5 mb-1.5">
                  <Zap className="w-3.5 h-3.5" style={{ color: 'var(--accent, #2E66FF)' }} />
                  <span className="text-xs font-semibold" style={{ color: '#1E293B' }}>
                    ARIA&apos;s Analysis
                  </span>
                </div>
                <p className="text-xs leading-relaxed" style={{ color: '#5B6E8A' }}>
                  {linkedInsight.content}
                </p>
                {linkedInsight.recommended_actions.length > 0 && (
                  <div className="mt-2">
                    <span className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: '#5B6E8A' }}>
                      Recommended:
                    </span>
                    <ul className="mt-1 space-y-0.5">
                      {linkedInsight.recommended_actions.slice(0, 3).map((action, i) => (
                        <li key={i} className="text-xs" style={{ color: '#5B6E8A' }}>
                          &bull; {action}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            <div className="flex items-center gap-3 flex-wrap">
              {signal.source_url && (
                <a
                  href={signal.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  className="text-xs font-medium underline"
                  style={{ color: "var(--accent)" }}
                >
                  View Source
                </a>
              )}
              {signal.created_at && (
                <span
                  className="text-xs"
                  style={{
                    color: "var(--text-tertiary, var(--text-secondary))",
                  }}
                >
                  {new Date(signal.created_at).toLocaleDateString("en-US", {
                    month: "short",
                    day: "numeric",
                    year: "numeric",
                  })}
                </span>
              )}
              {relevance > 0 && (
                <span
                  className="text-xs"
                  style={{
                    color: "var(--text-tertiary, var(--text-secondary))",
                  }}
                >
                  Relevance: {Math.round(relevance * 100)}%
                </span>
              )}
            </div>
          </div>
        )}

        {/* Footer (always visible when collapsed) */}
        {!expanded && (
          <div className="flex items-center gap-3 mt-2">
            {signal.source && (
              <span
                className="text-xs font-mono truncate max-w-[160px]"
                style={{
                  color: "var(--text-tertiary, var(--text-secondary))",
                }}
              >
                {formatSourceName(signal.source)}
              </span>
            )}
            <span
              className="text-xs font-mono"
              style={{
                color: "var(--text-tertiary, var(--text-secondary))",
              }}
            >
              {formatRelativeTime(signal.created_at)}
            </span>
          </div>
        )}
      </div>

      {/* Actions */}
      <div
        className="flex-shrink-0 flex items-center gap-1"
        onClick={(e) => e.stopPropagation()}
      >
        {isUnread && (
          <button
            onClick={() => onMarkRead(signal.id)}
            className="p-1.5 rounded-md hover:bg-[var(--bg-subtle)] transition-colors"
            title="Mark as read"
          >
            <Eye
              className="w-3.5 h-3.5"
              style={{ color: "var(--text-secondary)" }}
            />
          </button>
        )}
        <button
          onClick={() => onDismiss(signal.id)}
          className="p-1.5 rounded-md hover:bg-[var(--bg-subtle)] transition-colors"
          title="Dismiss"
        >
          <X
            className="w-3.5 h-3.5"
            style={{ color: "var(--text-secondary)" }}
          />
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Loading Skeleton
// ---------------------------------------------------------------------------
function SignalSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 4 }).map((_, i) => (
        <div
          key={i}
          className="flex items-start gap-3 p-4 rounded-lg border animate-pulse"
          style={{
            backgroundColor: "var(--bg-elevated)",
            borderColor: "var(--border)",
          }}
        >
          <div
            className="w-8 h-8 rounded-full flex-shrink-0"
            style={{ backgroundColor: "var(--border)" }}
          />
          <div className="flex-1 space-y-2">
            <div className="flex items-center gap-2">
              <div
                className="h-4 w-24 rounded"
                style={{ backgroundColor: "var(--border)" }}
              />
              <div
                className="h-4 w-16 rounded"
                style={{ backgroundColor: "var(--border)" }}
              />
            </div>
            <div
              className="h-3 w-full rounded"
              style={{ backgroundColor: "var(--border)" }}
            />
            <div
              className="h-3 w-3/4 rounded"
              style={{ backgroundColor: "var(--border)" }}
            />
            <div className="flex gap-3 mt-1">
              <div
                className="h-3 w-20 rounded"
                style={{ backgroundColor: "var(--border)" }}
              />
              <div
                className="h-3 w-12 rounded"
                style={{ backgroundColor: "var(--border)" }}
              />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Empty State
// ---------------------------------------------------------------------------
function SignalEmptyState({ hasFilters }: { hasFilters: boolean }) {
  return (
    <div
      className="flex flex-col items-center justify-center py-12 text-center"
      style={{ color: "var(--text-secondary)" }}
    >
      <Filter className="w-8 h-8 mb-3 opacity-40" />
      <p className="text-sm font-medium mb-1" style={{ color: "var(--text-primary)" }}>
        {hasFilters ? "No signals match your filters" : "No market signals yet"}
      </p>
      <p className="text-xs max-w-xs">
        {hasFilters
          ? "Try adjusting filters or clearing them to see all signals."
          : "ARIA will detect competitor moves, funding rounds, FDA approvals, and more as they happen."}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------
export function MarketSignalsFeed() {
  const [selectedType, setSelectedType] = useState<string | undefined>(undefined);
  const [selectedCompany, setSelectedCompany] = useState<string | undefined>(undefined);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [watchedOnly, setWatchedOnly] = useState(false);

  // Data hooks
  const { data: signals, isLoading } = useSignals({
    signal_type: selectedType,
    unread_only: unreadOnly || undefined,
    limit: 50,
  });
  const { data: unreadCount } = useUnreadSignalCount();
  const { data: priorityData } = usePrioritySignals(48);
  const { data: watchTopicsData } = useWatchTopics();
  const { data: allInsights } = useIntelligenceInsights({ limit: 30 });
  const markRead = useMarkSignalRead();
  const markAllRead = useMarkAllSignalsRead();
  const dismiss = useDismissSignal();

  const watchTopics = watchTopicsData?.topics ?? [];
  const prioritySignals = priorityData?.signals ?? [];

  // Build insight lookup by ID for linked insights
  const insightById = useMemo(() => {
    const map: Record<string, { content: string; recommended_actions: string[]; classification: string }> = {};
    for (const ins of allInsights ?? []) {
      map[ins.id] = {
        content: ins.content,
        recommended_actions: ins.recommended_actions ?? [],
        classification: ins.classification,
      };
    }
    return map;
  }, [allInsights]);

  // Build company filter chips from loaded signals
  const companyChips = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const s of signals ?? []) {
      if (s.company_name && !s.dismissed_at) {
        counts[s.company_name] = (counts[s.company_name] || 0) + 1;
      }
    }
    const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
    const named = entries.filter(([, c]) => c >= 3).map(([name]) => name);
    const hasOther = entries.some(([, c]) => c < 3);
    return { named, hasOther };
  }, [signals]);

  // Build cluster counts for deduplication
  const clusterCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const s of signals ?? []) {
      const clusterId = (s as unknown as { cluster_id?: string }).cluster_id;
      if (clusterId) {
        counts[clusterId] = (counts[clusterId] || 0) + 1;
      }
    }
    return counts;
  }, [signals]);

  // Filter: dismissed, company, dedup (show only primary or no cluster), watched
  const visibleSignals = useMemo(() => {
    let filtered = (signals ?? []).filter((s) => !s.dismissed_at);

    // Dedup: hide non-primary cluster members
    filtered = filtered.filter((s) => {
      const ext = s as unknown as { is_cluster_primary?: boolean; cluster_id?: string };
      if (ext.cluster_id && ext.is_cluster_primary === false) return false;
      return true;
    });

    // Company filter
    if (selectedCompany === "__other__") {
      const namedSet = new Set(companyChips.named);
      filtered = filtered.filter(
        (s) => s.company_name && !namedSet.has(s.company_name)
      );
    } else if (selectedCompany) {
      filtered = filtered.filter((s) => s.company_name === selectedCompany);
    }

    // Watched filter
    if (watchedOnly && watchTopics.length > 0) {
      const watchKeywords = watchTopics
        .flatMap((t) => [t.topic_value.toLowerCase(), ...t.keywords.map((k) => k.toLowerCase())]);
      filtered = filtered.filter((s) => {
        const text = ((s.content ?? '') + ' ' + (s.company_name ?? '')).toLowerCase();
        return watchKeywords.some((kw) => text.includes(kw));
      });
    }

    return filtered;
  }, [signals, selectedCompany, companyChips.named, watchedOnly, watchTopics]);

  const hasFilters = !!selectedType || !!selectedCompany || unreadOnly || watchedOnly;

  return (
    <div
      className="rounded-xl border overflow-hidden"
      style={{
        borderColor: "var(--border)",
        backgroundColor: "var(--bg-elevated)",
      }}
    >
      {/* Priority Signals Section */}
      {prioritySignals.length > 0 && !hasFilters && (
        <div
          className="px-4 py-3 border-b"
          style={{ borderColor: "var(--border)", backgroundColor: "#FFFDF7" }}
        >
          <div className="flex items-center gap-2 mb-3">
            <Zap className="w-4 h-4" style={{ color: "#F59E0B" }} />
            <span
              className="text-xs font-semibold uppercase tracking-wider"
              style={{ color: "#92400E" }}
            >
              Priority Signals ({prioritySignals.length})
            </span>
          </div>
          <div className="space-y-2">
            {prioritySignals.slice(0, 3).map((ps) => (
              <PrioritySignalCard key={ps.id} signal={ps} />
            ))}
          </div>
        </div>
      )}

      {/* Toolbar */}
      <div
        className="px-4 py-3 border-b flex items-center justify-between gap-3"
        style={{ borderColor: "var(--border)" }}
      >
        {/* Filter chips - scrollable */}
        <div className="flex items-center gap-2 overflow-x-auto no-scrollbar">
          <FilterChip
            label="All"
            active={!selectedType && !watchedOnly}
            onClick={() => { setSelectedType(undefined); setWatchedOnly(false); }}
          />
          {ALL_SIGNAL_TYPES.map((type) => (
            <FilterChip
              key={type}
              label={SIGNAL_TYPE_MAP[type].label}
              active={selectedType === type}
              onClick={() => {
                setSelectedType(selectedType === type ? undefined : type);
                setWatchedOnly(false);
              }}
            />
          ))}
          {watchTopics.length > 0 && (
            <FilterChip
              label="Watched"
              active={watchedOnly}
              onClick={() => {
                setWatchedOnly(!watchedOnly);
                setSelectedType(undefined);
              }}
            />
          )}
        </div>

        {/* Right actions */}
        <div className="flex items-center gap-3 flex-shrink-0">
          {/* Unread toggle */}
          <button
            onClick={() => setUnreadOnly(!unreadOnly)}
            className={cn(
              "px-2.5 py-1.5 rounded-md text-xs font-medium transition-colors",
              "border"
            )}
            style={{
              backgroundColor: unreadOnly ? "var(--accent)" : "transparent",
              color: unreadOnly ? "white" : "var(--text-secondary)",
              borderColor: unreadOnly ? "var(--accent)" : "var(--border)",
            }}
          >
            Unread
          </button>

          {/* Mark all read */}
          {(unreadCount?.count ?? 0) > 0 && (
            <button
              onClick={() => markAllRead.mutate()}
              className="text-xs font-medium transition-colors hover:underline whitespace-nowrap"
              style={{ color: "var(--accent)" }}
              disabled={markAllRead.isPending}
            >
              <span className="flex items-center gap-1">
                <Check className="w-3 h-3" />
                Mark all read
              </span>
            </button>
          )}
        </div>
      </div>

      {/* Company filter chips */}
      {companyChips.named.length > 0 && (
        <div
          className="flex items-center gap-2 overflow-x-auto no-scrollbar px-4 pb-3 border-b"
          style={{ borderColor: "var(--border)" }}
        >
          <span
            className="text-[10px] uppercase tracking-wider font-semibold flex-shrink-0"
            style={{
              color: "var(--text-tertiary, var(--text-secondary))",
            }}
          >
            Company
          </span>
          <FilterChip
            label="All"
            active={!selectedCompany}
            onClick={() => setSelectedCompany(undefined)}
          />
          {companyChips.named.map((name) => (
            <FilterChip
              key={name}
              label={name}
              active={selectedCompany === name}
              onClick={() =>
                setSelectedCompany(
                  selectedCompany === name ? undefined : name
                )
              }
            />
          ))}
          {companyChips.hasOther && (
            <FilterChip
              label="Other"
              active={selectedCompany === "__other__"}
              onClick={() =>
                setSelectedCompany(
                  selectedCompany === "__other__" ? undefined : "__other__"
                )
              }
            />
          )}
        </div>
      )}

      {/* Content */}
      <div className="p-4">
        {isLoading ? (
          <SignalSkeleton />
        ) : visibleSignals.length === 0 ? (
          <SignalEmptyState hasFilters={hasFilters} />
        ) : (
          <div className="space-y-2">
            {visibleSignals.map((signal) => {
              const ext = signal as unknown as { cluster_id?: string; linked_insight_id?: string };
              const clusterCount = ext.cluster_id ? (clusterCounts[ext.cluster_id] ?? 1) : 1;
              const insight = ext.linked_insight_id ? insightById[ext.linked_insight_id] : null;

              return (
                <SignalCard
                  key={signal.id}
                  signal={signal}
                  clusterCount={clusterCount}
                  onMarkRead={(id) => markRead.mutate(id)}
                  onDismiss={(id) => dismiss.mutate(id)}
                  linkedInsight={insight}
                />
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
