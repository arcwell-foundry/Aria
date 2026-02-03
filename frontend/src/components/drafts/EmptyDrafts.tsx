interface EmptyDraftsProps {
  onCreateClick: () => void;
  hasFilter?: boolean;
}

export function EmptyDrafts({ onCreateClick, hasFilter = false }: EmptyDraftsProps) {
  return (
    <div className="flex flex-col items-center justify-center py-20 px-6">
      {/* Elegant envelope illustration */}
      <div className="relative mb-8">
        <div className="w-32 h-24 bg-gradient-to-br from-slate-700/50 to-slate-800/50 rounded-2xl border border-slate-600/30 transform -rotate-6 absolute -left-4 -top-2" />
        <div className="w-32 h-24 bg-gradient-to-br from-slate-700/80 to-slate-800/80 rounded-2xl border border-slate-600/50 relative flex items-center justify-center">
          <svg className="w-12 h-12 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
            />
          </svg>
        </div>
      </div>

      <h3 className="text-xl font-semibold text-white mb-2">
        {hasFilter ? "No drafts match your filter" : "No email drafts yet"}
      </h3>
      <p className="text-slate-400 text-center max-w-sm mb-8">
        {hasFilter
          ? "Try adjusting your filter or create a new draft."
          : "Let ARIA help you compose the perfect email. Your drafts will appear here."}
      </p>

      <button
        onClick={onCreateClick}
        className="group inline-flex items-center gap-3 px-6 py-3.5 bg-gradient-to-r from-primary-600 to-primary-500 hover:from-primary-500 hover:to-primary-400 text-white font-medium rounded-2xl transition-all duration-300 shadow-lg shadow-primary-600/25 hover:shadow-primary-500/40 hover:scale-[1.02]"
      >
        <svg className="w-5 h-5 transition-transform group-hover:rotate-90 duration-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
        </svg>
        Compose New Draft
      </button>
    </div>
  );
}
