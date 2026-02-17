import { useQuery } from '@tanstack/react-query';
import { getStakeholders } from '@/api/stakeholders';

export const stakeholderKeys = {
  all: ['stakeholders'] as const,
};

export function useStakeholders() {
  return useQuery({
    queryKey: stakeholderKeys.all,
    queryFn: getStakeholders,
  });
}
