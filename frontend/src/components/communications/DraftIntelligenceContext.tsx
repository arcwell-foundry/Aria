/**
 * DraftIntelligenceContext - Collapsible panel showing Jarvis insights
 * and market signals relevant to an email draft's recipient.
 *
 * Follows ARIA Design System v1.0:
 * - LIGHT THEME (Communications is a content page)
 * - CSS variables for all colors
 * - Lucide icons
 * - Collapsible panel, collapsed by default
 */

import { useState, useMemo } from 'react';
import {
  Zap,
  ChevronDown,
  ChevronRight,
  TrendingUp,
  Shield,
  Clock,
} from 'lucide-react';
import { useIntelligenceInsights, useSignals } from '@/hooks/useIntelPanelData';
import type { IntelligenceInsight } from '@/api/intelligence';
import type { Signal } from '@/api/signals';

interface DraftIntelligenceContextProps {
  leadId?: string;
  companyName?: string;
}

// Classification to border color mapping
const CLASSIFICATION_BORDER: Record<string, string> = {
  opportunity: 'var(--success)',
  threat: 'var(--critical)',
  neutral: 'var(--text-secondary)',
};

// Classification to icon mapping
const CLASSIFICATION_ICON: Record<string, typeof TrendingUp> = {
  opportunity: TrendingUp,
  threat: Shield,
  neutral: Clock,
};

// Time horizon display labels
const TIME_HORIZON_LABELS: Record<string, string> = {
  immediate: 'Immediate',
  short_term: 'Short-term',
  medium_term: 'Medium-term',
  long_term: 'Long-term',
};

export function DraftIntelligenceContext({
  leadId,
  companyName,
}: DraftIntelligenceContextProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const { data: allInsights } = useIntelligenceInsights({ limit: 5 });
  const { data: allSignals } = useSignals({ company: companyName, limit: 5 });

  // Filter insights relevant to this draft's lead/company
  const relevantInsights = useMemo(() => {
    if (!allInsights) return [];
    const lowerCompany = companyName?.toLowerCase() ?? '';

    return allInsights
      .filter((insight: IntelligenceInsight) => {
        const matchesLead = leadId && insight.affected_goals.length > 0;
        const matchesCompany =
          lowerCompany &&
          insight.trigger_event.toLowerCase().includes(lowerCompany);
        return matchesLead || matchesCompany;
      })
      .slice(0, 3);
  }, [allInsights, leadId, companyName]);

  // Filter signals: exclude dismissed ones
  const relevantSignals = useMemo(() => {
    if (!allSignals) return [];
    return allSignals
      .filter((signal: Signal) => !signal.dismissed_at)
      .slice(0, 3);
  }, [allSignals]);

  const totalItems = relevantInsights.length + relevantSignals.length;

  // Don't render if there's no relevant content
  if (totalItems === 0) return null;

  const ChevronIcon = isExpanded ? ChevronDown : ChevronRight;

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
        <span
          className="ml-auto px-2 py-0.5 rounded-full text-xs font-mono"
          style={{
            backgroundColor: 'var(--bg-subtle)',
            color: 'var(--text-secondary)',
          }}
        >
          {totalItems}
        </span>
      </button>

      {/* Expanded content */}
      {isExpanded && (
        <div
          className="border-t px-4 pb-4"
          style={{ borderColor: 'var(--border)' }}
        >
          {/* Jarvis Insights sub-section */}
          {relevantInsights.length > 0 && (
            <div className="mt-4">
              <h4
                className="text-xs font-medium uppercase tracking-wider mb-3"
                style={{ color: 'var(--text-secondary)' }}
              >
                Jarvis Insights
              </h4>
              <div className="space-y-3">
                {relevantInsights.map((insight: IntelligenceInsight) => {
                  const borderColor =
                    CLASSIFICATION_BORDER[insight.classification] ??
                    'var(--text-secondary)';
                  const IconComponent =
                    CLASSIFICATION_ICON[insight.classification] ?? Clock;

                  return (
                    <div
                      key={insight.id}
                      className="pl-3 py-2 rounded-r"
                      style={{
                        borderLeft: `3px solid ${borderColor}`,
                        backgroundColor: 'var(--bg-subtle)',
                      }}
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <IconComponent
                          className="w-3.5 h-3.5 flex-shrink-0"
                          style={{ color: borderColor }}
                        />
                        <span
                          className="text-xs font-medium uppercase"
                          style={{ color: borderColor }}
                        >
                          {insight.classification}
                        </span>
                        {insight.time_horizon && (
                          <span
                            className="text-xs font-mono ml-auto"
                            style={{ color: 'var(--text-secondary)' }}
                          >
                            {TIME_HORIZON_LABELS[insight.time_horizon] ??
                              insight.time_horizon}
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
                        {insight.content}
                      </p>
                      <div className="flex items-center gap-3 mt-1.5">
                        <span
                          className="text-xs font-mono"
                          style={{ color: 'var(--text-secondary)' }}
                        >
                          Confidence: {Math.round(insight.confidence * 100)}%
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Market Signals sub-section */}
          {relevantSignals.length > 0 && (
            <div className={relevantInsights.length > 0 ? 'mt-4' : 'mt-4'}>
              <h4
                className="text-xs font-medium uppercase tracking-wider mb-3"
                style={{ color: 'var(--text-secondary)' }}
              >
                Market Signals
              </h4>
              <div className="space-y-3">
                {relevantSignals.map((signal: Signal) => (
                  <div
                    key={signal.id}
                    className="pl-3 py-2 rounded-r"
                    style={{
                      borderLeft: '3px solid var(--accent)',
                      backgroundColor: 'var(--bg-subtle)',
                    }}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <span
                        className="text-xs font-medium uppercase"
                        style={{ color: 'var(--accent)' }}
                      >
                        {signal.signal_type.replace(/_/g, ' ')}
                      </span>
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
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
