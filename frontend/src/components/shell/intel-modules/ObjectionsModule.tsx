import { ShieldAlert } from 'lucide-react';

interface Objection {
  objection: string;
  response: string;
}

const PLACEHOLDER_OBJECTIONS: Objection[] = [
  {
    objection: 'Pricing concern',
    response:
      'Emphasize total cost of ownership — your compliance support saves $200K/yr on average vs. in-house',
  },
  {
    objection: 'Timeline too aggressive',
    response:
      'Reference Catalent project delivered 2 weeks early. Offer phased approach if needed.',
  },
];

export interface ObjectionsModuleProps {
  objections?: Objection[];
}

export function ObjectionsModule({ objections = PLACEHOLDER_OBJECTIONS }: ObjectionsModuleProps) {
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
                "{obj.objection}"
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
