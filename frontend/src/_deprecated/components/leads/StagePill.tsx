import type { LifecycleStage } from "@/api/leads";

interface StagePillProps {
  stage: LifecycleStage;
  size?: "sm" | "md" | "lg";
}

export function StagePill({ stage, size = "md" }: StagePillProps) {
  const stageConfig: Record<LifecycleStage, { bg: string; text: string; border: string }> = {
    lead: { bg: "bg-slate-500/10", text: "text-slate-300", border: "border-slate-500/20" },
    opportunity: { bg: "bg-primary-500/10", text: "text-primary-400", border: "border-primary-500/20" },
    account: { bg: "bg-accent-500/10", text: "text-accent-400", border: "border-accent-500/20" },
  };

  const config = stageConfig[stage];
  const sizeClasses = {
    sm: "px-2 py-0.5 text-[10px]",
    md: "px-2.5 py-1 text-xs",
    lg: "px-3 py-1.5 text-sm",
  };

  return (
    <span className={`inline-flex items-center ${sizeClasses[size]} rounded-full font-medium capitalize ${config.bg} ${config.text} ${config.border} border`}>
      {stage}
    </span>
  );
}
