import type { LeadScoreBreakdown } from "@/api/leadGeneration";

function scoreColor(score: number): string {
  if (score >= 70) return "text-emerald-400";
  if (score >= 40) return "text-amber-400";
  return "text-red-400";
}

function barColor(score: number): string {
  if (score >= 70) return "bg-emerald-500";
  if (score >= 40) return "bg-amber-500";
  return "bg-red-500";
}

interface ScoreBreakdownProps {
  breakdown: LeadScoreBreakdown;
}

export function ScoreBreakdown({ breakdown }: ScoreBreakdownProps) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 space-y-4">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-slate-300">Overall Score</span>
        <span className={`text-2xl font-bold ${scoreColor(breakdown.overall_score)}`}>
          {breakdown.overall_score}
        </span>
      </div>
      <div className="space-y-3">
        {breakdown.factors.map((factor) => (
          <div key={factor.name}>
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm text-slate-300">{factor.name}</span>
              <span className="text-sm text-slate-400">
                {factor.score}/100 ({Math.round(factor.weight * 100)}%)
              </span>
            </div>
            <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${barColor(factor.score)}`}
                style={{ width: `${factor.score}%` }}
              />
            </div>
            <p className="text-xs text-slate-500 mt-1">{factor.explanation}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
