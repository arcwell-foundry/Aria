import type { GoalStatus } from "@/api/goals";

interface GoalStatusBadgeProps {
  status: GoalStatus;
  size?: "sm" | "md";
}

const statusConfig: Record<GoalStatus, { label: string; color: string; pulse?: boolean }> = {
  draft: {
    label: "Draft",
    color: "bg-slate-500/20 text-slate-400 border-slate-500/30",
  },
  active: {
    label: "Active",
    color: "bg-green-500/20 text-green-400 border-green-500/30",
    pulse: true,
  },
  paused: {
    label: "Paused",
    color: "bg-warning/20 text-warning border-warning/30",
  },
  complete: {
    label: "Complete",
    color: "bg-primary-500/20 text-primary-400 border-primary-500/30",
  },
  failed: {
    label: "Failed",
    color: "bg-critical/20 text-critical border-critical/30",
  },
};

export function GoalStatusBadge({ status, size = "md" }: GoalStatusBadgeProps) {
  const config = statusConfig[status];
  const sizeClasses = size === "sm" ? "px-2 py-0.5 text-xs" : "px-2.5 py-1 text-sm";

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border font-medium ${config.color} ${sizeClasses}`}
    >
      {config.pulse && (
        <span className="relative flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
          <span className="relative inline-flex rounded-full h-2 w-2 bg-green-400" />
        </span>
      )}
      {config.label}
    </span>
  );
}
