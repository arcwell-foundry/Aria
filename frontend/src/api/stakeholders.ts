import { apiClient } from "./client";

// Types for stakeholder mapping API

export type RelationshipType =
  | "champion"
  | "decision_maker"
  | "influencer"
  | "end_user"
  | "blocker"
  | "other";

export interface StakeholderInput {
  name: string;
  title?: string;
  company?: string;
  email?: string;
  relationship_type: RelationshipType;
  notes?: string;
}

export interface Stakeholder {
  id: string;
  name: string;
  title?: string;
  company?: string;
  email?: string;
  relationship_type: RelationshipType;
  notes?: string;
}

export interface SaveStakeholdersRequest {
  stakeholders: StakeholderInput[];
}

export interface SaveStakeholdersResponse {
  count: number;
  stakeholder_ids: string[];
}

// API functions

export async function saveStakeholders(
  data: SaveStakeholdersRequest
): Promise<SaveStakeholdersResponse> {
  const response = await apiClient.post<SaveStakeholdersResponse>(
    "/onboarding/stakeholders/save",
    data
  );
  return response.data;
}

export async function getStakeholders(): Promise<Stakeholder[]> {
  const response = await apiClient.get<Stakeholder[]>("/onboarding/stakeholders");
  return response.data;
}
