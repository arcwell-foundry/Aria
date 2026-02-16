import { Brain } from 'lucide-react';
import { useIntelDraft, useIntelDrafts, useRouteContext } from '@/hooks/useIntelPanelData';

interface Reasoning {
  summary: string;
  factors: string[];
}

function WhyIWroteThisSkeleton() {
  return (
    <div className="space-y-3">
      <div className="h-3 w-28 rounded bg-[var(--border)] animate-pulse" />
      <div className="h-20 rounded-lg bg-[var(--border)] animate-pulse" />
      <div className="space-y-1.5 pl-1">
        <div className="h-3 w-full rounded bg-[var(--border)] animate-pulse" />
        <div className="h-3 w-3/4 rounded bg-[var(--border)] animate-pulse" />
        <div className="h-3 w-5/6 rounded bg-[var(--border)] animate-pulse" />
      </div>
    </div>
  );
}

export interface WhyIWroteThisModuleProps {
  reasoning?: Reasoning;
}

export function WhyIWroteThisModule({ reasoning: propReasoning }: WhyIWroteThisModuleProps) {
  const { draftId, isDraftDetail } = useRouteContext();
  const { data: draft, isLoading: draftLoading } = useIntelDraft(draftId);
  const { data: drafts, isLoading: draftsLoading } = useIntelDrafts();

  const isLoading = isDraftDetail ? draftLoading : draftsLoading;

  if (isLoading && !propReasoning) return <WhyIWroteThisSkeleton />;

  let reasoning: Reasoning;
  if (propReasoning) {
    reasoning = propReasoning;
  } else if (isDraftDetail && draft) {
    const ctx = draft.context as Record<string, string> | undefined;
    reasoning = {
      summary: ctx?.user_context ?? `This ${draft.purpose} email to ${draft.recipient_name ?? draft.recipient_email} was crafted based on your communication history and relationship context.`,
      factors: [
        `Purpose: ${draft.purpose}`,
        `Tone: ${draft.tone}`,
        `Recipient: ${draft.recipient_name ?? draft.recipient_email}`,
        ...(draft.style_match_score ? [`Style match: ${draft.style_match_score}%`] : []),
        ...(draft.lead_memory_id ? ['Linked to pipeline lead'] : []),
      ],
    };
  } else if (drafts && drafts.length > 0) {
    const latest = drafts[0];
    reasoning = {
      summary: `Most recent draft: ${latest.purpose} email to ${latest.recipient_name ?? latest.recipient_email}.`,
      factors: [
        `Purpose: ${latest.purpose}`,
        `Tone: ${latest.tone}`,
        `Status: ${latest.status}`,
      ],
    };
  } else {
    return (
      <div data-aria-id="intel-why-wrote" className="space-y-3">
        <h3
          className="font-sans text-[11px] font-medium uppercase tracking-wider"
          style={{ color: 'var(--text-secondary)' }}
        >
          Why I Wrote This
        </h3>
        <div
          className="rounded-lg border p-4"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
        >
          <p className="font-sans text-[12px]" style={{ color: 'var(--text-secondary)' }}>
            No draft context available. ARIA will explain her reasoning when composing emails.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div data-aria-id="intel-why-wrote" className="space-y-3">
      <h3
        className="font-sans text-[11px] font-medium uppercase tracking-wider"
        style={{ color: 'var(--text-secondary)' }}
      >
        Why I Wrote This
      </h3>
      <div
        className="rounded-lg border p-3"
        style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
      >
        <div className="flex items-start gap-2">
          <Brain size={14} className="mt-0.5 flex-shrink-0" style={{ color: 'var(--accent)' }} />
          <p className="font-sans text-[13px] leading-[1.6]" style={{ color: 'var(--text-primary)' }}>
            {reasoning.summary}
          </p>
        </div>
      </div>
      <div className="space-y-1.5 pl-1">
        {reasoning.factors.map((factor, i) => (
          <div key={i} className="flex items-start gap-2">
            <div
              className="w-1 h-1 rounded-full mt-2 flex-shrink-0"
              style={{ backgroundColor: 'var(--accent)' }}
            />
            <p className="font-sans text-[12px] leading-[1.5]" style={{ color: 'var(--text-secondary)' }}>
              {factor}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
