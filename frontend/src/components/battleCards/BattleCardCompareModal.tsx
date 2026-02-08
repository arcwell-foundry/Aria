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
              <h4 className="flex items-center gap-2 text-sm font-medium text-success uppercase tracking-wide mb-4">
                <div className="flex items-center justify-center w-6 h-6 rounded-md bg-success/20">
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
              <h4 className="flex items-center gap-2 text-sm font-medium text-warning uppercase tracking-wide mb-4">
                <div className="flex items-center justify-center w-6 h-6 rounded-md bg-warning/20">
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
      bg: "bg-success/5",
      border: "border-success/10",
      dot: "bg-success",
    },
    amber: {
      bg: "bg-warning/5",
      border: "border-warning/10",
      dot: "bg-warning",
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
