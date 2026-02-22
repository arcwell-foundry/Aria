/**
 * EmailDecisionsLog - Transparency log showing ARIA's email categorization decisions
 *
 * Shows why ARIA categorized each email as NEEDS_REPLY / FYI / SKIP,
 * and whether a draft was generated. Critical for user trust.
 */

import { useState, useMemo } from 'react';
import { Search, Filter, Mail, Clock, FileText, Eye } from 'lucide-react';
import { cn } from '@/utils/cn';
import { useEmailDecisions } from '@/hooks/useEmailDecisions';
import { EmptyState } from '@/components/common/EmptyState';
import type { EmailCategory, EmailUrgency, ScanDecisionInfo } from '@/api/emailDecisions';

// Category display config
const CATEGORY_STYLES: Record<EmailCategory, { label: string; bg: string; text: string }> = {
  NEEDS_REPLY: { label: 'Needs Reply', bg: 'var(--accent)', text: 'white' },
  FYI: { label: 'FYI', bg: 'var(--bg-subtle)', text: 'var(--text-secondary)' },
  SKIP: { label: 'Skip', bg: 'var(--bg-subtle)', text: 'var(--text-secondary)' },
};

// Urgency display config
const URGENCY_STYLES: Record<EmailUrgency, { label: string; bg: string; text: string }> = {
  URGENT: { label: 'Urgent', bg: 'var(--critical)', text: 'white' },
  NORMAL: { label: 'Normal', bg: 'var(--bg-subtle)', text: 'var(--text-secondary)' },
  LOW: { label: 'Low', bg: 'var(--bg-subtle)', text: 'var(--text-secondary)' },
};

// Filter options
const CATEGORY_FILTERS: { label: string; value: EmailCategory | 'all' }[] = [
  { label: 'All', value: 'all' },
  { label: 'Needs Reply', value: 'NEEDS_REPLY' },
  { label: 'FYI', value: 'FYI' },
  { label: 'Skip', value: 'SKIP' },
];

const DRAFTED_FILTERS: { label: string; value: 'all' | 'drafted' | 'not_drafted' }[] = [
  { label: 'All', value: 'all' },
  { label: 'Drafted', value: 'drafted' },
  { label: 'Not Drafted', value: 'not_drafted' },
];

const TIME_RANGE_OPTIONS: { label: string; hours: number }[] = [
  { label: 'Today', hours: 24 },
  { label: 'Last 3 days', hours: 72 },
  { label: 'Last 7 days', hours: 168 },
];

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

function DecisionsSkeleton() {
  return (
    <div className="space-y-3 animate-pulse">
      {Array.from({ length: 6 }).map((_, i) => (
        <div
          key={i}
          className="border rounded-lg p-4"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)' }}
        >
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-3 flex-1">
              <div className="w-9 h-9 rounded-full bg-[var(--border)]" />
              <div className="flex-1 space-y-2">
                <div className="h-4 w-40 bg-[var(--border)] rounded" />
                <div className="h-3 w-56 bg-[var(--border)] rounded" />
                <div className="h-3 w-full bg-[var(--border)] rounded" />
              </div>
            </div>
            <div className="flex gap-2">
              <div className="h-5 w-16 bg-[var(--border)] rounded-full" />
              <div className="h-5 w-14 bg-[var(--border)] rounded-full" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function DecisionRow({ decision }: { decision: ScanDecisionInfo }) {
  const [expanded, setExpanded] = useState(false);
  const categoryStyle = CATEGORY_STYLES[decision.category];
  const urgencyStyle = URGENCY_STYLES[decision.urgency];

  return (
    <button
      onClick={() => setExpanded(!expanded)}
      className={cn(
        'w-full text-left border rounded-lg p-4 transition-all duration-200',
        'hover:border-[var(--accent)]/50 hover:shadow-sm'
      )}
      style={{
        borderColor: 'var(--border)',
        backgroundColor: 'var(--bg-elevated)',
      }}
    >
      <div className="flex items-start justify-between gap-4">
        {/* Left: sender + subject */}
        <div className="flex items-start gap-3 min-w-0 flex-1">
          <div
            className="w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5"
            style={{ backgroundColor: 'var(--bg-subtle)' }}
          >
            <Mail className="w-4 h-4" style={{ color: 'var(--text-secondary)' }} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 mb-0.5">
              <span
                className="font-medium text-sm truncate"
                style={{ color: 'var(--text-primary)' }}
              >
                {decision.sender_name || decision.sender_email}
              </span>
              {decision.sender_name && (
                <span
                  className="text-xs truncate hidden sm:inline"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  {decision.sender_email}
                </span>
              )}
            </div>
            <p
              className="text-sm truncate mb-1"
              style={{ color: 'var(--text-secondary)' }}
            >
              {decision.subject || '(no subject)'}
            </p>
            {/* Reason - always show first line, expand for full */}
            <p
              className={cn('text-xs leading-relaxed', !expanded && 'line-clamp-1')}
              style={{ color: 'var(--text-secondary)' }}
            >
              {decision.reason}
            </p>
          </div>
        </div>

        {/* Right: badges + meta */}
        <div className="flex flex-col items-end gap-2 flex-shrink-0">
          <div className="flex items-center gap-1.5">
            {/* Category badge */}
            <span
              className="px-2 py-0.5 rounded-full text-[10px] font-medium uppercase tracking-wide"
              style={{ backgroundColor: categoryStyle.bg, color: categoryStyle.text }}
            >
              {categoryStyle.label}
            </span>
            {/* Urgency badge (only show non-normal) */}
            {decision.urgency !== 'NORMAL' && (
              <span
                className="px-2 py-0.5 rounded-full text-[10px] font-medium uppercase tracking-wide"
                style={{ backgroundColor: urgencyStyle.bg, color: urgencyStyle.text }}
              >
                {urgencyStyle.label}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {/* Drafted indicator */}
            <span
              className="flex items-center gap-1 text-[10px] font-medium uppercase tracking-wide"
              style={{ color: decision.needs_draft ? 'var(--success)' : 'var(--text-secondary)' }}
            >
              <FileText className="w-3 h-3" />
              {decision.needs_draft ? 'Drafted' : 'No draft'}
            </span>
            {/* Timestamp */}
            <span className="flex items-center gap-1">
              <Clock className="w-3 h-3" style={{ color: 'var(--text-secondary)' }} />
              <span
                className="font-mono text-[10px]"
                style={{ color: 'var(--text-secondary)' }}
              >
                {formatRelativeTime(decision.scanned_at)}
              </span>
            </span>
          </div>
        </div>
      </div>
    </button>
  );
}

export function EmailDecisionsLog() {
  const [searchQuery, setSearchQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState<EmailCategory | 'all'>('all');
  const [draftedFilter, setDraftedFilter] = useState<'all' | 'drafted' | 'not_drafted'>('all');
  const [timeRange, setTimeRange] = useState(24);

  const { data, isLoading, error } = useEmailDecisions({
    since_hours: timeRange,
    category: categoryFilter !== 'all' ? categoryFilter : undefined,
    limit: 100,
  });

  const filteredDecisions = useMemo(() => {
    if (!data?.decisions) return [];
    return data.decisions.filter((d) => {
      // Drafted filter (client-side)
      if (draftedFilter === 'drafted' && !d.needs_draft) return false;
      if (draftedFilter === 'not_drafted' && d.needs_draft) return false;
      // Search
      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        return (
          d.sender_email.toLowerCase().includes(q) ||
          d.sender_name?.toLowerCase().includes(q) ||
          d.subject?.toLowerCase().includes(q) ||
          d.reason.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [data?.decisions, draftedFilter, searchQuery]);

  const hasDecisions = filteredDecisions.length > 0;

  return (
    <div className="flex-1 overflow-y-auto p-8">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-1">
          <div
            className="w-2 h-2 rounded-full"
            style={{ backgroundColor: 'var(--accent)' }}
          />
          <h1
            className="font-display text-2xl italic"
            style={{ color: 'var(--text-primary)' }}
          >
            Email Decisions
          </h1>
        </div>
        <p
          className="text-sm ml-5"
          style={{ color: 'var(--text-secondary)' }}
        >
          How ARIA categorized your incoming emails and why.
        </p>
      </div>

      {/* Search + Filters */}
      <div className="space-y-3 mb-6">
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
          {/* Search */}
          <div className="relative flex-1 w-full sm:max-w-xs">
            <Search
              className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4"
              style={{ color: 'var(--text-secondary)' }}
            />
            <input
              type="text"
              placeholder="Search by sender, subject, reason..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className={cn(
                'w-full pl-9 pr-4 py-2 rounded-lg',
                'border border-[var(--border)] bg-[var(--bg-elevated)]',
                'text-sm placeholder:text-[var(--text-secondary)]',
                'focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/30 focus:border-[var(--accent)]'
              )}
              style={{ color: 'var(--text-primary)' }}
            />
          </div>

          {/* Time range */}
          <div className="flex items-center gap-2">
            <Clock className="w-4 h-4" style={{ color: 'var(--text-secondary)' }} />
            {TIME_RANGE_OPTIONS.map((opt) => (
              <button
                key={opt.hours}
                onClick={() => setTimeRange(opt.hours)}
                className={cn(
                  'px-3 py-1.5 rounded-full text-xs font-medium transition-colors',
                  timeRange === opt.hours
                    ? 'bg-[var(--accent)] text-white'
                    : 'bg-[var(--bg-subtle)] hover:bg-[var(--border)]'
                )}
                style={{
                  color: timeRange === opt.hours ? 'white' : 'var(--text-secondary)',
                }}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        {/* Category + Drafted filters */}
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 mr-1" style={{ color: 'var(--text-secondary)' }} />
            {CATEGORY_FILTERS.map((filter) => (
              <button
                key={filter.value}
                onClick={() => setCategoryFilter(filter.value)}
                className={cn(
                  'px-3 py-1.5 rounded-full text-xs font-medium transition-colors',
                  categoryFilter === filter.value
                    ? 'bg-[var(--accent)] text-white'
                    : 'bg-[var(--bg-subtle)] hover:bg-[var(--border)]'
                )}
                style={{
                  color: categoryFilter === filter.value ? 'white' : 'var(--text-secondary)',
                }}
              >
                {filter.label}
              </button>
            ))}
          </div>

          <div
            className="w-px h-5 hidden sm:block"
            style={{ backgroundColor: 'var(--border)' }}
          />

          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4 mr-1" style={{ color: 'var(--text-secondary)' }} />
            {DRAFTED_FILTERS.map((filter) => (
              <button
                key={filter.value}
                onClick={() => setDraftedFilter(filter.value)}
                className={cn(
                  'px-3 py-1.5 rounded-full text-xs font-medium transition-colors',
                  draftedFilter === filter.value
                    ? 'bg-[var(--accent)] text-white'
                    : 'bg-[var(--bg-subtle)] hover:bg-[var(--border)]'
                )}
                style={{
                  color: draftedFilter === filter.value ? 'white' : 'var(--text-secondary)',
                }}
              >
                {filter.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Count */}
      {data && !isLoading && (
        <p
          className="text-xs mb-4"
          style={{ color: 'var(--text-secondary)' }}
        >
          {filteredDecisions.length} decision{filteredDecisions.length !== 1 ? 's' : ''}
          {data.total_count > filteredDecisions.length &&
            ` (${data.total_count} total)`}
        </p>
      )}

      {/* Content */}
      {isLoading ? (
        <DecisionsSkeleton />
      ) : error ? (
        <div
          className="text-center py-8"
          style={{ color: 'var(--text-secondary)' }}
        >
          Error loading email decisions. Please try again.
        </div>
      ) : !hasDecisions ? (
        <EmptyState
          title="No decisions yet."
          description={
            searchQuery || categoryFilter !== 'all' || draftedFilter !== 'all'
              ? 'No decisions match your current filters. Try adjusting your criteria.'
              : 'ARIA will log email categorization decisions here once email scanning is active.'
          }
          icon={<Eye className="w-8 h-8" />}
        />
      ) : (
        <div className="space-y-3">
          {filteredDecisions.map((decision) => (
            <DecisionRow key={decision.email_id} decision={decision} />
          ))}
        </div>
      )}
    </div>
  );
}
