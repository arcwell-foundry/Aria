import { BarChart3 } from 'lucide-react';

interface CommStats {
  openRate: number;
  replyRate: number;
  avgResponseTime: string;
  trend: string;
}

const PLACEHOLDER_STATS: CommStats = {
  openRate: 68,
  replyRate: 34,
  avgResponseTime: '4.2 hours',
  trend: 'Reply rates up 12% since adopting ARIA suggestions',
};

export interface AnalysisModuleProps {
  stats?: CommStats;
}

export function AnalysisModule({ stats = PLACEHOLDER_STATS }: AnalysisModuleProps) {
  return (
    <div data-aria-id="intel-analysis" className="space-y-3">
      <h3
        className="font-sans text-[11px] font-medium uppercase tracking-wider"
        style={{ color: 'var(--text-secondary)' }}
      >
        Communication Analysis
      </h3>
      <div
        className="rounded-lg border p-3"
        style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
      >
        <div className="flex items-center gap-2 mb-3">
          <BarChart3 size={14} style={{ color: 'var(--accent)' }} />
          <span className="font-sans text-[12px] font-medium" style={{ color: 'var(--text-primary)' }}>
            Your Outreach Performance
          </span>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <div>
            <p className="font-mono text-[18px] font-medium" style={{ color: 'var(--text-primary)' }}>
              {stats.openRate}%
            </p>
            <p className="font-mono text-[9px] uppercase" style={{ color: 'var(--text-secondary)' }}>
              Open Rate
            </p>
          </div>
          <div>
            <p className="font-mono text-[18px] font-medium" style={{ color: 'var(--text-primary)' }}>
              {stats.replyRate}%
            </p>
            <p className="font-mono text-[9px] uppercase" style={{ color: 'var(--text-secondary)' }}>
              Reply Rate
            </p>
          </div>
          <div>
            <p className="font-mono text-[18px] font-medium" style={{ color: 'var(--text-primary)' }}>
              {stats.avgResponseTime}
            </p>
            <p className="font-mono text-[9px] uppercase" style={{ color: 'var(--text-secondary)' }}>
              Avg Response
            </p>
          </div>
        </div>
        <p className="font-sans text-[11px] mt-3 leading-[1.5]" style={{ color: 'var(--success)' }}>
          {stats.trend}
        </p>
      </div>
    </div>
  );
}
