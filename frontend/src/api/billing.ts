import { apiClient } from "./client";

// Types matching backend Pydantic models

export type SubscriptionStatus =
  | "trial"
  | "active"
  | "past_due"
  | "canceled"
  | "incomplete";

export interface SubscriptionStatusResponse {
  status: SubscriptionStatus;
  plan: string;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  seats_used: number;
}

export interface CheckoutRequest {
  success_url?: string;
  cancel_url?: string;
}

export interface CheckoutResponse {
  url: string;
}

export interface PortalRequest {
  return_url?: string;
}

export interface PortalResponse {
  url: string;
}

export interface Invoice {
  id: string;
  amount: number;
  currency: string;
  status: string;
  date: string | null;
  pdf_url: string | null;
}

export interface InvoicesResponse {
  invoices: Invoice[];
}

// API functions

export async function getBillingStatus(): Promise<SubscriptionStatusResponse> {
  const response = await apiClient.get<SubscriptionStatusResponse>(
    "/billing/status"
  );
  return response.data;
}

export async function createCheckoutSession(
  data: CheckoutRequest = {}
): Promise<CheckoutResponse> {
  const response = await apiClient.post<CheckoutResponse>(
    "/billing/checkout",
    data
  );
  return response.data;
}

export async function createPortalSession(
  data: PortalRequest = {}
): Promise<PortalResponse> {
  const response = await apiClient.post<PortalResponse>(
    "/billing/portal",
    data
  );
  return response.data;
}

export async function getInvoices(limit: number = 12): Promise<InvoicesResponse> {
  const response = await apiClient.get<InvoicesResponse>("/billing/invoices", {
    params: { limit },
  });
  return response.data;
}
