import { apiClient } from './client';

export interface FrictionItem {
  friction_id: string;
  level: 'flag' | 'challenge' | 'refuse';
  reasoning: string;
  user_message: string | null;
  original_request: string;
  created_at: string;
}

export interface FrictionRespondResult {
  friction_id: string;
  response: 'approve' | 'modify' | 'cancel';
  status: string;
  proceed: boolean;
}

export async function respondToFriction(
  frictionId: string,
  response: 'approve' | 'modify' | 'cancel',
): Promise<FrictionRespondResult> {
  const { data } = await apiClient.post<FrictionRespondResult>(
    `/friction/${frictionId}/respond`,
    { response },
  );
  return data;
}

export async function getPendingFriction(): Promise<FrictionItem[]> {
  const { data } = await apiClient.get<FrictionItem[]>('/friction/pending');
  return data;
}
