export function MeetingBriefSkeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      {/* Header skeleton */}
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-2">
          <div className="h-8 w-72 bg-slate-700/50 rounded-lg" />
          <div className="h-5 w-48 bg-slate-700/30 rounded" />
        </div>
        <div className="flex gap-2">
          <div className="h-10 w-24 bg-slate-700/30 rounded-lg" />
          <div className="h-10 w-10 bg-slate-700/30 rounded-lg" />
        </div>
      </div>

      {/* Summary skeleton */}
      <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-6">
        <div className="space-y-3">
          <div className="h-4 w-full bg-slate-700/50 rounded" />
          <div className="h-4 w-5/6 bg-slate-700/50 rounded" />
          <div className="h-4 w-4/6 bg-slate-700/50 rounded" />
        </div>
      </div>

      {/* Attendees skeleton */}
      <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl">
        <div className="p-4 flex items-center gap-3">
          <div className="w-5 h-5 bg-slate-700/50 rounded" />
          <div className="h-5 w-24 bg-slate-700/50 rounded" />
          <div className="h-5 w-6 bg-slate-700/30 rounded-full" />
        </div>
        <div className="px-4 pb-4 grid grid-cols-1 md:grid-cols-2 gap-4">
          {[1, 2].map((i) => (
            <div key={i} className="bg-slate-700/30 rounded-xl p-4 space-y-3">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 bg-slate-600/50 rounded-full" />
                <div className="space-y-2 flex-1">
                  <div className="h-4 w-32 bg-slate-600/50 rounded" />
                  <div className="h-3 w-24 bg-slate-600/30 rounded" />
                </div>
              </div>
              <div className="h-12 bg-slate-600/30 rounded" />
              <div className="flex gap-2">
                <div className="h-6 w-20 bg-slate-600/30 rounded-full" />
                <div className="h-6 w-24 bg-slate-600/30 rounded-full" />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Company & Agenda skeletons */}
      {[1, 2, 3].map((i) => (
        <div key={i} className="bg-slate-800/50 border border-slate-700/50 rounded-xl">
          <div className="p-4 flex items-center gap-3">
            <div className="w-5 h-5 bg-slate-700/50 rounded" />
            <div className="h-5 w-32 bg-slate-700/50 rounded" />
          </div>
          <div className="px-4 pb-4 space-y-2">
            <div className="h-4 w-full bg-slate-700/30 rounded" />
            <div className="h-4 w-3/4 bg-slate-700/30 rounded" />
          </div>
        </div>
      ))}
    </div>
  );
}
