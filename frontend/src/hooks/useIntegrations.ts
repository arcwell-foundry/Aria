import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  connectIntegration,
  disconnectIntegration,
  getAuthUrl,
  listAvailableIntegrations,
  listIntegrations,
  type ConnectIntegrationRequest,
  type IntegrationType,
} from "@/api/integrations";

// Query keys
export const integrationKeys = {
  all: ["integrations"] as const,
  lists: () => [...integrationKeys.all, "list"] as const,
  list: () => [...integrationKeys.lists(), "all"] as const,
  available: () => [...integrationKeys.all, "available"] as const,
};

// List all integrations
export function useIntegrations() {
  return useQuery({
    queryKey: integrationKeys.list(),
    queryFn: () => listIntegrations(),
  });
}

// List available integrations
export function useAvailableIntegrations() {
  return useQuery({
    queryKey: integrationKeys.available(),
    queryFn: () => listAvailableIntegrations(),
  });
}

// Connect integration mutation
export function useConnectIntegration() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      integrationType,
      data,
    }: {
      integrationType: IntegrationType;
      data: ConnectIntegrationRequest;
    }) => connectIntegration(integrationType, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: integrationKeys.lists() });
      queryClient.invalidateQueries({ queryKey: integrationKeys.available() });
    },
  });
}

// Get OAuth auth URL mutation
export function useGetAuthUrl() {
  return useMutation({
    mutationFn: ({
      integrationType,
      redirectUri,
    }: {
      integrationType: IntegrationType;
      redirectUri: string;
    }) => getAuthUrl(integrationType, redirectUri),
  });
}

// Disconnect integration mutation
export function useDisconnectIntegration() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (integrationType: IntegrationType) =>
      disconnectIntegration(integrationType),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: integrationKeys.lists() });
      queryClient.invalidateQueries({ queryKey: integrationKeys.available() });
    },
  });
}
