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

import { useState, useCallback, useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Search, Filter, Mail, Clock, ArrowRight, CircleAlert, Check, X, CheckSquare, Square, Calendar, FileEdit, ExternalLink } from 'lucide-react';
import { cn } from '@/utils/cn';
import { isPlaceholderDraft } from '@/utils/isPlaceholderDraft';
import { useDrafts, useBatchDraftAction } from '@/hooks/useDrafts';
import { EmptyState } from '@/components/common/EmptyState';
import { DraftDetailPage } from './DraftDetailPage';
import { EmailDecisionsLog } from '@/components/communications/EmailDecisionsLog';
import { LearningModeBanner } from '@/components/communications/LearningModeBanner';
import { ContactHistoryView } from '@/components/communications/ContactHistoryView';
import { useUpcomingMeetings } from '@/hooks/useUpcomingMeetings';
import type { UpcomingMeetingWithContext } from '@/api/communications';
import type { EmailDraftStatus, EmailDraftPurpose, ConfidenceTier, EmailDraftListItem } from '@/api/drafts';

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
  reply: 'Reply',
  other: 'Other',
  competitive_displacement: 'Competitive Displacement',
  conference_outreach: 'Conference Outreach',
  clinical_trial_outreach: 'Clinical Trial Outreach',
};

// Draft type badge styles for intelligence-generated drafts
const DRAFT_TYPE_STYLES: Record<string, { label: string; bg: string; text: string; icon?: string }> = {
  competitive_displacement: { label: 'Displacement', bg: '#7c3aed', text: 'white' },
  conference_outreach: { label: 'Conference', bg: '#0891b2', text: 'white' },
  clinical_trial_outreach: { label: 'Clinical', bg: '#059669', text: 'white' },
};

// Status badge styles - covers all known statuses plus fallback for unknown
const STATUS_STYLES: Record<EmailDraftStatus, { label: string; bg: string; text: string }> = {
  draft: { label: 'DRAFTING', bg: 'var(--accent)', text: 'white' },
  sent: { label: 'SENT', bg: 'var(--success)', text: 'white' },
  failed: { label: 'FAILED', bg: 'var(--critical)', text: 'white' },
  pending_review: { label: 'PENDING', bg: '#6366f1', text: 'white' },
  approved: { label: 'APPROVED', bg: 'var(--success)', text: 'white' },
  dismissed: { label: 'DISMISSED', bg: 'var(--text-secondary)', text: 'white' },
  saved_to_client: { label: 'SAVED', bg: '#0891b2', text: 'white' },
};

// Fallback style for any unrecognized status
const DEFAULT_STATUS_STYLE = { label: 'UNKNOWN', bg: 'var(--text-secondary)', text: 'white' };

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

// Generate a clean preview from email body
function generateBodyPreview(body: string | undefined, maxLength = 100): string | null {
  if (!body) return null;

  // Strip HTML tags
  let text = body.replace(/<[^>]*>/g, ' ');

  // Decode common HTML entities
  text = text
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'");

  // Remove common greeting patterns (including first-name-only greetings like "Keith," or "Ries,")
  text = text.replace(/^(Hi\s+[A-Za-z]+\s*,?\s*|Hi\s*,?\s*|Hello\s+[A-Za-z]+\s*,?\s*|Hello\s*,?\s*|Dear\s+[^,]+,?\s*)/i, '');
  text = text.replace(/^[A-Z][a-z]+\s*,\s*/, '');

  // Remove common signature patterns (everything after common sign-offs)
  const signOffPatterns = [
    /\s*(Thanks?\s*,?\s*|Best\s*(regards?)?,?\s*|Regards,?\s*|Sincerely,?\s*|Cheers,?\s*|Warmly,?\s*).*/is,
    /\s*--\s*$/m,
  ];

  for (const pattern of signOffPatterns) {
    const match = text.match(pattern);
    if (match && match.index !== undefined && match.index < text.length * 0.6) {
      // Only trim if sign-off is in the latter half
      text = text.substring(0, match.index);
    }
  }

  // Normalize whitespace and trim
  text = text.replace(/\s+/g, ' ').trim();

  if (!text) return null;

  // Truncate to max length
  if (text.length > maxLength) {
    return text.substring(0, maxLength).trim() + '...';
  }

  return text || null;
}

// Priority border accent color based on score
function getPriorityBorderColor(score: number | undefined): string | undefined {
  if (!score || score < 30) return undefined;
  if (score > 60) return '#ef4444'; // red-500
  return '#eab308'; // yellow-500
}

// Check if a draft can be selected for batch actions
const NON_ACTIONABLE_STATUSES: Set<EmailDraftStatus> = new Set([
  'sent', 'failed', 'dismissed', 'approved', 'saved_to_client',
]);

function isDraftSelectable(draft: EmailDraftListItem): boolean {
  if (isPlaceholderDraft(draft)) return false;
  if (NON_ACTIONABLE_STATUSES.has(draft.status)) return false;
  return true;
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

// Confirmation dialog for batch approve
function BatchConfirmDialog({
  count,
  onConfirm,
  onCancel,
  isLoading,
}: {
  count: number;
  onConfirm: () => void;
  onCancel: () => void;
  isLoading: boolean;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/40"
        onClick={onCancel}
      />
      {/* Dialog */}
      <div
        className="relative rounded-xl p-6 shadow-xl max-w-md w-full mx-4 border"
        style={{
          backgroundColor: 'var(--bg-elevated)',
          borderColor: 'var(--border)',
        }}
      >
        <h3
          className="font-display text-lg font-semibold mb-2"
          style={{ color: 'var(--text-primary)' }}
        >
          Approve {count} draft{count > 1 ? 's' : ''}?
        </h3>
        <p
          className="text-sm mb-6"
          style={{ color: 'var(--text-secondary)' }}
        >
          This will approve {count === 1 ? 'this draft' : `all ${count} selected drafts`} and
          save {count === 1 ? 'it' : 'them'} to your email client. You can review and send
          from your inbox.
        </p>
        <div className="flex items-center justify-end gap-3">
          <button
            onClick={onCancel}
            disabled={isLoading}
            className={cn(
              'px-4 py-2 rounded-lg text-sm font-medium transition-colors',
              'border border-[var(--border)] hover:bg-[var(--bg-subtle)]'
            )}
            style={{ color: 'var(--text-secondary)' }}
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={isLoading}
            className={cn(
              'px-4 py-2 rounded-lg text-sm font-medium transition-colors',
              'bg-[var(--accent)] text-white hover:opacity-90',
              'disabled:opacity-50'
            )}
          >
            {isLoading ? 'Approving...' : `Approve & Save (${count})`}
          </button>
        </div>
      </div>
    </div>
  );
}

// Upcoming meetings banner — shows meetings with email context
function UpcomingMeetingsBanner({
  onContactClick,
  onDraftClick,
}: {
  onContactClick: (email: string) => void;
  onDraftClick: (draftId: string) => void;
}) {
  const { data: meetings } = useUpcomingMeetings(24);

  if (!meetings || meetings.length === 0) return null;

  return (
    <div className="mb-6">
      <div className="flex items-center gap-2 mb-3">
        <Calendar
          className="w-4 h-4"
          style={{ color: 'var(--accent)' }}
        />
        <span
          className="text-xs font-medium uppercase tracking-wider"
          style={{ color: 'var(--text-secondary)' }}
        >
          Upcoming meetings
        </span>
      </div>
      <div className="flex gap-3 overflow-x-auto pb-1">
        {meetings.map((meeting: UpcomingMeetingWithContext) => (
          <MeetingContextCard
            key={meeting.meeting_id ?? meeting.meeting_time}
            meeting={meeting}
            onContactClick={onContactClick}
            onDraftClick={onDraftClick}
          />
        ))}
      </div>
    </div>
  );
}

// Single meeting context card
function MeetingContextCard({
  meeting,
  onContactClick,
  onDraftClick,
}: {
  meeting: UpcomingMeetingWithContext;
  onContactClick: (email: string) => void;
  onDraftClick: (draftId: string) => void;
}) {
  const ctx = meeting.email_context;
  const primaryAttendee = meeting.attendees[0];
  const attendeeDisplay = primaryAttendee?.name || ctx.contact_email.split('@')[0];

  return (
    <div
      className="flex-shrink-0 w-80 border rounded-lg p-3 transition-all duration-200 hover:shadow-sm"
      style={{
        backgroundColor: 'var(--bg-elevated)',
        borderColor: 'var(--border)',
        borderLeftWidth: '3px',
        borderLeftColor: 'var(--accent)',
      }}
    >
      {/* Meeting title + time */}
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="min-w-0 flex-1">
          <p
            className="text-sm font-medium truncate"
            style={{ color: 'var(--text-primary)' }}
          >
            {meeting.meeting_title}
          </p>
          <p
            className="text-xs"
            style={{ color: 'var(--text-secondary)' }}
          >
            in {meeting.time_until}
            {meeting.attendees.length > 1 && (
              <span className="ml-1">
                ({meeting.attendees.length} attendees)
              </span>
            )}
          </p>
        </div>
        <div
          className="flex-shrink-0 px-1.5 py-0.5 rounded text-[10px] font-medium"
          style={{
            backgroundColor: 'var(--accent)',
            color: 'white',
          }}
        >
          {meeting.time_until.includes('hour') || meeting.time_until.includes('minute') || meeting.time_until === 'now'
            ? 'SOON'
            : 'UPCOMING'}
        </div>
      </div>

      {/* Latest email context */}
      {ctx.latest_subject && (
        <div
          className="text-xs truncate mb-2 px-2 py-1.5 rounded"
          style={{
            backgroundColor: 'var(--bg-subtle)',
            color: 'var(--text-secondary)',
          }}
        >
          <span style={{ color: 'var(--text-primary)' }}>Latest:</span>{' '}
          {ctx.latest_subject}
          {ctx.latest_date_relative && (
            <span className="ml-1 opacity-70">{ctx.latest_date_relative}</span>
          )}
        </div>
      )}

      {/* Pipeline context badge */}
      {ctx.pipeline_context?.company_name && (
        <div className="mb-2">
          <span
            className="text-[10px] px-1.5 py-0.5 rounded"
            style={{
              backgroundColor: 'var(--bg-subtle)',
              color: 'var(--text-secondary)',
            }}
          >
            {ctx.pipeline_context.company_name}
            {ctx.pipeline_context.relationship_type && (
              <> ({ctx.pipeline_context.relationship_type.replace(/_/g, ' ')})</>
            )}
          </span>
        </div>
      )}

      {/* Action links */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => onContactClick(ctx.contact_email)}
          className="flex items-center gap-1 text-xs font-medium transition-colors hover:opacity-80"
          style={{ color: 'var(--accent)' }}
        >
          <ExternalLink className="w-3 h-3" />
          View Thread
        </button>
        {ctx.has_pending_draft && ctx.draft_id && (
          <button
            onClick={() => onDraftClick(ctx.draft_id!)}
            className="flex items-center gap-1 text-xs font-medium transition-colors hover:opacity-80"
            style={{ color: '#7c3aed' }}
          >
            <FileEdit className="w-3 h-3" />
            Review Draft
          </button>
        )}
        <span
          className="ml-auto text-[10px] font-mono"
          style={{ color: 'var(--text-secondary)', opacity: 0.6 }}
        >
          {ctx.total_emails} email{ctx.total_emails !== 1 ? 's' : ''} with {attendeeDisplay}
        </span>
      </div>
    </div>
  );
}

// Drafts List View
function DraftsList({ onContactClick }: { onContactClick: (email: string) => void }) {
  const navigate = useNavigate();
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<EmailDraftStatus | 'all'>('all');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);

  // Fetch drafts with filter
  const { data: drafts, isLoading, error } = useDrafts(
    statusFilter !== 'all' ? statusFilter : undefined
  );

  const batchAction = useBatchDraftAction();

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

  // Backend returns drafts sorted by priority_score DESC, created_at DESC.
  // Frontend preserves that order but ensures placeholders stay at bottom.
  const sortedDrafts = filteredDrafts?.slice().sort((a, b) => {
    const aIsPlaceholder = isPlaceholderDraft(a);
    const bIsPlaceholder = isPlaceholderDraft(b);
    // Non-placeholders come first
    if (aIsPlaceholder && !bIsPlaceholder) return 1;
    if (!aIsPlaceholder && bIsPlaceholder) return -1;
    // Within non-placeholders, preserve backend priority order
    return 0;
  });

  // Compute selectable drafts from current view
  const selectableDrafts = useMemo(
    () => sortedDrafts?.filter(isDraftSelectable) ?? [],
    [sortedDrafts]
  );

  const selectedCount = selectedIds.size;
  const allSelectableSelected = selectableDrafts.length > 0 && selectableDrafts.every(d => selectedIds.has(d.id));

  const toggleSelection = useCallback((draftId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(draftId)) {
        next.delete(draftId);
      } else {
        next.add(draftId);
      }
      return next;
    });
  }, []);

  const toggleSelectAll = useCallback(() => {
    if (allSelectableSelected) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(selectableDrafts.map(d => d.id)));
    }
  }, [allSelectableSelected, selectableDrafts]);

  const handleBatchApprove = useCallback(() => {
    setShowConfirmDialog(true);
  }, []);

  const confirmBatchApprove = useCallback(() => {
    batchAction.mutate(
      { draft_ids: Array.from(selectedIds), action: 'approve' },
      {
        onSuccess: () => {
          setSelectedIds(new Set());
          setShowConfirmDialog(false);
        },
        onError: () => {
          setShowConfirmDialog(false);
        },
      }
    );
  }, [batchAction, selectedIds]);

  const handleBatchDismiss = useCallback(() => {
    batchAction.mutate(
      { draft_ids: Array.from(selectedIds), action: 'dismiss' },
      {
        onSuccess: () => {
          setSelectedIds(new Set());
        },
      }
    );
  }, [batchAction, selectedIds]);

  const hasDrafts = sortedDrafts && sortedDrafts.length > 0;

  return (
    <div className="flex-1 overflow-y-auto p-8 relative">
      {/* Learning mode indicator */}
      <LearningModeBanner />

      {/* Upcoming meetings with email context */}
      <UpcomingMeetingsBanner
        onContactClick={onContactClick}
        onDraftClick={(draftId) => navigate(`/communications/drafts/${draftId}`)}
      />

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
              onClick={() => {
                setStatusFilter(filter.value);
                setSelectedIds(new Set()); // Clear selection on filter change
              }}
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
          title={
            statusFilter === 'sent'
              ? 'No emails sent yet.'
              : statusFilter === 'failed'
              ? 'No failed emails.'
              : 'No drafts yet.'
          }
          description={
            statusFilter === 'sent'
              ? 'When you send emails through ARIA, they will appear here.'
              : statusFilter === 'failed'
              ? 'Failed email sends will appear here for review.'
              : searchQuery || statusFilter !== 'all'
              ? 'No drafts match your current filters. Try adjusting your search criteria.'
              : 'Ask ARIA to draft an email to get started.'
          }
          suggestion={statusFilter === 'all' ? 'Start a conversation' : undefined}
          onSuggestion={statusFilter === 'all' ? () => navigate('/') : undefined}
          icon={
            statusFilter === 'sent' ? (
              <Mail className="w-8 h-8" />
            ) : statusFilter === 'failed' ? (
              <CircleAlert className="w-8 h-8" />
            ) : (
              <Mail className="w-8 h-8" />
            )
          }
        />
      ) : (
        <div className={cn("space-y-3", selectedCount > 0 && "pb-20")}>
          {sortedDrafts?.map((draft) => {
            // Use fallback for unrecognized statuses to prevent crashes
            const statusStyle = STATUS_STYLES[draft.status] || DEFAULT_STATUS_STYLE;
            const selectable = isDraftSelectable(draft);
            const isSelected = selectedIds.has(draft.id);
            const priorityColor = getPriorityBorderColor(draft.priority_score);
            return (
              <div
                key={draft.id}
                className={cn(
                  'w-full text-left border rounded-lg p-4 transition-all duration-200',
                  'hover:border-[var(--accent)]/50 hover:shadow-sm',
                  'flex items-center gap-3',
                  isSelected && 'ring-2 ring-[var(--accent)]/30'
                )}
                style={{
                  borderColor: isSelected ? 'var(--accent)' : 'var(--border)',
                  backgroundColor: 'var(--bg-elevated)',
                  borderLeftWidth: priorityColor ? '3px' : undefined,
                  borderLeftColor: priorityColor || undefined,
                }}
              >
                {/* Checkbox */}
                {selectable ? (
                  <button
                    onClick={(e) => toggleSelection(draft.id, e)}
                    className={cn(
                      'flex-shrink-0 w-5 h-5 rounded border transition-colors flex items-center justify-center',
                      isSelected
                        ? 'bg-[var(--accent)] border-[var(--accent)]'
                        : 'border-[var(--border)] hover:border-[var(--accent)]'
                    )}
                    aria-label={isSelected ? 'Deselect draft' : 'Select draft'}
                  >
                    {isSelected && <Check className="w-3.5 h-3.5 text-white" />}
                  </button>
                ) : (
                  <div className="flex-shrink-0 w-5 h-5" />
                )}

                {/* Clickable draft content */}
                <button
                  onClick={() => navigate(`/communications/drafts/${draft.id}`)}
                  className="flex-1 text-left min-w-0"
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
                          {/* Recipient name - clickable to view contact history */}
                          <span
                            role="button"
                            tabIndex={0}
                            onClick={(e) => {
                              e.stopPropagation();
                              onContactClick(draft.recipient_email);
                            }}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter' || e.key === ' ') {
                                e.preventDefault();
                                e.stopPropagation();
                                onContactClick(draft.recipient_email);
                              }
                            }}
                            className={cn(
                              "text-sm truncate hover:underline cursor-pointer",
                              isPlaceholderDraft(draft)
                                ? "font-normal italic"
                                : "font-medium"
                            )}
                            style={{ color: isPlaceholderDraft(draft) ? 'var(--text-secondary)' : 'var(--text-primary)' }}
                          >
                            {isPlaceholderDraft(draft)
                              ? 'Outreach Opportunity'
                              : draft.recipient_name || draft.recipient_email}
                          </span>
                          <span
                            className="font-mono text-xs"
                            style={{ color: 'var(--text-secondary)' }}
                          >
                            {PURPOSE_LABELS[draft.purpose]}
                          </span>
                          {draft.pipeline_context && draft.pipeline_context.company_name && (
                            <span
                              className="text-xs px-1.5 py-0.5 rounded"
                              style={{
                                backgroundColor: 'var(--bg-subtle)',
                                color: 'var(--text-secondary)',
                              }}
                              title={`Lead: ${draft.pipeline_context.lead_name || 'N/A'} | Stage: ${draft.pipeline_context.lifecycle_stage || 'N/A'} | Health: ${draft.pipeline_context.health_score ?? 'N/A'}`}
                            >
                              {draft.pipeline_context.company_name}
                              {draft.pipeline_context.relationship_type && (
                                <> ({draft.pipeline_context.relationship_type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())})</>
                              )}
                            </span>
                          )}
                        </div>
                        <p
                          className="text-sm truncate"
                          style={{ color: 'var(--text-secondary)' }}
                        >
                          {draft.subject}
                          {(draft.previous_versions_count ?? 0) > 0 && (
                            <span
                              className="ml-2 text-xs"
                              style={{ color: 'var(--text-tertiary, var(--text-secondary))', opacity: 0.7 }}
                            >
                              ({draft.previous_versions_count!} previous version{draft.previous_versions_count! > 1 ? 's' : ''})
                            </span>
                          )}
                        </p>
                        {generateBodyPreview(draft.body) && (
                          <p
                            className="text-xs truncate mt-0.5"
                            style={{ color: 'var(--text-tertiary, var(--text-secondary))', opacity: 0.7 }}
                          >
                            {generateBodyPreview(draft.body)}
                          </p>
                        )}
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

                      {/* Draft type badge for intelligence-generated drafts */}
                      {draft.draft_type && draft.draft_type !== 'reply' && DRAFT_TYPE_STYLES[draft.draft_type] && (
                        <span
                          className="px-2 py-0.5 rounded-full text-[10px] font-medium"
                          style={{
                            backgroundColor: DRAFT_TYPE_STYLES[draft.draft_type].bg,
                            color: DRAFT_TYPE_STYLES[draft.draft_type].text,
                          }}
                        >
                          {DRAFT_TYPE_STYLES[draft.draft_type].label}
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
              </div>
            );
          })}
        </div>
      )}

      {/* Floating batch action bar */}
      {selectedCount > 0 && (
        <div
          className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 rounded-xl shadow-2xl border px-5 py-3 flex items-center gap-4"
          style={{
            backgroundColor: 'var(--bg-elevated)',
            borderColor: 'var(--border)',
          }}
        >
          {/* Select all checkbox */}
          <button
            onClick={toggleSelectAll}
            className="flex items-center gap-2 text-sm font-medium transition-colors hover:opacity-80"
            style={{ color: 'var(--text-primary)' }}
          >
            {allSelectableSelected ? (
              <CheckSquare className="w-4 h-4" style={{ color: 'var(--accent)' }} />
            ) : (
              <Square className="w-4 h-4" style={{ color: 'var(--text-secondary)' }} />
            )}
            Select All
          </button>

          {/* Divider */}
          <div className="w-px h-6 bg-[var(--border)]" />

          {/* Count */}
          <span
            className="text-sm font-mono"
            style={{ color: 'var(--text-secondary)' }}
          >
            {selectedCount} of {selectableDrafts.length} selected
          </span>

          {/* Divider */}
          <div className="w-px h-6 bg-[var(--border)]" />

          {/* Approve & Send button */}
          <button
            onClick={handleBatchApprove}
            disabled={batchAction.isPending}
            className={cn(
              'px-4 py-1.5 rounded-lg text-sm font-medium transition-colors',
              'bg-[var(--accent)] text-white hover:opacity-90',
              'disabled:opacity-50'
            )}
          >
            Approve & Save ({selectedCount})
          </button>

          {/* Dismiss button */}
          <button
            onClick={handleBatchDismiss}
            disabled={batchAction.isPending}
            className={cn(
              'px-4 py-1.5 rounded-lg text-sm font-medium transition-colors',
              'border border-[var(--border)] hover:bg-[var(--bg-subtle)]',
              'disabled:opacity-50'
            )}
            style={{ color: 'var(--text-secondary)' }}
          >
            Dismiss ({selectedCount})
          </button>

          {/* Clear selection */}
          <button
            onClick={() => setSelectedIds(new Set())}
            className="p-1 rounded hover:bg-[var(--bg-subtle)] transition-colors"
            aria-label="Clear selection"
          >
            <X className="w-4 h-4" style={{ color: 'var(--text-secondary)' }} />
          </button>
        </div>
      )}

      {/* Confirmation dialog for batch approve */}
      {showConfirmDialog && (
        <BatchConfirmDialog
          count={selectedCount}
          onConfirm={confirmBatchApprove}
          onCancel={() => setShowConfirmDialog(false)}
          isLoading={batchAction.isPending}
        />
      )}
    </div>
  );
}

// Main CommunicationsPage component
export function CommunicationsPage() {
  const { draftId } = useParams<{ draftId: string }>();
  const [activeView, setActiveView] = useState<CommunicationsView>('drafts');
  const [selectedContactEmail, setSelectedContactEmail] = useState<string | null>(null);

  // Show detail view if draftId is present
  if (draftId) {
    return <DraftDetailPage draftId={draftId} />;
  }

  // Show contact history view if a contact is selected
  if (selectedContactEmail) {
    return (
      <div
        className="flex-1 flex flex-col h-full"
        style={{ backgroundColor: 'var(--bg-primary)' }}
      >
        <ContactHistoryView
          contactEmail={selectedContactEmail}
          onBack={() => setSelectedContactEmail(null)}
        />
      </div>
    );
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

      {activeView === 'drafts' ? (
        <DraftsList onContactClick={setSelectedContactEmail} />
      ) : (
        <EmailDecisionsLog onContactClick={setSelectedContactEmail} />
      )}
    </div>
  );
}
