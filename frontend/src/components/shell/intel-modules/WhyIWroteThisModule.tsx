import { Brain } from 'lucide-react';

interface Reasoning {
  summary: string;
  factors: string[];
}

const PLACEHOLDER_REASONING: Reasoning = {
  summary:
    "Based on Lonza's recent silence (14 days) and their Q2 budget cycle starting March 1, this follow-up targets re-engagement before budget lock.",
  factors: [
    'Last contact: Jan 28 (14 days silent)',
    'Q2 budget cycle begins March 1',
    'Champion prefers Tuesday morning outreach',
    'Previous response rate: 72% within 24h',
  ],
};

export interface WhyIWroteThisModuleProps {
  reasoning?: Reasoning;
}

export function WhyIWroteThisModule({ reasoning = PLACEHOLDER_REASONING }: WhyIWroteThisModuleProps) {
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
