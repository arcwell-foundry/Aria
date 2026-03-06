import { apiClient } from "./client";

// Types matching backend models
export interface BattleCardPricing {
  model?: string;
  range?: string;
  strategy?: string;
  notes?: string;
}

export interface BattleCardDifferentiation {
  area: string;
  our_advantage: string;
}

export interface BattleCardObjectionHandler {
  objection: string;
  response: string;
}

export interface BattleCardMetrics {
  market_cap_gap: number;
  win_rate: number;
  pricing_delta: number;
  last_signal_at: string | null;
}

export interface BattleCardStrategy {
  title: string;
  description: string;
  icon: string;
  agent: string;
}

export interface BattleCardFeatureGap {
  feature: string;
  aria_score: number;
  competitor_score: number;
}

export interface BattleCardCriticalGap {
  description: string;
  is_advantage: boolean;
}

export interface BattleCardMomentumDetail {
  signals_current_30d: number;
  signals_previous_30d: number;
}

export interface BattleCardNewsItem {
  title: string;
  date: string;
  source: string;
  relevance: string;
  signal_type?: string;
  url?: string;
}

export interface BattleCardSignal {
  id: string;
  headline: string;
  signal_type: string;
  source_name: string | null;
  source_url: string | null;
  relevance_score: number;
  detected_at: string;
  summary: string | null;
}

export interface BattleCardAnalysis {
  metrics?: BattleCardMetrics;
  strategies?: BattleCardStrategy[];
  feature_gaps?: BattleCardFeatureGap[];
  critical_gaps?: BattleCardCriticalGap[];
  threat_level?: 'high' | 'medium' | 'low';
  threat_score?: number;
  momentum?: 'increasing' | 'declining' | 'stable';
  momentum_detail?: BattleCardMomentumDetail;
  last_signal_at?: string;
  signal_count_30d?: number;
  signal_count_total?: number;
  high_impact_signals?: number;
  avg_relevance?: number;
  computed_at?: string;
  computation_method?: string;
  recent_news?: BattleCardNewsItem[];
}

export interface BattleCard {
  id: string;
  company_id: string;
  competitor_name: string;
  competitor_domain: string | null;
  overview: string | null;
  strengths: string[];
  weaknesses: string[];
  pricing: BattleCardPricing;
  differentiation: BattleCardDifferentiation[];
  objection_handlers: BattleCardObjectionHandler[];
  analysis: BattleCardAnalysis;
  last_updated: string;
  update_source: "manual" | "auto" | "demo_seed";
  recent_signals?: BattleCardSignal[];
  signal_count?: number;
}

export interface BattleCardChange {
  id: string;
  battle_card_id: string;
  change_type: string;
  field_name: string;
  old_value: unknown;
  new_value: unknown;
  detected_at: string;
}

export interface CreateBattleCardData {
  competitor_name: string;
  competitor_domain?: string;
  overview?: string;
  strengths?: string[];
  weaknesses?: string[];
  pricing?: BattleCardPricing;
  differentiation?: BattleCardDifferentiation[];
  objection_handlers?: BattleCardObjectionHandler[];
  analysis?: BattleCardAnalysis;
}

export interface UpdateBattleCardData {
  overview?: string;
  strengths?: string[];
  weaknesses?: string[];
  pricing?: BattleCardPricing;
  differentiation?: BattleCardDifferentiation[];
  objection_handlers?: BattleCardObjectionHandler[];
  analysis?: BattleCardAnalysis;
}

// API functions
export async function listBattleCards(search?: string): Promise<BattleCard[]> {
  const params = search ? `?search=${encodeURIComponent(search)}` : "";
  const response = await apiClient.get<BattleCard[]>(`/battlecards${params}`);
  return response.data;
}

export async function getBattleCard(competitorName: string): Promise<BattleCard> {
  const response = await apiClient.get<BattleCard>(
    `/battlecards/${encodeURIComponent(competitorName)}`
  );
  return response.data;
}

export async function createBattleCard(data: CreateBattleCardData): Promise<BattleCard> {
  const response = await apiClient.post<BattleCard>("/battlecards", data);
  return response.data;
}

export async function updateBattleCard(
  cardId: string,
  data: UpdateBattleCardData
): Promise<BattleCard> {
  const response = await apiClient.patch<BattleCard>(`/battlecards/${cardId}`, data);
  return response.data;
}

export async function deleteBattleCard(cardId: string): Promise<void> {
  await apiClient.delete(`/battlecards/${cardId}`);
}

export async function getBattleCardHistory(
  cardId: string,
  limit = 20
): Promise<BattleCardChange[]> {
  const response = await apiClient.get<BattleCardChange[]>(
    `/battlecards/${cardId}/history?limit=${limit}`
  );
  return response.data;
}

export async function addObjectionHandler(
  cardId: string,
  objection: string,
  response: string
): Promise<BattleCard> {
  const res = await apiClient.post<BattleCard>(
    `/battlecards/${cardId}/objections?objection=${encodeURIComponent(objection)}&response=${encodeURIComponent(response)}`
  );
  return res.data;
}
