import { MessageCircle } from 'lucide-react';
import { useIntelDraft, useIntelDrafts, useRouteContext } from '@/hooks/useIntelPanelData';

interface ToneAnalysis {
  current: string;
  recommendation: string;
  formalityScore: number;
}

const TONE_FORMALITY: Record<string, number> = {
  formal: 85,
  friendly: 40,
  urgent: 65,
};

function ToneSkeleton() {
  return (
    <div className="space-y-3">
      <div className="h-3 w-24 rounded bg-[var(--border)] animate-pulse" />
      <div className="h-28 rounded-lg bg-[var(--border)] animate-pulse" />
    </div>
  );
}

export interface ToneModuleProps {
  tone?: ToneAnalysis;
}

export function ToneModule({ tone: propTone }: ToneModuleProps) {
  const { draftId, isDraftDetail } = useRouteContext();
  const { data: draft, isLoading: draftLoading } = useIntelDraft(draftId);
  const { data: drafts, isLoading: draftsLoading } = useIntelDrafts();

  const isLoading = isDraftDetail ? draftLoading : draftsLoading;

  if (isLoading && !propTone) return <ToneSkeleton />;

  let tone: ToneAnalysis;
  if (propTone) {
    tone = propTone;
  } else if (isDraftDetail && draft) {
    tone = {
      current: `${draft.tone.charAt(0).toUpperCase()}${draft.tone.slice(1)}, ${draft.purpose}`,
      recommendation: draft.style_match_score
        ? `Style match score: ${draft.style_match_score}%. ${draft.style_match_score > 80 ? 'Well-matched to your writing style.' : 'Consider adjusting to better match your voice.'}`
        : `Tone is set to ${draft.tone}. ARIA adapts this based on recipient preferences.`,
      formalityScore: TONE_FORMALITY[draft.tone] ?? 60,
    };
  } else if (drafts && drafts.length > 0) {
    const latest = drafts[0];
    tone = {
      current: `${latest.tone.charAt(0).toUpperCase()}${latest.tone.slice(1)}, ${latest.purpose}`,
      recommendation: 'Based on recent drafts. ARIA calibrates tone to each recipient.',
      formalityScore: TONE_FORMALITY[latest.tone] ?? 60,
    };
  } else {
    return (
      <div data-aria-id="intel-tone" className="space-y-3">
        <h3
          className="font-sans text-[11px] font-medium uppercase tracking-wider"
          style={{ color: 'var(--text-secondary)' }}
        >
          Tone Guidance
        </h3>
        <div
          className="rounded-lg border p-4"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
        >
          <p className="font-sans text-[12px]" style={{ color: 'var(--text-secondary)' }}>
            No tone data available. ARIA will provide guidance when drafting communications.
          </p>
        </div>
      </div>
    );
  }

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
