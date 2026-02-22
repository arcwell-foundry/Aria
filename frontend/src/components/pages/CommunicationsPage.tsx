/**
 * CommunicationsPage - Email drafts list + decisions log
 *
 * Follows ARIA Design System v1.0:
 * - LIGHT THEME (content pages use light background)
 * - View toggle: "Drafts" / "Email Log"
 * - Search bar + status filter chips
 * - DraftsTable with sorting
 * - Email decisions transparency log
 * - Empty state drives to ARIA conversation
 *
 * Routes:
 * - /communications -> DraftsList (default) or EmailDecisionsLog
 * - /communications/drafts/:draftId -> DraftDetailPage
 */

import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Search, Filter, Mail, Clock, ArrowRight } from 'lucide-react';
import { cn } from '@/utils/cn';
import { useDrafts } from '@/hooks/useDrafts';
import { EmptyState } from '@/components/common/EmptyState';
import { DraftDetailPage } from './DraftDetailPage';
import { EmailDecisionsLog } from '@/components/communications/EmailDecisionsLog';
import { LearningModeBanner } from '@/components/communications/LearningModeBanner';
import type { EmailDraftStatus, EmailDraftPurpose, ConfidenceTier } from '@/api/drafts';

type CommunicationsView = 'drafts' | 'decisions';

const VIEW_OPTIONS: { label: string; value: CommunicationsView }[] = [
  { label: 'Drafts', value: 'drafts' },
  { label: 'Email Log', value: 'decisions' },
];

// Filter chip options
const STATUS_FILTERS: { label: string; value: EmailDraftStatus | 'all' }[] = [
  { label: 'All', value: 'all' },
  { label: 'Draft', value: 'draft' },
  { label: 'Sent', value: 'sent' },
  { label: 'Failed', value: 'failed' },
];

// Purpose display labels
const PURPOSE_LABELS: Record<EmailDraftPurpose, string> = {
  intro: 'Introduction',
  follow_up: 'Follow-up',
  proposal: 'Proposal',
  thank_you: 'Thank You',
  check_in: 'Check-in',
  other: 'Other',
};

// Status badge styles
const STATUS_STYLES: Record<EmailDraftStatus, { label: string; bg: string; text: string }> = {
  draft: { label: 'DRAFTING', bg: 'var(--accent)', text: 'white' },
  sent: { label: 'SENT', bg: 'var(--success)', text: 'white' },
  failed: { label: 'FAILED', bg: 'var(--critical)', text: 'white' },
};

// Confidence tier badge styles
const TIER_STYLES: Record<ConfidenceTier, { label: string; bg: string; text: string }> = {
  HIGH: { label: 'High Confidence', bg: 'var(--success)', text: 'white' },
  MEDIUM: { label: 'Medium', bg: 'var(--accent)', text: 'white' },
  LOW: { label: 'Learning', bg: '#d97706', text: 'white' },
  MINIMAL: { label: 'New Contact', bg: 'var(--text-secondary)', text: 'white' },
};

// Format relative time
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

// Skeleton for loading state
function DraftsSkeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      {Array.from({ length: 5 }).map((_, i) => (
        <div
          key={i}
          className="border border-[var(--border)] rounded-lg p-4"
          style={{ backgroundColor: 'var(--bg-elevated)' }}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-full bg-[var(--border)]" />
              <div className="space-y-2">
                <div className="h-4 w-32 bg-[var(--border)] rounded" />
                <div className="h-3 w-48 bg-[var(--border)] rounded" />
              </div>
            </div>
            <div className="h-6 w-16 bg-[var(--border)] rounded-full" />
          </div>
        </div>
      ))}
    </div>
  );
}

// Drafts List View
function DraftsList() {
  const navigate = useNavigate();
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<EmailDraftStatus | 'all'>('all');

  // Fetch drafts with filter
  const { data: drafts, isLoading, error } = useDrafts(
    statusFilter !== 'all' ? statusFilter : undefined
  );

  // Filter by search query
  const filteredDrafts = drafts?.filter((draft) => {
    if (!searchQuery) return true;
    const query = searchQuery.toLowerCase();
    return (
      draft.recipient_email.toLowerCase().includes(query) ||
      draft.recipient_name?.toLowerCase().includes(query) ||
      draft.subject.toLowerCase().includes(query)
    );
  });

  const hasDrafts = filteredDrafts && filteredDrafts.length > 0;

  return (
    <div className="flex-1 overflow-y-auto p-8">
      {/* Learning mode indicator */}
      <LearningModeBanner />

      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-1">
          {/* Status dot */}
          <div
            className="w-2 h-2 rounded-full"
            style={{ backgroundColor: 'var(--success)' }}
          />
          <h1
            className="font-display text-2xl italic"
            style={{ color: 'var(--text-primary)' }}
          >
            Email Drafts
          </h1>
        </div>
        <p
          className="text-sm ml-5"
          style={{ color: 'var(--text-secondary)' }}
        >
          AI-drafted emails ready for your review and approval.
        </p>
      </div>

      {/* Search and Filters */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4 mb-6">
        {/* Search bar */}
        <div className="relative flex-1 w-full sm:max-w-xs">
          <Search
            className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4"
            style={{ color: 'var(--text-secondary)' }}
          />
          <input
            type="text"
            placeholder="Search drafts..."
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

        {/* Filter chips */}
        <div className="flex items-center gap-2 flex-wrap">
          <Filter
            className="w-4 h-4 mr-1"
            style={{ color: 'var(--text-secondary)' }}
          />
          {STATUS_FILTERS.map((filter) => (
            <button
              key={filter.value}
              onClick={() => setStatusFilter(filter.value)}
              className={cn(
                'px-3 py-1.5 rounded-full text-xs font-medium transition-colors',
                statusFilter === filter.value
                  ? 'bg-[var(--accent)] text-white'
                  : 'bg-[var(--bg-subtle)] hover:bg-[var(--border)]'
              )}
              style={{
                color: statusFilter === filter.value ? 'white' : 'var(--text-secondary)',
              }}
            >
              {filter.label}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      {isLoading ? (
        <DraftsSkeleton />
      ) : error ? (
        <div
          className="text-center py-8"
          style={{ color: 'var(--text-secondary)' }}
        >
          Error loading drafts. Please try again.
        </div>
      ) : !hasDrafts ? (
        <EmptyState
          title="No drafts yet."
          description={
            searchQuery || statusFilter !== 'all'
              ? 'No drafts match your current filters. Try adjusting your search criteria.'
              : 'Ask ARIA to draft an email to get started.'
          }
          suggestion="Start a conversation"
          onSuggestion={() => navigate('/')}
          icon={<Mail className="w-8 h-8" />}
        />
      ) : (
        <div className="space-y-3">
          {filteredDrafts.map((draft) => {
            const statusStyle = STATUS_STYLES[draft.status];
            return (
              <button
                key={draft.id}
                onClick={() => navigate(`/communications/drafts/${draft.id}`)}
                className={cn(
                  'w-full text-left border rounded-lg p-4 transition-all duration-200',
                  'hover:border-[var(--accent)]/50 hover:shadow-sm'
                )}
                style={{
                  borderColor: 'var(--border)',
                  backgroundColor: 'var(--bg-elevated)',
                }}
              >
                <div className="flex items-center justify-between gap-4">
                  <div className="flex items-center gap-3 min-w-0 flex-1">
                    {/* Avatar */}
                    <div
                      className="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0"
                      style={{ backgroundColor: 'var(--bg-subtle)' }}
                    >
                      <Mail
                        className="w-5 h-5"
                        style={{ color: 'var(--text-secondary)' }}
                      />
                    </div>

                    {/* Content */}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 mb-0.5">
                        <span
                          className="font-medium text-sm truncate"
                          style={{ color: 'var(--text-primary)' }}
                        >
                          {draft.recipient_name || draft.recipient_email}
                        </span>
                        <span
                          className="font-mono text-xs"
                          style={{ color: 'var(--text-secondary)' }}
                        >
                          {PURPOSE_LABELS[draft.purpose]}
                        </span>
                      </div>
                      <p
                        className="text-sm truncate"
                        style={{ color: 'var(--text-secondary)' }}
                      >
                        {draft.subject}
                      </p>
                    </div>
                  </div>

                  {/* Right side */}
                  <div className="flex items-center gap-3 flex-shrink-0">
                    <div className="flex items-center gap-1.5">
                      <Clock
                        className="w-3.5 h-3.5"
                        style={{ color: 'var(--text-secondary)' }}
                      />
                      <span
                        className="font-mono text-xs"
                        style={{ color: 'var(--text-secondary)' }}
                      >
                        {formatRelativeTime(draft.created_at)}
                      </span>
                    </div>

                    {/* Confidence tier badge */}
                    {draft.confidence_tier && TIER_STYLES[draft.confidence_tier] && (
                      <span
                        className="px-2 py-0.5 rounded-full text-[10px] font-medium"
                        style={{
                          backgroundColor: TIER_STYLES[draft.confidence_tier].bg,
                          color: TIER_STYLES[draft.confidence_tier].text,
                        }}
                      >
                        {TIER_STYLES[draft.confidence_tier].label}
                      </span>
                    )}

                    {/* Status badge */}
                    <span
                      className="px-2 py-0.5 rounded-full text-xs font-medium"
                      style={{
                        backgroundColor: statusStyle.bg,
                        color: statusStyle.text,
                      }}
                    >
                      {statusStyle.label}
                    </span>

                    <ArrowRight
                      className="w-4 h-4"
                      style={{ color: 'var(--text-secondary)' }}
                    />
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// Main CommunicationsPage component
export function CommunicationsPage() {
  const { draftId } = useParams<{ draftId: string }>();
  const [activeView, setActiveView] = useState<CommunicationsView>('drafts');

  // Show detail view if draftId is present
  if (draftId) {
    return <DraftDetailPage draftId={draftId} />;
  }

  // Show list view with toggle
  return (
    <div
      className="flex-1 flex flex-col h-full"
      style={{ backgroundColor: 'var(--bg-primary)' }}
    >
      {/* View toggle */}
      <div className="px-8 pt-6 pb-0">
        <nav className="flex gap-2">
          {VIEW_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setActiveView(opt.value)}
              className={cn(
                'px-4 py-2 rounded-lg text-sm font-medium transition-colors',
                activeView === opt.value
                  ? 'bg-[var(--accent)] text-white'
                  : 'border border-[var(--border)] hover:bg-[var(--bg-subtle)]'
              )}
              style={{
                color: activeView === opt.value ? 'white' : 'var(--text-secondary)',
              }}
            >
              {opt.label}
            </button>
          ))}
        </nav>
      </div>

      {activeView === 'drafts' ? <DraftsList /> : <EmailDecisionsLog />}
    </div>
  );
}
