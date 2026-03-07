import { useState, useMemo } from 'react';
import { Calendar, MapPin, Users, ChevronDown, ChevronUp } from 'lucide-react';
import { useUpcomingConferences } from '@/hooks/useIntelPanelData';
import type { ConferenceRecommendation } from '@/api/conferences';

type FilterType = 'relevant' | 'must_attend' | 'consider' | 'all';

const RECOMMENDATION_CONFIG: Record<
  ConferenceRecommendation['recommendation_type'],
  { label: string; bg: string; text: string; dot: string }
> = {
  must_attend: {
    label: 'Must Attend',
    bg: '#DCFCE7',
    text: '#166534',
    dot: '#22C55E',
  },
  consider: {
    label: 'Consider',
    bg: '#FEF3C7',
    text: '#92400E',
    dot: '#F59E0B',
  },
  monitor_remotely: {
    label: 'Monitor',
    bg: '#F1F5F9',
    text: '#475569',
    dot: '#94A3B8',
  },
};

function formatDateRange(start: string | null, end: string | null): string {
  if (!start) return 'TBD';
  const s = new Date(start + 'T00:00:00');
  const sMonth = s.toLocaleString('en-US', { month: 'short' });
  const sDay = s.getDate();

  if (!end) return `${sMonth} ${sDay}`;

  const e = new Date(end + 'T00:00:00');
  const eMonth = e.toLocaleString('en-US', { month: 'short' });
  const eDay = e.getDate();

  if (sMonth === eMonth) {
    return `${sMonth} ${sDay}\u2013${eDay}`;
  }
  return `${sMonth} ${sDay} \u2013 ${eMonth} ${eDay}`;
}

function formatLocation(city: string | null, country: string | null): string {
  const parts = [city, country].filter(Boolean);
  return parts.join(', ') || 'TBD';
}

function ConferenceSkeleton() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {[1, 2, 3].map((i) => (
        <div
          key={i}
          className="rounded-xl border p-4 animate-pulse"
          style={{ backgroundColor: '#FFFFFF', borderColor: '#E2E8F0' }}
        >
          <div className="h-4 w-3/4 rounded bg-[#E2E8F0] mb-3" />
          <div className="h-3 w-1/2 rounded bg-[#F1F5F9] mb-2" />
          <div className="h-3 w-2/3 rounded bg-[#F1F5F9] mb-3" />
          <div className="h-5 w-24 rounded-full bg-[#F1F5F9]" />
        </div>
      ))}
    </div>
  );
}

const FILTER_OPTIONS: { key: FilterType; label: string }[] = [
  { key: 'relevant', label: 'Relevant' },
  { key: 'must_attend', label: 'Must Attend' },
  { key: 'consider', label: 'Consider' },
  { key: 'all', label: 'All' },
];

export function ConferenceSection() {
  const { data: conferences, isLoading } = useUpcomingConferences();
  const [filter, setFilter] = useState<FilterType>('relevant');
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const filtered = useMemo(() => {
    if (!conferences) return [];
    switch (filter) {
      case 'must_attend':
        return conferences.filter((c) => c.recommendation_type === 'must_attend');
      case 'consider':
        return conferences.filter((c) => c.recommendation_type === 'consider');
      case 'relevant':
        return conferences.filter(
          (c) => c.recommendation_type === 'must_attend' || c.recommendation_type === 'consider',
        );
      default:
        return conferences;
    }
  }, [conferences, filter]);

  if (isLoading) {
    return (
      <section>
        <h2
          className="text-base font-medium mb-4 flex items-center gap-2"
          style={{ color: 'var(--text-primary)' }}
        >
          <Calendar className="w-4 h-4" style={{ color: 'var(--text-secondary)' }} />
          Upcoming Conferences
        </h2>
        <ConferenceSkeleton />
      </section>
    );
  }

  if (!conferences || conferences.length === 0) return null;

  return (
    <section>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h2
          className="text-base font-medium flex items-center gap-2"
          style={{ color: 'var(--text-primary)' }}
        >
          <Calendar className="w-4 h-4" style={{ color: 'var(--text-secondary)' }} />
          Upcoming Conferences
          <span
            className="text-xs font-normal ml-1"
            style={{ color: 'var(--text-secondary)' }}
          >
            ({filtered.length})
          </span>
        </h2>

        {/* Filter pills */}
        <div className="flex gap-1">
          {FILTER_OPTIONS.map((opt) => (
            <button
              key={opt.key}
              onClick={() => setFilter(opt.key)}
              className="px-2.5 py-1 rounded-md text-[11px] font-medium transition-colors"
              style={{
                backgroundColor: filter === opt.key ? '#1E293B' : '#F1F5F9',
                color: filter === opt.key ? '#FFFFFF' : '#64748B',
              }}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* Conference cards */}
      {filtered.length === 0 ? (
        <div
          className="rounded-xl border p-6 text-center"
          style={{
            backgroundColor: '#FFFFFF',
            borderColor: '#E2E8F0',
          }}
        >
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            No conferences match this filter.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((conf) => {
            const isExpanded = expandedId === conf.conference_id;
            const config = RECOMMENDATION_CONFIG[conf.recommendation_type];
            const dateStr = formatDateRange(conf.start_date, conf.end_date);
            const location = formatLocation(conf.city, conf.country);

            return (
              <div
                key={conf.conference_id}
                onClick={() => setExpandedId(isExpanded ? null : conf.conference_id)}
                className="rounded-xl border p-4 cursor-pointer transition-all hover:-translate-y-0.5"
                style={{
                  backgroundColor: '#FFFFFF',
                  borderColor: isExpanded ? 'var(--accent)' : '#E2E8F0',
                  boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
                }}
              >
                {/* Top row: name + chevron */}
                <div className="flex items-start justify-between mb-1.5">
                  <div className="min-w-0 flex-1">
                    <h3
                      className="text-sm font-semibold leading-tight"
                      style={{ color: '#1E293B' }}
                    >
                      {conf.short_name || conf.conference_name}
                    </h3>
                    {conf.short_name && conf.short_name !== conf.conference_name && (
                      <p
                        className="text-[11px] mt-0.5 truncate"
                        style={{ color: '#94A3B8' }}
                      >
                        {conf.conference_name}
                      </p>
                    )}
                  </div>
                  {isExpanded ? (
                    <ChevronUp className="w-4 h-4 flex-shrink-0 ml-2" style={{ color: '#94A3B8' }} />
                  ) : (
                    <ChevronDown className="w-4 h-4 flex-shrink-0 ml-2" style={{ color: '#94A3B8' }} />
                  )}
                </div>

                {/* Date + Location */}
                <div className="flex items-center gap-3 text-[11px] mb-3" style={{ color: '#5B6E8A' }}>
                  <span className="flex items-center gap-1">
                    <Calendar className="w-3 h-3" />
                    {dateStr}
                  </span>
                  <span className="flex items-center gap-1">
                    <MapPin className="w-3 h-3" />
                    {location}
                  </span>
                </div>

                {/* Recommendation badge */}
                <div className="flex items-center justify-between">
                  <span
                    className="inline-flex items-center gap-1.5 text-[10px] font-semibold px-2 py-0.5 rounded-full uppercase tracking-wide"
                    style={{ backgroundColor: config.bg, color: config.text }}
                  >
                    <span
                      className="w-1.5 h-1.5 rounded-full"
                      style={{ backgroundColor: config.dot }}
                    />
                    {config.label}
                  </span>

                  {conf.competitor_presence > 0 && (
                    <span
                      className="flex items-center gap-1 text-[10px] font-medium"
                      style={{ color: '#DC2626' }}
                    >
                      <Users className="w-3 h-3" />
                      {conf.competitor_presence} competitor{conf.competitor_presence > 1 ? 's' : ''}
                    </span>
                  )}
                </div>

                {/* Expanded: reasons + attendance */}
                {isExpanded && (
                  <div className="mt-3 pt-3" style={{ borderTop: '1px solid #F1F5F9' }}>
                    {/* Reasons */}
                    {conf.reasons.length > 0 && (
                      <div className="space-y-1.5 mb-3">
                        {conf.reasons.map((r, i) => (
                          <p
                            key={i}
                            className="text-xs leading-relaxed"
                            style={{ color: '#5B6E8A' }}
                          >
                            <span style={{ color: '#1E293B' }}>&bull;</span>{' '}
                            {r.reason}
                          </p>
                        ))}
                      </div>
                    )}

                    {/* Attendance + relevance */}
                    <div
                      className="flex items-center gap-3 text-[10px]"
                      style={{ color: '#94A3B8' }}
                    >
                      {conf.estimated_attendance && (
                        <span>
                          ~{conf.estimated_attendance.toLocaleString()} attendees
                        </span>
                      )}
                      <span>
                        Relevance: {Math.round(conf.relevance_score * 100)}%
                      </span>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
