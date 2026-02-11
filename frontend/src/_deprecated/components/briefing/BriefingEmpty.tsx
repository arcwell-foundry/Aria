import { Sparkles, RefreshCw } from "lucide-react";

interface BriefingEmptyProps {
  onGenerate: () => void;
  isGenerating?: boolean;
}

export function BriefingEmpty({ onGenerate, isGenerating }: BriefingEmptyProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-4">
      {/* Illustration */}
      <div className="relative">
        <div className="absolute inset-0 bg-primary-500/20 blur-3xl rounded-full" />
        <div className="relative w-24 h-24 bg-slate-800 border border-slate-700 rounded-2xl flex items-center justify-center">
          <Sparkles className="w-12 h-12 text-primary-400" />
        </div>
      </div>

      {/* Text */}
      <h3 className="mt-6 text-xl font-semibold text-white">No briefing yet</h3>
      <p className="mt-2 text-slate-400 text-center max-w-md">
        ARIA hasn't generated your daily briefing yet. Generate one now to see your calendar,
        priority leads, and market signals.
      </p>

      {/* CTA */}
      <button
        onClick={onGenerate}
        disabled={isGenerating}
        className="mt-6 inline-flex items-center gap-2 px-5 py-2.5 bg-primary-600 hover:bg-primary-500 disabled:opacity-60 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors"
      >
        <RefreshCw className={`w-5 h-5 ${isGenerating ? "animate-spin" : ""}`} />
        {isGenerating ? "Generating..." : "Generate briefing"}
      </button>
    </div>
  );
}
