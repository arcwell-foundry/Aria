import { apiClient } from "./client";

// Types

export interface WritingStyleFingerprint {
  avg_sentence_length: number;
  sentence_length_variance: number;
  paragraph_style: "short_punchy" | "medium" | "long_detailed";
  lexical_diversity: number;
  formality_index: number;
  vocabulary_sophistication: "simple" | "moderate" | "advanced";
  uses_em_dashes: boolean;
  uses_semicolons: boolean;
  exclamation_frequency: "never" | "rare" | "occasional" | "frequent";
  ellipsis_usage: boolean;
  opening_style: string;
  closing_style: string;
  directness: number;
  warmth: number;
  assertiveness: number;
  data_driven: boolean;
  hedging_frequency: "low" | "moderate" | "high";
  emoji_usage: "never" | "rare" | "occasional" | "frequent";
  rhetorical_style: "analytical" | "narrative" | "persuasive" | "balanced";
  style_summary: string;
  confidence: number;
}

export type FingerprintResponse =
  | WritingStyleFingerprint
  | { status: "not_analyzed" };

// API functions

export async function analyzeWriting(
  samples: string[]
): Promise<WritingStyleFingerprint> {
  const response = await apiClient.post<WritingStyleFingerprint>(
    "/onboarding/writing-analysis/analyze",
    { samples }
  );
  return response.data;
}

export async function getFingerprint(): Promise<FingerprintResponse> {
  const response = await apiClient.get<FingerprintResponse>(
    "/onboarding/writing-analysis/fingerprint"
  );
  return response.data;
}

// Type guard

export function isFingerprint(
  r: FingerprintResponse
): r is WritingStyleFingerprint {
  return "confidence" in r;
}
