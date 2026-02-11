import { useCallback } from "react";
import { useParams } from "react-router-dom";
import { DashboardLayout } from "@/components/DashboardLayout";
import {
  AgendaSection,
  AttendeesSection,
  BriefNotesSection,
  BriefSummary,
  CompanySection,
  GeneratingOverlay,
  MeetingBriefEmpty,
  MeetingBriefHeader,
  MeetingBriefSkeleton,
  RisksOpportunitiesSection,
} from "@/components/meetingBrief";
import { useMeetingBrief, useGenerateMeetingBrief } from "@/hooks/useMeetingBrief";
import type { MeetingBriefContent } from "@/api/meetingBriefs";
import { HelpTooltip } from "@/components/HelpTooltip";

function isBriefContentPopulated(content: MeetingBriefContent | Record<string, never>): content is MeetingBriefContent {
  return "summary" in content && typeof content.summary === "string" && content.summary.length > 0;
}

export function MeetingBriefPage() {
  const { id: calendarEventId } = useParams<{ id: string }>();
  const { data: brief, isLoading, error } = useMeetingBrief(calendarEventId || "");
  const generateBrief = useGenerateMeetingBrief();

  const handleGenerate = useCallback(() => {
    if (!calendarEventId || !brief) return;

    generateBrief.mutate({
      calendarEventId,
      request: {
        meeting_title: brief.meeting_title,
        meeting_time: brief.meeting_time,
        attendee_emails: [], // Backend will use existing attendees
      },
    });
  }, [calendarEventId, brief, generateBrief]);

  const handleRefresh = useCallback(() => {
    handleGenerate();
  }, [handleGenerate]);

  const handlePrint = useCallback(() => {
    window.print();
  }, []);

  if (!calendarEventId) {
    return (
      <DashboardLayout>
        <div className="p-4 lg:p-8">
          <div className="max-w-4xl mx-auto text-center py-16">
            <p className="text-slate-400">No meeting ID provided</p>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="p-4 lg:p-8">
        <div className="max-w-4xl mx-auto">
          <div className="flex items-center gap-2 mb-4">
            <h1 className="text-2xl font-bold text-white">Meeting Brief</h1>
            <HelpTooltip content="Pre-meeting preparation briefs. ARIA researches attendees and suggests talking points." placement="right" />
          </div>
          {isLoading ? (
            <MeetingBriefSkeleton />
          ) : error ? (
            <MeetingBriefEmpty
              onGenerate={handleGenerate}
              isGenerating={generateBrief.isPending}
            />
          ) : brief ? (
            <>
              {/* Header */}
              <MeetingBriefHeader
                meetingTitle={brief.meeting_title}
                meetingTime={brief.meeting_time}
                status={brief.status}
                generatedAt={brief.generated_at}
                onRefresh={handleRefresh}
                onPrint={handlePrint}
                isRefreshing={generateBrief.isPending}
              />

              {/* Content */}
              <div className="mt-6 space-y-6">
                {brief.status === "generating" || brief.status === "pending" ? (
                  <GeneratingOverlay />
                ) : brief.status === "failed" ? (
                  <div className="text-center py-12">
                    <p className="text-critical mb-2">Failed to generate brief</p>
                    {brief.error_message && (
                      <p className="text-sm text-slate-400 mb-4">{brief.error_message}</p>
                    )}
                    <button
                      onClick={handleRefresh}
                      disabled={generateBrief.isPending}
                      className="px-4 py-2 bg-primary-600 hover:bg-primary-500 disabled:opacity-60 text-white font-medium rounded-lg transition-colors"
                    >
                      Try again
                    </button>
                  </div>
                ) : isBriefContentPopulated(brief.brief_content) ? (
                  <>
                    <BriefSummary summary={brief.brief_content.summary} />
                    <div className="space-y-4">
                      <AttendeesSection attendees={brief.brief_content.attendees} />
                      <CompanySection company={brief.brief_content.company} />
                      <AgendaSection agenda={brief.brief_content.suggested_agenda} />
                      <RisksOpportunitiesSection items={brief.brief_content.risks_opportunities} />
                      <BriefNotesSection />
                    </div>
                  </>
                ) : (
                  <MeetingBriefEmpty
                    meetingTitle={brief.meeting_title}
                    onGenerate={handleGenerate}
                    isGenerating={generateBrief.isPending}
                  />
                )}
              </div>
            </>
          ) : (
            <MeetingBriefEmpty
              onGenerate={handleGenerate}
              isGenerating={generateBrief.isPending}
            />
          )}
        </div>
      </div>

      {/* Print styles */}
      <style>{`
        @media print {
          nav, button, [data-print-hide] {
            display: none !important;
          }
          body {
            background: white !important;
          }
          .bg-slate-800, .bg-slate-700, .bg-slate-900 {
            background: white !important;
            border-color: #e5e7eb !important;
          }
          .text-white, .text-slate-200, .text-slate-300 {
            color: black !important;
          }
          .text-slate-400 {
            color: #6b7280 !important;
          }
        }
      `}</style>
    </DashboardLayout>
  );
}
