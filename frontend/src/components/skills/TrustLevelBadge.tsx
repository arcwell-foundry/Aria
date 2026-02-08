import type { TrustLevel } from "@/api/skills";

interface TrustLevelBadgeProps {
  level: TrustLevel;
  size?: "sm" | "md";
}

const trustConfig: Record<
  TrustLevel,
  { label: string; color: string; icon: string }
> = {
  core: {
    label: "Core",
    color: "bg-primary-500/20 text-primary-400 border-primary-500/30",
    icon: "M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z",
  },
  verified: {
    label: "Verified",
    color: "bg-success/20 text-success border-success/30",
    icon: "M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z",
  },
  community: {
    label: "Community",
    color: "bg-warning/20 text-warning border-warning/30",
    icon: "M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z",
  },
  user: {
    label: "User",
    color: "bg-slate-500/20 text-slate-400 border-slate-500/30",
    icon: "M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z",
  },
};

export function TrustLevelBadge({ level, size = "md" }: TrustLevelBadgeProps) {
  const config = trustConfig[level];
  const sizeClasses =
    size === "sm" ? "px-2 py-0.5 text-xs" : "px-2.5 py-1 text-sm";

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
