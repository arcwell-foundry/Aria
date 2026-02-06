import { useQuery } from "@tanstack/react-query";
import { getActivationStatus } from "@/api/onboarding";

export const activationKeys = {
  all: ["activation"] as const,
  status: () => [...activationKeys.all, "status"] as const,
};

/**
 * Poll activation status after onboarding completes.
 * Polls every 10s while any agents are still pending/running.
 */
export function useActivationStatus(enabled = true) {
  return useQuery({
    queryKey: activationKeys.status(),
    queryFn: getActivationStatus,
    enabled,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "pending" || status === "running") {
        return 10_000;
      }
      return false;
    },
  });
}
