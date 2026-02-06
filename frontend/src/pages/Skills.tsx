import { useState } from "react";
import { DashboardLayout } from "@/components/DashboardLayout";
import { SkillBrowser, InstalledSkills, SkillAuditLog } from "@/components/skills";

type SkillTab = "browse" | "installed" | "activity";

const tabs: { value: SkillTab; label: string; icon: string }[] = [
  {
    value: "browse",
    label: "Browse",
    icon: "M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z",
  },
  {
    value: "installed",
    label: "Installed",
    icon: "M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4",
  },
  {
    value: "activity",
    label: "Activity",
    icon: "M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2",
  },
];

export function SkillsPage() {
  const [activeTab, setActiveTab] = useState<SkillTab>("browse");

  return (
    <DashboardLayout>
      <div className="relative">
        {/* Background pattern */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-800 via-slate-900 to-slate-900 pointer-events-none" />

        <div className="relative max-w-6xl mx-auto px-4 py-8 lg:px-8">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-white">Skills</h1>
            <p className="mt-1 text-slate-400">
              Discover, install, and manage skills that extend ARIA&apos;s capabilities
            </p>
          </div>

          {/* Tab navigation */}
          <div className="flex gap-1 mb-8 bg-slate-800/50 border border-slate-700/50 rounded-xl p-1 w-fit">
            {tabs.map((tab) => (
              <button
                key={tab.value}
                onClick={() => setActiveTab(tab.value)}
                className={`inline-flex items-center gap-2 px-4 py-2.5 text-sm font-medium rounded-lg transition-all duration-200 ${
                  activeTab === tab.value
                    ? "bg-primary-600/20 text-primary-400 shadow-sm"
                    : "text-slate-400 hover:text-white hover:bg-slate-700/50"
                }`}
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
                    d={tab.icon}
                  />
                </svg>
                {tab.label}
              </button>
            ))}
          </div>

          {/* Tab content */}
          {activeTab === "browse" && <SkillBrowser />}
          {activeTab === "installed" && <InstalledSkills />}
          {activeTab === "activity" && <SkillAuditLog />}
        </div>
      </div>
    </DashboardLayout>
  );
}
