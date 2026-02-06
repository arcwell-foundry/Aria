import { apiClient } from "./client";

export interface MemoryDeltaFact {
  id: string;
  fact: string;
  confidence: number;
  source: string;
  category: string;
  language: string;
}

export interface MemoryDeltaGroup {
  domain: string;
  facts: MemoryDeltaFact[];
  summary: string;
  timestamp: string | null;
}

export interface CorrectionRequest {
  fact_id: string;
  corrected_value: string;
  correction_type?: string;
}

export interface CorrectionResponse {
  status: string;
  new_confidence: number | null;
}

export async function getMemoryDelta(
  since?: string,
  domain?: string
): Promise<MemoryDeltaGroup[]> {
  const params: Record<string, string> = {};
  if (since) params.since = since;
  if (domain) params.domain = domain;

  const response = await apiClient.get<MemoryDeltaGroup[]>("/memory/delta", {
    params,
  });
  return response.data;
}

export async function correctMemory(
  correction: CorrectionRequest
): Promise<CorrectionResponse> {
  const response = await apiClient.post<CorrectionResponse>(
    "/memory/correct",
    correction
  );
  return response.data;
}
