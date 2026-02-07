import { useQuery, type UseQueryOptions } from "@tanstack/react-query";
import {
  getAuditLogs,
  type AuditLogFilters,
  type AuditLogResponse,
} from "@/api/auditLog";

export const auditLogKeys = {
  all: ["auditLog"] as const,
  list: (filters: AuditLogFilters) => [...auditLogKeys.all, "list", filters] as const,
};

export function useAuditLogs(
  filters: AuditLogFilters = {},
  options?: Omit<UseQueryOptions<AuditLogResponse>, "queryKey" | "queryFn">,
) {
  return useQuery({
    queryKey: auditLogKeys.list(filters),
    queryFn: () => getAuditLogs(filters),
    staleTime: 30_000,
    ...options,
  });
}
