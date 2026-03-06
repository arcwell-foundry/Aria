/**
 * BriefingTranscriptView — Organized sectioned view for text-only briefings.
 *
 * Parses the briefing rich_content and groups cards into collapsible sections:
 * Summary, Priority Actions, Today's Meetings, Email Summary,
 * Market Intelligence, and Pipeline (Leads).
 * Renders in the Transcript panel instead of a flat card list.
 */

import { useState } from 'react';
import { AlertTriangle, Calendar, Mail, TrendingUp, Users, ChevronDown, ChevronRight, Link2 } from 'lucide-react';
import { BriefingSection } from './BriefingSection';
import { RichContentRenderer } from '@/components/rich/RichContentRenderer';
import type { RichContent } from '@/types/chat';
import type { BriefingCardData } from '@/components/rich/BriefingCard';

interface BriefingTranscriptViewProps {
  /** The markdown summary text */
  summary: string;
  /** The rich_content array from the message */
  richContent: RichContent[];
}

interface GroupedContent {
  priorityActions: RichContent[];
  meetings: RichContent[];
  emailSummary: BriefingCardData['email_summary'] | null;
  signals: RichContent[];
  leads: BriefingCardData['leads'] | null;
  /** Remaining items that don't fit a section */
  other: RichContent[];
}

function groupContent(richContent: RichContent[]): GroupedContent {
  const result: GroupedContent = {
    priorityActions: [],
    meetings: [],
    emailSummary: null,
    signals: [],
    leads: null,
    other: [],
  };

  for (const item of richContent) {
    switch (item.type) {
      case 'alert_card':
        result.priorityActions.push(item);
        break;
      case 'meeting_card':
        result.meetings.push(item);
        break;
      case 'signal_card':
        result.signals.push(item);
        break;
      case 'briefing': {
        // Extract structured data from the monolithic briefing card
        const data = item.data as unknown as BriefingCardData;
        if (data) {
          // Extract email summary
          if (data.email_summary) {
            result.emailSummary = data.email_summary;
          }

          // Extract leads
          if (data.leads) {
            result.leads = data.leads;
          }

          // Extract overdue tasks as alert-style items
          const tasks = data.tasks ?? { overdue: [], due_today: [] };
          for (const t of tasks.overdue ?? []) {
            result.priorityActions.push({
              type: 'alert_card',
              data: {
                id: t.id,
                company_name: '',
                headline: `Overdue: ${t.task ?? 'Unknown task'}`,
                summary: `Priority: ${t.priority ?? 'high'}. Due: ${t.due_at ?? ''}`,
                severity: 'high',
              },
            });
          }
          for (const t of tasks.due_today ?? []) {
            result.priorityActions.push({
              type: 'alert_card',
              data: {
                id: t.id,
                company_name: '',
                headline: t.task ?? 'Unknown task',
                summary: `Due today`,
                severity: 'medium',
              },
            });
          }

          // Extract meetings from briefing data
          const calendar = data.calendar ?? { meeting_count: 0, key_meetings: [] };
          for (const m of calendar.key_meetings ?? []) {
            // Only add if not already present as a standalone meeting_card
            const alreadyPresent = result.meetings.some(
              (mc) => {
                const mcData = mc.data as Record<string, unknown>;
                return mcData.title === m.title || mcData.time === m.time;
              },
            );
            if (!alreadyPresent) {
              result.meetings.push({
                type: 'meeting_card',
                data: {
                  id: `briefing-meeting-${m.time}`,
                  title: m.title,
                  time: m.time,
                  attendees: m.attendees ?? [],
                  company: m.title,
                  has_brief: false,
                },
              });
            }
          }

          // Extract signals from briefing data
          const signals = data.signals ?? { company_news: [], market_trends: [], competitive_intel: [] };
          const allSignals = [
            ...(signals.company_news ?? []),
            ...(signals.market_trends ?? []),
            ...(signals.competitive_intel ?? []),
          ];
          for (const s of allSignals) {
            result.signals.push({
              type: 'signal_card',
              data: {
                id: s.id,
                company_name: '',
                signal_type: 'engagement',
                headline: `${s.title}: ${s.summary}`,
              },
            });
          }
        }
        break;
      }
      default:
        result.other.push(item);
        break;
    }
  }

  return result;
}

export function BriefingTranscriptView({ summary, richContent }: BriefingTranscriptViewProps) {
  const grouped = groupContent(richContent);

  const hasEmail = grouped.emailSummary != null;
  const emailItemCount = hasEmail
    ? (grouped.emailSummary!.needs_attention?.length ?? 0) +
      (grouped.emailSummary!.fyi_count ?? 0)
    : 0;

  const hasLeads = grouped.leads != null;
  const leadCount = hasLeads
    ? (grouped.leads!.hot_leads?.length ?? 0) +
      (grouped.leads!.needs_attention?.length ?? 0)
    : 0;

  return (
    <div className="space-y-0">
      {/* Summary — always visible, not collapsible */}
      {summary && (
        <div className="pb-3 mb-1 border-b border-[var(--border)]/40">
          <p className="text-sm leading-relaxed text-[var(--text-primary)] font-light">{summary}</p>
        </div>
      )}

      {/* Priority Actions */}
      <BriefingSection
        title="Priority Actions"
        count={grouped.priorityActions.length}
        defaultExpanded={grouped.priorityActions.length > 0}
        icon={<AlertTriangle size={13} />}
      >
        {grouped.priorityActions.length === 0 ? (
          <p className="text-[11px] text-[var(--text-secondary)] italic">No urgent actions for today</p>
        ) : (
          <div className="space-y-2">
            <RichContentRenderer items={grouped.priorityActions} />
          </div>
        )}
      </BriefingSection>

      {/* Today's Meetings */}
      <BriefingSection
        title="Today's Meetings"
        count={grouped.meetings.length}
        defaultExpanded={grouped.meetings.length > 0}
        icon={<Calendar size={13} />}
      >
        {grouped.meetings.length === 0 ? (
          <p className="text-[11px] text-[var(--text-secondary)] italic">No meetings scheduled today</p>
        ) : (
          <div className="space-y-2">
            <RichContentRenderer items={grouped.meetings} />
          </div>
        )}
      </BriefingSection>

      {/* Email Summary */}
      <BriefingSection
        title="Email Summary"
        count={emailItemCount}
        defaultExpanded={false}
        icon={<Mail size={13} />}
      >
        {!hasEmail ? (
          <p className="text-[11px] text-[var(--text-secondary)] italic">No email data available for today</p>
        ) : (
          <EmailSummaryContent data={grouped.emailSummary!} />
        )}
      </BriefingSection>

      {/* Pipeline (Leads) */}
      <BriefingSection
        title="Pipeline"
        count={leadCount}
        defaultExpanded={false}
        icon={<Users size={13} />}
      >
        {!hasLeads || leadCount === 0 ? (
          <p className="text-[11px] text-[var(--text-secondary)] italic">No lead updates for today</p>
        ) : (
          <LeadsSectionContent data={grouped.leads!} />
        )}
      </BriefingSection>

      {/* Market Intelligence */}
      <BriefingSection
        title="Market Intelligence"
        count={grouped.signals.length}
        defaultExpanded={false}
        icon={<TrendingUp size={13} />}
      >
        {grouped.signals.length === 0 ? (
          <p className="text-[11px] text-[var(--text-secondary)] italic">No intelligence available for today</p>
        ) : (
          <div className="space-y-2">
            <RichContentRenderer items={grouped.signals} />
          </div>
        )}
      </BriefingSection>

      {/* Other uncategorized cards (if any) */}
      {grouped.other.length > 0 && (
        <div className="pt-2">
          <RichContentRenderer items={grouped.other} />
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Email summary inline content
// Mirrors BriefingCard email section: draft status, summary, aria_notes,
// confidence, connected threads, and filtered count.
// ---------------------------------------------------------------------------

function EmailSummaryContent({ data }: { data: NonNullable<BriefingCardData['email_summary']> }) {
  const [fyiOpen, setFyiOpen] = useState(false);

  return (
    <div className="space-y-2">
      {/* Stats row */}
      <p className="text-[10px] font-mono text-[var(--text-secondary)]">
        {data.total_received} received &middot; {data.drafts_waiting} drafts ready &middot; {data.fyi_count} FYI
      </p>

      {/* Needs attention */}
      {(data.needs_attention ?? []).length > 0 && (
        <ul className="space-y-2">
          {data.needs_attention.map((item, i) => (
            <li
              key={item.draft_id ?? i}
              className="rounded border border-[var(--border)] px-2 py-1.5"
              style={{ backgroundColor: 'var(--bg-subtle)' }}
            >
              <div className="flex items-center gap-2 text-[11px]">
                <span className="text-[var(--text-primary)] font-medium truncate">
                  {item.sender}
                </span>
                <span className="text-[var(--text-secondary)] text-[10px] font-mono truncate">
                  {item.company}
                </span>
                <span className="ml-auto shrink-0">
                  {item.draft_status === 'ready' && (
                    <span className="inline-flex items-center rounded px-1 py-0.5 text-[9px] font-mono bg-[var(--success)]/15 text-[var(--success)]">
                      Ready
                    </span>
                  )}
                  {item.draft_status === 'needs_review' && (
                    <span className="inline-flex items-center rounded px-1 py-0.5 text-[9px] font-mono bg-[var(--warning)]/15 text-[var(--warning)]">
                      Needs Review
                    </span>
                  )}
                  {item.draft_status !== 'ready' && item.draft_status !== 'needs_review' && (
                    <span className="inline-flex items-center rounded px-1 py-0.5 text-[9px] font-mono bg-[var(--text-secondary)]/10 text-[var(--text-secondary)]">
                      Not Drafted
                    </span>
                  )}
                </span>
              </div>
              <p className="text-[11px] text-[var(--text-primary)] leading-snug mt-0.5 truncate">
                {item.subject}
              </p>
              <p className="text-[10px] text-[var(--text-secondary)] leading-snug mt-0.5">
                {item.summary}
              </p>
              {item.aria_notes && (
                <p className="text-[10px] text-[var(--accent)] leading-snug mt-0.5 italic">
                  {item.aria_notes}
                </p>
              )}
              {item.draft_confidence && (
                <span className="text-[9px] font-mono text-[var(--text-secondary)] mt-0.5 inline-block">
                  confidence: {item.draft_confidence}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}

      {/* FYI highlights (collapsible) */}
      {(data.fyi_highlights ?? []).length > 0 && (
        <div className="mt-1">
          <button
            type="button"
            className="flex items-center gap-1 text-[10px] font-mono text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
            onClick={() => setFyiOpen((v) => !v)}
          >
            {fyiOpen ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
            <span>FYI ({data.fyi_count})</span>
          </button>
          {fyiOpen && (
            <ul className="mt-1 space-y-0.5 pl-3">
              {data.fyi_highlights.map((h, i) => (
                <li key={i} className="text-[10px] text-[var(--text-secondary)] leading-snug">
                  &middot; {h}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Connected threads */}
      {(data.connections ?? []).length > 0 && (
        <div className="mt-2 border-t border-[var(--border)] pt-2">
          <div className="flex items-center gap-1 text-[10px] font-mono text-[var(--text-secondary)] mb-1">
            <Link2 size={10} />
            <span>Connected threads</span>
          </div>
          <ul className="space-y-1">
            {data.connections!.map((conn, i) => (
              <li
                key={i}
                className="rounded border border-[var(--accent)]/20 px-2 py-1"
                style={{ backgroundColor: 'color-mix(in srgb, var(--accent) 5%, transparent)' }}
              >
                <p className="text-[10px] text-[var(--accent)] font-medium">{conn.topic}</p>
                {conn.emails.map((e, j) => (
                  <p key={j} className="text-[10px] text-[var(--text-secondary)] leading-snug">
                    &middot; {e}
                  </p>
                ))}
                <p className="text-[9px] text-[var(--text-secondary)] italic mt-0.5">
                  {conn.insight}
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Filtered footer */}
      {data.filtered_count > 0 && (
        <p className="text-[9px] font-mono text-[var(--text-secondary)] mt-2 opacity-60">
          {data.filtered_count} filtered (newsletters, automated)
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Leads section content — mirrors BriefingCard leads section
// ---------------------------------------------------------------------------

function LeadsSectionContent({ data }: { data: NonNullable<BriefingCardData['leads']> }) {
  return (
    <ul className="space-y-1">
      {(data.needs_attention ?? []).map((lead) => (
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
      {(data.hot_leads ?? []).map((lead) => (
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
  );
}
