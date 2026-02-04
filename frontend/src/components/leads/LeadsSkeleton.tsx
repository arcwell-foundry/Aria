interface LeadsSkeletonProps {
  viewMode: "card" | "table";
}

function CardSkeleton() {
  return (
    <div className="bg-slate-800/40 border border-slate-700/50 rounded-xl p-5 animate-pulse">
      <div className="flex items-start gap-4 mb-4">
        <div className="w-12 h-12 bg-slate-700 rounded-xl" />
        <div className="flex-1">
          <div className="h-5 bg-slate-700 rounded w-3/4 mb-2" />
          <div className="h-4 bg-slate-700 rounded w-1/2" />
        </div>
      </div>
      <div className="h-8 bg-slate-700 rounded-full w-20 mb-4" />
      <div className="grid grid-cols-2 gap-3">
        <div className="h-4 bg-slate-700 rounded" />
        <div className="h-4 bg-slate-700 rounded" />
      </div>
    </div>
  );
}

function TableRowSkeleton() {
  return (
    <tr className="border-b border-slate-700/30">
      <td className="px-4 py-4">
        <div className="w-5 h-5 bg-slate-700 rounded animate-pulse" />
      </td>
      <td className="px-4 py-4">
        <div className="h-5 bg-slate-700 rounded w-40 animate-pulse" />
      </td>
      <td className="px-4 py-4">
        <div className="h-5 bg-slate-700 rounded w-16 animate-pulse" />
      </td>
      <td className="px-4 py-4">
        <div className="h-6 bg-slate-700 rounded-full w-24 animate-pulse" />
      </td>
      <td className="px-4 py-4">
        <div className="h-6 bg-slate-700 rounded-full w-20 animate-pulse" />
      </td>
      <td className="px-4 py-4">
        <div className="h-5 bg-slate-700 rounded w-20 animate-pulse" />
      </td>
      <td className="px-4 py-4">
        <div className="h-5 bg-slate-700 rounded w-24 animate-pulse" />
      </td>
      <td className="px-4 py-4">
        <div className="h-5 bg-slate-700 rounded w-16 animate-pulse" />
      </td>
    </tr>
  );
}

export function LeadsSkeleton({ viewMode }: LeadsSkeletonProps) {
  if (viewMode === "table") {
    return (
      <div className="bg-slate-800/40 border border-slate-700/50 rounded-xl overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="bg-slate-800/60 text-left">
              <th className="w-12 px-4 py-3" />
              <th className="px-4 py-3 text-sm font-medium text-slate-400">Company</th>
              <th className="px-4 py-3 text-sm font-medium text-slate-400">Health</th>
              <th className="px-4 py-3 text-sm font-medium text-slate-400">Stage</th>
              <th className="px-4 py-3 text-sm font-medium text-slate-400">Status</th>
              <th className="px-4 py-3 text-sm font-medium text-slate-400">Value</th>
              <th className="px-4 py-3 text-sm font-medium text-slate-400">Last Activity</th>
              <th className="px-4 py-3 text-sm font-medium text-slate-400">Actions</th>
            </tr>
          </thead>
          <tbody>
            {[...Array(5)].map((_, i) => (
              <TableRowSkeleton key={i} />
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {[...Array(6)].map((_, i) => (
        <CardSkeleton key={i} />
      ))}
    </div>
  );
}
