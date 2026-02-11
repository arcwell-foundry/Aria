import { Newspaper } from 'lucide-react';

interface NewsItem {
  headline: string;
  source: string;
  time: string;
  impact: string;
}

const PLACEHOLDER_NEWS: NewsItem[] = [
  {
    headline: 'FDA approves new biologics pathway — potential impact on CMO demand',
    source: 'BioPharma Dive',
    time: '3h ago',
    impact: 'Your pipeline accounts may accelerate procurement timelines',
  },
  {
    headline: 'Life Sciences M&A activity up 23% QoQ',
    source: 'FiercePharma',
    time: '8h ago',
    impact: 'Watch for consolidation among mid-tier CDMO prospects',
  },
];

export interface NewsAlertsModuleProps {
  news?: NewsItem[];
}

export function NewsAlertsModule({ news = PLACEHOLDER_NEWS }: NewsAlertsModuleProps) {
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
