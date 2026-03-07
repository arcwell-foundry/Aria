import { apiClient } from "./client";

// Intelligence insight types from backend
export interface IntelligenceInsight {
  id: string;
  user_id: string;
  insight_type: string;
  trigger_event: string | null;
  engine_source: string | null;
  title: string | null;
  content: string;
  classification: "opportunity" | "threat" | "neutral";
  impact_score: number;
  confidence: number;
  urgency: number;
  combined_score: number;
  priority: number | null;
  time_horizon: "immediate" | "short_term" | "medium_term" | "long_term" | null;
  causal_chain: Record<string, unknown>[];
  affected_goals: string[];
  recommended_actions: string[];
  status: string;
  feedback_text: string | null;
  explanation: string | null;
  created_at: string;
  updated_at: string;
}

export interface InsightsListResponse {
  insights: IntelligenceInsight[];
  total: number;
}

export interface ProactiveInsight {
  id: string;
  insight_type: string;
  content: string;
  priority: number;
  context: Record<string, unknown>;
  created_at: string;
}

export interface ProactiveInsightsResponse {
  insights: ProactiveInsight[];
}

export interface InsightFilters {
  limit?: number;
  status?: string;
  classification?: string;
}

// API functions
export async function listInsights(filters?: InsightFilters): Promise<IntelligenceInsight[]> {
  const params = new URLSearchParams();
  if (filters?.limit) params.append("limit", filters.limit.toString());
  if (filters?.status) params.append("status", filters.status);
  if (filters?.classification) params.append("classification", filters.classification);

  const url = params.toString() ? `/intelligence/insights?${params}` : "/intelligence/insights";
  const response = await apiClient.get<IntelligenceInsight[] | InsightsListResponse>(url);
  // Handle both array and object response shapes
  if (Array.isArray(response.data)) {
    return response.data;
  }
  return (response.data as InsightsListResponse).insights ?? [];
}

export async function getInsight(insightId: string): Promise<IntelligenceInsight> {
  const response = await apiClient.get<IntelligenceInsight>(`/intelligence/insights/${insightId}`);
  return response.data;
}

export async function updateInsightFeedback(
  insightId: string,
  feedback: { status?: string; feedback?: string }
): Promise<IntelligenceInsight> {
  const response = await apiClient.patch<IntelligenceInsight>(
    `/intelligence/insights/${insightId}`,
    feedback
  );
  return response.data;
}

export async function getProactiveInsights(): Promise<ProactiveInsight[]> {
  const response = await apiClient.get<ProactiveInsightsResponse>("/insights/proactive");
  return response.data.insights ?? [];
}

export async function engageInsight(insightId: string): Promise<void> {
  await apiClient.post(`/insights/${insightId}/engage`);
}

export async function dismissInsight(insightId: string): Promise<void> {
  await apiClient.post(`/insights/${insightId}/dismiss`);
}

// =============================================================================
// INTELLIGENCE PAGE V2 API CLIENTS
// =============================================================================

// --- Watch Topics ---

export interface WatchTopic {
  id: string;
  user_id: string;
  topic_type: "keyword" | "company" | "therapeutic_area";
  topic_value: string;
  description: string | null;
  keywords: string[];
  signal_count: number;
  is_active: boolean;
  last_matched_at: string | null;
  created_at: string;
}

export interface WatchTopicsResponse {
  topics: WatchTopic[];
  count: number;
}

export interface AddWatchTopicRequest {
  topic_type?: "keyword" | "company" | "therapeutic_area";
  topic_value: string;
  description?: string;
}

export async function getWatchTopics(): Promise<WatchTopicsResponse> {
  const response = await apiClient.get<WatchTopicsResponse>("/intelligence/watch-topics");
  return response.data;
}

export async function addWatchTopic(data: AddWatchTopicRequest): Promise<{ topic: WatchTopic; retroactive_matches: number }> {
  const response = await apiClient.post<{ topic: WatchTopic; retroactive_matches: number }>(
    "/intelligence/watch-topics",
    data
  );
  return response.data;
}

export async function deleteWatchTopic(topicId: string): Promise<{ deleted: boolean }> {
  const response = await apiClient.delete<{ deleted: boolean }>(
    `/intelligence/watch-topics/${topicId}`
  );
  return response.data;
}

// --- Competitor Activity ---

export interface CompetitorSignal {
  headline: string;
  signal_type: string;
  detected_at: string;
}

export interface CompetitorActivity {
  competitor: string;
  signal_count: number;
  signals: CompetitorSignal[];
}

export interface CompetitorActivityResponse {
  activity: CompetitorActivity[];
  days: number;
}

export async function getCompetitorActivity(days: number = 30): Promise<CompetitorActivityResponse> {
  const response = await apiClient.get<CompetitorActivityResponse>(
    `/intelligence/competitor-activity?days=${days}`
  );
  return response.data;
}

// --- CRM Status ---

export interface CRMStatusResponse {
  connected: boolean;
  type: "salesforce" | "hubspot" | "dynamics" | null;
}

export async function getCRMStatus(): Promise<CRMStatusResponse> {
  const response = await apiClient.get<CRMStatusResponse>("/intelligence/crm-status");
  return response.data;
}

// --- Battle Card Detail ---

export interface BattleCardDetailSignal {
  id: string;
  headline: string;
  signal_type: string;
  detected_at: string;
}

export interface BattleCardDetailInsight {
  id: string;
  classification: string;
  content: string;
  confidence: number;
  priority_label: string | null;
}

export interface BattleCardDetailResponse {
  card: Record<string, unknown>;
  signals: BattleCardDetailSignal[];
  insights: BattleCardDetailInsight[];
}

export async function getBattleCardDetail(cardId: string): Promise<BattleCardDetailResponse> {
  const response = await apiClient.get<BattleCardDetailResponse>(
    `/intelligence/battle-cards/${cardId}`
  );
  return response.data;
}

// --- Priority Signals ---

export interface PrioritySignal {
  id: string;
  headline: string;
  company_name: string;
  signal_type: string;
  relevance_score: number;
  detected_at: string;
  linked_insight_id: string | null;
  linked_action_summary: string | null;
  is_cluster_primary: boolean;
}

export interface PrioritySignalsResponse {
  signals: PrioritySignal[];
  hours: number;
}

export async function getPrioritySignals(hours: number = 48): Promise<PrioritySignalsResponse> {
  const response = await apiClient.get<PrioritySignalsResponse>(
    `/intelligence/signals/priority?hours=${hours}`
  );
  return response.data;
}

// --- Therapeutic Trends ---

export interface TherapeuticTrend {
  trend_type: "therapeutic_area" | "manufacturing_modality";
  name: string;
  signal_count: number;
  companies_involved: string[];
  company_count: number;
  description: string;
  narrative: string;
  aligned_goal?: string;
}

export interface TherapeuticTrendsResponse {
  trends: TherapeuticTrend[];
  goals_count?: number;
}

export async function getTherapeuticTrendsWithNarratives(): Promise<TherapeuticTrendsResponse> {
  const response = await apiClient.get<TherapeuticTrendsResponse>(
    "/intelligence/therapeutic-trends-v2"
  );
  return response.data;
}
