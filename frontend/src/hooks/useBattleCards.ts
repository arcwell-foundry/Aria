import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  listBattleCards,
  getBattleCard,
  createBattleCard,
  updateBattleCard,
  deleteBattleCard,
  getBattleCardHistory,
  addObjectionHandler,
  type CreateBattleCardData,
  type UpdateBattleCardData,
} from "@/api/battleCards";

// Query keys factory
export const battleCardKeys = {
  all: ["battleCards"] as const,
  lists: () => [...battleCardKeys.all, "list"] as const,
  list: (search?: string) => [...battleCardKeys.lists(), { search }] as const,
  details: () => [...battleCardKeys.all, "detail"] as const,
  detail: (competitorName: string) => [...battleCardKeys.details(), competitorName] as const,
  histories: () => [...battleCardKeys.all, "history"] as const,
  history: (cardId: string) => [...battleCardKeys.histories(), cardId] as const,
};

// List battle cards
export function useBattleCards(search?: string) {
  return useQuery({
    queryKey: battleCardKeys.list(search),
    queryFn: () => listBattleCards(search),
  });
}

// Get single battle card by competitor name
export function useBattleCard(competitorName: string) {
  return useQuery({
    queryKey: battleCardKeys.detail(competitorName),
    queryFn: () => getBattleCard(competitorName),
    enabled: !!competitorName,
  });
}

// Get battle card change history
export function useBattleCardHistory(cardId: string, limit = 20) {
  return useQuery({
    queryKey: battleCardKeys.history(cardId),
    queryFn: () => getBattleCardHistory(cardId, limit),
    enabled: !!cardId,
  });
}

// Create battle card mutation
export function useCreateBattleCard() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CreateBattleCardData) => createBattleCard(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: battleCardKeys.lists() });
    },
  });
}

// Update battle card mutation
export function useUpdateBattleCard() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ cardId, data }: { cardId: string; data: UpdateBattleCardData }) =>
      updateBattleCard(cardId, data),
    onSuccess: (updatedCard) => {
      queryClient.invalidateQueries({ queryKey: battleCardKeys.lists() });
      queryClient.setQueryData(
        battleCardKeys.detail(updatedCard.competitor_name),
        updatedCard
      );
    },
  });
}

// Delete battle card mutation
export function useDeleteBattleCard() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (cardId: string) => deleteBattleCard(cardId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: battleCardKeys.lists() });
    },
  });
}

// Add objection handler mutation
export function useAddObjectionHandler() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      cardId,
      objection,
      response,
    }: {
      cardId: string;
      objection: string;
      response: string;
    }) => addObjectionHandler(cardId, objection, response),
    onSuccess: (updatedCard) => {
      queryClient.invalidateQueries({ queryKey: battleCardKeys.lists() });
      queryClient.setQueryData(
        battleCardKeys.detail(updatedCard.competitor_name),
        updatedCard
      );
      queryClient.invalidateQueries({
        queryKey: battleCardKeys.history(updatedCard.id),
      });
    },
  });
}
