# US-411: Battle Cards UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a premium, Apple-inspired Battle Cards UI for competitive intelligence at `/dashboard/battlecards`

**Architecture:** Page-based architecture following existing Goals page patterns. React Query for data fetching with query key factory. Component hierarchy: BattleCardsPage → BattleCardGrid/BattleCardDetail → individual card components. Side-by-side comparison via modal overlay. Edit via modal forms.

**Tech Stack:** React 18 / TypeScript / TanStack Query / Tailwind CSS / lucide-react icons

---

## Task 1: Create Battle Cards API Client

**Files:**
- Create: `frontend/src/api/battleCards.ts`

**Step 1: Write the API types and functions**

```typescript
import { apiClient } from "./client";

// Types matching backend models
export interface BattleCardPricing {
  model?: string;
  range?: string;
}

export interface BattleCardDifferentiation {
  area: string;
  our_advantage: string;
}

export interface BattleCardObjectionHandler {
  objection: string;
  response: string;
}

export interface BattleCard {
  id: string;
  company_id: string;
  competitor_name: string;
  competitor_domain: string | null;
  overview: string | null;
  strengths: string[];
  weaknesses: string[];
  pricing: BattleCardPricing;
  differentiation: BattleCardDifferentiation[];
  objection_handlers: BattleCardObjectionHandler[];
  last_updated: string;
  update_source: "manual" | "auto";
}

export interface BattleCardChange {
  id: string;
  battle_card_id: string;
  change_type: string;
  field_name: string;
  old_value: unknown;
  new_value: unknown;
  detected_at: string;
}

export interface CreateBattleCardData {
  competitor_name: string;
  competitor_domain?: string;
  overview?: string;
  strengths?: string[];
  weaknesses?: string[];
  pricing?: BattleCardPricing;
  differentiation?: BattleCardDifferentiation[];
  objection_handlers?: BattleCardObjectionHandler[];
}

export interface UpdateBattleCardData {
  overview?: string;
  strengths?: string[];
  weaknesses?: string[];
  pricing?: BattleCardPricing;
  differentiation?: BattleCardDifferentiation[];
  objection_handlers?: BattleCardObjectionHandler[];
}

// API functions
export async function listBattleCards(search?: string): Promise<BattleCard[]> {
  const params = search ? `?search=${encodeURIComponent(search)}` : "";
  const response = await apiClient.get<BattleCard[]>(`/battlecards${params}`);
  return response.data;
}

export async function getBattleCard(competitorName: string): Promise<BattleCard> {
  const response = await apiClient.get<BattleCard>(
    `/battlecards/${encodeURIComponent(competitorName)}`
  );
  return response.data;
}

export async function createBattleCard(data: CreateBattleCardData): Promise<BattleCard> {
  const response = await apiClient.post<BattleCard>("/battlecards", data);
  return response.data;
}

export async function updateBattleCard(
  cardId: string,
  data: UpdateBattleCardData
): Promise<BattleCard> {
  const response = await apiClient.patch<BattleCard>(`/battlecards/${cardId}`, data);
  return response.data;
}

export async function deleteBattleCard(cardId: string): Promise<void> {
  await apiClient.delete(`/battlecards/${cardId}`);
}

export async function getBattleCardHistory(
  cardId: string,
  limit = 20
): Promise<BattleCardChange[]> {
  const response = await apiClient.get<BattleCardChange[]>(
    `/battlecards/${cardId}/history?limit=${limit}`
  );
  return response.data;
}

export async function addObjectionHandler(
  cardId: string,
  objection: string,
  response: string
): Promise<BattleCard> {
  const res = await apiClient.post<BattleCard>(
    `/battlecards/${cardId}/objections?objection=${encodeURIComponent(objection)}&response=${encodeURIComponent(response)}`
  );
  return res.data;
}
```

**Step 2: Verify types match backend**

Run: `cd frontend && npm run typecheck`
Expected: PASS (no errors in new file)

**Step 3: Commit**

```bash
git add frontend/src/api/battleCards.ts
git commit -m "feat(api): add battle cards API client with types

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Create Battle Cards React Query Hooks

**Files:**
- Create: `frontend/src/hooks/useBattleCards.ts`

**Step 1: Write the React Query hooks**

```typescript
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
```

**Step 2: Verify hooks compile**

Run: `cd frontend && npm run typecheck`
Expected: PASS

**Step 3: Commit**

```bash
git add frontend/src/hooks/useBattleCards.ts
git commit -m "feat(hooks): add React Query hooks for battle cards

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Create Battle Card Grid Item Component

**Files:**
- Create: `frontend/src/components/battleCards/BattleCardGridItem.tsx`

**Step 1: Write the grid item component**

```typescript
import type { BattleCard } from "@/api/battleCards";

interface BattleCardGridItemProps {
  card: BattleCard;
  onView: () => void;
  onCompare: () => void;
  isSelected?: boolean;
}

export function BattleCardGridItem({
  card,
  onView,
  onCompare,
  isSelected = false,
}: BattleCardGridItemProps) {
  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  };

  return (
    <div
      className={`group relative bg-slate-800/50 border rounded-2xl p-6 transition-all duration-300 ease-out cursor-pointer hover:bg-slate-800/80 hover:shadow-xl hover:shadow-slate-900/50 hover:-translate-y-1 ${
        isSelected
          ? "border-primary-500 ring-2 ring-primary-500/20"
          : "border-slate-700 hover:border-slate-600"
      }`}
      onClick={onView}
    >
      {/* Gradient border effect on hover */}
      <div className="absolute inset-0 rounded-2xl bg-gradient-to-br from-primary-500/0 via-primary-500/5 to-accent-500/0 opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none" />

      {/* Header */}
      <div className="relative flex items-start justify-between gap-4 mb-5">
        <div className="flex-1 min-w-0">
          <h3 className="text-xl font-semibold text-white truncate group-hover:text-primary-400 transition-colors duration-200">
            {card.competitor_name}
          </h3>
          {card.competitor_domain && (
            <p className="mt-1 text-sm text-slate-500 truncate">{card.competitor_domain}</p>
          )}
        </div>

        {/* Compare button */}
        <button
          onClick={(e) => {
            e.stopPropagation();
            onCompare();
          }}
          className={`shrink-0 p-2.5 rounded-xl transition-all duration-200 ${
            isSelected
              ? "bg-primary-600 text-white"
              : "text-slate-400 hover:text-white hover:bg-slate-700"
          }`}
          title={isSelected ? "Selected for comparison" : "Add to comparison"}
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
            />
          </svg>
        </button>
      </div>

      {/* Overview excerpt */}
      {card.overview && (
        <p className="relative text-sm text-slate-400 line-clamp-2 mb-5 leading-relaxed">
          {card.overview}
        </p>
      )}

      {/* Strengths/Weaknesses summary */}
      <div className="relative grid grid-cols-2 gap-4 mb-5">
        <div className="flex items-center gap-2">
          <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-emerald-500/10">
            <svg
              className="w-4 h-4 text-emerald-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M5 13l4 4L19 7"
              />
            </svg>
          </div>
          <span className="text-sm text-slate-300">
            <span className="font-medium text-emerald-400">{card.strengths.length}</span>{" "}
            strengths
          </span>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-amber-500/10">
            <svg
              className="w-4 h-4 text-amber-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
          </div>
          <span className="text-sm text-slate-300">
            <span className="font-medium text-amber-400">{card.weaknesses.length}</span>{" "}
            weaknesses
          </span>
        </div>
      </div>

      {/* Pricing badge */}
      {card.pricing?.model && (
        <div className="relative inline-flex items-center gap-2 px-3 py-1.5 bg-slate-700/50 rounded-lg text-sm mb-5">
          <svg
            className="w-4 h-4 text-slate-400"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <span className="text-slate-300">{card.pricing.model}</span>
          {card.pricing.range && (
            <span className="text-slate-500">· {card.pricing.range}</span>
          )}
        </div>
      )}

      {/* Footer */}
      <div className="relative flex items-center justify-between pt-4 border-t border-slate-700/50">
        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium ${
              card.update_source === "auto"
                ? "bg-primary-500/10 text-primary-400"
                : "bg-slate-600/50 text-slate-400"
            }`}
          >
            {card.update_source === "auto" ? (
              <>
                <span className="relative flex h-1.5 w-1.5">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-primary-400" />
                </span>
                Auto-updated
              </>
            ) : (
              "Manual"
            )}
          </span>
        </div>
        <span className="text-xs text-slate-500">Updated {formatDate(card.last_updated)}</span>
      </div>
    </div>
  );
}
```

**Step 2: Verify component compiles**

Run: `cd frontend && npm run typecheck`
Expected: PASS

**Step 3: Commit**

```bash
git add frontend/src/components/battleCards/BattleCardGridItem.tsx
git commit -m "feat(ui): add BattleCardGridItem component with hover effects

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Create Empty State Component

**Files:**
- Create: `frontend/src/components/battleCards/EmptyBattleCards.tsx`

**Step 1: Write the empty state component**

```typescript
interface EmptyBattleCardsProps {
  onCreateClick: () => void;
  hasSearchFilter?: boolean;
}

export function EmptyBattleCards({ onCreateClick, hasSearchFilter = false }: EmptyBattleCardsProps) {
  if (hasSearchFilter) {
    return (
      <div className="flex flex-col items-center justify-center py-16 px-4">
        <div className="relative">
          <div className="absolute inset-0 bg-slate-500/10 blur-3xl rounded-full" />
          <div className="relative w-20 h-20 bg-slate-800 border border-slate-700 rounded-2xl flex items-center justify-center">
            <svg
              className="w-10 h-10 text-slate-500"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
              />
            </svg>
          </div>
        </div>

        <h3 className="mt-6 text-xl font-semibold text-white">No matches found</h3>
        <p className="mt-2 text-slate-400 text-center max-w-md">
          No battle cards match your search. Try adjusting your search terms or add a new competitor.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center py-16 px-4">
      {/* Illustration */}
      <div className="relative">
        <div className="absolute inset-0 bg-primary-500/20 blur-3xl rounded-full" />
        <div className="relative w-24 h-24 bg-slate-800 border border-slate-700 rounded-2xl flex items-center justify-center">
          <svg
            className="w-12 h-12 text-slate-500"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
            />
          </svg>
        </div>
      </div>

      {/* Text */}
      <h3 className="mt-6 text-xl font-semibold text-white">No battle cards yet</h3>
      <p className="mt-2 text-slate-400 text-center max-w-md">
        Add your first competitor to start building your competitive intelligence library. ARIA will
        help you stay ahead of the competition.
      </p>

      {/* CTA */}
      <button
        onClick={onCreateClick}
        className="mt-6 inline-flex items-center gap-2 px-5 py-2.5 bg-primary-600 hover:bg-primary-500 text-white font-medium rounded-xl transition-all duration-200 shadow-lg shadow-primary-600/25 hover:shadow-primary-500/30"
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
        </svg>
        Add your first competitor
      </button>
    </div>
  );
}
```

**Step 2: Verify component compiles**

Run: `cd frontend && npm run typecheck`
Expected: PASS

**Step 3: Commit**

```bash
git add frontend/src/components/battleCards/EmptyBattleCards.tsx
git commit -m "feat(ui): add EmptyBattleCards component with search variant

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Create Battle Card Detail Modal

**Files:**
- Create: `frontend/src/components/battleCards/BattleCardDetailModal.tsx`

**Step 1: Write the detail modal component**

```typescript
import { useState, useEffect, useCallback } from "react";
import type { BattleCard } from "@/api/battleCards";
import { useBattleCardHistory } from "@/hooks/useBattleCards";

interface BattleCardDetailModalProps {
  card: BattleCard | null;
  isOpen: boolean;
  onClose: () => void;
  onEdit: () => void;
}

type TabId = "overview" | "differentiation" | "objections" | "history";

export function BattleCardDetailModal({
  card,
  isOpen,
  onClose,
  onEdit,
}: BattleCardDetailModalProps) {
  const [activeTab, setActiveTab] = useState<TabId>("overview");

  const { data: history, isLoading: historyLoading } = useBattleCardHistory(
    card?.id ?? "",
    20
  );

  // Handle escape key
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    },
    [onClose]
  );

  useEffect(() => {
    if (isOpen) {
      document.addEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "hidden";
      return () => {
        document.removeEventListener("keydown", handleKeyDown);
        document.body.style.overflow = "";
      };
    }
  }, [isOpen, handleKeyDown]);

  // Reset tab when card changes
  useEffect(() => {
    setActiveTab("overview");
  }, [card?.id]);

  if (!isOpen || !card) return null;

  const tabs: { id: TabId; label: string }[] = [
    { id: "overview", label: "Overview" },
    { id: "differentiation", label: "Differentiation" },
    { id: "objections", label: "Objection Handlers" },
    { id: "history", label: "History" },
  ];

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-4xl max-h-[90vh] mx-4 bg-slate-800 border border-slate-700 rounded-2xl shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="shrink-0 flex items-start justify-between gap-4 px-6 py-5 border-b border-slate-700">
          <div className="flex-1 min-w-0">
            <h2 className="text-2xl font-bold text-white">{card.competitor_name}</h2>
            {card.competitor_domain && (
              <p className="mt-1 text-slate-400">{card.competitor_domain}</p>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={onEdit}
              className="inline-flex items-center gap-2 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white text-sm font-medium rounded-xl transition-colors"
            >
              <svg
                className="w-4 h-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
                />
              </svg>
              Edit
            </button>
            <button
              onClick={onClose}
              className="p-2 text-slate-400 hover:text-white hover:bg-slate-700 rounded-xl transition-colors"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="shrink-0 flex gap-1 px-6 pt-4 border-b border-slate-700">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2.5 text-sm font-medium rounded-t-lg transition-colors ${
                activeTab === tab.id
                  ? "bg-slate-700 text-white"
                  : "text-slate-400 hover:text-white hover:bg-slate-700/50"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {activeTab === "overview" && (
            <div className="space-y-6">
              {/* Overview text */}
              {card.overview && (
                <div>
                  <h4 className="text-sm font-medium text-slate-400 uppercase tracking-wide mb-2">
                    Overview
                  </h4>
                  <p className="text-slate-300 leading-relaxed">{card.overview}</p>
                </div>
              )}

              {/* Strengths and Weaknesses side by side */}
              <div className="grid md:grid-cols-2 gap-6">
                {/* Strengths */}
                <div>
                  <div className="flex items-center gap-2 mb-3">
                    <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-emerald-500/10">
                      <svg
                        className="w-4 h-4 text-emerald-400"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M5 13l4 4L19 7"
                        />
                      </svg>
                    </div>
                    <h4 className="text-sm font-medium text-emerald-400 uppercase tracking-wide">
                      Their Strengths
                    </h4>
                  </div>
                  {card.strengths.length > 0 ? (
                    <ul className="space-y-2">
                      {card.strengths.map((strength, idx) => (
                        <li
                          key={idx}
                          className="flex items-start gap-3 p-3 bg-emerald-500/5 border border-emerald-500/10 rounded-xl"
                        >
                          <span className="shrink-0 w-1.5 h-1.5 mt-2 rounded-full bg-emerald-400" />
                          <span className="text-slate-300">{strength}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-slate-500 italic">No strengths documented</p>
                  )}
                </div>

                {/* Weaknesses */}
                <div>
                  <div className="flex items-center gap-2 mb-3">
                    <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-amber-500/10">
                      <svg
                        className="w-4 h-4 text-amber-400"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                        />
                      </svg>
                    </div>
                    <h4 className="text-sm font-medium text-amber-400 uppercase tracking-wide">
                      Their Weaknesses
                    </h4>
                  </div>
                  {card.weaknesses.length > 0 ? (
                    <ul className="space-y-2">
                      {card.weaknesses.map((weakness, idx) => (
                        <li
                          key={idx}
                          className="flex items-start gap-3 p-3 bg-amber-500/5 border border-amber-500/10 rounded-xl"
                        >
                          <span className="shrink-0 w-1.5 h-1.5 mt-2 rounded-full bg-amber-400" />
                          <span className="text-slate-300">{weakness}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-slate-500 italic">No weaknesses documented</p>
                  )}
                </div>
              </div>

              {/* Pricing */}
              {(card.pricing?.model || card.pricing?.range) && (
                <div>
                  <h4 className="text-sm font-medium text-slate-400 uppercase tracking-wide mb-3">
                    Pricing
                  </h4>
                  <div className="inline-flex items-center gap-3 px-4 py-3 bg-slate-700/50 rounded-xl">
                    <svg
                      className="w-5 h-5 text-slate-400"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                      />
                    </svg>
                    <div>
                      {card.pricing.model && (
                        <span className="font-medium text-white">{card.pricing.model}</span>
                      )}
                      {card.pricing.range && (
                        <span className="text-slate-400 ml-2">{card.pricing.range}</span>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {activeTab === "differentiation" && (
            <div className="space-y-4">
              <h4 className="text-sm font-medium text-slate-400 uppercase tracking-wide mb-4">
                How We Win Against {card.competitor_name}
              </h4>
              {card.differentiation.length > 0 ? (
                <div className="space-y-3">
                  {card.differentiation.map((diff, idx) => (
                    <div
                      key={idx}
                      className="p-4 bg-primary-500/5 border border-primary-500/10 rounded-xl"
                    >
                      <div className="flex items-center gap-2 mb-2">
                        <div className="flex items-center justify-center w-6 h-6 rounded-md bg-primary-500/20">
                          <svg
                            className="w-3.5 h-3.5 text-primary-400"
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M13 10V3L4 14h7v7l9-11h-7z"
                            />
                          </svg>
                        </div>
                        <h5 className="font-medium text-primary-400">{diff.area}</h5>
                      </div>
                      <p className="text-slate-300 pl-8">{diff.our_advantage}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-slate-500 italic">
                  No differentiation points documented yet. Add areas where you have an advantage.
                </p>
              )}
            </div>
          )}

          {activeTab === "objections" && (
            <div className="space-y-4">
              <h4 className="text-sm font-medium text-slate-400 uppercase tracking-wide mb-4">
                Common Objections & Responses
              </h4>
              {card.objection_handlers.length > 0 ? (
                <div className="space-y-4">
                  {card.objection_handlers.map((handler, idx) => (
                    <div
                      key={idx}
                      className="rounded-xl border border-slate-700 overflow-hidden"
                    >
                      <div className="px-4 py-3 bg-red-500/5 border-b border-slate-700">
                        <div className="flex items-start gap-3">
                          <div className="shrink-0 flex items-center justify-center w-6 h-6 rounded-md bg-red-500/20 mt-0.5">
                            <svg
                              className="w-3.5 h-3.5 text-red-400"
                              fill="none"
                              stroke="currentColor"
                              viewBox="0 0 24 24"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                              />
                            </svg>
                          </div>
                          <p className="text-red-300 font-medium">"{handler.objection}"</p>
                        </div>
                      </div>
                      <div className="px-4 py-3 bg-emerald-500/5">
                        <div className="flex items-start gap-3">
                          <div className="shrink-0 flex items-center justify-center w-6 h-6 rounded-md bg-emerald-500/20 mt-0.5">
                            <svg
                              className="w-3.5 h-3.5 text-emerald-400"
                              fill="none"
                              stroke="currentColor"
                              viewBox="0 0 24 24"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                              />
                            </svg>
                          </div>
                          <p className="text-emerald-300">{handler.response}</p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-slate-500 italic">
                  No objection handlers documented yet. Add common objections and your winning responses.
                </p>
              )}
            </div>
          )}

          {activeTab === "history" && (
            <div className="space-y-4">
              <h4 className="text-sm font-medium text-slate-400 uppercase tracking-wide mb-4">
                Change History
              </h4>
              {historyLoading ? (
                <div className="space-y-3">
                  {[1, 2, 3].map((i) => (
                    <div key={i} className="animate-pulse flex gap-4 p-4 bg-slate-700/30 rounded-xl">
                      <div className="w-10 h-10 bg-slate-700 rounded-lg" />
                      <div className="flex-1 space-y-2">
                        <div className="h-4 bg-slate-700 rounded w-1/3" />
                        <div className="h-3 bg-slate-700 rounded w-1/4" />
                      </div>
                    </div>
                  ))}
                </div>
              ) : history && history.length > 0 ? (
                <div className="space-y-3">
                  {history.map((change) => (
                    <div
                      key={change.id}
                      className="flex gap-4 p-4 bg-slate-700/30 rounded-xl"
                    >
                      <div className="shrink-0 flex items-center justify-center w-10 h-10 bg-slate-700 rounded-lg">
                        <svg
                          className="w-5 h-5 text-slate-400"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
                          />
                        </svg>
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-white font-medium">
                          {change.field_name.replace(/_/g, " ")} updated
                        </p>
                        <p className="text-sm text-slate-400 mt-0.5">
                          {formatDate(change.detected_at)}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-slate-500 italic">No changes recorded yet.</p>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="shrink-0 flex items-center justify-between px-6 py-4 border-t border-slate-700 bg-slate-800/50">
          <span className="text-sm text-slate-500">
            Last updated {formatDate(card.last_updated)}
          </span>
          <span
            className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium ${
              card.update_source === "auto"
                ? "bg-primary-500/10 text-primary-400"
                : "bg-slate-600/50 text-slate-400"
            }`}
          >
            {card.update_source === "auto" ? "Auto-updated by Scout" : "Manually updated"}
          </span>
        </div>
      </div>
    </div>
  );
}
```

**Step 2: Verify component compiles**

Run: `cd frontend && npm run typecheck`
Expected: PASS

**Step 3: Commit**

```bash
git add frontend/src/components/battleCards/BattleCardDetailModal.tsx
git commit -m "feat(ui): add BattleCardDetailModal with tabs for overview/diff/objections/history

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Create Battle Card Comparison Modal

**Files:**
- Create: `frontend/src/components/battleCards/BattleCardCompareModal.tsx`

**Step 1: Write the comparison modal**

```typescript
import { useEffect, useCallback } from "react";
import type { BattleCard } from "@/api/battleCards";

interface BattleCardCompareModalProps {
  cards: BattleCard[];
  isOpen: boolean;
  onClose: () => void;
}

export function BattleCardCompareModal({
  cards,
  isOpen,
  onClose,
}: BattleCardCompareModalProps) {
  // Handle escape key
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    },
    [onClose]
  );

  useEffect(() => {
    if (isOpen) {
      document.addEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "hidden";
      return () => {
        document.removeEventListener("keydown", handleKeyDown);
        document.body.style.overflow = "";
      };
    }
  }, [isOpen, handleKeyDown]);

  if (!isOpen || cards.length < 2) return null;

  const [cardA, cardB] = cards;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-6xl max-h-[90vh] mx-4 bg-slate-800 border border-slate-700 rounded-2xl shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="shrink-0 flex items-center justify-between gap-4 px-6 py-5 border-b border-slate-700">
          <h2 className="text-xl font-bold text-white">Compare Competitors</h2>
          <button
            onClick={onClose}
            className="p-2 text-slate-400 hover:text-white hover:bg-slate-700 rounded-xl transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {/* Competitor names header */}
          <div className="grid grid-cols-2 gap-6 mb-6">
            <div className="text-center">
              <h3 className="text-2xl font-bold text-white">{cardA.competitor_name}</h3>
              {cardA.competitor_domain && (
                <p className="text-sm text-slate-400 mt-1">{cardA.competitor_domain}</p>
              )}
            </div>
            <div className="text-center">
              <h3 className="text-2xl font-bold text-white">{cardB.competitor_name}</h3>
              {cardB.competitor_domain && (
                <p className="text-sm text-slate-400 mt-1">{cardB.competitor_domain}</p>
              )}
            </div>
          </div>

          {/* Divider */}
          <div className="flex items-center gap-4 mb-8">
            <div className="flex-1 h-px bg-slate-700" />
            <span className="text-sm font-medium text-slate-500 uppercase tracking-wide">vs</span>
            <div className="flex-1 h-px bg-slate-700" />
          </div>

          {/* Comparison sections */}
          <div className="space-y-8">
            {/* Strengths */}
            <div>
              <h4 className="flex items-center gap-2 text-sm font-medium text-emerald-400 uppercase tracking-wide mb-4">
                <div className="flex items-center justify-center w-6 h-6 rounded-md bg-emerald-500/20">
                  <svg
                    className="w-3.5 h-3.5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M5 13l4 4L19 7"
                    />
                  </svg>
                </div>
                Their Strengths
              </h4>
              <div className="grid grid-cols-2 gap-6">
                <CompareList items={cardA.strengths} color="emerald" />
                <CompareList items={cardB.strengths} color="emerald" />
              </div>
            </div>

            {/* Weaknesses */}
            <div>
              <h4 className="flex items-center gap-2 text-sm font-medium text-amber-400 uppercase tracking-wide mb-4">
                <div className="flex items-center justify-center w-6 h-6 rounded-md bg-amber-500/20">
                  <svg
                    className="w-3.5 h-3.5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                    />
                  </svg>
                </div>
                Their Weaknesses
              </h4>
              <div className="grid grid-cols-2 gap-6">
                <CompareList items={cardA.weaknesses} color="amber" />
                <CompareList items={cardB.weaknesses} color="amber" />
              </div>
            </div>

            {/* Pricing */}
            <div>
              <h4 className="flex items-center gap-2 text-sm font-medium text-slate-400 uppercase tracking-wide mb-4">
                <div className="flex items-center justify-center w-6 h-6 rounded-md bg-slate-600">
                  <svg
                    className="w-3.5 h-3.5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                    />
                  </svg>
                </div>
                Pricing
              </h4>
              <div className="grid grid-cols-2 gap-6">
                <PricingDisplay pricing={cardA.pricing} />
                <PricingDisplay pricing={cardB.pricing} />
              </div>
            </div>

            {/* Differentiation */}
            <div>
              <h4 className="flex items-center gap-2 text-sm font-medium text-primary-400 uppercase tracking-wide mb-4">
                <div className="flex items-center justify-center w-6 h-6 rounded-md bg-primary-500/20">
                  <svg
                    className="w-3.5 h-3.5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M13 10V3L4 14h7v7l9-11h-7z"
                    />
                  </svg>
                </div>
                Our Differentiation
              </h4>
              <div className="grid grid-cols-2 gap-6">
                <DifferentiationList items={cardA.differentiation} />
                <DifferentiationList items={cardB.differentiation} />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function CompareList({ items, color }: { items: string[]; color: "emerald" | "amber" }) {
  const colorClasses = {
    emerald: {
      bg: "bg-emerald-500/5",
      border: "border-emerald-500/10",
      dot: "bg-emerald-400",
    },
    amber: {
      bg: "bg-amber-500/5",
      border: "border-amber-500/10",
      dot: "bg-amber-400",
    },
  };

  const c = colorClasses[color];

  if (items.length === 0) {
    return <p className="text-slate-500 italic text-sm">None documented</p>;
  }

  return (
    <ul className="space-y-2">
      {items.map((item, idx) => (
        <li
          key={idx}
          className={`flex items-start gap-3 p-3 ${c.bg} border ${c.border} rounded-xl`}
        >
          <span className={`shrink-0 w-1.5 h-1.5 mt-2 rounded-full ${c.dot}`} />
          <span className="text-sm text-slate-300">{item}</span>
        </li>
      ))}
    </ul>
  );
}

function PricingDisplay({ pricing }: { pricing: { model?: string; range?: string } }) {
  if (!pricing?.model && !pricing?.range) {
    return <p className="text-slate-500 italic text-sm">No pricing info</p>;
  }

  return (
    <div className="inline-flex items-center gap-3 px-4 py-3 bg-slate-700/50 rounded-xl">
      <div>
        {pricing.model && <span className="font-medium text-white">{pricing.model}</span>}
        {pricing.range && <span className="text-slate-400 ml-2">{pricing.range}</span>}
      </div>
    </div>
  );
}

function DifferentiationList({
  items,
}: {
  items: { area: string; our_advantage: string }[];
}) {
  if (items.length === 0) {
    return <p className="text-slate-500 italic text-sm">None documented</p>;
  }

  return (
    <div className="space-y-3">
      {items.map((diff, idx) => (
        <div
          key={idx}
          className="p-3 bg-primary-500/5 border border-primary-500/10 rounded-xl"
        >
          <h5 className="font-medium text-primary-400 text-sm">{diff.area}</h5>
          <p className="text-sm text-slate-300 mt-1">{diff.our_advantage}</p>
        </div>
      ))}
    </div>
  );
}
```

**Step 2: Verify component compiles**

Run: `cd frontend && npm run typecheck`
Expected: PASS

**Step 3: Commit**

```bash
git add frontend/src/components/battleCards/BattleCardCompareModal.tsx
git commit -m "feat(ui): add BattleCardCompareModal for side-by-side competitor comparison

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Create Battle Card Edit Modal

**Files:**
- Create: `frontend/src/components/battleCards/BattleCardEditModal.tsx`

**Step 1: Write the edit modal component**

```typescript
import { useState, useEffect, useCallback } from "react";
import type { BattleCard, UpdateBattleCardData, CreateBattleCardData } from "@/api/battleCards";

interface BattleCardEditModalProps {
  card: BattleCard | null;
  isOpen: boolean;
  onClose: () => void;
  onSave: (data: UpdateBattleCardData | CreateBattleCardData) => void;
  isLoading?: boolean;
  mode: "create" | "edit";
}

export function BattleCardEditModal({
  card,
  isOpen,
  onClose,
  onSave,
  isLoading = false,
  mode,
}: BattleCardEditModalProps) {
  const [competitorName, setCompetitorName] = useState("");
  const [competitorDomain, setCompetitorDomain] = useState("");
  const [overview, setOverview] = useState("");
  const [strengths, setStrengths] = useState<string[]>([]);
  const [weaknesses, setWeaknesses] = useState<string[]>([]);
  const [pricingModel, setPricingModel] = useState("");
  const [pricingRange, setPricingRange] = useState("");

  // Initialize form when card changes or modal opens
  useEffect(() => {
    if (isOpen && card && mode === "edit") {
      setCompetitorName(card.competitor_name);
      setCompetitorDomain(card.competitor_domain || "");
      setOverview(card.overview || "");
      setStrengths(card.strengths);
      setWeaknesses(card.weaknesses);
      setPricingModel(card.pricing?.model || "");
      setPricingRange(card.pricing?.range || "");
    } else if (isOpen && mode === "create") {
      setCompetitorName("");
      setCompetitorDomain("");
      setOverview("");
      setStrengths([]);
      setWeaknesses([]);
      setPricingModel("");
      setPricingRange("");
    }
  }, [isOpen, card, mode]);

  // Handle escape key
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape" && !isLoading) {
        onClose();
      }
    },
    [onClose, isLoading]
  );

  useEffect(() => {
    if (isOpen) {
      document.addEventListener("keydown", handleKeyDown);
      return () => document.removeEventListener("keydown", handleKeyDown);
    }
  }, [isOpen, handleKeyDown]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (mode === "create" && !competitorName.trim()) return;

    const data: UpdateBattleCardData | CreateBattleCardData =
      mode === "create"
        ? {
            competitor_name: competitorName.trim(),
            competitor_domain: competitorDomain.trim() || undefined,
            overview: overview.trim() || undefined,
            strengths,
            weaknesses,
            pricing: {
              model: pricingModel.trim() || undefined,
              range: pricingRange.trim() || undefined,
            },
          }
        : {
            overview: overview.trim() || undefined,
            strengths,
            weaknesses,
            pricing: {
              model: pricingModel.trim() || undefined,
              range: pricingRange.trim() || undefined,
            },
          };

    onSave(data);
  };

  const addStrength = () => setStrengths([...strengths, ""]);
  const updateStrength = (idx: number, value: string) => {
    const updated = [...strengths];
    updated[idx] = value;
    setStrengths(updated);
  };
  const removeStrength = (idx: number) => setStrengths(strengths.filter((_, i) => i !== idx));

  const addWeakness = () => setWeaknesses([...weaknesses, ""]);
  const updateWeakness = (idx: number, value: string) => {
    const updated = [...weaknesses];
    updated[idx] = value;
    setWeaknesses(updated);
  };
  const removeWeakness = (idx: number) => setWeaknesses(weaknesses.filter((_, i) => i !== idx));

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={isLoading ? undefined : onClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-2xl max-h-[90vh] mx-4 bg-slate-800 border border-slate-700 rounded-2xl shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="shrink-0 flex items-center justify-between px-6 py-4 border-b border-slate-700">
          <h2 className="text-xl font-semibold text-white">
            {mode === "create" ? "Add Competitor" : `Edit ${card?.competitor_name}`}
          </h2>
          <button
            onClick={onClose}
            disabled={isLoading}
            className="p-2 text-slate-400 hover:text-white hover:bg-slate-700 rounded-xl transition-colors disabled:opacity-50"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto">
          <div className="px-6 py-5 space-y-6">
            {/* Basic Info */}
            {mode === "create" && (
              <div className="grid sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1.5">
                    Competitor Name <span className="text-red-400">*</span>
                  </label>
                  <input
                    type="text"
                    value={competitorName}
                    onChange={(e) => setCompetitorName(e.target.value)}
                    placeholder="e.g., Acme Corp"
                    className="w-full px-4 py-2.5 bg-slate-900 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all"
                    required
                    disabled={isLoading}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1.5">
                    Website Domain
                  </label>
                  <input
                    type="text"
                    value={competitorDomain}
                    onChange={(e) => setCompetitorDomain(e.target.value)}
                    placeholder="e.g., acme.com"
                    className="w-full px-4 py-2.5 bg-slate-900 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all"
                    disabled={isLoading}
                  />
                </div>
              </div>
            )}

            {/* Overview */}
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5">
                Overview
              </label>
              <textarea
                value={overview}
                onChange={(e) => setOverview(e.target.value)}
                placeholder="Brief description of this competitor..."
                rows={3}
                className="w-full px-4 py-2.5 bg-slate-900 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all resize-none"
                disabled={isLoading}
              />
            </div>

            {/* Pricing */}
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5">
                Pricing
              </label>
              <div className="grid sm:grid-cols-2 gap-4">
                <input
                  type="text"
                  value={pricingModel}
                  onChange={(e) => setPricingModel(e.target.value)}
                  placeholder="Model (e.g., Per seat)"
                  className="w-full px-4 py-2.5 bg-slate-900 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all"
                  disabled={isLoading}
                />
                <input
                  type="text"
                  value={pricingRange}
                  onChange={(e) => setPricingRange(e.target.value)}
                  placeholder="Range (e.g., $50-200/user/mo)"
                  className="w-full px-4 py-2.5 bg-slate-900 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all"
                  disabled={isLoading}
                />
              </div>
            </div>

            {/* Strengths */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-sm font-medium text-emerald-400">Their Strengths</label>
                <button
                  type="button"
                  onClick={addStrength}
                  disabled={isLoading}
                  className="text-sm text-primary-400 hover:text-primary-300 disabled:opacity-50"
                >
                  + Add strength
                </button>
              </div>
              <div className="space-y-2">
                {strengths.map((strength, idx) => (
                  <div key={idx} className="flex gap-2">
                    <input
                      type="text"
                      value={strength}
                      onChange={(e) => updateStrength(idx, e.target.value)}
                      placeholder="Enter a strength..."
                      className="flex-1 px-4 py-2.5 bg-slate-900 border border-emerald-500/20 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/50 focus:border-transparent transition-all"
                      disabled={isLoading}
                    />
                    <button
                      type="button"
                      onClick={() => removeStrength(idx)}
                      disabled={isLoading}
                      className="p-2.5 text-slate-400 hover:text-red-400 hover:bg-red-500/10 rounded-xl transition-colors disabled:opacity-50"
                    >
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                        />
                      </svg>
                    </button>
                  </div>
                ))}
                {strengths.length === 0 && (
                  <p className="text-sm text-slate-500 italic">No strengths added yet</p>
                )}
              </div>
            </div>

            {/* Weaknesses */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-sm font-medium text-amber-400">Their Weaknesses</label>
                <button
                  type="button"
                  onClick={addWeakness}
                  disabled={isLoading}
                  className="text-sm text-primary-400 hover:text-primary-300 disabled:opacity-50"
                >
                  + Add weakness
                </button>
              </div>
              <div className="space-y-2">
                {weaknesses.map((weakness, idx) => (
                  <div key={idx} className="flex gap-2">
                    <input
                      type="text"
                      value={weakness}
                      onChange={(e) => updateWeakness(idx, e.target.value)}
                      placeholder="Enter a weakness..."
                      className="flex-1 px-4 py-2.5 bg-slate-900 border border-amber-500/20 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-500/50 focus:border-transparent transition-all"
                      disabled={isLoading}
                    />
                    <button
                      type="button"
                      onClick={() => removeWeakness(idx)}
                      disabled={isLoading}
                      className="p-2.5 text-slate-400 hover:text-red-400 hover:bg-red-500/10 rounded-xl transition-colors disabled:opacity-50"
                    >
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                        />
                      </svg>
                    </button>
                  </div>
                ))}
                {weaknesses.length === 0 && (
                  <p className="text-sm text-slate-500 italic">No weaknesses added yet</p>
                )}
              </div>
            </div>
          </div>

          {/* Footer */}
          <div className="shrink-0 flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-700">
            <button
              type="button"
              onClick={onClose}
              disabled={isLoading}
              className="px-4 py-2 text-sm font-medium text-slate-400 hover:text-white hover:bg-slate-700 rounded-xl transition-colors disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isLoading || (mode === "create" && !competitorName.trim())}
              className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium bg-primary-600 hover:bg-primary-500 text-white rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isLoading ? (
                <>
                  <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                    />
                  </svg>
                  Saving...
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M5 13l4 4L19 7"
                    />
                  </svg>
                  {mode === "create" ? "Add Competitor" : "Save Changes"}
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
```

**Step 2: Verify component compiles**

Run: `cd frontend && npm run typecheck`
Expected: PASS

**Step 3: Commit**

```bash
git add frontend/src/components/battleCards/BattleCardEditModal.tsx
git commit -m "feat(ui): add BattleCardEditModal for creating and editing competitors

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Create Components Barrel Export

**Files:**
- Create: `frontend/src/components/battleCards/index.ts`

**Step 1: Write the barrel export**

```typescript
export { BattleCardGridItem } from "./BattleCardGridItem";
export { BattleCardDetailModal } from "./BattleCardDetailModal";
export { BattleCardCompareModal } from "./BattleCardCompareModal";
export { BattleCardEditModal } from "./BattleCardEditModal";
export { EmptyBattleCards } from "./EmptyBattleCards";
```

**Step 2: Verify exports compile**

Run: `cd frontend && npm run typecheck`
Expected: PASS

**Step 3: Commit**

```bash
git add frontend/src/components/battleCards/index.ts
git commit -m "feat(ui): add barrel export for battleCards components

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 9: Create Battle Cards Page

**Files:**
- Create: `frontend/src/pages/BattleCards.tsx`

**Step 1: Write the page component**

```typescript
import { useState, useMemo } from "react";
import type { BattleCard, CreateBattleCardData, UpdateBattleCardData } from "@/api/battleCards";
import { DashboardLayout } from "@/components/DashboardLayout";
import {
  BattleCardGridItem,
  BattleCardDetailModal,
  BattleCardCompareModal,
  BattleCardEditModal,
  EmptyBattleCards,
} from "@/components/battleCards";
import {
  useBattleCards,
  useCreateBattleCard,
  useUpdateBattleCard,
  useDeleteBattleCard,
} from "@/hooks/useBattleCards";

export function BattleCardsPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCard, setSelectedCard] = useState<BattleCard | null>(null);
  const [compareCards, setCompareCards] = useState<BattleCard[]>([]);
  const [editingCard, setEditingCard] = useState<BattleCard | null>(null);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isDetailModalOpen, setIsDetailModalOpen] = useState(false);
  const [isCompareModalOpen, setIsCompareModalOpen] = useState(false);

  // Queries
  const { data: battleCards, isLoading, error } = useBattleCards(
    searchQuery.trim() || undefined
  );

  // Mutations
  const createBattleCard = useCreateBattleCard();
  const updateBattleCard = useUpdateBattleCard();
  const deleteBattleCard = useDeleteBattleCard();

  // Filter cards based on search (already filtered by API, but keep for instant feedback)
  const filteredCards = useMemo(() => {
    if (!battleCards) return [];
    if (!searchQuery.trim()) return battleCards;
    const query = searchQuery.toLowerCase();
    return battleCards.filter((card) =>
      card.competitor_name.toLowerCase().includes(query)
    );
  }, [battleCards, searchQuery]);

  const handleViewCard = (card: BattleCard) => {
    setSelectedCard(card);
    setIsDetailModalOpen(true);
  };

  const handleToggleCompare = (card: BattleCard) => {
    setCompareCards((prev) => {
      const isSelected = prev.some((c) => c.id === card.id);
      if (isSelected) {
        return prev.filter((c) => c.id !== card.id);
      }
      if (prev.length >= 2) {
        // Replace the first one
        return [prev[1], card];
      }
      return [...prev, card];
    });
  };

  const handleOpenCompare = () => {
    if (compareCards.length === 2) {
      setIsCompareModalOpen(true);
    }
  };

  const handleCreateCard = (data: CreateBattleCardData) => {
    createBattleCard.mutate(data, {
      onSuccess: () => {
        setIsCreateModalOpen(false);
      },
    });
  };

  const handleUpdateCard = (data: UpdateBattleCardData) => {
    if (!editingCard) return;
    updateBattleCard.mutate(
      { cardId: editingCard.id, data },
      {
        onSuccess: () => {
          setEditingCard(null);
        },
      }
    );
  };

  const handleEditFromDetail = () => {
    if (selectedCard) {
      setEditingCard(selectedCard);
      setIsDetailModalOpen(false);
    }
  };

  return (
    <DashboardLayout>
      <div className="relative">
        {/* Background pattern */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-800 via-slate-900 to-slate-900 pointer-events-none" />

        <div className="relative max-w-7xl mx-auto px-4 py-8 lg:px-8">
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
            <div>
              <h1 className="text-3xl font-bold text-white">Battle Cards</h1>
              <p className="mt-1 text-slate-400">
                Competitive intelligence at your fingertips
              </p>
            </div>

            <div className="flex items-center gap-3">
              {/* Compare button */}
              {compareCards.length === 2 && (
                <button
                  onClick={handleOpenCompare}
                  className="inline-flex items-center gap-2 px-4 py-2.5 bg-accent-600 hover:bg-accent-500 text-white font-medium rounded-xl transition-all duration-200"
                >
                  <svg
                    className="w-5 h-5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
                    />
                  </svg>
                  Compare ({compareCards.length}/2)
                </button>
              )}

              {/* Add button */}
              <button
                onClick={() => setIsCreateModalOpen(true)}
                className="inline-flex items-center gap-2 px-5 py-2.5 bg-primary-600 hover:bg-primary-500 text-white font-medium rounded-xl transition-all duration-200 shadow-lg shadow-primary-600/25 hover:shadow-primary-500/30"
              >
                <svg
                  className="w-5 h-5"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 4v16m8-8H4"
                  />
                </svg>
                Add Competitor
              </button>
            </div>
          </div>

          {/* Search bar */}
          <div className="relative mb-8">
            <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
              <svg
                className="w-5 h-5 text-slate-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                />
              </svg>
            </div>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search competitors..."
              className="w-full pl-12 pr-4 py-3.5 bg-slate-800/50 border border-slate-700 rounded-2xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all text-lg"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery("")}
                className="absolute inset-y-0 right-0 pr-4 flex items-center text-slate-400 hover:text-white"
              >
                <svg
                  className="w-5 h-5"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              </button>
            )}
          </div>

          {/* Compare hint */}
          {compareCards.length === 1 && (
            <div className="mb-6 px-4 py-3 bg-accent-500/10 border border-accent-500/20 rounded-xl">
              <p className="text-sm text-accent-400">
                <span className="font-medium">{compareCards[0].competitor_name}</span> selected.
                Select one more competitor to compare.
              </p>
            </div>
          )}

          {/* Error state */}
          {error && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 mb-6">
              <p className="text-red-400">
                Failed to load battle cards. Please try again.
              </p>
            </div>
          )}

          {/* Loading state */}
          {isLoading && (
            <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
              {[1, 2, 3, 4, 5, 6].map((i) => (
                <div
                  key={i}
                  className="bg-slate-800/50 border border-slate-700 rounded-2xl p-6 animate-pulse"
                >
                  <div className="flex items-start justify-between gap-4 mb-5">
                    <div className="flex-1 space-y-2">
                      <div className="h-6 bg-slate-700 rounded w-3/4" />
                      <div className="h-4 bg-slate-700 rounded w-1/2" />
                    </div>
                    <div className="w-10 h-10 bg-slate-700 rounded-xl" />
                  </div>
                  <div className="h-12 bg-slate-700 rounded mb-5" />
                  <div className="grid grid-cols-2 gap-4 mb-5">
                    <div className="h-10 bg-slate-700 rounded-lg" />
                    <div className="h-10 bg-slate-700 rounded-lg" />
                  </div>
                  <div className="h-8 bg-slate-700 rounded-lg w-1/2" />
                </div>
              ))}
            </div>
          )}

          {/* Empty state */}
          {!isLoading && filteredCards.length === 0 && (
            <EmptyBattleCards
              onCreateClick={() => setIsCreateModalOpen(true)}
              hasSearchFilter={!!searchQuery.trim()}
            />
          )}

          {/* Cards grid */}
          {!isLoading && filteredCards.length > 0 && (
            <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
              {filteredCards.map((card, index) => (
                <div
                  key={card.id}
                  className="animate-in fade-in slide-in-from-bottom-4"
                  style={{
                    animationDelay: `${index * 50}ms`,
                    animationFillMode: "both",
                  }}
                >
                  <BattleCardGridItem
                    card={card}
                    onView={() => handleViewCard(card)}
                    onCompare={() => handleToggleCompare(card)}
                    isSelected={compareCards.some((c) => c.id === card.id)}
                  />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Modals */}
        <BattleCardDetailModal
          card={selectedCard}
          isOpen={isDetailModalOpen}
          onClose={() => setIsDetailModalOpen(false)}
          onEdit={handleEditFromDetail}
        />

        <BattleCardCompareModal
          cards={compareCards}
          isOpen={isCompareModalOpen}
          onClose={() => setIsCompareModalOpen(false)}
        />

        <BattleCardEditModal
          card={editingCard}
          isOpen={editingCard !== null}
          onClose={() => setEditingCard(null)}
          onSave={handleUpdateCard}
          isLoading={updateBattleCard.isPending}
          mode="edit"
        />

        <BattleCardEditModal
          card={null}
          isOpen={isCreateModalOpen}
          onClose={() => setIsCreateModalOpen(false)}
          onSave={(data) => handleCreateCard(data as CreateBattleCardData)}
          isLoading={createBattleCard.isPending}
          mode="create"
        />
      </div>
    </DashboardLayout>
  );
}
```

**Step 2: Verify page compiles**

Run: `cd frontend && npm run typecheck`
Expected: PASS

**Step 3: Commit**

```bash
git add frontend/src/pages/BattleCards.tsx
git commit -m "feat(ui): add BattleCardsPage with search, grid, compare, and CRUD modals

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 10: Update Pages Barrel Export

**Files:**
- Modify: `frontend/src/pages/index.ts`

**Step 1: Add BattleCardsPage export**

```typescript
export { AriaChatPage } from "./AriaChat";
export { BattleCardsPage } from "./BattleCards";
export { DashboardPage } from "./Dashboard";
export { GoalsPage } from "./Goals";
export { LoginPage } from "./Login";
export { SignupPage } from "./Signup";
```

**Step 2: Verify export compiles**

Run: `cd frontend && npm run typecheck`
Expected: PASS

**Step 3: Commit**

```bash
git add frontend/src/pages/index.ts
git commit -m "feat(pages): export BattleCardsPage from barrel

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 11: Add Route to App Router

**Files:**
- Modify: `frontend/src/App.tsx`

**Step 1: Add the battle cards route**

Add import for BattleCardsPage:
```typescript
import { AriaChatPage, BattleCardsPage, LoginPage, SignupPage, DashboardPage, GoalsPage } from "@/pages";
```

Add route after /goals route:
```typescript
<Route
  path="/dashboard/battlecards"
  element={
    <ProtectedRoute>
      <BattleCardsPage />
    </ProtectedRoute>
  }
/>
```

**Step 2: Verify app compiles**

Run: `cd frontend && npm run typecheck`
Expected: PASS

**Step 3: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(router): add /dashboard/battlecards route

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 12: Add Battle Cards to Sidebar Navigation

**Files:**
- Modify: `frontend/src/components/DashboardLayout.tsx`

**Step 1: Add nav item and icon**

Add to navItems array (after Goals):
```typescript
{ name: "Battle Cards", href: "/dashboard/battlecards", icon: "swords" },
```

Add swords icon to NavIcon component icons object:
```typescript
swords: (
  <svg
    className="w-5 h-5"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
    />
  </svg>
),
```

**Step 2: Verify component compiles**

Run: `cd frontend && npm run typecheck`
Expected: PASS

**Step 3: Commit**

```bash
git add frontend/src/components/DashboardLayout.tsx
git commit -m "feat(nav): add Battle Cards to sidebar navigation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 13: Add Animations to CSS

**Files:**
- Modify: `frontend/src/index.css`

**Step 1: Add card hover animation keyframes**

Add after existing keyframes:
```css
@keyframes card-lift {
  from {
    transform: translateY(0);
    box-shadow: 0 0 0 rgba(0, 0, 0, 0);
  }
  to {
    transform: translateY(-4px);
    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
  }
}

.animate-card-lift {
  animation: card-lift 0.3s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
}
```

**Step 2: Verify CSS is valid**

Run: `cd frontend && npm run build`
Expected: PASS (build completes)

**Step 3: Commit**

```bash
git add frontend/src/index.css
git commit -m "feat(css): add card-lift animation keyframes

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 14: Final Verification

**Step 1: Run full type check**

Run: `cd frontend && npm run typecheck`
Expected: PASS

**Step 2: Run linter**

Run: `cd frontend && npm run lint`
Expected: PASS (or only pre-existing warnings)

**Step 3: Run build**

Run: `cd frontend && npm run build`
Expected: PASS

**Step 4: Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix: address lint/type issues in battle cards implementation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Summary

This plan creates a complete Battle Cards UI with:

1. **API Client** - Types and functions matching backend endpoints
2. **React Query Hooks** - Query key factory with proper cache invalidation
3. **Grid Item Component** - Premium card design with hover effects and comparison selection
4. **Empty State** - Two variants (no cards / no search results)
5. **Detail Modal** - Tabbed view with overview, differentiation, objections, and history
6. **Compare Modal** - Side-by-side competitor comparison
7. **Edit Modal** - Create and edit functionality
8. **Page Component** - Full page with search, grid, and modal orchestration
9. **Router Integration** - Protected route at /dashboard/battlecards
10. **Navigation Integration** - Sidebar link with icon

Design follows existing ARIA patterns:
- Dark slate theme with primary/accent colors
- Semi-transparent backgrounds with subtle borders
- Staggered fade-in animations
- Hover states with gradient border effects
- Consistent spacing and typography
