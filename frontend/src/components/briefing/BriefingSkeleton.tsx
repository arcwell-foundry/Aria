export function BriefingSkeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      {/* Greeting skeleton */}
      <div className="space-y-3">
        <div className="h-10 w-64 bg-slate-700/50 rounded-lg" />
        <div className="h-5 w-96 bg-slate-700/30 rounded" />
      </div>

      {/* Summary card skeleton */}
      <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-6">
        <div className="space-y-3">
          <div className="h-4 w-full bg-slate-700/50 rounded" />
          <div className="h-4 w-5/6 bg-slate-700/50 rounded" />
          <div className="h-4 w-4/6 bg-slate-700/50 rounded" />
        </div>
      </div>

      {/* Section skeletons */}
      {[1, 2, 3, 4].map((i) => (
        <div key={i} className="bg-slate-800/50 border border-slate-700/50 rounded-xl">
          <div className="p-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-5 h-5 bg-slate-700/50 rounded" />
              <div className="h-5 w-32 bg-slate-700/50 rounded" />
              <div className="h-5 w-8 bg-slate-700/30 rounded-full" />
            </div>
            <div className="w-5 h-5 bg-slate-700/30 rounded" />
          </div>
          <div className="px-4 pb-4 space-y-3">
            <div className="h-16 bg-slate-700/30 rounded-lg" />
            <div className="h-16 bg-slate-700/30 rounded-lg" />
          </div>
        </div>
      ))}
    </div>
  );
}
