import { Zap } from 'lucide-react';
import { useIntelligenceInsights } from '@/hooks/useIntelPanelData';

interface NextAction {
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
  const { data: insights, isLoading } = useIntelligenceInsights({ limit: 5 });

  if (isLoading && !propAction) return <NextBestActionSkeleton />;

  let action: NextAction;
  if (propAction) {
    action = propAction;
  } else if (insights && insights.length > 0) {
    const top = insights[0];
    action = {
      action: top.recommended_actions?.[0] ?? top.content,
      priority: mapUrgencyToPriority(top.urgency ?? 0),
      impact: top.content,
      agent: top.insight_type ?? 'Strategist',
    };
  } else {
    return (
      <div data-aria-id="intel-next-action" className="space-y-2">
        <h3
          className="font-sans text-[11px] font-medium uppercase tracking-wider mb-3"
          style={{ color: 'var(--text-secondary)' }}
        >
          Recommended Action
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
        Recommended Action
      </h3>
      <div
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
          <div className="min-w-0">
            <p className="font-sans text-[13px] leading-[1.5] font-medium" style={{ color: 'var(--text-primary)' }}>
              {action.action}
            </p>
            {action.impact !== action.action && (
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
          </div>
        </div>
      </div>
    </div>
  );
}
