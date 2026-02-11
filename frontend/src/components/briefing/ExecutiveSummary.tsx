import { Sparkles } from "lucide-react";

interface ExecutiveSummaryProps {
  summary?: string;
}

export function ExecutiveSummary({ summary }: ExecutiveSummaryProps) {
  if (!summary) return null;

  return (
    <div className="relative overflow-hidden bg-gradient-to-br from-slate-800/80 via-slate-800/60 to-primary-900/30 border border-slate-700/50 rounded-xl p-6">
      {/* Subtle gradient overlay */}
      <div className="absolute top-0 right-0 w-64 h-64 bg-primary-500/5 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2" />

      <div className="relative">
        <div className="flex items-center gap-2 mb-3">
          <Sparkles className="w-5 h-5 text-primary-400" />
          <h2 className="text-sm font-medium text-primary-400 uppercase tracking-wider">
            Today's Summary
          </h2>
        </div>
        <p className="text-lg text-white leading-relaxed">{summary}</p>
      </div>
    </div>
  );
}
