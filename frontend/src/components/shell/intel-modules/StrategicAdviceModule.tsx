import { Lightbulb } from 'lucide-react';
import { useIntelligenceInsights, useIntelLeadInsights, useRouteContext } from '@/hooks/useIntelPanelData';

interface StrategicAdvice {
  advice: string;
  confidence: number;
  basis: string;
}

function StrategicAdviceSkeleton() {
  return (
    <div className="space-y-2">
      <div className="h-3 w-28 rounded bg-[var(--border)] animate-pulse" />
      <div className="h-28 rounded-lg bg-[var(--border)] animate-pulse" />
    </div>
  );
}

export interface StrategicAdviceModuleProps {
  advice?: StrategicAdvice;
}

export function StrategicAdviceModule({ advice: propAdvice }: StrategicAdviceModuleProps) {
  const { leadId, isLeadDetail } = useRouteContext();
  const { data: leadInsights, isLoading: leadLoading } = useIntelLeadInsights(leadId);
  const { data: globalInsights, isLoading: globalLoading } = useIntelligenceInsights({ limit: 3 });

  const isLoading = isLeadDetail ? leadLoading : globalLoading;

  if (isLoading && !propAdvice) return <StrategicAdviceSkeleton />;

  let advice: StrategicAdvice;
  if (propAdvice) {
    advice = propAdvice;
  } else if (isLeadDetail && leadInsights && leadInsights.length > 0) {
    const top = leadInsights[0];
    advice = {
      advice: top.content,
      confidence: Math.round(top.confidence * 100),
      basis: `Based on ${leadInsights.length} insight${leadInsights.length !== 1 ? 's' : ''} from lead analysis`,
    };
  } else if (globalInsights && globalInsights.length > 0) {
    const top = globalInsights[0];
    advice = {
      advice: top.content,
      confidence: Math.round(top.confidence * 100),
      basis: top.trigger_event || `Based on ${globalInsights.length} intelligence insight${globalInsights.length !== 1 ? 's' : ''}`,
    };
  } else {
    return (
      <div data-aria-id="intel-strategic-advice" className="space-y-2">
        <h3
          className="font-sans text-[11px] font-medium uppercase tracking-wider mb-3"
          style={{ color: 'var(--text-secondary)' }}
        >
          Strategic Advice
        </h3>
        <div
          className="rounded-lg border p-4"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
        >
          <p className="font-sans text-[12px]" style={{ color: 'var(--text-secondary)' }}>
            No strategic advice available yet. ARIA will provide insights as intelligence is gathered.
          </p>
        </div>
      </div>
    );
  }

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
