import { useQuery } from "@tanstack/react-query";
import { getActivationStatus } from "@/api/onboarding";

export const activationKeys = {
  all: ["activation"] as const,
  status: () => [...activationKeys.all, "status"] as const,
};

/**
 * Poll activation status after onboarding completes.
 * Polls every 3s while agents are idle/pending/running.
 * "idle" means the background task hasn't created goals yet — keep polling.
 * Stops only when status is "complete" or "failed".
 */
export function useActivationStatus(enabled = true) {
  return useQuery({
    queryKey: activationKeys.status(),
    queryFn: getActivationStatus,
    enabled,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "complete") {
        return false;
      }
      // Keep polling for idle/pending/running — goals may not exist yet
      return 3_000;
    },
  });
}
