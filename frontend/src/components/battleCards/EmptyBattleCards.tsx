interface EmptyBattleCardsProps {
  onCreateClick: () => void;
  hasSearchFilter?: boolean;
}

export function EmptyBattleCards({ onCreateClick, hasSearchFilter = false }: EmptyBattleCardsProps) {
  if (hasSearchFilter) {
    return (
      <div className="flex flex-col items-center justify-center py-16 px-4">
        <div className="relative">
          <div className="absolute inset-0 bg-slate-500/10 blur-3xl rounded-full" />
          <div className="relative w-20 h-20 bg-slate-800 border border-slate-700 rounded-2xl flex items-center justify-center">
            <svg
              className="w-10 h-10 text-slate-500"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
              />
            </svg>
          </div>
        </div>

        <h3 className="mt-6 text-xl font-semibold text-white">No matches found</h3>
        <p className="mt-2 text-slate-400 text-center max-w-md">
          No battle cards match your search. Try adjusting your search terms or add a new competitor.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center py-16 px-4">
      {/* Illustration */}
      <div className="relative">
        <div className="absolute inset-0 bg-primary-500/20 blur-3xl rounded-full" />
        <div className="relative w-24 h-24 bg-slate-800 border border-slate-700 rounded-2xl flex items-center justify-center">
          <svg
            className="w-12 h-12 text-slate-500"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
            />
          </svg>
        </div>
      </div>

      {/* Text */}
      <h3 className="mt-6 text-xl font-semibold text-white">No battle cards yet</h3>
      <p className="mt-2 text-slate-400 text-center max-w-md">
        Add your first competitor to start building your competitive intelligence library. ARIA will
        help you stay ahead of the competition.
      </p>

      {/* CTA */}
      <button
        onClick={onCreateClick}
        className="mt-6 inline-flex items-center gap-2 px-5 py-2.5 bg-primary-600 hover:bg-primary-500 text-white font-medium rounded-xl transition-all duration-200 shadow-lg shadow-primary-600/25 hover:shadow-primary-500/30"
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
        </svg>
        Add your first competitor
      </button>
    </div>
  );
}
