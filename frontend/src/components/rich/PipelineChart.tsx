import { BarChart3 } from 'lucide-react';

export interface PipelineChartData {
  stages: { stage: string; count: number }[];
  total: number;
  avg_health?: number;
}

const STAGE_LABELS: Record<string, string> = {
  prospect: 'Prospect',
  qualified: 'Qualified',
  proposal: 'Proposal',
  negotiation: 'Negotiation',
  won: 'Won',
};

export function PipelineChart({ data }: { data: PipelineChartData }) {
  const maxCount = Math.max(...data.stages.map((s) => s.count), 1);

  return (
    <div
      className="rounded-lg border border-[var(--border)] overflow-hidden"
      style={{ backgroundColor: 'var(--bg-elevated)' }}
      data-aria-id="pipeline-chart"
    >
      <div
        className="flex items-center justify-between px-4 py-2.5"
        style={{
          borderBottom: '1px solid var(--border)',
          backgroundColor: 'rgba(46,102,255,0.05)',
        }}
      >
        <div className="flex items-center gap-2">
          <BarChart3 className="w-3.5 h-3.5" style={{ color: 'var(--accent)' }} />
          <span className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
            Pipeline Summary
          </span>
        </div>
        <span className="text-[10px] font-mono" style={{ color: 'var(--text-secondary)' }}>
          {data.total} leads
        </span>
      </div>

      <div className="px-4 py-3 space-y-2">
        {data.stages.map((stage) => (
          <div key={stage.stage} className="flex items-center gap-3">
            <span
              className="text-[10px] font-mono uppercase tracking-wider w-20 shrink-0 text-right"
              style={{ color: 'var(--text-secondary)' }}
            >
              {STAGE_LABELS[stage.stage] || stage.stage}
            </span>
            <div className="flex-1 h-5 rounded" style={{ backgroundColor: 'var(--bg-subtle)' }}>
              <div
                className="h-full rounded flex items-center justify-end pr-2 transition-all"
                style={{
                  width: `${Math.max((stage.count / maxCount) * 100, stage.count > 0 ? 15 : 0)}%`,
                  backgroundColor: 'var(--accent)',
                  opacity: stage.count > 0 ? 1 : 0.2,
                }}
              >
                {stage.count > 0 && (
                  <span className="text-[10px] font-mono text-white">
                    {stage.count}
                  </span>
                )}
              </div>
            </div>
          </div>
        ))}

        {data.avg_health != null && (
          <div className="pt-2 mt-1" style={{ borderTop: '1px solid var(--border)' }}>
            <span className="text-[10px] font-mono" style={{ color: 'var(--text-secondary)' }}>
              Avg Health: <span style={{ color: 'var(--accent)' }}>{data.avg_health}/100</span>
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
