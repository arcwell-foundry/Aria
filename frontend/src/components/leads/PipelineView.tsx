import { BarChart3, DollarSign, TrendingUp } from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { usePipeline } from "@/hooks/useLeadGeneration";
import type { PipelineStage } from "@/api/leadGeneration";

const stageLabels: Record<PipelineStage, string> = {
  prospect: "Prospect",
  qualified: "Qualified",
  opportunity: "Opportunity",
  customer: "Customer",
};

const stageColors: Record<PipelineStage, string> = {
  prospect: "#64748b",
  qualified: "#0ea5e9",
  opportunity: "#8b5cf6",
  customer: "#10b981",
};

const stageOrder: PipelineStage[] = [
  "prospect",
  "qualified",
  "opportunity",
  "customer",
];

function formatCurrency(value: number): string {
  return `$${value.toLocaleString()}`;
}

interface ChartDataPoint {
  stage: PipelineStage;
  label: string;
  count: number;
  total_value: number;
  color: string;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: Array<{
    payload: ChartDataPoint;
  }>;
}

function CustomTooltip({ active, payload }: CustomTooltipProps) {
  if (!active || !payload || payload.length === 0) {
    return null;
  }

  const data = payload[0].payload;

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-3 shadow-xl">
      <p className="text-sm font-medium text-white mb-1">{data.label}</p>
      <p className="text-sm text-slate-300">
        {data.count} {data.count === 1 ? "lead" : "leads"}
      </p>
      <p className="text-sm text-slate-400">{formatCurrency(data.total_value)}</p>
    </div>
  );
}

function PipelineSkeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 bg-slate-700 rounded-lg" />
        <div>
          <div className="h-4 bg-slate-700 rounded w-32 mb-2" />
          <div className="h-7 bg-slate-700 rounded w-40" />
        </div>
      </div>

      <div className="h-[280px] bg-slate-700/30 rounded-lg flex items-end gap-4 p-6">
        {[0.4, 0.7, 0.5, 0.3].map((height, i) => (
          <div
            key={i}
            className="flex-1 bg-slate-700 rounded-t"
            style={{ height: `${height * 100}%` }}
          />
        ))}
      </div>

      <div className="grid grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="bg-slate-800/50 border border-slate-700/50 rounded-lg p-4"
          >
            <div className="h-3 bg-slate-700 rounded w-20 mb-3" />
            <div className="h-6 bg-slate-700 rounded w-12 mb-2" />
            <div className="h-3 bg-slate-700 rounded w-24" />
          </div>
        ))}
      </div>
    </div>
  );
}

function EmptyPipeline() {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-4">
      <div className="w-20 h-20 bg-slate-800/50 rounded-2xl flex items-center justify-center mb-6 border border-slate-700/50">
        <BarChart3 className="w-10 h-10 text-slate-500" />
      </div>
      <h3 className="text-xl font-semibold text-white mb-2">
        No leads in pipeline yet
      </h3>
      <p className="text-slate-400 text-center max-w-md">
        Approve discovered leads to build your pipeline.
      </p>
    </div>
  );
}

export function PipelineView() {
  const { data: pipeline, isLoading } = usePipeline();

  if (isLoading) {
    return <PipelineSkeleton />;
  }

  if (
    !pipeline ||
    pipeline.total_leads === 0 ||
    pipeline.stages.length === 0
  ) {
    return <EmptyPipeline />;
  }

  const stageMap = new Map(
    pipeline.stages.map((s) => [s.stage, s])
  );

  const chartData: ChartDataPoint[] = stageOrder.map((stage) => {
    const stageSummary = stageMap.get(stage);
    return {
      stage,
      label: stageLabels[stage],
      count: stageSummary?.count ?? 0,
      total_value: stageSummary?.total_value ?? 0,
      color: stageColors[stage],
    };
  });

  return (
    <div className="space-y-6">
      {/* Total pipeline value header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-emerald-500/10 rounded-lg flex items-center justify-center">
            <DollarSign className="w-5 h-5 text-emerald-400" />
          </div>
          <div>
            <p className="text-sm text-slate-400">Total Pipeline Value</p>
            <p className="text-2xl font-bold text-white">
              {formatCurrency(pipeline.total_pipeline_value)}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <TrendingUp className="w-4 h-4" />
          <span>
            {pipeline.total_leads} {pipeline.total_leads === 1 ? "lead" : "leads"} total
          </span>
        </div>
      </div>

      {/* Bar chart */}
      <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-5">
        <ResponsiveContainer width="100%" height={280}>
          <BarChart
            data={chartData}
            margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
          >
            <XAxis
              dataKey="label"
              tick={{ fill: "#94a3b8", fontSize: 13 }}
              axisLine={{ stroke: "#334155" }}
              tickLine={false}
            />
            <YAxis
              tick={{ fill: "#94a3b8", fontSize: 12 }}
              axisLine={false}
              tickLine={false}
              allowDecimals={false}
            />
            <Tooltip
              content={<CustomTooltip />}
              cursor={{ fill: "rgba(148, 163, 184, 0.08)" }}
            />
            <Bar dataKey="count" radius={[6, 6, 0, 0]} maxBarSize={64}>
              {chartData.map((entry) => (
                <Cell key={entry.stage} fill={entry.color} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Stage summary cards */}
      <div className="grid grid-cols-4 gap-4">
        {chartData.map((entry) => {
          const percentage =
            pipeline.total_pipeline_value > 0
              ? (entry.total_value / pipeline.total_pipeline_value) * 100
              : 0;

          return (
            <div
              key={entry.stage}
              className="bg-slate-800/50 border border-slate-700/50 rounded-lg p-4"
            >
              <div className="flex items-center gap-2 mb-2">
                <span
                  className="w-2.5 h-2.5 rounded-full"
                  style={{ backgroundColor: entry.color }}
                />
                <span className="text-sm text-slate-400">{entry.label}</span>
              </div>
              <p className="text-xl font-bold text-white mb-1">{entry.count}</p>
              <p className="text-sm text-slate-300">
                {formatCurrency(entry.total_value)}
              </p>
              <p className="text-xs text-slate-500 mt-1">
                {percentage.toFixed(1)}% of pipeline
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
