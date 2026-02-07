import { apiClient } from "./client";

// Types
export interface ResponseFeedbackRequest {
  message_id: string;
  rating: "up" | "down";
  comment?: string;
}

export interface GeneralFeedbackRequest {
  type: "bug" | "feature" | "other";
  message: string;
  page?: string;
}

export interface FeedbackSubmissionResponse {
  message: string;
  feedback_id: string;
}

// API functions
export async function submitResponseFeedback(
  data: ResponseFeedbackRequest
): Promise<FeedbackSubmissionResponse> {
  const response = await apiClient.post<FeedbackSubmissionResponse>(
    "/feedback/response",
    data
  );
  return response.data;
}

export async function submitGeneralFeedback(
  data: GeneralFeedbackRequest
): Promise<FeedbackSubmissionResponse> {
  const response = await apiClient.post<FeedbackSubmissionResponse>(
    "/feedback/general",
    data
  );
  return response.data;
}
