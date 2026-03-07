import { useQuery } from "@tanstack/react-query";
import { getCRMStatus, type CRMStatusResponse } from "@/api/intelligence";

export function useCRMStatus() {
  return useQuery<CRMStatusResponse>({
    queryKey: ["intel", "crm-status"],
    queryFn: getCRMStatus,
    staleTime: 5 * 60_000,
  });
}
