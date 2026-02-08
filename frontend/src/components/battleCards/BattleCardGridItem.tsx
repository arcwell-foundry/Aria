import type { BattleCard } from "@/api/battleCards";

interface BattleCardGridItemProps {
  card: BattleCard;
  onView: () => void;
  onCompare: () => void;
  isSelected?: boolean;
}

export function BattleCardGridItem({
  card,
  onView,
  onCompare,
  isSelected = false,
}: BattleCardGridItemProps) {
  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  };

  return (
    <div
      className={`group relative bg-slate-800/50 border rounded-2xl p-6 transition-all duration-300 ease-out cursor-pointer hover:bg-slate-800/80 hover:shadow-xl hover:shadow-slate-900/50 hover:-translate-y-1 ${
        isSelected
          ? "border-primary-500 ring-2 ring-primary-500/20"
          : "border-slate-700 hover:border-slate-600"
      }`}
      onClick={onView}
    >
      {/* Gradient border effect on hover */}
      <div className="absolute inset-0 rounded-2xl bg-gradient-to-br from-primary-500/0 via-primary-500/5 to-accent-500/0 opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none" />

      {/* Header */}
      <div className="relative flex items-start justify-between gap-4 mb-5">
        <div className="flex-1 min-w-0">
          <h3 className="text-xl font-semibold text-white truncate group-hover:text-primary-400 transition-colors duration-200">
            {card.competitor_name}
          </h3>
          {card.competitor_domain && (
            <p className="mt-1 text-sm text-slate-500 truncate">{card.competitor_domain}</p>
          )}
        </div>

        {/* Compare button */}
        <button
          onClick={(e) => {
            e.stopPropagation();
            onCompare();
          }}
          className={`shrink-0 p-2.5 rounded-xl transition-all duration-200 ${
            isSelected
              ? "bg-primary-600 text-white"
              : "text-slate-400 hover:text-white hover:bg-slate-700"
          }`}
          title={isSelected ? "Selected for comparison" : "Add to comparison"}
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
            />
          </svg>
        </button>
      </div>

      {/* Overview excerpt */}
      {card.overview && (
        <p className="relative text-sm text-slate-400 line-clamp-2 mb-5 leading-relaxed">
          {card.overview}
        </p>
      )}

      {/* Strengths/Weaknesses summary */}
      <div className="relative grid grid-cols-2 gap-4 mb-5">
        <div className="flex items-center gap-2">
          <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-success/10">
            <svg
              className="w-4 h-4 text-success"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M5 13l4 4L19 7"
              />
            </svg>
          </div>
          <span className="text-sm text-slate-300">
            <span className="font-medium text-success">{card.strengths.length}</span>{" "}
            strengths
          </span>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-warning/10">
            <svg
              className="w-4 h-4 text-warning"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
          </div>
          <span className="text-sm text-slate-300">
            <span className="font-medium text-warning">{card.weaknesses.length}</span>{" "}
            weaknesses
          </span>
        </div>
      </div>

      {/* Pricing badge */}
      {card.pricing?.model && (
        <div className="relative inline-flex items-center gap-2 px-3 py-1.5 bg-slate-700/50 rounded-lg text-sm mb-5">
          <svg
            className="w-4 h-4 text-slate-400"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <span className="text-slate-300">{card.pricing.model}</span>
          {card.pricing.range && (
            <span className="text-slate-500">· {card.pricing.range}</span>
          )}
        </div>
      )}

      {/* Footer */}
      <div className="relative flex items-center justify-between pt-4 border-t border-slate-700/50">
        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium ${
              card.update_source === "auto"
                ? "bg-primary-500/10 text-primary-400"
                : "bg-slate-600/50 text-slate-400"
            }`}
          >
            {card.update_source === "auto" ? (
              <>
                <span className="relative flex h-1.5 w-1.5">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-primary-400" />
                </span>
                Auto-updated
              </>
            ) : (
              "Manual"
            )}
          </span>
        </div>
        <span className="text-xs text-slate-500">Updated {formatDate(card.last_updated)}</span>
      </div>
    </div>
  );
}
