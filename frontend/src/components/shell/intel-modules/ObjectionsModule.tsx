import { ShieldAlert } from 'lucide-react';
import { useIntelLeadInsights, useIntelBattleCards, useRouteContext } from '@/hooks/useIntelPanelData';

interface Objection {
  objection: string;
  response: string;
}

function ObjectionsSkeleton() {
  return (
    <div className="space-y-2">
      <div className="h-3 w-32 rounded bg-[var(--border)] animate-pulse" />
      <div className="h-20 rounded-lg bg-[var(--border)] animate-pulse" />
      <div className="h-20 rounded-lg bg-[var(--border)] animate-pulse" />
    </div>
  );
}

export interface ObjectionsModuleProps {
  objections?: Objection[];
}

export function ObjectionsModule({ objections: propObjections }: ObjectionsModuleProps) {
  const { leadId, isLeadDetail } = useRouteContext();
  const { data: leadInsights, isLoading: leadLoading } = useIntelLeadInsights(leadId);
  const { data: battleCards, isLoading: cardsLoading } = useIntelBattleCards();

  const isLoading = isLeadDetail ? leadLoading : cardsLoading;

  if (isLoading && !propObjections) return <ObjectionsSkeleton />;

  let objections: Objection[];
  if (propObjections) {
    objections = propObjections;
  } else if (isLeadDetail && leadInsights && leadInsights.length > 0) {
    const objectionInsights = leadInsights.filter((i) => i.insight_type === 'objection');
    objections = objectionInsights.map((i) => ({
      objection: i.content,
      response: i.addressed_at ? 'Addressed' : 'Prepare a response for this concern.',
    }));
  } else if (battleCards && battleCards.length > 0) {
    objections = battleCards
      .flatMap((card) =>
        (card.objection_handlers ?? []).map((h) => ({
          objection: h.objection,
          response: h.response,
        }))
      )
      .slice(0, 5);
  } else {
    objections = [];
  }

  if (objections.length === 0) {
    return (
      <div data-aria-id="intel-objections" className="space-y-2">
        <h3
          className="font-sans text-[11px] font-medium uppercase tracking-wider mb-3"
          style={{ color: 'var(--text-secondary)' }}
        >
          Predicted Objections
        </h3>
        <div
          className="rounded-lg border p-4"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
        >
          <p className="font-sans text-[12px]" style={{ color: 'var(--text-secondary)' }}>
            No objections identified yet. ARIA will predict objections as deal context develops.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div data-aria-id="intel-objections" className="space-y-2">
      <h3
        className="font-sans text-[11px] font-medium uppercase tracking-wider mb-3"
        style={{ color: 'var(--text-secondary)' }}
      >
        Predicted Objections
      </h3>
      {objections.map((obj, i) => (
        <div
          key={i}
          className="rounded-lg border p-3"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
        >
          <div className="flex items-start gap-2">
            <ShieldAlert size={14} className="mt-0.5 flex-shrink-0" style={{ color: 'var(--warning)' }} />
            <div className="min-w-0">
              <p className="font-sans text-[12px] font-medium mb-1" style={{ color: 'var(--text-primary)' }}>
                &ldquo;{obj.objection}&rdquo;
              </p>
              <p className="font-sans text-[12px] leading-[1.5]" style={{ color: 'var(--text-secondary)' }}>
                {obj.response}
              </p>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
