import { Loader2 } from "lucide-react";

export function GeneratingOverlay() {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-4">
      {/* Animated spinner */}
      <div className="relative">
        <div className="absolute inset-0 bg-primary-500/20 blur-3xl rounded-full animate-pulse" />
        <div className="relative w-24 h-24 bg-slate-800 border border-slate-700 rounded-2xl flex items-center justify-center">
          <Loader2 className="w-12 h-12 text-primary-400 animate-spin" />
        </div>
      </div>

      {/* Text */}
      <h3 className="mt-6 text-xl font-semibold text-white">Generating your brief</h3>
      <p className="mt-2 text-slate-400 text-center max-w-md">
        ARIA is researching attendees, gathering company intel, and preparing talking points.
        This usually takes 15-30 seconds.
      </p>

      {/* Progress indicators */}
      <div className="mt-8 space-y-3 w-full max-w-sm">
        {["Researching attendees", "Gathering company intel", "Analyzing relationships", "Preparing talking points"].map(
          (step, i) => (
            <div key={step} className="flex items-center gap-3">
              <div
                className={`w-2 h-2 rounded-full ${
                  i < 2 ? "bg-primary-400" : "bg-slate-600"
                } ${i === 1 ? "animate-pulse" : ""}`}
              />
              <span className={`text-sm ${i < 2 ? "text-slate-300" : "text-slate-500"}`}>
                {step}
              </span>
            </div>
          )
        )}
      </div>
    </div>
  );
}
