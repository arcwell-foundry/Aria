import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getAriaConfig,
  updateAriaConfig,
  resetPersonality,
  generatePreview,
  type ARIAConfig,
  type ARIAConfigUpdateRequest,
} from "@/api/ariaConfig";

export const ariaConfigKeys = {
  all: ["ariaConfig"] as const,
  detail: () => [...ariaConfigKeys.all, "detail"] as const,
};

export function useAriaConfig() {
  return useQuery({
    queryKey: ariaConfigKeys.detail(),
    queryFn: () => getAriaConfig(),
  });
}

export function useUpdateAriaConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: ARIAConfigUpdateRequest) => updateAriaConfig(data),
    onMutate: async (newData) => {
      await queryClient.cancelQueries({ queryKey: ariaConfigKeys.detail() });

      const previous = queryClient.getQueryData<ARIAConfig>(
        ariaConfigKeys.detail()
      );

      if (previous) {
        queryClient.setQueryData<ARIAConfig>(ariaConfigKeys.detail(), {
          ...previous,
          ...newData,
          updated_at: new Date().toISOString(),
        });
      }

      return { previous };
    },
    onError: (_err, _newData, context) => {
      if (context?.previous) {
        queryClient.setQueryData(ariaConfigKeys.detail(), context.previous);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ariaConfigKeys.detail() });
    },
  });
}

export function useResetPersonality() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => resetPersonality(),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ariaConfigKeys.detail() });
    },
  });
}

export function useGeneratePreview() {
  return useMutation({
    mutationFn: (data: ARIAConfigUpdateRequest) => generatePreview(data),
  });
}
