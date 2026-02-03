import { X, Calendar } from "lucide-react";
import { useEffect } from "react";
import { useBriefingList } from "@/hooks/useBriefing";

interface BriefingHistoryModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectDate: (date: string) => void;
}

export function BriefingHistoryModal({
  isOpen,
  onClose,
  onSelectDate,
}: BriefingHistoryModalProps) {
  const { data: briefings, isLoading } = useBriefingList(14);

  // Handle Escape key to close modal
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    if (isOpen) {
      document.addEventListener("keydown", handleEscape);
      return () => document.removeEventListener("keydown", handleEscape);
    }
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-slate-900/80 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-md bg-slate-800 border border-slate-700 rounded-xl shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-700">
          <h2 className="text-lg font-semibold text-white">Past Briefings</h2>
          <button
            onClick={onClose}
            className="p-2 text-slate-400 hover:text-white hover:bg-slate-700 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-4 max-h-96 overflow-y-auto">
          {isLoading ? (
            <div className="space-y-3">
              {[1, 2, 3, 4, 5].map((i) => (
                <div
                  key={i}
                  className="h-14 bg-slate-700/50 rounded-lg animate-pulse"
                />
              ))}
            </div>
          ) : briefings && briefings.length > 0 ? (
            <div className="space-y-2">
              {briefings.map((briefing) => {
                // Parse date with timezone safety (compare date strings directly)
                const today = new Date().toISOString().split("T")[0];
                const isToday = briefing.briefing_date === today;
                const date = new Date(briefing.briefing_date + "T12:00:00");

                return (
                  <button
                    key={briefing.id}
                    onClick={() => {
                      onSelectDate(briefing.briefing_date);
                      onClose();
                    }}
                    className="w-full flex items-center gap-3 p-3 bg-slate-700/30 hover:bg-slate-700/50 border border-slate-600/30 rounded-lg transition-colors text-left"
                  >
                    <div className="flex-shrink-0 p-2 bg-slate-600/50 rounded-lg">
                      <Calendar className="w-4 h-4 text-slate-400" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <h4 className="text-white font-medium">
                        {date.toLocaleDateString("en-US", {
                          weekday: "long",
                          month: "short",
                          day: "numeric",
                        })}
                        {isToday && (
                          <span className="ml-2 text-xs text-primary-400">
                            Today
                          </span>
                        )}
                      </h4>
                      <p className="text-sm text-slate-400 truncate">
                        {briefing.content.summary?.slice(0, 60)}...
                      </p>
                    </div>
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="text-center py-8 text-slate-400">
              <Calendar className="w-12 h-12 mx-auto mb-3 opacity-50" />
              <p>No past briefings found</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-3 p-4 border-t border-slate-700">
          <button
            onClick={onClose}
            className="px-4 py-2 text-slate-300 hover:text-white hover:bg-slate-700 rounded-lg transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
