import { Lightbulb } from 'lucide-react';

interface StrategicAdvice {
  advice: string;
  confidence: number;
  basis: string;
}

const PLACEHOLDER_ADVICE: StrategicAdvice = {
  advice:
    'Lonza is evaluating 3 CDMOs. Your differentiator: regulatory expertise. Lead with compliance case studies from the Merck engagement.',
  confidence: 85,
  basis: 'Based on 12 interactions, 3 competitor mentions, and procurement timeline analysis',
};

export interface StrategicAdviceModuleProps {
  advice?: StrategicAdvice;
}

export function StrategicAdviceModule({ advice = PLACEHOLDER_ADVICE }: StrategicAdviceModuleProps) {
  return (
    <div data-aria-id="intel-strategic-advice" className="space-y-2">
      <h3
        className="font-sans text-[11px] font-medium uppercase tracking-wider mb-3"
        style={{ color: 'var(--text-secondary)' }}
      >
        Strategic Advice
      </h3>
      <div
        className="rounded-lg border p-3"
        style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
      >
        <div className="flex items-start gap-2">
          <Lightbulb size={14} className="mt-0.5 flex-shrink-0" style={{ color: 'var(--warning)' }} />
          <div className="min-w-0">
            <p className="font-sans text-[13px] leading-[1.6]" style={{ color: 'var(--text-primary)' }}>
              {advice.advice}
            </p>
            <div className="flex items-center gap-3 mt-2">
              <div className="flex items-center gap-1.5">
                <div
                  className="h-1.5 rounded-full"
                  style={{
                    width: '48px',
                    backgroundColor: 'var(--border)',
                  }}
                >
                  <div
                    className="h-1.5 rounded-full"
                    style={{
                      width: `${advice.confidence}%`,
                      backgroundColor: 'var(--success)',
                    }}
                  />
                </div>
                <span className="font-mono text-[10px]" style={{ color: 'var(--text-secondary)' }}>
                  {advice.confidence}%
                </span>
              </div>
            </div>
            <p className="font-sans text-[11px] mt-2 leading-[1.4]" style={{ color: 'var(--text-secondary)' }}>
              {advice.basis}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
