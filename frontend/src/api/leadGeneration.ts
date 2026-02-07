import { apiClient } from "./client";

// Types
export interface ICPDefinition {
  industry: string[];
  company_size: { min: number; max: number };
  modalities: string[];
  therapeutic_areas: string[];
  geographies: string[];
  signals: string[];
  exclusions: string[];
}

export interface ICPResponse {
  id: string;
  user_id: string;
  icp_data: ICPDefinition;
  version: number;
  created_at: string;
  updated_at: string;
}

export type ReviewStatus = "pending" | "approved" | "rejected" | "saved";
export type PipelineStage = "prospect" | "qualified" | "opportunity" | "customer";

export interface ScoreFactor {
  name: string;
  score: number;
  weight: number;
  explanation: string;
}

export interface LeadScoreBreakdown {
  overall_score: number;
  factors: ScoreFactor[];
}

export interface DiscoveredLead {
  id: string;
  user_id: string;
  icp_id: string | null;
  company_name: string;
  company_data: Record<string, unknown>;
  contacts: Record<string, unknown>[];
  fit_score: number;
  score_breakdown: LeadScoreBreakdown | null;
  signals: string[];
  review_status: ReviewStatus;
  reviewed_at: string | null;
  source: string;
  lead_memory_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface PipelineStageSummary {
  stage: PipelineStage;
  count: number;
  total_value: number;
}

export interface PipelineSummary {
  stages: PipelineStageSummary[];
  total_leads: number;
  total_pipeline_value: number;
}

export interface OutreachRequest {
  subject: string;
  message: string;
  tone?: string;
}

export interface OutreachResponse {
  id: string;
  lead_id: string;
  draft_subject: string;
  draft_body: string;
  status: string;
  created_at: string;
}

// API functions
export async function saveICP(icp: ICPDefinition): Promise<ICPResponse> {
  const response = await apiClient.post<ICPResponse>("/leads/icp", icp);
  return response.data;
}

export async function getICP(): Promise<ICPResponse | null> {
  const response = await apiClient.get<ICPResponse | null>("/leads/icp");
  return response.data;
}

export async function discoverLeads(
  targetCount: number = 10
): Promise<DiscoveredLead[]> {
  const response = await apiClient.post<DiscoveredLead[]>(
    "/leads/discovered",
    { target_count: targetCount }
  );
  return response.data;
}

export async function listDiscoveredLeads(
  statusFilter?: ReviewStatus
): Promise<DiscoveredLead[]> {
  const params = new URLSearchParams();
  if (statusFilter) params.append("review_status", statusFilter);
  const url = params.toString()
    ? `/leads/discovered?${params}`
    : "/leads/discovered";
  const response = await apiClient.get<DiscoveredLead[]>(url);
  return response.data;
}

export async function reviewLead(
  leadId: string,
  action: ReviewStatus
): Promise<DiscoveredLead> {
  const response = await apiClient.post<DiscoveredLead>(
    `/leads/${leadId}/review`,
    { action }
  );
  return response.data;
}

export async function getScoreExplanation(
  leadId: string
): Promise<LeadScoreBreakdown> {
  const response = await apiClient.get<LeadScoreBreakdown>(
    `/leads/${leadId}/score-explanation`
  );
  return response.data;
}

export async function getPipeline(): Promise<PipelineSummary> {
  const response = await apiClient.get<PipelineSummary>("/leads/pipeline");
  return response.data;
}

export async function initiateOutreach(
  leadId: string,
  outreach: OutreachRequest
): Promise<OutreachResponse> {
  const response = await apiClient.post<OutreachResponse>(
    `/leads/outreach/${leadId}`,
    outreach
  );
  return response.data;
}
