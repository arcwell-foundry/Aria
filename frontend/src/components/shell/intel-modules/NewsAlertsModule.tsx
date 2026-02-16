import { Newspaper } from 'lucide-react';
import { useSignals, formatRelativeTime } from '@/hooks/useIntelPanelData';

interface NewsItem {
  headline: string;
  source: string;
  time: string;
  impact: string;
}

function NewsAlertsSkeleton() {
  return (
    <div className="space-y-2">
      <div className="h-3 w-24 rounded bg-[var(--border)] animate-pulse" />
      <div className="h-24 rounded-lg bg-[var(--border)] animate-pulse" />
      <div className="h-24 rounded-lg bg-[var(--border)] animate-pulse" />
    </div>
  );
}

export interface NewsAlertsModuleProps {
  news?: NewsItem[];
}

export function NewsAlertsModule({ news: propNews }: NewsAlertsModuleProps) {
  const { data: signals, isLoading } = useSignals({ limit: 5 });

  if (isLoading && !propNews) return <NewsAlertsSkeleton />;

  const news: NewsItem[] = propNews ?? (signals ?? []).map((s) => ({
    headline: s.content,
    source: s.source ?? 'Market Intelligence',
    time: formatRelativeTime(s.created_at),
    impact: s.company_name ? `Relevant to ${s.company_name}` : 'Relevant to your pipeline',
  }));

  if (news.length === 0) {
    return (
      <div data-aria-id="intel-news" className="space-y-2">
        <h3
          className="font-sans text-[11px] font-medium uppercase tracking-wider mb-3"
          style={{ color: 'var(--text-secondary)' }}
        >
          Industry News
        </h3>
        <div
          className="rounded-lg border p-4"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
        >
          <p className="font-sans text-[12px]" style={{ color: 'var(--text-secondary)' }}>
            No industry news yet. ARIA is monitoring your market.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div data-aria-id="intel-news" className="space-y-2">
      <h3
        className="font-sans text-[11px] font-medium uppercase tracking-wider mb-3"
        style={{ color: 'var(--text-secondary)' }}
      >
        Industry News
      </h3>
      {news.map((item, i) => (
        <div
          key={i}
          className="rounded-lg border p-3"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
        >
          <div className="flex items-start gap-2">
            <Newspaper size={14} className="mt-0.5 flex-shrink-0" style={{ color: 'var(--info)' }} />
            <div className="min-w-0">
              <p className="font-sans text-[13px] leading-[1.5] font-medium" style={{ color: 'var(--text-primary)' }}>
                {item.headline}
              </p>
              <p className="font-sans text-[12px] leading-[1.5] mt-1" style={{ color: 'var(--text-secondary)' }}>
                {item.impact}
              </p>
              <p className="font-mono text-[10px] mt-1.5" style={{ color: 'var(--text-secondary)' }}>
                {item.source} · {item.time}
              </p>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
