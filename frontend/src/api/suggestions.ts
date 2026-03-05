import { apiClient } from "./client";

// Suggestion chip types from backend
export interface SuggestionChip {
  text: string;   // Short display text for the chip
  action: string; // Full message to send when clicked
}

export interface SuggestionsResponse {
  suggestions: SuggestionChip[];
}

/**
 * Fetch context-aware suggestion chips for the current user.
 * Returns up to 4 suggestions based on user's current state:
 * - Upcoming meetings within 4 hours
 * - Unread market signals
 * - Pending email drafts
 * - Open tasks/goals
 * - Default fallbacks
 */
export async function fetchSuggestions(): Promise<SuggestionsResponse> {
  const response = await apiClient.get<SuggestionsResponse>("/suggestions");
  return response.data;
}
