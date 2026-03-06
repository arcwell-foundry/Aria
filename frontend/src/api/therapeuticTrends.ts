import { apiClient } from "./client";

export interface TherapeuticTrend {
  trend_type: "therapeutic_area" | "manufacturing_modality";
  name: string;
  signal_count: number;
  companies_involved: string[];
  company_count: number;
  description: string;
}

export async function getTherapeuticTrends(
  days: number = 30,
  minSignals: number = 3,
): Promise<TherapeuticTrend[]> {
  const params = new URLSearchParams();
  params.append("days", days.toString());
  params.append("min_signals", minSignals.toString());
  const response = await apiClient.get<{ trends: TherapeuticTrend[]; count: number }>(
    `/intelligence/therapeutic-trends?${params}`,
  );
  return response.data.trends;
}
