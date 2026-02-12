import { useCallback, useState } from 'react';
import { apiClient } from '@/api/client';

interface Phase {
  name: string;
  timeline: string;
  agents: string[];
  output: string;
  status: 'pending' | 'active' | 'complete';
}

interface ExecutionPlanData {
  goal_id: string;
  title: string;
  phases: Phase[];
  autonomy: {
    autonomous: string;
    requires_approval: string;
  };
}

interface ExecutionPlanCardProps {
  data: ExecutionPlanData;
}

const AGENT_COLORS: Record<string, string> = {
  Hunter: '#2E66FF',
  Analyst: '#8B5CF6',
  Strategist: '#F59E0B',
  Scribe: '#10B981',
  Operator: '#EF4444',
  Scout: '#06B6D4',
};

const PHASE_ICONS: Record<string, string> = {
  pending: '\u25CB',
  active: '\u25CF',
  complete: '\u2713',
};

export function ExecutionPlanCard({ data }: ExecutionPlanCardProps) {
  const [isApproved, setIsApproved] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const handleApprove = useCallback(async () => {
    setIsLoading(true);
    try {
      await apiClient.post(`/goals/${data.goal_id}/start`);
      setIsApproved(true);
    } catch {
      // Error surfaced in conversation
    } finally {
      setIsLoading(false);
    }
  }, [data.goal_id]);

  return (
    <div
      className="rounded-lg border border-[var(--border)] overflow-hidden"
      style={{ backgroundColor: 'var(--bg-elevated)' }}
      data-aria-id={`execution-plan-${data.goal_id}`}
    >
      <div className="px-4 pt-4 pb-2 flex items-start justify-between">
        <div>
          <p className="text-[10px] font-mono uppercase tracking-wider text-[var(--accent)] mb-1">
            Execution Plan
          </p>
          <h3 className="font-display italic text-base text-[var(--text-primary)]">
            {data.title}
          </h3>
        </div>
        {isApproved && (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono uppercase tracking-wider bg-emerald-500/20 text-emerald-400">
            Active
          </span>
        )}
      </div>

      <div className="px-4 pb-3">
        <div className="space-y-0">
          {data.phases.map((phase, i) => (
            <div key={phase.name} className="flex gap-3">
              <div className="flex flex-col items-center w-5 shrink-0">
                <span
                  className="text-sm leading-none mt-1"
                  style={{
                    color: phase.status === 'complete' ? '#10B981'
                      : phase.status === 'active' ? 'var(--accent)'
                      : 'var(--text-secondary)',
                  }}
                >
                  {PHASE_ICONS[phase.status]}
                </span>
                {i < data.phases.length - 1 && (
                  <div className="w-px flex-1 min-h-[24px] bg-[var(--border)]" />
                )}
              </div>
              <div className="pb-4 flex-1 min-w-0">
                <div className="flex items-baseline justify-between gap-2">
                  <p className="text-sm font-medium text-[var(--text-primary)]">
                    {phase.name}
                  </p>
                  <span className="text-[10px] font-mono text-[var(--text-secondary)] shrink-0">
                    {phase.timeline}
                  </span>
                </div>
                <p className="text-xs text-[var(--text-secondary)] mt-0.5 leading-relaxed">
                  {phase.output}
                </p>
                {phase.agents.length > 0 && (
                  <div className="flex gap-1 mt-1.5">
                    {phase.agents.map((agent) => (
                      <span
                        key={agent}
                        className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-mono uppercase tracking-wider"
                        style={{
                          backgroundColor: `${AGENT_COLORS[agent] || '#6B7280'}15`,
                          color: AGENT_COLORS[agent] || '#6B7280',
                        }}
                      >
                        {agent}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="border-t border-[var(--border)] px-4 py-3 space-y-1.5">
        <div className="flex items-start gap-2">
          <span className="text-emerald-400 text-xs mt-0.5 shrink-0">AUTO</span>
          <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
            {data.autonomy.autonomous}
          </p>
        </div>
        <div className="flex items-start gap-2">
          <span className="text-amber-400 text-xs mt-0.5 shrink-0">APPROVAL</span>
          <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
            {data.autonomy.requires_approval}
          </p>
        </div>
      </div>

      {!isApproved && (
        <div className="border-t border-[var(--border)] px-4 py-3 flex items-center gap-2">
          <button
            onClick={handleApprove}
            disabled={isLoading}
            className="px-3 py-1.5 rounded-md text-xs font-medium text-white transition-colors disabled:opacity-50"
            style={{ backgroundColor: 'var(--accent)' }}
          >
            {isLoading ? 'Starting...' : 'Approve Plan'}
          </button>
          <button className="px-3 py-1.5 rounded-md text-xs font-medium border border-[var(--border)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors">
            Modify
          </button>
          <button className="px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors">
            Discuss Further
          </button>
        </div>
      )}
    </div>
  );
}
