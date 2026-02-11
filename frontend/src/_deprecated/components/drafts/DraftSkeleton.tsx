export function DraftSkeleton() {
  return (
    <div className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-5 animate-pulse">
      {/* Header row */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex-1">
          <div className="h-5 bg-slate-700 rounded-lg w-3/4 mb-2" />
          <div className="h-4 bg-slate-700/70 rounded-lg w-1/2" />
        </div>
        <div className="h-6 w-16 bg-slate-700 rounded-lg" />
      </div>

      {/* Tags row */}
      <div className="flex items-center gap-2 mb-4">
        <div className="h-7 w-24 bg-slate-700/70 rounded-lg" />
        <div className="h-7 w-20 bg-slate-700/70 rounded-lg" />
      </div>

      {/* Footer row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-slate-700 rounded-full" />
          <div className="h-4 w-20 bg-slate-700/70 rounded-lg" />
        </div>
        <div className="h-4 w-24 bg-slate-700/70 rounded-lg" />
      </div>
    </div>
  );
}
