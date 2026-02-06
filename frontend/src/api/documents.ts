import { apiClient } from "./client";

// Types

export interface CompanyDocument {
  id: string;
  company_id: string;
  uploaded_by: string;
  filename: string;
  file_type: string;
  file_size_bytes: number;
  storage_path: string;
  processing_status: "uploaded" | "processing" | "complete" | "failed";
  processing_progress: number;
  chunk_count: number;
  entity_count: number;
  quality_score: number;
  extracted_metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface DocumentStatus {
  processing_status: "uploaded" | "processing" | "complete" | "failed";
  processing_progress: number;
  chunk_count: number;
  entity_count: number;
  quality_score: number;
}

// API functions

export async function uploadDocument(file: File): Promise<CompanyDocument> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await apiClient.post<CompanyDocument>(
    "/onboarding/documents/upload",
    formData,
    { headers: { "Content-Type": "multipart/form-data" } }
  );
  return response.data;
}

export async function getDocuments(): Promise<CompanyDocument[]> {
  const response = await apiClient.get<CompanyDocument[]>(
    "/onboarding/documents"
  );
  return response.data;
}

export async function getDocumentStatus(
  docId: string
): Promise<DocumentStatus> {
  const response = await apiClient.get<DocumentStatus>(
    `/onboarding/documents/${docId}/status`
  );
  return response.data;
}
