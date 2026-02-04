interface HealthScoreBadgeProps {
  score: number;
  size?: "sm" | "md" | "lg";
  showLabel?: boolean;
}

export function HealthScoreBadge({ score, size = "md", showLabel = true }: HealthScoreBadgeProps) {
  const getHealthConfig = (score: number) => {
    if (score >= 70) {
      return {
        indicator: "bg-emerald-500",
        bg: "bg-emerald-500/10",
        border: "border-emerald-500/20",
        text: "text-emerald-400",
        glow: "shadow-emerald-500/20",
        label: "Healthy",
      };
    }
    if (score >= 40) {
      return {
        indicator: "bg-amber-500",
        bg: "bg-amber-500/10",
        border: "border-amber-500/20",
        text: "text-amber-400",
        glow: "shadow-amber-500/20",
        label: "Attention",
      };
    }
    return {
      indicator: "bg-red-500",
      bg: "bg-red-500/10",
      border: "border-red-500/20",
      text: "text-red-400",
      glow: "shadow-red-500/20",
      label: "At Risk",
    };
  };

  const config = getHealthConfig(score);

  const sizeClasses = {
    sm: { container: "px-2 py-0.5 gap-1", indicator: "w-1.5 h-1.5", score: "text-xs", label: "text-[10px]" },
    md: { container: "px-2.5 py-1 gap-1.5", indicator: "w-2 h-2", score: "text-sm", label: "text-xs" },
    lg: { container: "px-3 py-1.5 gap-2", indicator: "w-2.5 h-2.5", score: "text-base", label: "text-xs" },
  };

  const s = sizeClasses[size];

  return (
    <div className={`inline-flex items-center ${s.container} rounded-full ${config.bg} ${config.border} border shadow-sm ${config.glow}`}>
      <span className={`${s.indicator} rounded-full ${config.indicator} animate-pulse`} />
      <span className={`font-semibold ${s.score} ${config.text}`}>{score}</span>
      {showLabel && <span className={`${s.label} ${config.text} opacity-80`}>{config.label}</span>}
    </div>
  );
}
