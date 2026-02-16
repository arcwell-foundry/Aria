import { BarChart3 } from 'lucide-react';
import { useIntelDrafts } from '@/hooks/useIntelPanelData';

interface CommStats {
  openRate: number;
  replyRate: number;
  avgResponseTime: string;
  trend: string;
}

function AnalysisSkeleton() {
  return (
    <div className="space-y-3">
      <div className="h-3 w-36 rounded bg-[var(--border)] animate-pulse" />
      <div className="h-32 rounded-lg bg-[var(--border)] animate-pulse" />
    </div>
  );
}

export interface AnalysisModuleProps {
  stats?: CommStats;
}

export function AnalysisModule({ stats: propStats }: AnalysisModuleProps) {
  const { data: drafts, isLoading } = useIntelDrafts();

  if (isLoading && !propStats) return <AnalysisSkeleton />;

  let stats: CommStats;
  if (propStats) {
    stats = propStats;
  } else if (drafts && drafts.length > 0) {
    const total = drafts.length;
    const sent = drafts.filter((d) => d.status === 'sent').length;
    const sentRate = total > 0 ? Math.round((sent / total) * 100) : 0;
    const avgScore = drafts.reduce((sum, d) => sum + (d.style_match_score ?? 0), 0);
    const avgMatch = total > 0 ? Math.round(avgScore / total) : 0;

    stats = {
      openRate: sentRate,
      replyRate: avgMatch,
      avgResponseTime: `${total} drafts`,
      trend: sent > 0
        ? `${sent} of ${total} drafts sent. Average style match: ${avgMatch}%.`
        : `${total} drafts created. None sent yet.`,
    };
  } else {
    return (
      <div data-aria-id="intel-analysis" className="space-y-3">
        <h3
          className="font-sans text-[11px] font-medium uppercase tracking-wider"
          style={{ color: 'var(--text-secondary)' }}
        >
          Communication Analysis
        </h3>
        <div
          className="rounded-lg border p-4"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
        >
          <p className="font-sans text-[12px]" style={{ color: 'var(--text-secondary)' }}>
            No communication data yet. Metrics will appear as ARIA drafts and sends emails.
          </p>
        </div>
      </div>
    );
  }

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
              Sent Rate
            </p>
          </div>
          <div>
            <p className="font-mono text-[18px] font-medium" style={{ color: 'var(--text-primary)' }}>
              {stats.replyRate}%
            </p>
            <p className="font-mono text-[9px] uppercase" style={{ color: 'var(--text-secondary)' }}>
              Style Match
            </p>
          </div>
          <div>
            <p className="font-mono text-[18px] font-medium" style={{ color: 'var(--text-primary)' }}>
              {stats.avgResponseTime}
            </p>
            <p className="font-mono text-[9px] uppercase" style={{ color: 'var(--text-secondary)' }}>
              Total
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
