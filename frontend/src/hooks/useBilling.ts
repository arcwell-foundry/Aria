import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationOptions,
  type UseQueryOptions,
} from "@tanstack/react-query";
import {
  createCheckoutSession,
  createPortalSession,
  getBillingStatus,
  getInvoices,
  type CheckoutRequest,
  type Invoice,
  type PortalRequest,
  type SubscriptionStatusResponse,
} from "@/api/billing";

// Query keys
export const billingKeys = {
  all: ["billing"] as const,
  status: () => [...billingKeys.all, "status"] as const,
  invoices: () => [...billingKeys.all, "invoices"] as const,
};

// Billing Status Query
export function useBillingStatus(options?: UseQueryOptions<SubscriptionStatusResponse>) {
  return useQuery({
    queryKey: billingKeys.status(),
    queryFn: getBillingStatus,
    staleTime: 30_000, // 30 seconds
    ...options,
  });
}

// Invoices Query
export function useInvoices(
  limit: number = 12,
  options?: UseQueryOptions<Invoice[]>
) {
  return useQuery({
    queryKey: [...billingKeys.invoices(), limit],
    queryFn: async () => {
      const response = await getInvoices(limit);
      return response.invoices;
    },
    staleTime: 60_000, // 1 minute
    ...options,
  });
}

// Checkout Session Mutation
export function useCheckoutSession(
  options?: UseMutationOptions<{ url: string }, Error, CheckoutRequest>
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CheckoutRequest) => createCheckoutSession(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: billingKeys.status() });
    },
    ...options,
  });
}

// Portal Session Mutation
export function usePortalSession(
  options?: UseMutationOptions<{ url: string }, Error, PortalRequest>
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: PortalRequest) => createPortalSession(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: billingKeys.status() });
    },
    ...options,
  });
}
