/**
 * DraftIntelligenceContext - Collapsible panel showing intelligence insights
 * and market signals relevant to an email draft's recipient.
 *
 * Uses relevance-based matching via backend endpoint:
 * 1. RECIPIENT MATCH: Domain matches monitored_entity's domains
 * 2. SUBJECT MATCH: Keywords from subject line match signal headlines
 * 3. RELATIONSHIP CONTEXT: Email interaction history fallback
 * 4. EMPTY STATE: Clean message if nothing relevant
 *
 * Follows ARIA Design System v1.0:
 * - LIGHT THEME (Communications is a content page)
 * - CSS variables for all colors
 * - Lucide icons
 * - Collapsible panel, collapsed by default
 */

import { useState } from 'react';
import {
  Zap,
  ChevronDown,
  ChevronRight,
  Users,
  Mail,
  Inbox,
} from 'lucide-react';
import { useDraftIntelligenceContext, formatRelativeTime } from '@/hooks/useIntelPanelData';

interface DraftIntelligenceContextProps {
  draftId: string;
}

// Classification to border color mapping
const CLASSIFICATION_COLORS: Record<string, string> = {
  opportunity: 'var(--success)',
  threat: 'var(--critical)',
  neutral: 'var(--text-secondary)',
  // Signal types
  funding: 'var(--accent)',
  hiring: 'var(--success)',
  leadership: 'var(--accent)',
  product: 'var(--success)',
  partnership: 'var(--accent)',
  regulatory: 'var(--critical)',
  earnings: 'var(--text-secondary)',
  clinical_trial: 'var(--success)',
  fda_approval: 'var(--success)',
  patent: 'var(--text-secondary)',
};

// Signal type to display label mapping
const SIGNAL_TYPE_LABELS: Record<string, string> = {
  funding: 'Funding',
  hiring: 'Hiring',
  leadership: 'Leadership',
  product: 'Product',
  partnership: 'Partnership',
  regulatory: 'Regulatory',
  earnings: 'Earnings',
  clinical_trial: 'Clinical Trial',
  fda_approval: 'FDA Approval',
  patent: 'Patent',
};

export function DraftIntelligenceContext({
  draftId,
}: DraftIntelligenceContextProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const { data: context, isLoading, error } = useDraftIntelligenceContext(draftId);

  // Loading state
  if (isLoading) {
    return (
      <div
        className="mb-6 rounded-lg border animate-pulse"
        style={{
          borderColor: 'var(--border)',
          backgroundColor: 'var(--bg-elevated)',
        }}
      >
        <div className="px-4 py-3 flex items-center gap-2">
          <div className="w-4 h-4 rounded bg-[var(--border)]" />
          <div className="w-32 h-4 rounded bg-[var(--border)]" />
        </div>
      </div>
    );
  }

  // Error or no data - don't render
  if (error || !context) {
    return null;
  }

  // Empty state - show clean message
  const hasContent = context.has_signals || context.relationship_context;
  if (!hasContent && context.match_type === 'empty') {
    return null; // Don't show anything if no relevant context
  }

  const ChevronIcon = isExpanded ? ChevronDown : ChevronRight;
  const totalItems = context.signals.length + (context.relationship_context ? 1 : 0);

  return (
    <div
      className="mb-6 rounded-lg border overflow-hidden"
      style={{
        borderColor: 'var(--border)',
        backgroundColor: 'var(--bg-elevated)',
      }}
      data-aria-id="draft-intelligence-context"
    >
      {/* Header - always visible */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center gap-2 px-4 py-3 text-left transition-colors hover:opacity-90"
        style={{ backgroundColor: 'var(--bg-elevated)' }}
      >
        <ChevronIcon
          className="w-4 h-4 flex-shrink-0"
          style={{ color: 'var(--text-secondary)' }}
        />
        <Zap
          className="w-4 h-4 flex-shrink-0"
          style={{ color: 'var(--accent)' }}
        />
        <span
          className="text-sm font-medium"
          style={{ color: 'var(--text-primary)' }}
        >
          Intelligence Context
        </span>
        {totalItems > 0 && (
          <span
            className="ml-auto px-2 py-0.5 rounded-full text-xs font-mono"
            style={{
              backgroundColor: 'var(--bg-subtle)',
              color: 'var(--text-secondary)',
            }}
          >
            {totalItems}
          </span>
        )}
      </button>

      {/* Expanded content */}
      {isExpanded && (
        <div
          className="border-t px-4 pb-4"
          style={{ borderColor: 'var(--border)' }}
        >
          {/* Market Signals */}
          {context.has_signals && context.signals.length > 0 && (
            <div className="mt-4">
              <h4
                className="text-xs font-medium uppercase tracking-wider mb-3"
                style={{ color: 'var(--text-secondary)' }}
              >
                Market Signals
              </h4>
              <div className="space-y-3">
                {context.signals.map((signal) => {
                  const borderColor =
                    CLASSIFICATION_COLORS[signal.signal_type] ??
                    'var(--accent)';

                  return (
                    <div
                      key={signal.id}
                      className="pl-3 py-2 rounded-r"
                      style={{
                        borderLeft: `3px solid ${borderColor}`,
                        backgroundColor: 'var(--bg-subtle)',
                      }}
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <span
                          className="text-xs font-medium uppercase"
                          style={{ color: borderColor }}
                        >
                          {SIGNAL_TYPE_LABELS[signal.signal_type] ??
                            signal.signal_type.replace(/_/g, ' ')}
                        </span>
                        {signal.relevance_source === 'domain' && (
                          <span
                            className="text-xs px-1.5 py-0.5 rounded"
                            style={{
                              backgroundColor: 'var(--accent)',
                              color: 'white',
                            }}
                          >
                            Domain Match
                          </span>
                        )}
                        {signal.relevance_source === 'subject' && (
                          <span
                            className="text-xs px-1.5 py-0.5 rounded"
                            style={{
                              backgroundColor: 'var(--text-secondary)',
                              color: 'white',
                            }}
                          >
                            Topic Match
                          </span>
                        )}
                      </div>
                      <p
                        className="text-sm leading-snug"
                        style={{
                          color: 'var(--text-primary)',
                          display: '-webkit-box',
                          WebkitLineClamp: 2,
                          WebkitBoxOrient: 'vertical',
                          overflow: 'hidden',
                        }}
                      >
                        {signal.content}
                      </p>
                      <div className="flex items-center gap-3 mt-1.5">
                        <span
                          className="text-xs font-mono"
                          style={{ color: 'var(--text-secondary)' }}
                        >
                          {signal.company_name}
                        </span>
                        <span
                          className="text-xs"
                          style={{ color: 'var(--text-secondary)' }}
                        >
                          {formatRelativeTime(signal.created_at)}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Relationship Context (fallback) */}
          {!context.has_signals && context.relationship_context && (
            <div className="mt-4">
              <h4
                className="text-xs font-medium uppercase tracking-wider mb-3"
                style={{ color: 'var(--text-secondary)' }}
              >
                Relationship Context
              </h4>
              <div
                className="pl-3 py-2 rounded-r"
                style={{
                  borderLeft: '3px solid var(--text-secondary)',
                  backgroundColor: 'var(--bg-subtle)',
                }}
              >
                <div className="flex items-center gap-2 mb-2">
                  <Users
                    className="w-3.5 h-3.5"
                    style={{ color: 'var(--text-secondary)' }}
                  />
                  <span
                    className="text-sm"
                    style={{ color: 'var(--text-primary)' }}
                  >
                    {context.relationship_context.relationship_summary}
                  </span>
                </div>
                {context.relationship_context.last_interaction_date && (
                  <div className="flex items-center gap-2 mt-1.5">
                    <Mail
                      className="w-3 h-3"
                      style={{ color: 'var(--text-secondary)' }}
                    />
                    <span
                      className="text-xs"
                      style={{ color: 'var(--text-secondary)' }}
                    >
                      Last contact:{' '}
                      {formatRelativeTime(
                        context.relationship_context.last_interaction_date
                      )}
                    </span>
                  </div>
                )}
              </div>
              <p
                className="mt-2 text-xs italic"
                style={{ color: 'var(--text-secondary)' }}
              >
                No specific market intelligence for this contact
              </p>
            </div>
          )}

          {/* Empty State */}
          {!context.has_signals && !context.relationship_context && (
            <div
              className="mt-4 flex items-center gap-3 py-3 px-3 rounded-lg"
              style={{ backgroundColor: 'var(--bg-subtle)' }}
            >
              <Inbox
                className="w-5 h-5 flex-shrink-0"
                style={{ color: 'var(--text-secondary)' }}
              />
              <p
                className="text-sm"
                style={{ color: 'var(--text-secondary)' }}
              >
                No intelligence context available for this conversation.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
