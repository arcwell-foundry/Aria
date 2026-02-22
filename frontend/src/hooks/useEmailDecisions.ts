import { useQuery } from "@tanstack/react-query";
import {
  getEmailDecisions,
  type GetEmailDecisionsParams,
} from "@/api/emailDecisions";

export const emailDecisionKeys = {
  all: ["emailDecisions"] as const,
  list: (params?: GetEmailDecisionsParams) =>
    [...emailDecisionKeys.all, params ?? {}] as const,
};

export function useEmailDecisions(params?: GetEmailDecisionsParams) {
  return useQuery({
    queryKey: emailDecisionKeys.list(params),
    queryFn: () => getEmailDecisions(params),
  });
}
