import { useState } from 'react';
import { Zap, Shield, TrendingUp, ThumbsUp, ThumbsDown, Clock } from 'lucide-react';

interface JarvisInsightData {
  id: string;
  content: string;
  classification: 'opportunity' | 'threat' | 'neutral';
  confidence: number;
  time_horizon: string | null;
}

const PLACEHOLDER_INSIGHTS: JarvisInsightData[] = [
  {
    id: '1',
    content: 'Lonza Q2 capacity expansion creates window for renegotiating supply terms before competitors react',
    classification: 'opportunity',
    confidence: 0.87,
    time_horizon: 'short_term',
  },
  {
    id: '2',
    content: 'FDA advisory committee vote on biosimilar pathway may impact 3 active pipeline deals',
    classification: 'threat',
    confidence: 0.72,
    time_horizon: 'medium_term',
  },
  {
    id: '3',
    content: 'Cross-domain connection detected between Catalent logistics delay and Lonza opportunity',
    classification: 'neutral',
    confidence: 0.65,
    time_horizon: null,
  },
];

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

export interface JarvisInsightsModuleProps {
  insights?: JarvisInsightData[];
}

export function JarvisInsightsModule({ insights = PLACEHOLDER_INSIGHTS }: JarvisInsightsModuleProps) {
  const [feedbackGiven, setFeedbackGiven] = useState<Record<string, string>>({});

  const handleFeedback = (insightId: string, feedback: string) => {
    setFeedbackGiven((prev) => ({ ...prev, [insightId]: feedback }));
    // In production, this would call PATCH /intelligence/insights/{id}/feedback
  };

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
                  <span
                    className="font-mono text-[10px] uppercase font-medium"
                    style={{ color: style.color }}
                  >
                    {insight.classification}
                  </span>
                  <p
                    className="font-sans text-[12px] leading-[1.5] mt-0.5"
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

                  {/* Confidence bar */}
                  <div
                    className="mt-1.5 h-[3px] rounded-full"
                    style={{ backgroundColor: 'var(--border)', width: '100%' }}
                  >
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${insight.confidence * 100}%`,
                        backgroundColor: style.color,
                        opacity: 0.7,
                      }}
                    />
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
                      <span
                        className="font-mono text-[10px]"
                        style={{ color: 'var(--text-secondary)' }}
                      >
                        {(insight.confidence * 100).toFixed(0)}% conf
                      </span>
                    </div>

                    {/* Feedback buttons */}
                    {!hasFeedback ? (
                      <div className="flex items-center gap-1">
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
                          aria-label="Not helpful"
                        >
                          <ThumbsDown size={11} />
                        </button>
                      </div>
                    ) : (
                      <span
                        className="font-mono text-[10px]"
                        style={{ color: 'var(--text-secondary)' }}
                      >
                        {hasFeedback === 'helpful' ? 'Noted' : 'Noted'}
                      </span>
                    )}
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
