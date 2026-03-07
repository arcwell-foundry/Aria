import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Zap, Shield, TrendingUp, ThumbsUp, ThumbsDown, Clock, Bookmark, ChevronDown, ChevronUp } from 'lucide-react';
import { useIntelligenceInsights, useInsightFeedback } from '@/hooks/useIntelPanelData';

interface JarvisInsightData {
  id: string;
  content: string;
  classification: 'opportunity' | 'threat' | 'neutral';
  confidence: number;
  combined_score: number;
  time_horizon: string | null;
}

/** Minimum quality score threshold for displaying insights */
const QUALITY_THRESHOLD = 0.5;
/** Minimum insights to show even if below threshold (never show empty when data exists) */
const MIN_INSIGHTS_TO_SHOW = 2;

const CLASSIFICATION_STYLES: Record<string, { color: string; icon: typeof Zap }> = {
  opportunity: { color: 'var(--success)', icon: TrendingUp },
  threat: { color: 'var(--critical)', icon: Shield },
  neutral: { color: 'var(--text-secondary)', icon: Zap },
};

const HORIZON_LABELS: Record<string, string> = {
  immediate: 'Immediate',
  short_term: 'Short-term',
  medium_term: 'Medium-term',
  long_term: 'Long-term',
};

function getPriorityLabel(insight: JarvisInsightData): { label: string; color: string } {
  if (insight.confidence >= 0.7 && insight.classification === 'threat') {
    return { label: 'Critical', color: '#DC2626' };
  }
  if (insight.confidence >= 0.6) {
    return { label: 'High Priority', color: '#F59E0B' };
  }
  if (insight.confidence >= 0.4) {
    return { label: 'Medium', color: '#5B6E8A' };
  }
  return { label: 'Low', color: '#94A3B8' };
}

function JarvisInsightsSkeleton() {
  return (
    <div className="space-y-2">
      <div className="h-3 w-32 rounded bg-[var(--border)] animate-pulse" />
      <div className="space-y-2">
        <div className="h-24 rounded-lg bg-[var(--border)] animate-pulse" />
        <div className="h-24 rounded-lg bg-[var(--border)] animate-pulse" />
        <div className="h-24 rounded-lg bg-[var(--border)] animate-pulse" />
      </div>
    </div>
  );
}

export interface JarvisInsightsModuleProps {
  insights?: JarvisInsightData[];
}

export function JarvisInsightsModule({ insights: propInsights }: JarvisInsightsModuleProps) {
  const [feedbackGiven, setFeedbackGiven] = useState<Record<string, string>>({});
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [bookmarked, setBookmarked] = useState<Set<string>>(new Set());
  const { data: apiInsights, isLoading } = useIntelligenceInsights({ limit: 5 });
  const feedbackMutation = useInsightFeedback();
  const navigate = useNavigate();

  if (isLoading && !propInsights) return <JarvisInsightsSkeleton />;

  const rawInsights: JarvisInsightData[] = propInsights ?? (apiInsights ?? []).map((i) => ({
    id: i.id,
    content: i.content,
    classification: i.classification,
    confidence: i.confidence,
    combined_score: i.combined_score ?? i.confidence,
    time_horizon: i.time_horizon,
  }));

  // Filter by quality threshold, but always show at least MIN_INSIGHTS_TO_SHOW
  const qualityInsights = rawInsights.filter((i) => i.combined_score >= QUALITY_THRESHOLD);
  const insights = qualityInsights.length >= MIN_INSIGHTS_TO_SHOW
    ? qualityInsights
    : rawInsights.slice(0, MIN_INSIGHTS_TO_SHOW);

  const handleFeedback = (insightId: string, feedback: string) => {
    setFeedbackGiven((prev) => ({ ...prev, [insightId]: feedback }));
    feedbackMutation.mutate({ insightId, feedback });
  };

  const toggleExpand = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleBookmark = (id: string) => {
    setBookmarked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleAct = (insight: JarvisInsightData) => {
    navigate(`/?discuss=insight&title=${encodeURIComponent(insight.content.slice(0, 80))}`);
  };

  if (insights.length === 0) {
    return (
      <div data-aria-id="intel-jarvis-insights" className="space-y-2">
        <h3
          className="font-sans text-[11px] font-medium uppercase tracking-wider mb-3"
          style={{ color: 'var(--text-secondary)' }}
        >
          Intelligence Insights
        </h3>
        <div
          className="rounded-lg border p-4"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
        >
          <p className="font-sans text-[12px]" style={{ color: 'var(--text-secondary)' }}>
            No intelligence insights yet. ARIA is analyzing your market.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div data-aria-id="intel-jarvis-insights" className="space-y-2">
      <h3
        className="font-sans text-[11px] font-medium uppercase tracking-wider mb-3"
        style={{ color: 'var(--text-secondary)' }}
      >
        Intelligence Insights
      </h3>
      <div className="space-y-2">
        {insights.slice(0, 5).map((insight) => {
          const style = CLASSIFICATION_STYLES[insight.classification] ?? CLASSIFICATION_STYLES.neutral;
          const Icon = style.icon;
          const hasFeedback = feedbackGiven[insight.id];
          const isExpanded = expandedIds.has(insight.id);
          const isBookmarked = bookmarked.has(insight.id);
          const priority = getPriorityLabel(insight);

          return (
            <div
              key={insight.id}
              className="rounded-lg border p-3"
              style={{
                borderColor: 'var(--border)',
                backgroundColor: 'var(--bg-subtle)',
                borderLeftWidth: '3px',
                borderLeftColor: style.color,
              }}
            >
              <div className="flex items-start gap-2">
                <Icon size={14} className="mt-0.5 flex-shrink-0" style={{ color: style.color }} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <span
                      className="font-mono text-[10px] uppercase font-medium"
                      style={{ color: style.color }}
                    >
                      {insight.classification}
                    </span>
                    <span
                      className="font-mono text-[10px] font-semibold px-1 py-0.5 rounded"
                      style={{
                        color: priority.color,
                        backgroundColor: `${priority.color}15`,
                      }}
                    >
                      {priority.label}
                    </span>
                  </div>

                  {/* Expandable content */}
                  <div
                    onClick={() => toggleExpand(insight.id)}
                    className="cursor-pointer"
                  >
                    <p
                      className="font-sans text-[12px] leading-[1.5] mt-0.5"
                      style={{
                        color: 'var(--text-primary)',
                        ...(isExpanded ? {} : {
                          display: '-webkit-box',
                          WebkitLineClamp: 2,
                          WebkitBoxOrient: 'vertical' as const,
                          overflow: 'hidden',
                        }),
                      }}
                    >
                      {insight.content}
                    </p>
                    <button
                      className="flex items-center gap-0.5 mt-1"
                      style={{ color: 'var(--text-secondary)' }}
                    >
                      {isExpanded ? (
                        <ChevronUp size={12} />
                      ) : (
                        <ChevronDown size={12} />
                      )}
                      <span className="font-mono text-[10px]">
                        {isExpanded ? 'Less' : 'More'}
                      </span>
                    </button>
                  </div>

                  <div className="flex items-center justify-between mt-1.5">
                    <div className="flex items-center gap-2">
                      {insight.time_horizon && (
                        <span className="flex items-center gap-0.5">
                          <Clock size={10} style={{ color: 'var(--text-secondary)' }} />
                          <span
                            className="font-mono text-[10px]"
                            style={{ color: 'var(--text-secondary)' }}
                          >
                            {HORIZON_LABELS[insight.time_horizon] ?? insight.time_horizon}
                          </span>
                        </span>
                      )}
                      {/* Act button */}
                      <button
                        onClick={() => handleAct(insight)}
                        className="inline-flex items-center gap-0.5 font-sans text-[10px] font-medium px-1.5 py-0.5 rounded-md transition-colors"
                        style={{ color: 'var(--accent)', backgroundColor: 'rgba(46, 102, 255, 0.08)' }}
                      >
                        <Zap size={10} />
                        Act
                      </button>
                    </div>

                    {/* Feedback + Bookmark buttons */}
                    <div className="flex items-center gap-1">
                      {!hasFeedback ? (
                        <>
                          <button
                            onClick={() => handleFeedback(insight.id, 'helpful')}
                            className="p-0.5 rounded transition-colors cursor-pointer"
                            style={{ color: 'var(--text-secondary)' }}
                            onMouseEnter={(e) => {
                              e.currentTarget.style.color = 'var(--success)';
                            }}
                            onMouseLeave={(e) => {
                              e.currentTarget.style.color = 'var(--text-secondary)';
                            }}
                            title="Mark as useful (improves ARIA's relevance)"
                            aria-label="Helpful"
                          >
                            <ThumbsUp size={11} />
                          </button>
                          <button
                            onClick={() => handleFeedback(insight.id, 'not_helpful')}
                            className="p-0.5 rounded transition-colors cursor-pointer"
                            style={{ color: 'var(--text-secondary)' }}
                            onMouseEnter={(e) => {
                              e.currentTarget.style.color = 'var(--critical)';
                            }}
                            onMouseLeave={(e) => {
                              e.currentTarget.style.color = 'var(--text-secondary)';
                            }}
                            title="Not helpful (improves ARIA's relevance)"
                            aria-label="Not helpful"
                          >
                            <ThumbsDown size={11} />
                          </button>
                        </>
                      ) : (
                        <span
                          className="font-mono text-[10px]"
                          style={{ color: 'var(--text-secondary)' }}
                        >
                          Noted
                        </span>
                      )}
                      <button
                        onClick={() => toggleBookmark(insight.id)}
                        className="p-0.5 rounded transition-colors cursor-pointer"
                        style={{ color: isBookmarked ? 'var(--accent)' : 'var(--text-secondary)' }}
                        title="Save to your intelligence library"
                        aria-label="Bookmark"
                      >
                        <Bookmark size={11} fill={isBookmarked ? 'currentColor' : 'none'} />
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
