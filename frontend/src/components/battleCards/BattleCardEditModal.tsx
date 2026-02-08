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
  /* eslint-disable react-hooks/set-state-in-effect -- syncing form state with prop changes */
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
  /* eslint-enable react-hooks/set-state-in-effect */

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
                    Competitor Name <span className="text-critical">*</span>
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
                <label className="text-sm font-medium text-success">Their Strengths</label>
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
                      className="flex-1 px-4 py-2.5 bg-slate-900 border border-success/20 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-success/50 focus:border-transparent transition-all"
                      disabled={isLoading}
                    />
                    <button
                      type="button"
                      onClick={() => removeStrength(idx)}
                      disabled={isLoading}
                      className="p-2.5 text-slate-400 hover:text-critical hover:bg-critical/10 rounded-xl transition-colors disabled:opacity-50"
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
                <label className="text-sm font-medium text-warning">Their Weaknesses</label>
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
                      className="flex-1 px-4 py-2.5 bg-slate-900 border border-warning/20 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-warning/50 focus:border-transparent transition-all"
                      disabled={isLoading}
                    />
                    <button
                      type="button"
                      onClick={() => removeWeakness(idx)}
                      disabled={isLoading}
                      className="p-2.5 text-slate-400 hover:text-critical hover:bg-critical/10 rounded-xl transition-colors disabled:opacity-50"
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
