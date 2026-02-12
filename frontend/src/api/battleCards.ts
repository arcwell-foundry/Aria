import { apiClient } from "./client";

// Types matching backend models
export interface BattleCardPricing {
  model?: string;
  range?: string;
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

export interface BattleCardAnalysis {
  metrics?: BattleCardMetrics;
  strategies?: BattleCardStrategy[];
  feature_gaps?: BattleCardFeatureGap[];
  critical_gaps?: BattleCardCriticalGap[];
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
