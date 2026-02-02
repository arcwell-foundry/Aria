import type { GoalType } from "@/api/goals";

interface GoalTypeBadgeProps {
  type: GoalType;
  size?: "sm" | "md";
}

const typeConfig: Record<GoalType, { label: string; color: string; icon: string }> = {
  lead_gen: {
    label: "Lead Gen",
    color: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
    icon: "M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z M15 11a3 3 0 11-6 0 3 3 0 016 0z",
  },
  research: {
    label: "Research",
    color: "bg-blue-500/20 text-blue-400 border-blue-500/30",
    icon: "M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01",
  },
  outreach: {
    label: "Outreach",
    color: "bg-violet-500/20 text-violet-400 border-violet-500/30",
    icon: "M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z",
  },
  analysis: {
    label: "Analysis",
    color: "bg-amber-500/20 text-amber-400 border-amber-500/30",
    icon: "M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z",
  },
  custom: {
    label: "Custom",
    color: "bg-slate-500/20 text-slate-400 border-slate-500/30",
    icon: "M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4",
  },
};

export function GoalTypeBadge({ type, size = "md" }: GoalTypeBadgeProps) {
  const config = typeConfig[type];
  const sizeClasses = size === "sm" ? "px-2 py-0.5 text-xs" : "px-2.5 py-1 text-sm";

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border font-medium ${config.color} ${sizeClasses}`}
    >
      <svg
        className={size === "sm" ? "w-3 h-3" : "w-3.5 h-3.5"}
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d={config.icon}
        />
      </svg>
      {config.label}
    </span>
  );
}
