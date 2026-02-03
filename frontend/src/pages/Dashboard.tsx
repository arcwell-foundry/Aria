import { useState } from "react";
import { DashboardLayout } from "@/components/DashboardLayout";
import {
  BriefingEmpty,
  BriefingHeader,
  BriefingHistoryModal,
  BriefingSkeleton,
  CalendarSection,
  ExecutiveSummary,
  LeadsSection,
  SignalsSection,
  TasksSection,
} from "@/components/briefing";
import { useTodayBriefing, useRegenerateBriefing, useBriefingByDate } from "@/hooks/useBriefing";
import { useAuth } from "@/hooks/useAuth";

export function DashboardPage() {
  const { user } = useAuth();
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  const {
    data: todayBriefing,
    isLoading: isTodayLoading,
    error: todayError,
  } = useTodayBriefing();

  const { data: historicalBriefing, isLoading: isHistoricalLoading, error: historicalError } =
    useBriefingByDate(selectedDate || "");

  const regenerateMutation = useRegenerateBriefing();

  // Use historical briefing if selected, otherwise today's
  const briefing = selectedDate ? historicalBriefing?.content : todayBriefing;
  const isLoading = selectedDate ? isHistoricalLoading : isTodayLoading;

  const handleRefresh = () => {
    setSelectedDate(null); // Clear historical selection
    regenerateMutation.mutate();
  };

  const handleSelectHistoricalDate = (date: string) => {
    const today = new Date().toISOString().split("T")[0];
    if (date === today) {
      setSelectedDate(null);
    } else {
      setSelectedDate(date);
    }
  };

  const handleViewHistory = () => {
    setIsHistoryOpen(true);
  };

  // Refetch on window focus
  // useEffect(() => {
  //   const handleFocus = () => {
  //     if (!selectedDate) {
  //       queryClient.invalidateQueries({ queryKey: briefingKeys.today() });
  //     }
  //   };
  //   window.addEventListener("focus", handleFocus);
  //   return () => window.removeEventListener("focus", handleFocus);
  // }, [selectedDate, queryClient]);

  return (
    <DashboardLayout>
      <div className="p-4 lg:p-8">
        <div className="max-w-4xl mx-auto">
          {/* Header */}
          <BriefingHeader
            userName={user?.full_name ?? undefined}
            generatedAt={briefing?.generated_at}
            onRefresh={handleRefresh}
            onViewHistory={handleViewHistory}
            isRefreshing={regenerateMutation.isPending}
          />

          {/* Historical indicator */}
          {selectedDate && (
            <div className="mt-4 flex items-center gap-2 px-4 py-2 bg-amber-500/10 border border-amber-500/30 rounded-lg">
              <span className="text-amber-400 text-sm">
                Viewing briefing from{" "}
                {new Date(selectedDate).toLocaleDateString("en-US", {
                  weekday: "long",
                  month: "long",
                  day: "numeric",
                })}
              </span>
              <button
                onClick={() => setSelectedDate(null)}
                className="ml-auto text-xs text-amber-400 hover:text-amber-300 underline"
              >
                Return to today
              </button>
            </div>
          )}

          {/* Content */}
          <div className="mt-6 space-y-6">
            {isLoading ? (
              <BriefingSkeleton />
            ) : historicalError && selectedDate ? (
              <div className="text-center py-12">
                <p className="text-slate-400 mb-4">
                  Could not load briefing for this date.
                </p>
                <button
                  onClick={() => setSelectedDate(null)}
                  className="text-primary-400 hover:text-primary-300 underline"
                >
                  Return to today's briefing
                </button>
              </div>
            ) : todayError && !selectedDate ? (
              <BriefingEmpty
                onGenerate={() => regenerateMutation.mutate()}
                isGenerating={regenerateMutation.isPending}
              />
            ) : briefing ? (
              <>
                {/* Executive Summary */}
                <ExecutiveSummary summary={briefing.summary} />

                {/* Collapsible Sections */}
                <div className="space-y-4">
                  <CalendarSection calendar={briefing.calendar} />
                  <LeadsSection leads={briefing.leads} />
                  <SignalsSection signals={briefing.signals} />
                  <TasksSection tasks={briefing.tasks} />
                </div>
              </>
            ) : (
              <BriefingEmpty
                onGenerate={() => regenerateMutation.mutate()}
                isGenerating={regenerateMutation.isPending}
              />
            )}
          </div>
        </div>
      </div>

      {/* History Modal */}
      <BriefingHistoryModal
        isOpen={isHistoryOpen}
        onClose={() => setIsHistoryOpen(false)}
        onSelectDate={handleSelectHistoricalDate}
      />
    </DashboardLayout>
  );
}
