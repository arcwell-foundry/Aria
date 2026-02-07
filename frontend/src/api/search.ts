import { apiClient } from "./client";

// Search result type matching backend SearchResult
export interface SearchResult {
  type: string;
  id: string;
  title: string;
  snippet: string;
  score: number;
  url: string;
}

// Recent item type matching backend RecentItem
export interface RecentItem {
  type: string;
  id: string;
  title: string;
  url: string;
  accessed_at: string;
}

// Global search params
export interface GlobalSearchParams {
  query: string;
  types?: string[];
  limit?: number;
}

// Global search response
export type GlobalSearchResponse = SearchResult[];

// Recent items response
export type RecentItemsResponse = RecentItem[];

// API functions
export async function globalSearch(params: GlobalSearchParams): Promise<GlobalSearchResponse> {
  const { query, types, limit = 10 } = params;
  const searchParams = new URLSearchParams();
  searchParams.append("query", query);
  if (types) {
    types.forEach((type) => searchParams.append("types", type));
  }
  if (limit !== 10) {
    searchParams.append("limit", limit.toString());
  }

  const response = await apiClient.get<GlobalSearchResponse>(
    `/search/global?${searchParams.toString()}`
  );
  return response.data;
}

export async function getRecentItems(limit = 10): Promise<RecentItemsResponse> {
  const response = await apiClient.get<RecentItemsResponse>(
    `/search/recent?limit=${limit}`
  );
  return response.data;
}

export async function recordAccess(
  type: string,
  id: string,
  title: string,
  url: string
): Promise<void> {
  await apiClient.post("/search/record", {
    type,
    id,
    title,
    url,
  });
}

// Convenience export
export const searchApi = {
  globalSearch,
  getRecentItems,
  recordAccess,
};
