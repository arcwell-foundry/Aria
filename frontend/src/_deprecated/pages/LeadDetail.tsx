import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  Activity,
  ArrowLeft,
  Building2,
  Lightbulb,
  MessageSquarePlus,
  RefreshCw,
  Users,
} from "lucide-react";
import { DashboardLayout } from "@/components/DashboardLayout";
import {
  HealthScoreBadge,
  StagePill,
  StatusIndicator,
} from "@/components/leads";
import {
  ActivityTab,
  AddEventModal,
  EditStakeholderModal,
  InsightsTab,
  StageTransitionModal,
  StakeholdersTab,
  TimelineTab,
} from "@/components/leads/detail";
import {
  useLead,
  useLeadTimeline,
  useLeadStakeholders,
  useLeadInsights,
  useAddEvent,
  useUpdateStakeholder,
  useTransitionStage,
} from "@/hooks/useLeads";
import type { LeadEvent, Stakeholder, StakeholderUpdate, StageTransition } from "@/api/leads";

// Tab type definition
type Tab = "timeline" | "stakeholders" | "insights" | "activity";

// Tab configuration
const tabs: { id: Tab; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { id: "timeline", label: "Timeline", icon: Activity },
  { id: "stakeholders", label: "Stakeholders", icon: Users },
  { id: "insights", label: "Insights", icon: Lightbulb },
  { id: "activity", label: "Activity", icon: Activity },
];

// Loading skeleton for the detail page
function LeadDetailSkeleton() {
  return (
    <DashboardLayout>
      <div className="p-6 lg:p-8 animate-pulse">
        {/* Back link skeleton */}
        <div className="mb-6">
          <div className="h-5 w-32 bg-slate-700 rounded" />
        </div>

        {/* Header skeleton */}
        <div className="mb-8">
          <div className="flex items-start gap-4 mb-4">
            <div className="w-16 h-16 bg-slate-700 rounded-xl" />
            <div className="flex-1">
              <div className="h-8 w-64 bg-slate-700 rounded mb-3" />
              <div className="flex items-center gap-3">
                <div className="h-6 w-24 bg-slate-700 rounded-full" />
                <div className="h-6 w-20 bg-slate-700 rounded-full" />
                <div className="h-5 w-16 bg-slate-700 rounded" />
              </div>
            </div>
            <div className="flex gap-3">
              <div className="h-10 w-28 bg-slate-700 rounded-lg" />
              <div className="h-10 w-36 bg-slate-700 rounded-lg" />
            </div>
          </div>
        </div>

        {/* Tab navigation skeleton */}
        <div className="flex gap-2 mb-6 border-b border-slate-700/50 pb-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-10 w-28 bg-slate-700 rounded-lg" />
          ))}
        </div>

        {/* Content skeleton */}
        <div className="space-y-4">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-24 bg-slate-700/50 rounded-xl" />
          ))}
        </div>
      </div>
    </DashboardLayout>
  );
}

// Not found component
function NotFound() {
  return (
    <DashboardLayout>
      <div className="flex flex-col items-center justify-center min-h-[60vh] p-6">
        <div className="w-20 h-20 bg-slate-800/50 rounded-2xl flex items-center justify-center mb-6 border border-slate-700/50">
          <Building2 className="w-10 h-10 text-slate-500" />
        </div>
        <h1 className="text-2xl font-bold text-white mb-2">Lead Not Found</h1>
        <p className="text-slate-400 text-center max-w-md mb-6">
          The lead you are looking for does not exist or has been removed.
        </p>
        <Link
          to="/dashboard/leads"
          className="inline-flex items-center gap-2 px-4 py-2.5 bg-primary-600 hover:bg-primary-500 text-white font-medium rounded-lg transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Leads
        </Link>
      </div>
    </DashboardLayout>
  );
}

export function LeadDetailPage() {
  const { id } = useParams<{ id: string }>();

  // State management
  const [activeTab, setActiveTab] = useState<Tab>("timeline");
  const [showAddEvent, setShowAddEvent] = useState(false);
  const [showTransition, setShowTransition] = useState(false);
  const [editingStakeholder, setEditingStakeholder] = useState<Stakeholder | null>(null);

  // Data queries
  const { data: lead, isLoading: leadLoading, error: leadError } = useLead(id || "");
  const { data: timeline = [], isLoading: timelineLoading } = useLeadTimeline(id || "");
  const { data: stakeholders = [], isLoading: stakeholdersLoading } = useLeadStakeholders(id || "");
  const { data: insights = [], isLoading: insightsLoading } = useLeadInsights(id || "");

  // Mutations
  const addEventMutation = useAddEvent();
  const updateStakeholderMutation = useUpdateStakeholder();
  const transitionStageMutation = useTransitionStage();

  // Event handlers
  const handleAddEvent = (event: Omit<LeadEvent, "id" | "lead_memory_id" | "created_at">) => {
    if (!id) return;
    addEventMutation.mutate(
      { leadId: id, event },
      {
        onSuccess: () => {
          setShowAddEvent(false);
        },
      }
    );
  };

  const handleUpdateStakeholder = (updates: StakeholderUpdate) => {
    if (!id || !editingStakeholder) return;
    updateStakeholderMutation.mutate(
      { leadId: id, stakeholderId: editingStakeholder.id, updates },
      {
        onSuccess: () => {
          setEditingStakeholder(null);
        },
      }
    );
  };

  const handleTransitionStage = (transition: StageTransition) => {
    if (!id) return;
    transitionStageMutation.mutate(
      { leadId: id, transition },
      {
        onSuccess: () => {
          setShowTransition(false);
        },
      }
    );
  };

  // Loading state
  if (leadLoading) {
    return <LeadDetailSkeleton />;
  }

  // Error or not found state
  if (leadError || !lead) {
    return <NotFound />;
  }

  // Render active tab content
  const renderTabContent = () => {
    switch (activeTab) {
      case "timeline":
        return <TimelineTab events={timeline} isLoading={timelineLoading} />;
      case "stakeholders":
        return (
          <StakeholdersTab
            stakeholders={stakeholders}
            isLoading={stakeholdersLoading}
            onEdit={setEditingStakeholder}
          />
        );
      case "insights":
        return <InsightsTab insights={insights} isLoading={insightsLoading} />;
      case "activity":
        return <ActivityTab events={timeline} isLoading={timelineLoading} />;
      default:
        return null;
    }
  };

  return (
    <DashboardLayout>
      <div className="p-6 lg:p-8">
        {/* Back navigation */}
        <div className="mb-6">
          <Link
            to="/dashboard/leads"
            className="inline-flex items-center gap-2 text-sm text-slate-400 hover:text-white transition-colors group"
          >
            <ArrowLeft className="w-4 h-4 transition-transform group-hover:-translate-x-1" />
            Back to Leads
          </Link>
        </div>

        {/* Header section */}
        <div className="mb-8">
          <div className="flex flex-col lg:flex-row lg:items-start gap-4 lg:gap-6">
            {/* Company icon and name */}
            <div className="flex items-start gap-4 flex-1">
              <div className="w-14 h-14 lg:w-16 lg:h-16 bg-gradient-to-br from-slate-700 to-slate-800 rounded-xl flex items-center justify-center border border-slate-600/50 shrink-0">
                <Building2 className="w-7 h-7 lg:w-8 lg:h-8 text-slate-400" />
              </div>
              <div className="min-w-0 flex-1">
                <h1 className="text-2xl lg:text-3xl font-bold text-white mb-2 truncate">
                  {lead.company_name}
                </h1>
                <div className="flex flex-wrap items-center gap-3">
                  <HealthScoreBadge score={lead.health_score} size="md" />
                  <StagePill stage={lead.lifecycle_stage} size="md" />
                  <StatusIndicator status={lead.status} />
                </div>
              </div>
            </div>

            {/* Action buttons */}
            <div className="flex gap-3 shrink-0">
              <button
                onClick={() => setShowAddEvent(true)}
                className="inline-flex items-center gap-2 px-4 py-2.5 bg-slate-700 hover:bg-slate-600 text-white font-medium rounded-lg transition-colors"
              >
                <MessageSquarePlus className="w-4 h-4" />
                Add Event
              </button>
              <button
                onClick={() => setShowTransition(true)}
                className="inline-flex items-center gap-2 px-4 py-2.5 bg-primary-600 hover:bg-primary-500 text-white font-medium rounded-lg transition-colors shadow-lg shadow-primary-600/25"
              >
                <RefreshCw className="w-4 h-4" />
                Transition Stage
              </button>
            </div>
          </div>
        </div>

        {/* Tab navigation */}
        <div className="mb-6 border-b border-slate-700/50">
          <nav className="flex gap-1 -mb-px overflow-x-auto scrollbar-hide">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`inline-flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
                    isActive
                      ? "border-primary-500 text-primary-400"
                      : "border-transparent text-slate-400 hover:text-white hover:border-slate-600"
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  {tab.label}
                </button>
              );
            })}
          </nav>
        </div>

        {/* Tab content */}
        <div className="min-h-[400px]">{renderTabContent()}</div>

        {/* Modals */}
        <AddEventModal
          leadId={id || ""}
          companyName={lead.company_name}
          isOpen={showAddEvent}
          onClose={() => setShowAddEvent(false)}
          onSubmit={handleAddEvent}
          isLoading={addEventMutation.isPending}
        />

        <StageTransitionModal
          currentStage={lead.lifecycle_stage}
          companyName={lead.company_name}
          isOpen={showTransition}
          onClose={() => setShowTransition(false)}
          onSubmit={handleTransitionStage}
          isLoading={transitionStageMutation.isPending}
        />

        <EditStakeholderModal
          stakeholder={editingStakeholder}
          isOpen={editingStakeholder !== null}
          onClose={() => setEditingStakeholder(null)}
          onSubmit={handleUpdateStakeholder}
          isLoading={updateStakeholderMutation.isPending}
        />
      </div>
    </DashboardLayout>
  );
}
