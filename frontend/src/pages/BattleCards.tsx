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
} from "@/hooks/useBattleCards";
import { HelpTooltip } from "@/components/HelpTooltip";

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
              <div className="flex items-center gap-2">
                <h1 className="text-3xl font-bold text-white">Battle Cards</h1>
                <HelpTooltip content="Competitive intelligence cards. ARIA keeps these updated with the latest market data." placement="right" />
              </div>
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
