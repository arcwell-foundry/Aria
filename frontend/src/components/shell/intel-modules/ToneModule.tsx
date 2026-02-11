import { MessageCircle } from 'lucide-react';

interface ToneAnalysis {
  current: string;
  recommendation: string;
  formalityScore: number; // 0-100, 0 = very casual, 100 = very formal
}

const PLACEHOLDER_TONE: ToneAnalysis = {
  current: 'Professional, consultative',
  recommendation:
    'Consider warmer opening — Dr. Chen responds better to relationship-first messaging based on 8 prior exchanges.',
  formalityScore: 72,
};

export interface ToneModuleProps {
  tone?: ToneAnalysis;
}

export function ToneModule({ tone = PLACEHOLDER_TONE }: ToneModuleProps) {
  return (
    <div data-aria-id="intel-tone" className="space-y-3">
      <h3
        className="font-sans text-[11px] font-medium uppercase tracking-wider"
        style={{ color: 'var(--text-secondary)' }}
      >
        Tone Guidance
      </h3>
      <div
        className="rounded-lg border p-3"
        style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
      >
        <div className="flex items-start gap-2 mb-3">
          <MessageCircle size={14} className="mt-0.5 flex-shrink-0" style={{ color: 'var(--accent)' }} />
          <div>
            <p className="font-mono text-[11px] mb-1" style={{ color: 'var(--accent)' }}>
              Current: {tone.current}
            </p>
            <p className="font-sans text-[12px] leading-[1.5]" style={{ color: 'var(--text-secondary)' }}>
              {tone.recommendation}
            </p>
          </div>
        </div>
        {/* Tone spectrum bar */}
        <div className="mt-3">
          <div className="flex justify-between mb-1">
            <span className="font-mono text-[9px]" style={{ color: 'var(--text-secondary)' }}>
              CASUAL
            </span>
            <span className="font-mono text-[9px]" style={{ color: 'var(--text-secondary)' }}>
              FORMAL
            </span>
          </div>
          <div
            className="h-1.5 rounded-full w-full"
            style={{ backgroundColor: 'var(--border)' }}
          >
            <div
              className="h-1.5 rounded-full transition-all"
              style={{
                width: `${tone.formalityScore}%`,
                backgroundColor: 'var(--accent)',
              }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
