import { useNavigate } from 'react-router-dom';
import { Zap, X } from 'lucide-react';
import { useShallow } from 'zustand/react/shallow';
import { useIntelligenceInsights } from '@/hooks/useIntelPanelData';
import { useRecommendationsStore } from '@/stores/recommendationsStore';

interface NextAction {
  id?: string;
  action: string;
  priority: 'high' | 'medium' | 'low';
  impact: string;
  agent: string;
}

const PRIORITY_COLORS: Record<string, string> = {
  high: 'var(--critical)',
  medium: 'var(--warning)',
  low: 'var(--info)',
};

function mapUrgencyToPriority(urgency: number): 'high' | 'medium' | 'low' {
  if (urgency >= 0.7) return 'high';
  if (urgency >= 0.4) return 'medium';
  return 'low';
}

function NextBestActionSkeleton() {
  return (
    <div className="space-y-2">
      <div className="h-3 w-32 rounded bg-[var(--border)] animate-pulse" />
      <div className="h-24 rounded-lg bg-[var(--border)] animate-pulse" />
    </div>
  );
}

export interface NextBestActionModuleProps {
  action?: NextAction;
}

export function NextBestActionModule({ action: propAction }: NextBestActionModuleProps) {
  const navigate = useNavigate();
  const { data: insights, isLoading } = useIntelligenceInsights({ limit: 5 });
  const liveRecommendations = useRecommendationsStore(
    useShallow((s) => s.items.filter((r) => !r.dismissed)),
  );
  const dismiss = useRecommendationsStore((s) => s.dismiss);

  if (isLoading && !propAction && liveRecommendations.length === 0) return <NextBestActionSkeleton />;

  // Build list of actions: live WS recommendations first, then API insights
  const actions: NextAction[] = [];

  // Live WS-pushed recommendations take priority
  for (const rec of liveRecommendations.slice(0, 3)) {
    actions.push({
      id: rec.id,
      action: rec.title,
      priority: rec.priority,
      impact: rec.description,
      agent: rec.agent,
    });
  }

  // Prop-based override
  if (propAction) {
    actions.unshift(propAction);
  }

  // Fill from API if no live recommendations
  if (actions.length === 0 && insights && insights.length > 0) {
    const top = insights[0];
    actions.push({
      action: top.recommended_actions?.[0] ?? top.content,
      priority: mapUrgencyToPriority(top.urgency ?? 0),
      impact: top.content,
      agent: top.insight_type ?? 'Strategist',
    });
  }

  if (actions.length === 0) {
    return (
      <div data-aria-id="intel-next-action" className="space-y-2">
        <h3
          className="font-sans text-[11px] font-medium uppercase tracking-wider mb-3"
          style={{ color: 'var(--text-secondary)' }}
        >
          Recommended Actions
        </h3>
        <div
          className="rounded-lg border p-4"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
        >
          <p className="font-sans text-[12px]" style={{ color: 'var(--text-secondary)' }}>
            No recommended actions right now. ARIA is analyzing your pipeline.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div data-aria-id="intel-next-action" className="space-y-2">
      <h3
        className="font-sans text-[11px] font-medium uppercase tracking-wider mb-3"
        style={{ color: 'var(--text-secondary)' }}
      >
        Recommended Actions
        {liveRecommendations.length > 0 && (
          <span
            className="ml-1.5 inline-flex items-center justify-center min-w-[18px] h-[18px] rounded-full text-[10px] font-mono px-1"
            style={{ backgroundColor: 'var(--accent)', color: 'white' }}
          >
            {liveRecommendations.length}
          </span>
        )}
      </h3>
      <div className="space-y-2">
        {actions.map((action, i) => (
          <div
            key={action.id ?? `action-${i}`}
            className="rounded-lg border p-3"
            style={{
              borderColor: 'var(--border)',
              backgroundColor: 'var(--bg-subtle)',
              borderLeftWidth: '3px',
              borderLeftColor: PRIORITY_COLORS[action.priority],
            }}
          >
            <div className="flex items-start gap-2">
              <Zap
                size={14}
                className="mt-0.5 flex-shrink-0"
                style={{ color: PRIORITY_COLORS[action.priority] }}
              />
              <div className="min-w-0 flex-1">
                <p className="font-sans text-[13px] leading-[1.5] font-medium" style={{ color: 'var(--text-primary)' }}>
                  {action.action}
                </p>
                {action.impact && action.impact !== action.action && (
                  <p className="font-sans text-[12px] leading-[1.5] mt-1" style={{ color: 'var(--text-secondary)' }}>
                    {action.impact}
                  </p>
                )}
                <div className="flex items-center gap-2 mt-1.5">
                  <span
                    className="font-mono text-[10px] uppercase"
                    style={{ color: PRIORITY_COLORS[action.priority] }}
                  >
                    {action.priority} priority
                  </span>
                  <span className="font-mono text-[10px]" style={{ color: 'var(--text-secondary)' }}>
                    · via {action.agent}
                  </span>
                </div>
                {/* Action buttons for live recommendations */}
                {action.id && (
                  <div className="flex items-center gap-2 mt-2">
                    <button
                      onClick={() => navigate(`/?discuss=recommendation&title=${encodeURIComponent(action.action)}`)}
                      className="font-sans text-[11px] font-medium px-2 py-1 rounded-md transition-colors"
                      style={{ color: 'var(--accent)', backgroundColor: 'rgba(46, 102, 255, 0.1)' }}
                    >
                      Act on This
                    </button>
                    <button
                      onClick={() => dismiss(action.id!)}
                      className="font-sans text-[11px] font-medium px-2 py-1 rounded-md transition-colors"
                      style={{ color: 'var(--text-secondary)' }}
                    >
                      <X size={12} className="inline mr-0.5" />
                      Dismiss
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
