import { useState } from "react";
import { DashboardLayout } from "@/components/DashboardLayout";
import { ICPBuilder } from "@/components/leads/ICPBuilder";
import { Target, ListChecks, BarChart3 } from "lucide-react";

type Tab = "icp" | "review" | "pipeline";

export function LeadGenPage() {
  const [activeTab, setActiveTab] = useState<Tab>("icp");

  const tabs = [
    { id: "icp" as const, label: "ICP Builder", icon: Target },
    { id: "review" as const, label: "Review Queue", icon: ListChecks },
    { id: "pipeline" as const, label: "Pipeline", icon: BarChart3 },
  ];

  return (
    <DashboardLayout>
      <div className="relative min-h-screen">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-800 via-slate-900 to-slate-900 pointer-events-none" />
        <div className="relative max-w-7xl mx-auto px-4 py-8 lg:px-8">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-white font-display">Lead Generation</h1>
            <p className="text-slate-400 mt-1">Build your ICP, discover leads, and manage your pipeline</p>
          </div>

          {/* Tabs */}
          <div className="flex gap-2 mb-8">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-2 px-4 py-2.5 rounded-lg border text-sm font-medium transition-all ${
                    isActive
                      ? "bg-primary-600/20 border-primary-500/50 text-primary-300"
                      : "bg-slate-800/50 border-slate-700/50 text-slate-400 hover:text-slate-300 hover:border-slate-600/50"
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  {tab.label}
                </button>
              );
            })}
          </div>

          {/* Tab Content */}
          {activeTab === "icp" && <ICPBuilder />}
          {activeTab === "review" && (
            <div className="text-slate-400 text-center py-16">Review Queue — coming soon</div>
          )}
          {activeTab === "pipeline" && (
            <div className="text-slate-400 text-center py-16">Pipeline View — coming soon</div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
