import { PieChart, Pie, Cell } from "recharts";

interface MiniDonutChartProps {
  /** Value from 0 to 1 */
  value: number;
  /** Size in pixels */
  size?: number;
  /** Color for the filled portion */
  color?: string;
  /** Color for the unfilled portion */
  bgColor?: string;
}

export function MiniDonutChart({
  value,
  size = 40,
  color = "#22c55e",
  bgColor = "#334155",
}: MiniDonutChartProps) {
  const clamped = Math.max(0, Math.min(1, value));
  const data = [
    { value: clamped },
    { value: 1 - clamped },
  ];

  return (
    <PieChart width={size} height={size}>
      <Pie
        data={data}
        cx={size / 2 - 1}
        cy={size / 2 - 1}
        innerRadius={size / 2 - 8}
        outerRadius={size / 2 - 2}
        startAngle={90}
        endAngle={-270}
        dataKey="value"
        stroke="none"
      >
        <Cell fill={color} />
        <Cell fill={bgColor} />
      </Pie>
    </PieChart>
  );
}
