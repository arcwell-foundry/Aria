import { BarChart3 } from 'lucide-react';
import { useIntelDrafts } from '@/hooks/useIntelPanelData';
import { isPlaceholderDraft } from '@/utils/isPlaceholderDraft';

function AnalysisSkeleton() {
  return (
    <div className="space-y-3">
      <div className="h-3 w-36 rounded bg-[var(--border)] animate-pulse" />
      <div className="h-32 rounded-lg bg-[var(--border)] animate-pulse" />
    </div>
  );
}

export interface AnalysisModuleProps {
  stats?: {
    openRate: number;
    replyRate: number;
    avgResponseTime: string;
    trend: string;
  };
}

const LEARNING_THRESHOLD = 5;
const IMPROVING_THRESHOLD = 30;

export function AnalysisModule({ stats: propStats }: AnalysisModuleProps) {
  const { data: drafts, isLoading } = useIntelDrafts();

  if (isLoading && !propStats) return <AnalysisSkeleton />;

  if (propStats) {
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
                {propStats.openRate}%
              </p>
              <p className="font-mono text-[9px] uppercase" style={{ color: 'var(--text-secondary)' }}>
                Sent Rate
              </p>
            </div>
            <div>
              <p className="font-mono text-[18px] font-medium" style={{ color: 'var(--text-primary)' }}>
                {propStats.replyRate}%
              </p>
              <p className="font-mono text-[9px] uppercase" style={{ color: 'var(--text-secondary)' }}>
                Style Match
              </p>
            </div>
            <div>
              <p className="font-mono text-[18px] font-medium" style={{ color: 'var(--text-primary)' }}>
                {propStats.avgResponseTime}
              </p>
              <p className="font-mono text-[9px] uppercase" style={{ color: 'var(--text-secondary)' }}>
                Total
              </p>
            </div>
          </div>
          <p className="font-sans text-[11px] mt-3 leading-[1.5]" style={{ color: 'var(--success)' }}>
            {propStats.trend}
          </p>
        </div>
      </div>
    );
  }

  if (!drafts || drafts.length === 0) {
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

  // Filter out placeholder/pending_review drafts for metrics
  const realDrafts = drafts.filter((d) => !isPlaceholderDraft(d));
  const realTotal = realDrafts.length;
  const sent = realDrafts.filter((d) => d.status === 'sent').length;
  const sentRate = realTotal > 0 ? Math.round((sent / realTotal) * 100) : 0;

  // Style match: only average drafts that have a real score (not null, not 0)
  const scoredDrafts = realDrafts.filter(
    (d) => d.style_match_score != null && d.style_match_score > 0
  );
  const avgMatch =
    scoredDrafts.length > 0
      ? Math.round(
          scoredDrafts.reduce((sum, d) => sum + d.style_match_score!, 0) / scoredDrafts.length
        )
      : 0;

  // Determine style match display based on learning state
  const isLearning = sent < LEARNING_THRESHOLD;
  let styleMatchDisplay: string;
  let styleMatchSubtitle: string;
  if (isLearning) {
    styleMatchDisplay = 'Learning';
    styleMatchSubtitle = 'Send more emails to calibrate';
  } else if (avgMatch < IMPROVING_THRESHOLD) {
    styleMatchDisplay = `${avgMatch}%`;
    styleMatchSubtitle = 'Improving';
  } else {
    styleMatchDisplay = `${avgMatch}%`;
    styleMatchSubtitle = 'Style Match';
  }

  const trend = sent > 0
    ? `${sent} of ${realTotal} drafts sent. ${isLearning ? 'Style match calibrating.' : `Average style match: ${avgMatch}%.`}`
    : `${realTotal} draft${realTotal === 1 ? '' : 's'} created. None sent yet.`;

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
              {sentRate}%
            </p>
            <p className="font-mono text-[9px] uppercase" style={{ color: 'var(--text-secondary)' }}>
              Sent Rate
            </p>
          </div>
          <div>
            <p
              className={`font-mono font-medium ${isLearning ? 'text-[14px]' : 'text-[18px]'}`}
              style={{ color: isLearning ? 'var(--text-secondary)' : 'var(--text-primary)' }}
            >
              {styleMatchDisplay}
            </p>
            <p className="font-mono text-[9px] uppercase" style={{ color: 'var(--text-secondary)' }}>
              {styleMatchSubtitle}
            </p>
          </div>
          <div>
            <p className="font-mono text-[18px] font-medium" style={{ color: 'var(--text-primary)' }}>
              {realTotal} drafts
            </p>
            <p className="font-mono text-[9px] uppercase" style={{ color: 'var(--text-secondary)' }}>
              Total
            </p>
          </div>
        </div>
        <p className="font-sans text-[11px] mt-3 leading-[1.5]" style={{ color: 'var(--success)' }}>
          {trend}
        </p>
      </div>
    </div>
  );
}
