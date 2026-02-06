import {
  Radar,
  Search,
  Target,
  Settings,
  PenTool,
  CheckCircle2,
  Loader2,
} from "lucide-react";
import { useActivationStatus } from "@/hooks/useActivationStatus";

const AGENT_META: Record<
  string,
  { label: string; icon: typeof Radar; color: string }
> = {
  scout: { label: "Scout", icon: Radar, color: "#7B8EAA" },
  analyst: { label: "Analyst", icon: Search, color: "#8B9DC3" },
  hunter: { label: "Hunter", icon: Target, color: "#A3856E" },
  operator: { label: "Operator", icon: Settings, color: "#7A9B8E" },
  scribe: { label: "Scribe", icon: PenTool, color: "#9B8EA3" },
};

function StatusIndicator({ status }: { status: string }) {
  if (status === "complete") {
    return <CheckCircle2 size={16} strokeWidth={1.5} className="text-emerald-400" />;
  }
  if (status === "failed") {
    return (
      <span className="inline-block w-2 h-2 rounded-full bg-red-400" />
    );
  }
  // pending or running
  return (
    <Loader2
      size={16}
      strokeWidth={1.5}
      className="text-[#7B8EAA] animate-spin"
      style={{ animationDuration: "3s" }}
    />
  );
}

export function AgentActivationStatus() {
  const { data, isLoading } = useActivationStatus();

  if (isLoading || !data || data.activations.length === 0) {
    return null;
  }

  const allComplete = data.status === "complete";

  return (
    <div className="rounded-lg border border-[#2A2A2E] bg-[#161B2E]/80 overflow-hidden">
      {/* Header */}
      <div className="px-5 py-4 border-b border-[#2A2A2E] flex items-center gap-3">
        <div className="relative">
          <div
            className="w-2 h-2 rounded-full"
            style={{
              backgroundColor: allComplete ? "#4ade80" : "#7B8EAA",
            }}
          />
          {!allComplete && (
            <div
              className="absolute inset-0 w-2 h-2 rounded-full aria-breathe"
              style={{ backgroundColor: "#7B8EAA" }}
            />
          )}
        </div>
        <h3
          className="text-[#E8E6E1] text-sm tracking-wide"
          style={{ fontFamily: "'Satoshi', sans-serif", fontWeight: 500 }}
        >
          {allComplete
            ? "ARIA has completed initial tasks"
            : "ARIA is getting to work\u2026"}
        </h3>
      </div>

      {/* Agent Cards */}
      <div className="divide-y divide-[#2A2A2E]/60">
        {data.activations.map((activation, i) => {
          const meta = AGENT_META[activation.agent] || {
            label: activation.agent,
            icon: Settings,
            color: "#7B8EAA",
          };
          const Icon = meta.icon;

          return (
            <div
              key={activation.goal_id}
              className="px-5 py-3.5 flex items-start gap-3 transition-colors hover:bg-[#1A2036]/50"
              style={{
                animationDelay: `${i * 120}ms`,
              }}
            >
              {/* Agent Icon */}
              <div
                className="mt-0.5 flex-shrink-0 w-8 h-8 rounded-md flex items-center justify-center"
                style={{ backgroundColor: `${meta.color}18` }}
              >
                <Icon
                  size={16}
                  strokeWidth={1.5}
                  style={{ color: meta.color }}
                />
              </div>

              {/* Task Info */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span
                    className="text-[#E8E6E1] text-sm"
                    style={{
                      fontFamily: "'Satoshi', sans-serif",
                      fontWeight: 500,
                    }}
                  >
                    {meta.label}
                  </span>
                  <span
                    className="text-[10px] px-1.5 py-0.5 rounded-full text-[#7B8EAA] border border-[#2A2A2E]"
                    style={{
                      fontFamily: "'JetBrains Mono', monospace",
                      letterSpacing: "0.05em",
                    }}
                  >
                    {activation.status === "complete"
                      ? "Done"
                      : activation.status === "running"
                        ? "Working"
                        : "Queued"}
                  </span>
                </div>
                <p
                  className="text-[#7B8EAA] text-xs mt-0.5 leading-relaxed line-clamp-2"
                  style={{ fontFamily: "'Satoshi', sans-serif" }}
                >
                  {activation.task}
                </p>
              </div>

              {/* Status */}
              <div className="flex-shrink-0 mt-1">
                <StatusIndicator status={activation.status} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
