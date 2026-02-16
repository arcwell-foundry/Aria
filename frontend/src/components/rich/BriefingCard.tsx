import { useState } from 'react';
import {
  Calendar,
  Users,
  TrendingUp,
  AlertCircle,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';

// ---------------------------------------------------------------------------
// Data types
// ---------------------------------------------------------------------------

export interface BriefingCardData {
  summary: string;
  calendar: {
    meeting_count: number;
    key_meetings: { time: string; title: string; attendees: string[] }[];
  };
  leads: {
    hot_leads: { id: string; name: string; company: string; health_score?: number }[];
    needs_attention: { id: string; name: string; company: string; health_score?: number }[];
  };
  signals: {
    company_news: { id: string; title: string; summary: string }[];
    market_trends: { id: string; title: string; summary: string }[];
    competitive_intel: { id: string; title: string; summary: string }[];
  };
  tasks: {
    overdue: { id: string; title: string; due_date?: string }[];
    due_today: { id: string; title: string; due_date?: string }[];
  };
}

// ---------------------------------------------------------------------------
// Collapsible section
// ---------------------------------------------------------------------------

interface SectionProps {
  icon: React.ReactNode;
  title: string;
  badge?: number;
  defaultOpen: boolean;
  children: React.ReactNode;
}

function Section({ icon, title, badge, defaultOpen, children }: SectionProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="border-t border-[var(--border)]">
      <button
        type="button"
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-[11px] font-mono uppercase tracking-wider text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? (
          <ChevronDown size={12} className="shrink-0 text-[var(--text-secondary)]" />
        ) : (
          <ChevronRight size={12} className="shrink-0 text-[var(--text-secondary)]" />
        )}
        <span className="shrink-0 text-[var(--accent)]">{icon}</span>
        <span>{title}</span>
        {badge != null && badge > 0 && (
          <span className="ml-auto inline-flex items-center justify-center rounded-full bg-[var(--accent)]/15 px-1.5 text-[10px] font-mono text-[var(--accent)]">
            {badge}
          </span>
        )}
      </button>
      {open && <div className="px-3 pb-3">{children}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// BriefingCard
// ---------------------------------------------------------------------------

interface BriefingCardProps {
  data: BriefingCardData;
}

export function BriefingCard({ data }: BriefingCardProps) {
  // Pre-compute signal totals
  const allSignals = [
    ...data.signals.company_news,
    ...data.signals.market_trends,
    ...data.signals.competitive_intel,
  ];
  const signalCount = allSignals.length;
  const topSignals = allSignals.slice(0, 5);

  const overdueCount = data.tasks.overdue.length;
  const dueTodayCount = data.tasks.due_today.length;

  return (
    <div
      className="rounded-lg border border-[var(--border)] overflow-hidden"
      style={{ backgroundColor: 'var(--bg-elevated)' }}
      data-aria-id="briefing-card"
    >
      {/* Header */}
      <div className="px-3 pt-3 pb-2">
        <h3 className="text-[10px] font-mono uppercase tracking-widest text-[var(--accent)] mb-1">
          Daily Intelligence Briefing
        </h3>
        <p className="text-xs leading-relaxed text-[var(--text-secondary)]">
          {data.summary}
        </p>
      </div>

      {/* 1. Calendar */}
      <Section
        icon={<Calendar size={12} />}
        title="Calendar"
        badge={data.calendar.meeting_count}
        defaultOpen={data.calendar.key_meetings.length > 0}
      >
        {data.calendar.key_meetings.length === 0 ? (
          <p className="text-[11px] text-[var(--text-secondary)]">No meetings today.</p>
        ) : (
          <ul className="space-y-1.5">
            {data.calendar.key_meetings.map((m, i) => (
              <li key={i} className="flex items-start gap-2 text-[11px]">
                <span className="shrink-0 font-mono text-[var(--text-secondary)] w-12">
                  {m.time}
                </span>
                <span className="text-[var(--text-primary)] leading-snug flex-1 min-w-0">
                  {m.title}
                </span>
                <span className="shrink-0 font-mono text-[var(--text-secondary)]">
                  {m.attendees.length} {m.attendees.length === 1 ? 'person' : 'people'}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      {/* 2. Leads */}
      <Section
        icon={<Users size={12} />}
        title="Leads"
        badge={data.leads.hot_leads.length + data.leads.needs_attention.length}
        defaultOpen={data.leads.needs_attention.length > 0}
      >
        {data.leads.needs_attention.length === 0 && data.leads.hot_leads.length === 0 ? (
          <p className="text-[11px] text-[var(--text-secondary)]">No lead updates.</p>
        ) : (
          <ul className="space-y-1">
            {data.leads.needs_attention.map((lead) => (
              <li key={lead.id} className="flex items-center gap-2 text-[11px]">
                <span className="inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--critical)]" />
                <span className="text-[var(--text-primary)] truncate flex-1 min-w-0">
                  {lead.name}
                </span>
                <span className="shrink-0 font-mono text-[var(--text-secondary)] text-[10px]">
                  {lead.company}
                </span>
                {lead.health_score != null && (
                  <span className="shrink-0 font-mono text-[10px] text-[var(--critical)]">
                    {lead.health_score}
                  </span>
                )}
              </li>
            ))}
            {data.leads.hot_leads.map((lead) => (
              <li key={lead.id} className="flex items-center gap-2 text-[11px]">
                <span className="inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--success)]" />
                <span className="text-[var(--text-primary)] truncate flex-1 min-w-0">
                  {lead.name}
                </span>
                <span className="shrink-0 font-mono text-[var(--text-secondary)] text-[10px]">
                  {lead.company}
                </span>
                {lead.health_score != null && (
                  <span className="shrink-0 font-mono text-[10px] text-[var(--success)]">
                    {lead.health_score}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </Section>

      {/* 3. Signals */}
      <Section
        icon={<TrendingUp size={12} />}
        title="Signals"
        badge={signalCount}
        defaultOpen={signalCount > 0}
      >
        {topSignals.length === 0 ? (
          <p className="text-[11px] text-[var(--text-secondary)]">No new signals.</p>
        ) : (
          <ul className="space-y-1.5">
            {topSignals.map((s) => (
              <li key={s.id}>
                <p className="text-[11px] text-[var(--text-primary)] leading-snug">
                  {s.title}
                </p>
                <p className="text-[10px] text-[var(--text-secondary)] leading-snug">
                  {s.summary}
                </p>
              </li>
            ))}
            {signalCount > 5 && (
              <li className="text-[10px] font-mono text-[var(--accent)]">
                +{signalCount - 5} more signals
              </li>
            )}
          </ul>
        )}
      </Section>

      {/* 4. Tasks */}
      <Section
        icon={<AlertCircle size={12} />}
        title="Tasks"
        badge={overdueCount + dueTodayCount}
        defaultOpen={overdueCount > 0}
      >
        {overdueCount === 0 && dueTodayCount === 0 ? (
          <p className="text-[11px] text-[var(--text-secondary)]">All clear -- no pending tasks.</p>
        ) : (
          <ul className="space-y-1">
            {data.tasks.overdue.map((t) => (
              <li key={t.id} className="flex items-center gap-2 text-[11px]">
                <span className="inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--critical)]" />
                <span className="text-[var(--text-primary)] truncate flex-1 min-w-0">
                  {t.title}
                </span>
                {t.due_date && (
                  <span className="shrink-0 font-mono text-[10px] text-[var(--critical)]">
                    {t.due_date}
                  </span>
                )}
              </li>
            ))}
            {data.tasks.due_today.map((t) => (
              <li key={t.id} className="flex items-center gap-2 text-[11px]">
                <span className="inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--warning)]" />
                <span className="text-[var(--text-primary)] truncate flex-1 min-w-0">
                  {t.title}
                </span>
                {t.due_date && (
                  <span className="shrink-0 font-mono text-[10px] text-[var(--warning)]">
                    {t.due_date}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  );
}
