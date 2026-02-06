import { apiClient } from "./client";

// Types matching backend Pydantic models

export type OnboardingStep =
  | "company_discovery"
  | "document_upload"
  | "user_profile"
  | "writing_samples"
  | "email_integration"
  | "integration_wizard"
  | "first_goal"
  | "activation";

export const SKIPPABLE_STEPS: Set<OnboardingStep> = new Set([
  "document_upload",
  "writing_samples",
  "email_integration",
]);

export interface ReadinessScores {
  corporate_memory: number;
  digital_twin: number;
  relationship_graph: number;
  integrations: number;
  goal_clarity: number;
}

export interface OnboardingState {
  id: string;
  user_id: string;
  current_step: OnboardingStep;
  step_data: Record<string, unknown>;
  completed_steps: string[];
  skipped_steps: string[];
  started_at: string;
  updated_at: string;
  completed_at: string | null;
  readiness_scores: ReadinessScores;
  metadata: Record<string, unknown>;
}

export interface OnboardingStateResponse {
  state: OnboardingState;
  progress_percentage: number;
  total_steps: number;
  completed_count: number;
  current_step_index: number;
  is_complete: boolean;
}

export interface RoutingDecision {
  route: "onboarding" | "resume" | "dashboard" | "admin";
}

// API functions

export async function getOnboardingState(): Promise<OnboardingStateResponse> {
  const response =
    await apiClient.get<OnboardingStateResponse>("/onboarding/state");
  return response.data;
}

export async function completeStep(
  step: OnboardingStep,
  stepData: Record<string, unknown> = {}
): Promise<OnboardingStateResponse> {
  const response = await apiClient.post<OnboardingStateResponse>(
    `/onboarding/steps/${step}/complete`,
    { step_data: stepData }
  );
  return response.data;
}

export async function skipStep(
  step: OnboardingStep,
  reason?: string
): Promise<OnboardingStateResponse> {
  const response = await apiClient.post<OnboardingStateResponse>(
    `/onboarding/steps/${step}/skip`,
    { reason: reason ?? null }
  );
  return response.data;
}

export async function getRoutingDecision(): Promise<RoutingDecision> {
  const response = await apiClient.get<RoutingDecision>("/onboarding/routing");
  return response.data;
}

// Enrichment status (US-903)

export interface CompanyClassification {
  company_type: string;
  primary_modality: string;
  company_posture: string;
  therapeutic_areas: string[];
  likely_pain_points: string[];
  confidence: number;
}

export interface EnrichmentStatus {
  status: "no_company" | "not_found" | "in_progress" | "complete";
  quality_score?: number;
  classification?: CompanyClassification;
  enriched_at?: string;
}

export async function getEnrichmentStatus(): Promise<EnrichmentStatus> {
  const response = await apiClient.get<EnrichmentStatus>(
    "/onboarding/enrichment/status"
  );
  return response.data;
}
