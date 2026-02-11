import { useState, useEffect, useCallback } from "react";
import type { BattleCard } from "@/api/battleCards";
import { useBattleCardHistory } from "@/hooks/useBattleCards";

interface BattleCardDetailModalProps {
  card: BattleCard | null;
  isOpen: boolean;
  onClose: () => void;
  onEdit: () => void;
}

type TabId = "overview" | "differentiation" | "objections" | "history";

export function BattleCardDetailModal({
  card,
  isOpen,
  onClose,
  onEdit,
}: BattleCardDetailModalProps) {
  const [activeTab, setActiveTab] = useState<TabId>("overview");

  const { data: history, isLoading: historyLoading } = useBattleCardHistory(
    card?.id ?? "",
    20
  );

  // Handle escape key
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    },
    [onClose]
  );

  useEffect(() => {
    if (isOpen) {
      document.addEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "hidden";
      return () => {
        document.removeEventListener("keydown", handleKeyDown);
        document.body.style.overflow = "";
      };
    }
  }, [isOpen, handleKeyDown]);

  // Reset tab when card changes
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- syncing tab state with prop changes
    setActiveTab("overview");
  }, [card?.id]);

  if (!isOpen || !card) return null;

  const tabs: { id: TabId; label: string }[] = [
    { id: "overview", label: "Overview" },
    { id: "differentiation", label: "Differentiation" },
    { id: "objections", label: "Objection Handlers" },
    { id: "history", label: "History" },
  ];

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-4xl max-h-[90vh] mx-4 bg-slate-800 border border-slate-700 rounded-2xl shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="shrink-0 flex items-start justify-between gap-4 px-6 py-5 border-b border-slate-700">
          <div className="flex-1 min-w-0">
            <h2 className="text-2xl font-bold text-white">{card.competitor_name}</h2>
            {card.competitor_domain && (
              <p className="mt-1 text-slate-400">{card.competitor_domain}</p>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={onEdit}
              className="inline-flex items-center gap-2 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white text-sm font-medium rounded-xl transition-colors"
            >
              <svg
                className="w-4 h-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
                />
              </svg>
              Edit
            </button>
            <button
              onClick={onClose}
              className="p-2 text-slate-400 hover:text-white hover:bg-slate-700 rounded-xl transition-colors"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="shrink-0 flex gap-1 px-6 pt-4 border-b border-slate-700">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2.5 text-sm font-medium rounded-t-lg transition-colors ${
                activeTab === tab.id
                  ? "bg-slate-700 text-white"
                  : "text-slate-400 hover:text-white hover:bg-slate-700/50"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {activeTab === "overview" && (
            <div className="space-y-6">
              {/* Overview text */}
              {card.overview && (
                <div>
                  <h4 className="text-sm font-medium text-slate-400 uppercase tracking-wide mb-2">
                    Overview
                  </h4>
                  <p className="text-slate-300 leading-relaxed">{card.overview}</p>
                </div>
              )}

              {/* Strengths and Weaknesses side by side */}
              <div className="grid md:grid-cols-2 gap-6">
                {/* Strengths */}
                <div>
                  <div className="flex items-center gap-2 mb-3">
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
                    <h4 className="text-sm font-medium text-success uppercase tracking-wide">
                      Their Strengths
                    </h4>
                  </div>
                  {card.strengths.length > 0 ? (
                    <ul className="space-y-2">
                      {card.strengths.map((strength, idx) => (
                        <li
                          key={idx}
                          className="flex items-start gap-3 p-3 bg-success/5 border border-success/10 rounded-xl"
                        >
                          <span className="shrink-0 w-1.5 h-1.5 mt-2 rounded-full bg-success" />
                          <span className="text-slate-300">{strength}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-slate-500 italic">No strengths documented</p>
                  )}
                </div>

                {/* Weaknesses */}
                <div>
                  <div className="flex items-center gap-2 mb-3">
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
                    <h4 className="text-sm font-medium text-warning uppercase tracking-wide">
                      Their Weaknesses
                    </h4>
                  </div>
                  {card.weaknesses.length > 0 ? (
                    <ul className="space-y-2">
                      {card.weaknesses.map((weakness, idx) => (
                        <li
                          key={idx}
                          className="flex items-start gap-3 p-3 bg-warning/5 border border-warning/10 rounded-xl"
                        >
                          <span className="shrink-0 w-1.5 h-1.5 mt-2 rounded-full bg-warning" />
                          <span className="text-slate-300">{weakness}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-slate-500 italic">No weaknesses documented</p>
                  )}
                </div>
              </div>

              {/* Pricing */}
              {(card.pricing?.model || card.pricing?.range) && (
                <div>
                  <h4 className="text-sm font-medium text-slate-400 uppercase tracking-wide mb-3">
                    Pricing
                  </h4>
                  <div className="inline-flex items-center gap-3 px-4 py-3 bg-slate-700/50 rounded-xl">
                    <svg
                      className="w-5 h-5 text-slate-400"
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
                    <div>
                      {card.pricing.model && (
                        <span className="font-medium text-white">{card.pricing.model}</span>
                      )}
                      {card.pricing.range && (
                        <span className="text-slate-400 ml-2">{card.pricing.range}</span>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {activeTab === "differentiation" && (
            <div className="space-y-4">
              <h4 className="text-sm font-medium text-slate-400 uppercase tracking-wide mb-4">
                How We Win Against {card.competitor_name}
              </h4>
              {card.differentiation.length > 0 ? (
                <div className="space-y-3">
                  {card.differentiation.map((diff, idx) => (
                    <div
                      key={idx}
                      className="p-4 bg-primary-500/5 border border-primary-500/10 rounded-xl"
                    >
                      <div className="flex items-center gap-2 mb-2">
                        <div className="flex items-center justify-center w-6 h-6 rounded-md bg-primary-500/20">
                          <svg
                            className="w-3.5 h-3.5 text-primary-400"
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M13 10V3L4 14h7v7l9-11h-7z"
                            />
                          </svg>
                        </div>
                        <h5 className="font-medium text-primary-400">{diff.area}</h5>
                      </div>
                      <p className="text-slate-300 pl-8">{diff.our_advantage}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-slate-500 italic">
                  No differentiation points documented yet. Add areas where you have an advantage.
                </p>
              )}
            </div>
          )}

          {activeTab === "objections" && (
            <div className="space-y-4">
              <h4 className="text-sm font-medium text-slate-400 uppercase tracking-wide mb-4">
                Common Objections & Responses
              </h4>
              {card.objection_handlers.length > 0 ? (
                <div className="space-y-4">
                  {card.objection_handlers.map((handler, idx) => (
                    <div
                      key={idx}
                      className="rounded-xl border border-slate-700 overflow-hidden"
                    >
                      <div className="px-4 py-3 bg-critical/5 border-b border-slate-700">
                        <div className="flex items-start gap-3">
                          <div className="shrink-0 flex items-center justify-center w-6 h-6 rounded-md bg-critical/20 mt-0.5">
                            <svg
                              className="w-3.5 h-3.5 text-critical"
                              fill="none"
                              stroke="currentColor"
                              viewBox="0 0 24 24"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                              />
                            </svg>
                          </div>
                          <p className="text-red-300 font-medium">"{handler.objection}"</p>
                        </div>
                      </div>
                      <div className="px-4 py-3 bg-success/5">
                        <div className="flex items-start gap-3">
                          <div className="shrink-0 flex items-center justify-center w-6 h-6 rounded-md bg-success/20 mt-0.5">
                            <svg
                              className="w-3.5 h-3.5 text-success"
                              fill="none"
                              stroke="currentColor"
                              viewBox="0 0 24 24"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                              />
                            </svg>
                          </div>
                          <p className="text-emerald-300">{handler.response}</p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-slate-500 italic">
                  No objection handlers documented yet. Add common objections and your winning responses.
                </p>
              )}
            </div>
          )}

          {activeTab === "history" && (
            <div className="space-y-4">
              <h4 className="text-sm font-medium text-slate-400 uppercase tracking-wide mb-4">
                Change History
              </h4>
              {historyLoading ? (
                <div className="space-y-3">
                  {[1, 2, 3].map((i) => (
                    <div key={i} className="animate-pulse flex gap-4 p-4 bg-slate-700/30 rounded-xl">
                      <div className="w-10 h-10 bg-slate-700 rounded-lg" />
                      <div className="flex-1 space-y-2">
                        <div className="h-4 bg-slate-700 rounded w-1/3" />
                        <div className="h-3 bg-slate-700 rounded w-1/4" />
                      </div>
                    </div>
                  ))}
                </div>
              ) : history && history.length > 0 ? (
                <div className="space-y-3">
                  {history.map((change) => (
                    <div
                      key={change.id}
                      className="flex gap-4 p-4 bg-slate-700/30 rounded-xl"
                    >
                      <div className="shrink-0 flex items-center justify-center w-10 h-10 bg-slate-700 rounded-lg">
                        <svg
                          className="w-5 h-5 text-slate-400"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
                          />
                        </svg>
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-white font-medium">
                          {change.field_name.replace(/_/g, " ")} updated
                        </p>
                        <p className="text-sm text-slate-400 mt-0.5">
                          {formatDate(change.detected_at)}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-slate-500 italic">No changes recorded yet.</p>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="shrink-0 flex items-center justify-between px-6 py-4 border-t border-slate-700 bg-slate-800/50">
          <span className="text-sm text-slate-500">
            Last updated {formatDate(card.last_updated)}
          </span>
          <span
            className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium ${
              card.update_source === "auto"
                ? "bg-primary-500/10 text-primary-400"
                : "bg-slate-600/50 text-slate-400"
            }`}
          >
            {card.update_source === "auto" ? "Auto-updated by Scout" : "Manually updated"}
          </span>
        </div>
      </div>
    </div>
  );
}
