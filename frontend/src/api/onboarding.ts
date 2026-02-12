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

// Enrichment Memory Delta (US-920)

export interface EnrichmentMemoryFact {
  id: string;
  fact: string;
  confidence: number;
  source: string;
  category: string;
  language: string;
}

export interface EnrichmentMemoryDelta {
  domain: string;
  facts: EnrichmentMemoryFact[];
  summary: string;
  timestamp: string | null;
}

export async function getEnrichmentDelta(): Promise<EnrichmentMemoryDelta[]> {
  const response = await apiClient.get<EnrichmentMemoryDelta[]>(
    "/onboarding/enrichment/delta"
  );
  return response.data;
}

// Integration Wizard (US-909)

export type IntegrationAppName =
  | "SALESFORCE"
  | "HUBSPOT"
  | "GOOGLECALENDAR"
  | "OUTLOOK365CALENDAR"
  | "SLACK";

export interface IntegrationStatus {
  name: IntegrationAppName;
  display_name: string;
  category: "crm" | "calendar" | "messaging";
  connected: boolean;
  connected_at: string | null;
  connection_id: string | null;
}

export interface IntegrationPreferences {
  slack_channels: string[];
  notification_enabled: boolean;
  sync_frequency_hours: number;
}

export interface IntegrationsStatusResponse {
  crm: IntegrationStatus[];
  calendar: IntegrationStatus[];
  messaging: IntegrationStatus[];
  preferences: IntegrationPreferences;
}

export interface ConnectIntegrationRequest {
  app_name: IntegrationAppName;
}

export interface ConnectIntegrationResponse {
  auth_url: string;
  connection_id: string;
  status: string;
  message?: string;
}

export interface DisconnectIntegrationRequest {
  app_name: IntegrationAppName;
}

export interface SaveIntegrationPreferencesRequest {
  slack_channels: string[];
  notification_enabled: boolean;
  sync_frequency_hours: number;
}

export async function getIntegrationWizardStatus(): Promise<IntegrationsStatusResponse> {
  const response = await apiClient.get<IntegrationsStatusResponse>(
    "/onboarding/integrations/status"
  );
  return response.data;
}

export async function connectIntegration(
  appName: IntegrationAppName
): Promise<ConnectIntegrationResponse> {
  const response = await apiClient.post<ConnectIntegrationResponse>(
    "/onboarding/integrations/connect",
    { app_name: appName }
  );
  return response.data;
}

export async function disconnectIntegration(
  appName: IntegrationAppName
): Promise<{ status: string; message?: string }> {
  const response = await apiClient.post<{ status: string; message?: string }>(
    "/onboarding/integrations/disconnect",
    { app_name: appName }
  );
  return response.data;
}

export async function saveIntegrationPreferences(
  preferences: SaveIntegrationPreferencesRequest
): Promise<{ status: string; connected_count: number }> {
  const response = await apiClient.post<{ status: string; connected_count: number }>(
    "/onboarding/integrations/preferences",
    preferences
  );
  return response.data;
}

// First Goal endpoints (US-910)

export interface GoalSuggestion {
  title: string;
  description: string;
  category: string;
  urgency: string;
  reason: string;
  goal_type: string;
}

export interface GoalTemplate {
  title: string;
  description: string;
  category: string;
  goal_type: string;
  applicable_roles: string[];
}

export interface FirstGoalSuggestionsResponse {
  suggestions: GoalSuggestion[];
  templates: Record<string, GoalTemplate[]>;
  enrichment_context: {
    company: { name: string; classification: Record<string, unknown> } | null;
    connected_integrations: string[];
  } | null;
}

export interface SmartValidationRequest {
  title: string;
  description?: string;
}

export interface SmartValidationResponse {
  is_smart: boolean;
  score: number;
  feedback: string[];
  refined_version: string | null;
}

export interface FirstGoalCreateRequest {
  title: string;
  description?: string;
  goal_type?: string;
}

export interface FirstGoalCreateResponse {
  goal: {
    id: string;
    title: string;
    description: string | null;
    goal_type: string;
    status: string;
  };
  status: string;
  message: string;
}

export async function getFirstGoalSuggestions(): Promise<FirstGoalSuggestionsResponse> {
  const response = await apiClient.get<FirstGoalSuggestionsResponse>(
    "/onboarding/first-goal/suggestions"
  );
  return response.data;
}

export async function validateGoalSmart(
  request: SmartValidationRequest
): Promise<SmartValidationResponse> {
  const response = await apiClient.post<SmartValidationResponse>(
    "/onboarding/first-goal/validate-smart",
    request
  );
  return response.data;
}

export async function createFirstGoal(
  request: FirstGoalCreateRequest
): Promise<FirstGoalCreateResponse> {
  const response = await apiClient.post<FirstGoalCreateResponse>(
    "/onboarding/first-goal/create",
    request
  );
  return response.data;
}

// Activation endpoint (US-911)

export interface ActivateAriaResponse {
  status: "activated";
  redirect: string;
}

export async function activateAria(): Promise<ActivateAriaResponse> {
  const response = await apiClient.post<ActivateAriaResponse>(
    "/onboarding/activate"
  );
  return response.data;
}

// Readiness Score endpoint (US-913)

export interface ReadinessBreakdown {
  corporate_memory: number;
  digital_twin: number;
  relationship_graph: number;
  integrations: number;
  goal_clarity: number;
  overall: number;
  confidence_modifier: "low" | "moderate" | "high" | "very_high";
}

export async function getReadiness(): Promise<ReadinessBreakdown> {
  const response = await apiClient.get<ReadinessBreakdown>(
    "/onboarding/readiness"
  );
  return response.data;
}

// Adaptive OODA Injected Questions (US-916)

export interface InjectedQuestion {
  question: string;
  context: string;
  insert_after_step: string;
}

export async function getInjectedQuestions(
  step: string
): Promise<InjectedQuestion[]> {
  const response = await apiClient.get<InjectedQuestion[]>(
    `/onboarding/steps/${step}/injected-questions`
  );
  return response.data;
}

export async function answerInjectedQuestion(
  step: string,
  question: string,
  answer: string
): Promise<{ status: string }> {
  const response = await apiClient.post<{ status: string }>(
    `/onboarding/steps/${step}/injected-questions/answer`,
    { question, answer }
  );
  return response.data;
}

// Agent Activation Status (US-915)

export interface AgentActivationEntry {
  goal_id: string;
  agent: string;
  goal_title: string;
  task: string;
  status: "pending" | "running" | "complete" | "failed";
  progress: number;
}

export interface ActivationStatusResponse {
  status: "idle" | "pending" | "running" | "complete";
  activations: AgentActivationEntry[];
}

export async function getActivationStatus(): Promise<ActivationStatusResponse> {
  const response = await apiClient.get<ActivationStatusResponse>(
    "/onboarding/activation-status"
  );
  return response.data;
}

// Cross-user acceleration endpoints (US-917)

export interface CompanyFact {
  id: string;
  fact: string;
  domain: string;
  confidence: number;
  source: string;
}

export interface CompanyMemoryDelta {
  facts: CompanyFact[];
  high_confidence_facts: CompanyFact[];
  domains_covered: string[];
  total_fact_count: number;
}

export interface CrossUserAccelerationResponse {
  exists: boolean;
  company_id: string | null;
  company_name: string | null;
  richness_score: number;
  recommendation: "skip" | "partial" | "full";
  facts: CompanyFact[];
}

export interface ConfirmCompanyDataRequest {
  company_id: string;
  corrections: Record<string, string>;
}

export interface ConfirmCompanyDataResponse {
  user_linked: boolean;
  steps_skipped: string[];
  readiness_inherited: number;
  corrections_applied: number;
}

export async function checkCrossUser(
  domain: string
): Promise<CrossUserAccelerationResponse> {
  const response = await apiClient.get<CrossUserAccelerationResponse>(
    `/onboarding/cross-user?domain=${encodeURIComponent(domain)}`
  );
  return response.data;
}

export async function confirmCompanyData(
  request: ConfirmCompanyDataRequest
): Promise<OnboardingState> {
  const response = await apiClient.post<{ state: OnboardingState }>(
    "/onboarding/cross-user/confirm",
    request
  );
  return response.data.state;
}

// Skills Pre-Configuration endpoints (US-918)

export interface SkillRecommendation {
  skill_id: string;
  trust_level: string;
}

export interface SkillRecommendationsRequest {
  company_type: string;
  role?: string;
}

export interface SkillRecommendationsResponse {
  recommendations: SkillRecommendation[];
  message: string | null;
}

export interface SkillInstallRequest {
  skill_ids: string[];
}

export interface SkillInstallResponse {
  installed_count: number;
  total_count: number;
  failed_skills: string[];
}

export async function getSkillRecommendations(
  request: SkillRecommendationsRequest
): Promise<SkillRecommendationsResponse> {
  const response = await apiClient.post<SkillRecommendationsResponse>(
    "/onboarding/skills/recommendations",
    request
  );
  return response.data;
}

export async function installRecommendedSkills(
  request: SkillInstallRequest
): Promise<SkillInstallResponse> {
  const response = await apiClient.post<SkillInstallResponse>(
    "/onboarding/skills/install",
    request
  );
  return response.data;
}

// Record integration connection (OAuth callback)

export interface RecordConnectionRequest {
  integration_type: string;
  connection_id: string;
}

export interface RecordConnectionResponse {
  status: string;
  integration_type: string;
}

export async function recordIntegrationConnection(
  request: RecordConnectionRequest
): Promise<RecordConnectionResponse> {
  const response = await apiClient.post<RecordConnectionResponse>(
    "/onboarding/integrations/record-connection",
    request
  );
  return response.data;
}

// Personality Calibration endpoints (US-919)

export interface PersonalityCalibrationResponse {
  directness: number;
  warmth: number;
  assertiveness: number;
  detail_orientation: number;
  formality: number;
  tone_guidance: string;
  example_adjustments: string[];
}

export interface PersonalityCalibrationStatus {
  status: "not_calibrated";
}

export async function calibratePersonality(): Promise<PersonalityCalibrationResponse> {
  const response = await apiClient.post<PersonalityCalibrationResponse>(
    "/onboarding/personality/calibrate"
  );
  return response.data;
}

export async function getPersonalityCalibration(): Promise<
  PersonalityCalibrationResponse | PersonalityCalibrationStatus
> {
  const response = await apiClient.get<
    PersonalityCalibrationResponse | PersonalityCalibrationStatus
  >("/onboarding/personality/calibration");
  return response.data;
}

// Company Discovery endpoint (US-902)

export interface CompanyDiscoveryRequest {
  company_name: string;
  website: string;
  email: string;
}

export interface CompanyDiscoverySuccessResponse {
  success: true;
  company: {
    id: string;
    name: string;
    domain: string;
    is_existing: boolean;
  };
  gate_result: {
    is_life_sciences: boolean;
    confidence: number;
  };
  enrichment_status: string;
}

export interface CompanyDiscoveryErrorResponse {
  success: false;
  error: string;
  type: "email_validation" | "vertical_mismatch";
  message?: string;
  reasoning?: string;
}

export type CompanyDiscoveryResponse =
  | CompanyDiscoverySuccessResponse
  | CompanyDiscoveryErrorResponse;

export async function submitCompanyDiscovery(
  request: CompanyDiscoveryRequest
): Promise<CompanyDiscoveryResponse> {
  const response = await apiClient.post<CompanyDiscoveryResponse>(
    "/onboarding/company-discovery/submit",
    request
  );
  return response.data;
}

