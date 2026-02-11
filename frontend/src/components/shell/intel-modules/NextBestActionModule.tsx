import { Zap } from 'lucide-react';

interface NextAction {
  action: string;
  priority: 'high' | 'medium' | 'low';
  impact: string;
  agent: string;
}

const PLACEHOLDER_ACTION: NextAction = {
  action: 'Send follow-up to Dr. Sarah Chen at Lonza RE: Q2 capacity planning',
  priority: 'high',
  impact: 'Re-engage stalled $450K opportunity before budget lock',
  agent: 'Strategist',
};

const PRIORITY_COLORS: Record<string, string> = {
  high: 'var(--critical)',
  medium: 'var(--warning)',
  low: 'var(--info)',
};

export interface NextBestActionModuleProps {
  action?: NextAction;
}

export function NextBestActionModule({ action = PLACEHOLDER_ACTION }: NextBestActionModuleProps) {
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
            <p className="font-sans text-[12px] leading-[1.5] mt-1" style={{ color: 'var(--text-secondary)' }}>
              {action.impact}
            </p>
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
