/**
 * LeadDetailPage - Detailed view for a single lead
 *
 * Follows ARIA Design System v1.0:
 * - LIGHT THEME (content pages use light background)
 * - Header: Company name (font-display, Instrument Serif italic), verified badge, status tag, Lead ID
 * - Metrics bar: Health Score bar, CRM sync indicator
 * - Two-column layout: Stakeholders (left 280px) + Timeline (center, flex)
 * - StakeholderCard: avatar, name, title, role tag, sentiment indicator
 * - TimelineEvent: chronological cards with dot indicator
 * - data-aria-id on stakeholders and timeline events
 */

import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Check,
  AlertCircle,
  Clock,
  RefreshCw,
  Mail,
  Phone,
  Calendar,
  FileText,
  Zap,
  ChevronUp,
  ChevronDown,
  Minus,
  UserCircle2,
} from 'lucide-react';
import { cn } from '@/utils/cn';
import { Avatar } from '@/components/primitives/Avatar';
import { HealthBar } from '@/components/pipeline/HealthBar';
import { EmptyState } from '@/components/common/EmptyState';
import {
  useLead,
  useLeadStakeholders,
  useLeadTimeline,
  useLeadInsights,
  type Stakeholder,
  type LeadEvent,
  type Insight,
} from '@/hooks/useLeads';
import {
  type StakeholderRole,
  type Sentiment,
  type EventType,
} from '@/api/leads';

// ============================================================================
// Types
// ============================================================================

interface LeadDetailPageProps {
  leadId: string;
}

// ============================================================================
// Helper Functions
// ============================================================================

function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function formatFullDate(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleDateString('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

function getStatusColor(status: string): string {
  switch (status) {
    case 'active':
      return 'var(--success)';
    case 'won':
      return 'var(--accent)';
    case 'lost':
      return 'var(--critical)';
    case 'dormant':
      return 'var(--text-muted)';
    default:
      return 'var(--text-secondary)';
  }
}

function getRoleColor(role: StakeholderRole | null): string {
  switch (role) {
    case 'champion':
      return 'var(--success)';
    case 'decision_maker':
      return 'var(--accent-primary)';
    case 'blocker':
      return 'var(--critical)';
    case 'influencer':
      return 'var(--warning)';
    case 'user':
      return 'var(--text-secondary)';
    default:
      return 'var(--text-muted)';
  }
}

function getRoleLabel(role: StakeholderRole | null): string {
  switch (role) {
    case 'champion':
      return 'Champion';
    case 'decision_maker':
      return 'Decision Maker';
    case 'blocker':
      return 'Blocker';
    case 'influencer':
      return 'Influencer';
    case 'user':
      return 'User';
    default:
      return 'Unknown';
  }
}

function getSentimentIndicator(sentiment: Sentiment): {
  icon: React.ReactNode;
  label: string;
  color: string;
} {
  switch (sentiment) {
    case 'positive':
      return {
        icon: <ChevronUp className="w-3 h-3" />,
        label: 'Positive',
        color: 'var(--success)',
      };
    case 'negative':
      return {
        icon: <ChevronDown className="w-3 h-3" />,
        label: 'Negative',
        color: 'var(--critical)',
      };
    case 'neutral':
      return {
        icon: <Minus className="w-3 h-3" />,
        label: 'Neutral',
        color: 'var(--text-muted)',
      };
    default:
      return {
        icon: <Minus className="w-3 h-3" />,
        label: 'Unknown',
        color: 'var(--text-muted)',
      };
  }
}

function getEventIcon(eventType: EventType): React.ReactNode {
  switch (eventType) {
    case 'email_sent':
    case 'email_received':
      return <Mail className="w-4 h-4" />;
    case 'meeting':
      return <Calendar className="w-4 h-4" />;
    case 'call':
      return <Phone className="w-4 h-4" />;
    case 'note':
      return <FileText className="w-4 h-4" />;
    case 'signal':
      return <Zap className="w-4 h-4" />;
    default:
      return <FileText className="w-4 h-4" />;
  }
}

function getEventTypeLabel(eventType: EventType): string {
  switch (eventType) {
    case 'email_sent':
      return 'Email Sent';
    case 'email_received':
      return 'Email Received';
    case 'meeting':
      return 'Meeting';
    case 'call':
      return 'Call';
    case 'note':
      return 'Note';
    case 'signal':
      return 'Signal Detected';
    default:
      return 'Event';
  }
}

// ============================================================================
// Sub-Components
// ============================================================================

function StakeholderCard({ stakeholder }: { stakeholder: Stakeholder }) {
  const roleColor = getRoleColor(stakeholder.role);
  const roleLabel = getRoleLabel(stakeholder.role);
  const sentimentInfo = getSentimentIndicator(stakeholder.sentiment);

  return (
    <div
      className={cn(
        'p-3 rounded-lg border transition-all duration-200',
        'hover:shadow-sm cursor-pointer'
      )}
      style={{
        backgroundColor: 'var(--bg-elevated)',
        borderColor: 'var(--border)',
      }}
      data-aria-id={`stakeholder-${stakeholder.id}`}
    >
      {/* Header with Avatar and Name */}
      <div className="flex items-start gap-3">
        <Avatar
          name={stakeholder.contact_name || stakeholder.contact_email}
          size="md"
        />
        <div className="flex-1 min-w-0">
          <h4
            className="text-sm font-medium truncate"
            style={{ color: 'var(--text-primary)' }}
          >
            {stakeholder.contact_name || stakeholder.contact_email.split('@')[0]}
          </h4>
          <p
            className="text-xs truncate"
            style={{ color: 'var(--text-secondary)' }}
          >
            {stakeholder.title || 'No title'}
          </p>
        </div>
      </div>

      {/* Role and Sentiment Tags */}
      <div className="flex items-center gap-2 mt-3">
        {/* Role Tag */}
        <span
          className="px-2 py-0.5 rounded text-xs font-medium"
          style={{
            backgroundColor: `${roleColor}15`,
            color: roleColor,
          }}
        >
          {roleLabel}
        </span>

        {/* Sentiment Indicator */}
        <span
          className="flex items-center gap-1 px-2 py-0.5 rounded text-xs"
          style={{
            backgroundColor: `${sentimentInfo.color}10`,
            color: sentimentInfo.color,
          }}
          title={`Sentiment: ${sentimentInfo.label}`}
        >
          {sentimentInfo.icon}
          <span className="sr-only">{sentimentInfo.label}</span>
        </span>
      </div>

      {/* Last Contacted */}
      {stakeholder.last_contacted_at && (
        <p
          className="text-xs mt-2 flex items-center gap-1"
          style={{ color: 'var(--text-muted)' }}
        >
          <Clock className="w-3 h-3" />
          Last contact: {formatRelativeTime(stakeholder.last_contacted_at)}
        </p>
      )}
    </div>
  );
}

function TimelineEventCard({
  event,
  isLatest,
}: {
  event: LeadEvent;
  isLatest: boolean;
}) {
  const eventIcon = getEventIcon(event.event_type);
  const eventTypeLabel = getEventTypeLabel(event.event_type);

  return (
    <div
      className={cn('flex gap-3', isLatest && 'relative')}
      data-aria-id={`event-${event.id}`}
    >
      {/* Timeline Dot and Line */}
      <div className="flex flex-col items-center">
        <div
          className={cn(
            'w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0',
            isLatest && 'ring-2 ring-offset-2 ring-[var(--accent)] ring-offset-[var(--bg-primary)]'
          )}
          style={{
            backgroundColor: isLatest ? 'var(--accent)' : 'var(--bg-subtle)',
            color: isLatest ? 'white' : 'var(--text-secondary)',
          }}
        >
          {eventIcon}
        </div>
        {/* Vertical line */}
        <div
          className="flex-1 w-px mt-2"
          style={{ backgroundColor: 'var(--border)' }}
        />
      </div>

      {/* Event Content Card */}
      <div
        className={cn(
          'flex-1 pb-6',
          'rounded-lg border p-4 transition-all duration-200',
          'hover:shadow-sm'
        )}
        style={{
          backgroundColor: 'var(--bg-elevated)',
          borderColor: isLatest ? 'var(--accent)' : 'var(--border)',
        }}
      >
        {/* Event Header */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <span
              className="text-xs font-medium px-2 py-0.5 rounded"
              style={{
                backgroundColor: 'var(--bg-subtle)',
                color: 'var(--text-secondary)',
              }}
            >
              {eventTypeLabel}
            </span>
            {event.direction && (
              <span
                className="text-xs"
                style={{ color: 'var(--text-muted)' }}
              >
                {event.direction === 'inbound' ? 'Inbound' : 'Outbound'}
              </span>
            )}
          </div>
          <time
            className="text-xs"
            style={{ color: 'var(--text-muted)' }}
            dateTime={event.occurred_at}
            title={formatFullDate(event.occurred_at)}
          >
            {formatRelativeTime(event.occurred_at)}
          </time>
        </div>

        {/* Subject */}
        {event.subject && (
          <h4
            className="text-sm font-medium mb-2"
            style={{ color: 'var(--text-primary)' }}
          >
            {event.subject}
          </h4>
        )}

        {/* Content */}
        {event.content && (
          <p
            className="text-sm leading-relaxed"
            style={{ color: 'var(--text-secondary)' }}
          >
            {event.content}
          </p>
        )}

        {/* Participants */}
        {event.participants && event.participants.length > 0 && (
          <div className="mt-3 flex items-center gap-1 flex-wrap">
            <UserCircle2
              className="w-3 h-3 flex-shrink-0"
              style={{ color: 'var(--text-muted)' }}
            />
            {event.participants.map((participant, index) => (
              <span
                key={index}
                className="text-xs"
                style={{ color: 'var(--text-muted)' }}
              >
                {participant}
                {index < event.participants.length - 1 && ', '}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function InsightBadge({ insight }: { insight: Insight }) {
  const typeColors: Record<string, { bg: string; text: string }> = {
    buying_signal: { bg: 'rgba(107, 143, 113, 0.15)', text: 'var(--success)' },
    commitment: { bg: 'rgba(46, 102, 255, 0.15)', text: 'var(--accent)' },
    objection: { bg: 'rgba(184, 149, 106, 0.15)', text: 'var(--warning)' },
    risk: { bg: 'rgba(166, 107, 107, 0.15)', text: 'var(--critical)' },
    opportunity: { bg: 'rgba(46, 102, 255, 0.15)', text: 'var(--accent)' },
  };

  const colors = typeColors[insight.insight_type] || {
    bg: 'var(--bg-subtle)',
    text: 'var(--text-secondary)',
  };

  const typeLabels: Record<string, string> = {
    buying_signal: 'Buying Signal',
    commitment: 'Commitment',
    objection: 'Objection',
    risk: 'Risk',
    opportunity: 'Opportunity',
  };

  return (
    <div
      className="px-2 py-1 rounded text-xs font-medium"
      style={{
        backgroundColor: colors.bg,
        color: colors.text,
      }}
      title={`${typeLabels[insight.insight_type] || insight.insight_type}: ${insight.content}`}
    >
      {typeLabels[insight.insight_type] || insight.insight_type}
    </div>
  );
}

// ============================================================================
// Loading Skeleton
// ============================================================================

function LeadDetailSkeleton() {
  return (
    <div className="flex-1 overflow-y-auto p-8 animate-pulse">
      {/* Back button skeleton */}
      <div className="h-4 w-32 bg-[var(--border)] rounded mb-6" />

      {/* Header skeleton */}
      <div className="bg-[var(--bg-elevated)] border border-[var(--border)] rounded-xl p-6 mb-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="h-8 w-64 bg-[var(--border)] rounded" />
          <div className="h-5 w-16 bg-[var(--border)] rounded-full" />
          <div className="h-5 w-20 bg-[var(--border)] rounded-full" />
        </div>
        <div className="h-4 w-40 bg-[var(--border)] rounded mb-4" />
        <div className="flex items-center gap-4">
          <div className="h-2 w-24 bg-[var(--border)] rounded-full" />
          <div className="h-4 w-20 bg-[var(--border)] rounded" />
        </div>
      </div>

      {/* Content skeleton */}
      <div className="flex gap-6">
        {/* Stakeholders skeleton */}
        <div className="w-[280px] flex-shrink-0">
          <div className="h-4 w-24 bg-[var(--border)] rounded mb-4" />
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <div
                key={i}
                className="p-3 rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)]"
              >
                <div className="flex items-center gap-3 mb-3">
                  <div className="w-10 h-10 rounded-full bg-[var(--border)]" />
                  <div className="flex-1">
                    <div className="h-4 w-24 bg-[var(--border)] rounded mb-1" />
                    <div className="h-3 w-16 bg-[var(--border)] rounded" />
                  </div>
                </div>
                <div className="flex gap-2">
                  <div className="h-5 w-16 bg-[var(--border)] rounded" />
                  <div className="h-5 w-10 bg-[var(--border)] rounded" />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Timeline skeleton */}
        <div className="flex-1">
          <div className="h-4 w-20 bg-[var(--border)] rounded mb-4" />
          <div className="space-y-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="flex gap-3">
                <div className="w-8 h-8 rounded-full bg-[var(--border)]" />
                <div className="flex-1 p-4 rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)]">
                  <div className="flex justify-between mb-2">
                    <div className="h-4 w-20 bg-[var(--border)] rounded" />
                    <div className="h-3 w-12 bg-[var(--border)] rounded" />
                  </div>
                  <div className="h-4 w-3/4 bg-[var(--border)] rounded mb-2" />
                  <div className="h-3 w-full bg-[var(--border)] rounded" />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Main Component
// ============================================================================

export function LeadDetailPage({ leadId }: LeadDetailPageProps) {
  const navigate = useNavigate();

  // Fetch lead data
  const { data: lead, isLoading: isLeadLoading, error: leadError } = useLead(leadId);
  const { data: stakeholders, isLoading: isStakeholdersLoading } = useLeadStakeholders(leadId);
  const { data: timeline, isLoading: isTimelineLoading } = useLeadTimeline(leadId);
  const { data: insights } = useLeadInsights(leadId);

  // Combined loading state
  const isLoading = isLeadLoading || isStakeholdersLoading || isTimelineLoading;

  // Handle not found
  if (!isLoading && (leadError || !lead)) {
    return (
      <div
        className="flex-1 flex flex-col h-full"
        style={{ backgroundColor: 'var(--bg-primary)' }}
      >
        <div className="flex-1 overflow-y-auto p-8">
          <button
            onClick={() => navigate('/pipeline')}
            className={cn(
              'flex items-center gap-2 mb-6',
              'text-sm font-medium transition-colors',
              'hover:text-[var(--accent)]'
            )}
            style={{ color: 'var(--text-secondary)' }}
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Pipeline
          </button>
          <EmptyState
            title="Lead not found"
            description="This lead may have been removed or the ID is invalid."
            suggestion="Return to Pipeline"
            onSuggestion={() => navigate('/pipeline')}
            icon={<AlertCircle className="w-8 h-8" />}
          />
        </div>
      </div>
    );
  }

  // Loading state
  if (isLoading) {
    return (
      <div
        className="flex-1 flex flex-col h-full"
        style={{ backgroundColor: 'var(--bg-primary)' }}
      >
        <LeadDetailSkeleton />
      </div>
    );
  }

  // Sort timeline by date (newest first)
  const sortedTimeline = [...(timeline || [])].sort(
    (a, b) => new Date(b.occurred_at).getTime() - new Date(a.occurred_at).getTime()
  );

  // Get unaddressed insights
  const activeInsights = (insights || []).filter((i) => !i.addressed_at);

  return (
    <div
      className="flex-1 flex flex-col h-full"
      style={{ backgroundColor: 'var(--bg-primary)' }}
    >
      <div className="flex-1 overflow-y-auto p-8">
        {/* Back button */}
        <button
          onClick={() => navigate('/pipeline')}
          className={cn(
            'flex items-center gap-2 mb-6',
            'text-sm font-medium transition-colors',
            'hover:text-[var(--accent)]'
          )}
          style={{ color: 'var(--text-secondary)' }}
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Pipeline
        </button>

        {/* Header Card */}
        <div
          className="bg-[var(--bg-elevated)] border border-[var(--border)] rounded-xl p-6 mb-6"
          data-aria-id={`lead-header-${leadId}`}
        >
          {/* Company Name with Badges */}
          <div className="flex items-center gap-3 flex-wrap mb-3">
            <h1
              className="font-display text-2xl italic"
              style={{ color: 'var(--text-primary)' }}
            >
              {lead!.company_name}
            </h1>

            {/* CRM Verified Badge */}
            {lead!.crm_id && (
              <span
                className="flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium"
                style={{
                  backgroundColor: 'rgba(107, 143, 113, 0.15)',
                  color: 'var(--success)',
                }}
              >
                <Check className="w-3 h-3" />
                CRM Verified
              </span>
            )}

            {/* Status Tag */}
            <span
              className="px-2 py-0.5 rounded-full text-xs font-medium capitalize"
              style={{
                backgroundColor: `${getStatusColor(lead!.status)}15`,
                color: getStatusColor(lead!.status),
              }}
            >
              {lead!.status}
            </span>
          </div>

          {/* Lead ID */}
          <p
            className="text-xs mb-4"
            style={{ color: 'var(--text-muted)' }}
          >
            Lead ID: {lead!.id}
          </p>

          {/* Metrics Bar */}
          <div className="flex items-center gap-6 flex-wrap">
            {/* Health Score */}
            <div className="flex items-center gap-2">
              <span
                className="text-xs font-medium"
                style={{ color: 'var(--text-secondary)' }}
              >
                Health Score
              </span>
              <HealthBar score={lead!.health_score} size="sm" />
            </div>

            {/* Lifecycle Stage */}
            <div className="flex items-center gap-2">
              <span
                className="text-xs font-medium"
                style={{ color: 'var(--text-secondary)' }}
              >
                Stage
              </span>
              <span
                className="px-2 py-0.5 rounded text-xs font-medium capitalize"
                style={{
                  backgroundColor: 'var(--bg-subtle)',
                  color: 'var(--text-primary)',
                }}
              >
                {lead!.lifecycle_stage}
              </span>
            </div>

            {/* CRM Sync Indicator */}
            {lead!.crm_provider && (
              <div className="flex items-center gap-1.5">
                <RefreshCw
                  className="w-3.5 h-3.5"
                  style={{ color: 'var(--success)' }}
                />
                <span
                  className="text-xs"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  Synced with {lead!.crm_provider}
                </span>
              </div>
            )}

            {/* Expected Value */}
            {lead!.expected_value && (
              <div className="flex items-center gap-2">
                <span
                  className="text-xs font-medium"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  Value
                </span>
                <span
                  className="text-sm font-medium"
                  style={{ color: 'var(--text-primary)' }}
                >
                  ${lead!.expected_value.toLocaleString()}
                </span>
              </div>
            )}

            {/* Expected Close Date */}
            {lead!.expected_close_date && (
              <div className="flex items-center gap-2">
                <span
                  className="text-xs font-medium"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  Close Date
                </span>
                <span
                  className="text-sm"
                  style={{ color: 'var(--text-primary)' }}
                >
                  {new Date(lead!.expected_close_date).toLocaleDateString('en-US', {
                    month: 'short',
                    day: 'numeric',
                    year: 'numeric',
                  })}
                </span>
              </div>
            )}
          </div>

          {/* Active Insights */}
          {activeInsights.length > 0 && (
            <div className="mt-4 pt-4 border-t border-[var(--border)]">
              <span
                className="text-xs font-medium mb-2 block"
                style={{ color: 'var(--text-secondary)' }}
              >
                Active Insights
              </span>
              <div className="flex flex-wrap gap-2">
                {activeInsights.slice(0, 5).map((insight) => (
                  <InsightBadge key={insight.id} insight={insight} />
                ))}
                {activeInsights.length > 5 && (
                  <span
                    className="px-2 py-1 rounded text-xs"
                    style={{
                      backgroundColor: 'var(--bg-subtle)',
                      color: 'var(--text-muted)',
                    }}
                  >
                    +{activeInsights.length - 5} more
                  </span>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Two-Column Layout: Stakeholders + Timeline */}
        <div className="flex gap-6">
          {/* Stakeholders Column */}
          <div className="w-[280px] flex-shrink-0">
            <h2
              className="text-sm font-medium mb-4"
              style={{ color: 'var(--text-primary)' }}
            >
              Stakeholders ({stakeholders?.length || 0})
            </h2>

            {stakeholders && stakeholders.length > 0 ? (
              <div className="space-y-3">
                {stakeholders.map((stakeholder) => (
                  <StakeholderCard
                    key={stakeholder.id}
                    stakeholder={stakeholder}
                  />
                ))}
              </div>
            ) : (
              <div
                className="p-4 rounded-lg border border-dashed"
                style={{
                  borderColor: 'var(--border)',
                  backgroundColor: 'var(--bg-subtle)',
                }}
              >
                <p
                  className="text-sm text-center"
                  style={{ color: 'var(--text-muted)' }}
                >
                  No stakeholders identified yet.
                </p>
                <p
                  className="text-xs text-center mt-1"
                  style={{ color: 'var(--text-muted)' }}
                >
                  ARIA will identify stakeholders from conversations.
                </p>
              </div>
            )}
          </div>

          {/* Timeline Column */}
          <div className="flex-1">
            <h2
              className="text-sm font-medium mb-4"
              style={{ color: 'var(--text-primary)' }}
            >
              Activity Timeline ({timeline?.length || 0} events)
            </h2>

            {sortedTimeline.length > 0 ? (
              <div className="space-y-0">
                {sortedTimeline.map((event, index) => (
                  <TimelineEventCard
                    key={event.id}
                    event={event}
                    isLatest={index === 0}
                  />
                ))}
              </div>
            ) : (
              <div
                className="p-6 rounded-lg border border-dashed"
                style={{
                  borderColor: 'var(--border)',
                  backgroundColor: 'var(--bg-subtle)',
                }}
              >
                <p
                  className="text-sm text-center"
                  style={{ color: 'var(--text-muted)' }}
                >
                  No activity recorded yet.
                </p>
                <p
                  className="text-xs text-center mt-1"
                  style={{ color: 'var(--text-muted)' }}
                >
                  Events will appear here as ARIA tracks interactions.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default LeadDetailPage;
