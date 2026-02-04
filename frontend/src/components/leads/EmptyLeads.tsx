import { Building2, Plus } from "lucide-react";

interface EmptyLeadsProps {
  hasFilters: boolean;
  onClearFilters?: () => void;
}

export function EmptyLeads({ hasFilters, onClearFilters }: EmptyLeadsProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-4">
      <div className="w-20 h-20 bg-slate-800/50 rounded-2xl flex items-center justify-center mb-6 border border-slate-700/50">
        <Building2 className="w-10 h-10 text-slate-500" />
      </div>

      {hasFilters ? (
        <>
          <h3 className="text-xl font-semibold text-white mb-2">No leads found</h3>
          <p className="text-slate-400 text-center max-w-md mb-6">
            No leads match your current filters. Try adjusting your search or filter criteria.
          </p>
          <button
            onClick={onClearFilters}
            className="inline-flex items-center gap-2 px-4 py-2.5 bg-slate-700 hover:bg-slate-600 text-white font-medium rounded-lg transition-colors"
          >
            Clear Filters
          </button>
        </>
      ) : (
        <>
          <h3 className="text-xl font-semibold text-white mb-2">No leads yet</h3>
          <p className="text-slate-400 text-center max-w-md mb-6">
            Leads will appear here as ARIA tracks your sales pursuits. Start a conversation or approve an outbound email to begin.
          </p>
          <div className="flex items-center gap-3 text-sm text-slate-500">
            <Plus className="w-4 h-4" />
            <span>Leads are created automatically from your interactions</span>
          </div>
        </>
      )}
    </div>
  );
}
