interface StyleMatchIndicatorProps {
  score: number; // 0-1 scale
  size?: "sm" | "md" | "lg";
  showLabel?: boolean;
}

export function StyleMatchIndicator({ score, size = "md", showLabel = true }: StyleMatchIndicatorProps) {
  const percentage = Math.round(score * 100);

  const sizeConfig = {
    sm: { ring: 28, stroke: 3, text: "text-[10px]", label: "text-xs" },
    md: { ring: 40, stroke: 4, text: "text-xs", label: "text-sm" },
    lg: { ring: 56, stroke: 5, text: "text-sm", label: "text-base" },
  };

  const config = sizeConfig[size];
  const radius = (config.ring - config.stroke) / 2;
  const circumference = radius * 2 * Math.PI;
  const offset = circumference - (score * circumference);

  // Color based on score
  const getColor = () => {
    if (percentage >= 80) return { stroke: "stroke-success", text: "text-success", bg: "bg-success/10" };
    if (percentage >= 60) return { stroke: "stroke-primary-500", text: "text-primary-400", bg: "bg-primary-500/10" };
    if (percentage >= 40) return { stroke: "stroke-warning", text: "text-warning", bg: "bg-warning/10" };
    return { stroke: "stroke-critical", text: "text-critical", bg: "bg-critical/10" };
  };

  const colors = getColor();

  return (
    <div className="flex items-center gap-2">
      <div className={`relative ${colors.bg} rounded-full p-1`}>
        <svg
          width={config.ring}
          height={config.ring}
          className="transform -rotate-90"
        >
          {/* Background ring */}
          <circle
            cx={config.ring / 2}
            cy={config.ring / 2}
            r={radius}
            stroke="currentColor"
            strokeWidth={config.stroke}
            fill="none"
            className="text-slate-700/50"
          />
          {/* Progress ring */}
          <circle
            cx={config.ring / 2}
            cy={config.ring / 2}
            r={radius}
            strokeWidth={config.stroke}
            fill="none"
            strokeLinecap="round"
            className={`${colors.stroke} transition-all duration-500 ease-out`}
            style={{
              strokeDasharray: circumference,
              strokeDashoffset: offset,
            }}
          />
        </svg>
        {/* Percentage text */}
        <span className={`absolute inset-0 flex items-center justify-center font-semibold ${colors.text} ${config.text}`}>
          {percentage}
        </span>
      </div>

      {showLabel && (
        <span className={`${config.label} text-slate-400`}>Style Match</span>
      )}
    </div>
  );
}
