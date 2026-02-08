import { useEnrichmentStatus } from "@/hooks/useEnrichmentStatus";

interface EnrichmentProgressProps {
  companyName: string;
}

const STAGE_MESSAGES: Record<string, string> = {
  no_company: "Preparing research...",
  not_found: "Setting up analysis...",
  in_progress: "Researching across multiple sources...",
  complete: "Research complete",
};

export function EnrichmentProgress({ companyName }: EnrichmentProgressProps) {
  const { status, qualityScore, isComplete, isLoading } =
    useEnrichmentStatus(true);

  return (
    <div
      className="flex flex-col gap-6 animate-in fade-in"
      role="status"
      aria-live="polite"
      aria-label={`ARIA enrichment progress for ${companyName}`}
    >
      {/* Ambient presence mark */}
      <div className="relative flex items-center justify-center h-24 overflow-hidden">
        <PresenceMark isComplete={isComplete} />
      </div>

      {/* Header */}
      <div className="flex flex-col gap-2 text-center">
        {isComplete ? (
          <h2 className="font-display text-[24px] leading-[1.3] text-content aria-settle">
            ARIA now knows {qualityScore ?? 0}% of what she needs about{" "}
            {companyName}
          </h2>
        ) : (
          <h2 className="font-display text-[24px] leading-[1.3] text-content">
            ARIA is researching {companyName}
          </h2>
        )}

        <p className="font-sans text-[15px] leading-relaxed text-secondary">
          {isLoading
            ? "Starting research..."
            : STAGE_MESSAGES[status ?? "in_progress"]}
        </p>
      </div>

      {/* Live stats */}
      {isComplete && qualityScore !== null && (
        <div className="aria-settle">
          <QualityIndicator score={qualityScore} />
        </div>
      )}

      {/* Non-blocking message */}
      {!isComplete && (
        <p className="font-sans text-[13px] leading-relaxed text-secondary text-center italic">
          You can continue with the next steps — I'll keep researching in the
          background.
        </p>
      )}
    </div>
  );
}

function PresenceMark({ isComplete }: { isComplete: boolean }) {
  if (isComplete) {
    return (
      <div className="relative w-20 h-20 aria-settle">
        {/* Settled state — still, defined */}
        <div className="absolute inset-0 rounded-full bg-success/10" />
        <div className="absolute inset-2 rounded-full bg-success/8" />
        <div className="absolute inset-4 rounded-full bg-success/6" />
      </div>
    );
  }

  return (
    <div className="relative w-24 h-24">
      {/* Outer glow layer — slowest, subtlest */}
      <div
        className="absolute inset-0 rounded-full bg-interactive/10 aria-glow"
        aria-hidden="true"
      />
      {/* Middle breathing layer */}
      <div
        className="absolute inset-3 rounded-full bg-interactive/12 aria-breathe"
        style={{ animationDelay: "1s" }}
        aria-hidden="true"
      />
      {/* Inner drift layer — organic movement */}
      <div
        className="absolute inset-6 rounded-full bg-interactive/15 aria-drift"
        aria-hidden="true"
      />
      {/* Core — subtle steady presence */}
      <div
        className="absolute inset-8 rounded-full bg-interactive/20 aria-breathe"
        style={{ animationDelay: "3s" }}
        aria-hidden="true"
      />
    </div>
  );
}

function QualityIndicator({ score }: { score: number }) {
  const label = score >= 70 ? "Strong foundation" : score >= 40 ? "Good start" : "Building...";

  return (
    <div className="flex flex-col items-center gap-3">
      {/* Quality bar — minimal, not a standard progress bar */}
      <div className="w-full max-w-[200px] h-1 rounded-full bg-border overflow-hidden">
        <div
          className="h-full rounded-full bg-success transition-all duration-[800ms] ease-out"
          style={{ width: `${Math.min(score, 100)}%` }}
        />
      </div>
      <span className="font-sans text-[13px] text-secondary">{label}</span>
    </div>
  );
}
