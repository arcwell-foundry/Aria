import { useState } from "react";
import { DashboardLayout } from "@/components/DashboardLayout";
import { AgentActivationStatus } from "@/components/AgentActivationStatus";
import { HelpTooltip } from "@/components/HelpTooltip";
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
          <div className="flex items-center gap-2 mb-2">
            <h1 className="text-2xl font-bold text-white">Dashboard</h1>
            <HelpTooltip content="Your daily briefing from ARIA with key insights, tasks, and signals. Refreshes each morning." placement="right" />
          </div>
          <BriefingHeader
            userName={user?.full_name ?? undefined}
            generatedAt={briefing?.generated_at}
            onRefresh={handleRefresh}
            onViewHistory={handleViewHistory}
            isRefreshing={regenerateMutation.isPending}
          />

          {/* Historical indicator */}
          {selectedDate && (
            <div className="mt-4 flex items-center gap-2 px-4 py-2 bg-warning/10 border border-warning/30 rounded-lg">
              <span className="text-warning text-sm">
                Viewing briefing from{" "}
                {new Date(selectedDate).toLocaleDateString("en-US", {
                  weekday: "long",
                  month: "long",
                  day: "numeric",
                })}
              </span>
              <button
                onClick={() => setSelectedDate(null)}
                className="ml-auto text-xs text-warning hover:text-warning underline"
              >
                Return to today
              </button>
            </div>
          )}

          {/* Agent Activation Status (US-915) */}
          <div className="mt-6">
            <AgentActivationStatus />
          </div>

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
