import { Calendar, MapPin } from 'lucide-react';
import { useUpcomingConferences } from '@/hooks/useIntelPanelData';

const REC_COLORS: Record<string, { bg: string; text: string }> = {
  must_attend: { bg: '#DCFCE7', text: '#166534' },
  consider: { bg: '#FEF3C7', text: '#92400E' },
  monitor_remotely: { bg: '#F1F5F9', text: '#475569' },
};

const REC_LABELS: Record<string, string> = {
  must_attend: 'Must Attend',
  consider: 'Consider',
  monitor_remotely: 'Monitor',
};

function formatShortDate(dateStr: string | null): string {
  if (!dateStr) return 'TBD';
  const d = new Date(dateStr + 'T00:00:00');
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function UpcomingConferencesSkeleton() {
  return (
    <div className="space-y-2">
      <div className="h-3 w-36 rounded bg-[var(--border)] animate-pulse" />
      <div className="h-16 rounded-lg bg-[var(--border)] animate-pulse" />
      <div className="h-16 rounded-lg bg-[var(--border)] animate-pulse" />
    </div>
  );
}

export function UpcomingConferencesModule() {
  const { data: conferences, isLoading } = useUpcomingConferences();

  if (isLoading) return <UpcomingConferencesSkeleton />;

  // Show top 3 by relevance (already sorted from API)
  const top = (conferences ?? [])
    .filter((c) => c.recommendation_type !== 'monitor_remotely')
    .slice(0, 3);

  if (top.length === 0) {
    return (
      <div data-aria-id="intel-conferences" className="space-y-2">
        <h3
          className="font-sans text-[11px] font-medium uppercase tracking-wider mb-3"
          style={{ color: 'var(--text-secondary)' }}
        >
          Upcoming Conferences
        </h3>
        <div
          className="rounded-lg border p-4"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
        >
          <p className="font-sans text-[12px]" style={{ color: 'var(--text-secondary)' }}>
            No upcoming conferences detected for your market.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div data-aria-id="intel-conferences" className="space-y-2">
      <h3
        className="font-sans text-[11px] font-medium uppercase tracking-wider mb-3"
        style={{ color: 'var(--text-secondary)' }}
      >
        Upcoming Conferences
      </h3>
      {top.map((conf) => {
        const colors = REC_COLORS[conf.recommendation_type] ?? REC_COLORS.monitor_remotely;
        const label = REC_LABELS[conf.recommendation_type] ?? 'Monitor';

        return (
          <div
            key={conf.conference_id}
            className="rounded-lg border p-3"
            style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
          >
            <div className="flex items-start gap-2">
              <Calendar
                size={14}
                className="mt-0.5 flex-shrink-0"
                style={{ color: 'var(--accent)' }}
              />
              <div className="min-w-0 flex-1">
                <p
                  className="font-sans text-[13px] font-medium leading-tight"
                  style={{ color: 'var(--text-primary)' }}
                >
                  {conf.short_name || conf.conference_name}
                </p>
                <div
                  className="flex items-center gap-2 mt-1 text-[10px]"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  <span>{formatShortDate(conf.start_date)}</span>
                  {conf.city && (
                    <>
                      <span style={{ color: 'var(--border)' }}>&middot;</span>
                      <span className="flex items-center gap-0.5">
                        <MapPin size={9} />
                        {conf.city}
                      </span>
                    </>
                  )}
                </div>
                <div className="flex items-center gap-2 mt-1.5">
                  <span
                    className="text-[9px] font-semibold px-1.5 py-0.5 rounded uppercase tracking-wide"
                    style={{ backgroundColor: colors.bg, color: colors.text }}
                  >
                    {label}
                  </span>
                  {conf.competitor_presence > 0 && (
                    <span
                      className="font-mono text-[9px]"
                      style={{ color: 'var(--text-secondary)' }}
                    >
                      {conf.competitor_presence} competitor{conf.competitor_presence > 1 ? 's' : ''}
                    </span>
                  )}
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
