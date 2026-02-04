import type { LeadStatus } from "@/api/leads";

interface StatusIndicatorProps {
  status: LeadStatus;
  showLabel?: boolean;
}

export function StatusIndicator({ status, showLabel = true }: StatusIndicatorProps) {
  const statusConfig: Record<LeadStatus, { color: string; label: string }> = {
    active: { color: "text-emerald-400", label: "Active" },
    won: { color: "text-primary-400", label: "Won" },
    lost: { color: "text-red-400", label: "Lost" },
    dormant: { color: "text-slate-500", label: "Dormant" },
  };

  const config = statusConfig[status];

  return (
    <span className={`text-xs font-medium capitalize ${config.color}`}>
      {showLabel ? config.label : status}
    </span>
  );
}
