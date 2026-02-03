import { ChevronDown } from "lucide-react";
import { type ReactNode, useState } from "react";

interface CollapsibleSectionProps {
  title: string;
  icon?: ReactNode;
  badge?: string | number;
  badgeColor?: "primary" | "amber" | "red" | "green" | "slate";
  defaultExpanded?: boolean;
  children: ReactNode;
}

const badgeColors = {
  primary: "bg-primary-500/20 text-primary-400",
  amber: "bg-amber-500/20 text-amber-400",
  red: "bg-red-500/20 text-red-400",
  green: "bg-green-500/20 text-green-400",
  slate: "bg-slate-600/50 text-slate-400",
};

export function CollapsibleSection({
  title,
  icon,
  badge,
  badgeColor = "slate",
  defaultExpanded = true,
  children,
}: CollapsibleSectionProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  return (
    <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl overflow-hidden">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between p-4 hover:bg-slate-800/80 transition-colors"
      >
        <div className="flex items-center gap-3">
          {icon && <span className="text-slate-400">{icon}</span>}
          <h3 className="text-base font-semibold text-white">{title}</h3>
          {badge !== undefined && (
            <span
              className={`px-2 py-0.5 text-xs font-medium rounded-full ${badgeColors[badgeColor]}`}
            >
              {badge}
            </span>
          )}
        </div>
        <ChevronDown
          className={`w-5 h-5 text-slate-400 transition-transform duration-200 ${
            isExpanded ? "rotate-180" : ""
          }`}
        />
      </button>
      <div
        className={`transition-all duration-200 ease-in-out ${
          isExpanded ? "max-h-[2000px] opacity-100" : "max-h-0 opacity-0"
        } overflow-hidden`}
      >
        <div className="px-4 pb-4">{children}</div>
      </div>
    </div>
  );
}
