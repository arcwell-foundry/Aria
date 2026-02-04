import { X } from "lucide-react";
import { useEffect, useState } from "react";
import type { Stakeholder, StakeholderRole, StakeholderUpdate, Sentiment } from "@/api/leads";

interface EditStakeholderModalProps {
  stakeholder: Stakeholder | null;
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (updates: StakeholderUpdate) => void;
  isLoading: boolean;
}

// Role options for the select dropdown
const roleOptions: { value: StakeholderRole; label: string }[] = [
  { value: "decision_maker", label: "Decision Maker" },
  { value: "influencer", label: "Influencer" },
  { value: "champion", label: "Champion" },
  { value: "blocker", label: "Blocker" },
  { value: "user", label: "User" },
];

// Sentiment options for toggle buttons
const sentimentOptions: { value: Sentiment; label: string; color: string; activeColor: string }[] = [
  { value: "positive", label: "Positive", color: "text-emerald-400", activeColor: "bg-emerald-500/20 border-emerald-500/50 text-emerald-400" },
  { value: "neutral", label: "Neutral", color: "text-amber-400", activeColor: "bg-amber-500/20 border-amber-500/50 text-amber-400" },
  { value: "negative", label: "Negative", color: "text-red-400", activeColor: "bg-red-500/20 border-red-500/50 text-red-400" },
  { value: "unknown", label: "Unknown", color: "text-slate-400", activeColor: "bg-slate-500/20 border-slate-500/50 text-slate-400" },
];

export function EditStakeholderModal({
  stakeholder,
  isOpen,
  onClose,
  onSubmit,
  isLoading,
}: EditStakeholderModalProps) {
  const [name, setName] = useState("");
  const [title, setTitle] = useState("");
  const [role, setRole] = useState<StakeholderRole | "">("");
  const [sentiment, setSentiment] = useState<Sentiment>("unknown");
  const [influence, setInfluence] = useState(5);
  const [notes, setNotes] = useState("");

  // Populate form when stakeholder changes
  useEffect(() => {
    if (stakeholder) {
      setName(stakeholder.contact_name || "");
      setTitle(stakeholder.title || "");
      setRole(stakeholder.role || "");
      setSentiment(stakeholder.sentiment);
      setInfluence(stakeholder.influence_level);
      setNotes(stakeholder.notes || "");
    }
  }, [stakeholder]);

  if (!isOpen || !stakeholder) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const updates: StakeholderUpdate = {};

    // Only include changed fields
    if (name !== (stakeholder.contact_name || "")) {
      updates.contact_name = name || undefined;
    }
    if (title !== (stakeholder.title || "")) {
      updates.title = title || undefined;
    }
    if (role !== (stakeholder.role || "")) {
      updates.role = role || undefined;
    }
    if (sentiment !== stakeholder.sentiment) {
      updates.sentiment = sentiment;
    }
    if (influence !== stakeholder.influence_level) {
      updates.influence_level = influence;
    }
    if (notes !== (stakeholder.notes || "")) {
      updates.notes = notes || undefined;
    }

    onSubmit(updates);
  };

  const handleClose = () => {
    onClose();
  };

  // Get influence label and color
  const getInfluenceLabel = (value: number): { label: string; color: string } => {
    if (value <= 3) return { label: "Low", color: "text-slate-400" };
    if (value <= 6) return { label: "Medium", color: "text-amber-400" };
    return { label: "High", color: "text-emerald-400" };
  };

  const influenceInfo = getInfluenceLabel(influence);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-slate-900/80 backdrop-blur-sm animate-in fade-in duration-200"
        onClick={handleClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-lg bg-slate-800 border border-slate-700 rounded-2xl shadow-2xl animate-in fade-in zoom-in-95 duration-200 max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700 shrink-0">
          <div>
            <h2 className="text-lg font-semibold text-white">Edit Stakeholder</h2>
            <p className="text-sm text-slate-400 mt-0.5">{stakeholder.contact_email}</p>
          </div>
          <button
            onClick={handleClose}
            className="p-2 rounded-lg hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-6 overflow-y-auto">
          {/* Name field */}
          <div className="mb-5">
            <label htmlFor="stakeholder-name" className="block text-sm font-medium text-slate-300 mb-2">
              Name
            </label>
            <input
              id="stakeholder-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Contact name"
              className="w-full px-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500/50 transition-all"
            />
          </div>

          {/* Title field */}
          <div className="mb-5">
            <label htmlFor="stakeholder-title" className="block text-sm font-medium text-slate-300 mb-2">
              Title
            </label>
            <input
              id="stakeholder-title"
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Job title (e.g., VP of Research)"
              className="w-full px-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500/50 transition-all"
            />
          </div>

          {/* Role select */}
          <div className="mb-5">
            <label htmlFor="stakeholder-role" className="block text-sm font-medium text-slate-300 mb-2">
              Role
            </label>
            <select
              id="stakeholder-role"
              value={role}
              onChange={(e) => setRole(e.target.value as StakeholderRole | "")}
              className="w-full px-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl text-white focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500/50 transition-all appearance-none cursor-pointer"
              style={{
                backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%2394a3b8'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'%3E%3C/path%3E%3C/svg%3E")`,
                backgroundRepeat: "no-repeat",
                backgroundPosition: "right 1rem center",
                backgroundSize: "1.25rem",
              }}
            >
              <option value="" className="bg-slate-800">No role assigned</option>
              {roleOptions.map((option) => (
                <option key={option.value} value={option.value} className="bg-slate-800">
                  {option.label}
                </option>
              ))}
            </select>
          </div>

          {/* Sentiment toggle buttons */}
          <div className="mb-5">
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Sentiment
            </label>
            <div className="grid grid-cols-4 gap-2">
              {sentimentOptions.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setSentiment(option.value)}
                  className={`px-3 py-2.5 text-sm font-medium rounded-lg border transition-all duration-200 ${
                    sentiment === option.value
                      ? option.activeColor
                      : "bg-slate-900/50 border-slate-700 text-slate-400 hover:bg-slate-700/50 hover:border-slate-600"
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>

          {/* Influence range slider */}
          <div className="mb-5">
            <div className="flex items-center justify-between mb-2">
              <label htmlFor="stakeholder-influence" className="text-sm font-medium text-slate-300">
                Influence Level
              </label>
              <span className={`text-sm font-medium ${influenceInfo.color}`}>
                {influence}/10 - {influenceInfo.label}
              </span>
            </div>
            <div className="relative pt-1">
              <input
                id="stakeholder-influence"
                type="range"
                min="1"
                max="10"
                value={influence}
                onChange={(e) => setInfluence(parseInt(e.target.value))}
                className="w-full h-2 bg-slate-700 rounded-full appearance-none cursor-pointer slider-thumb"
                style={{
                  background: `linear-gradient(to right, rgb(99, 102, 241) 0%, rgb(99, 102, 241) ${(influence - 1) * 11.11}%, rgb(51, 65, 85) ${(influence - 1) * 11.11}%, rgb(51, 65, 85) 100%)`,
                }}
              />
              {/* Tick marks */}
              <div className="flex justify-between px-1 mt-2">
                {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((tick) => (
                  <span
                    key={tick}
                    className={`text-xs ${tick === influence ? "text-primary-400 font-medium" : "text-slate-600"}`}
                  >
                    {tick}
                  </span>
                ))}
              </div>
            </div>
          </div>

          {/* Notes textarea */}
          <div className="mb-6">
            <label htmlFor="stakeholder-notes" className="block text-sm font-medium text-slate-300 mb-2">
              Notes
            </label>
            <textarea
              id="stakeholder-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Add notes about this stakeholder..."
              rows={3}
              className="w-full px-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500/50 resize-none transition-all"
            />
          </div>

          {/* Action buttons */}
          <div className="flex justify-end gap-3">
            <button
              type="button"
              onClick={handleClose}
              className="px-4 py-2.5 text-sm font-medium text-slate-400 hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isLoading}
              className="px-5 py-2.5 bg-primary-600 hover:bg-primary-500 disabled:bg-primary-600/50 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors shadow-lg shadow-primary-600/25"
            >
              {isLoading ? (
                <span className="flex items-center gap-2">
                  <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24">
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                      fill="none"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                    />
                  </svg>
                  Saving...
                </span>
              ) : (
                "Save Changes"
              )}
            </button>
          </div>
        </form>
      </div>

      {/* Custom slider thumb styles */}
      <style>{`
        .slider-thumb::-webkit-slider-thumb {
          -webkit-appearance: none;
          appearance: none;
          width: 18px;
          height: 18px;
          border-radius: 50%;
          background: rgb(99, 102, 241);
          cursor: pointer;
          border: 2px solid white;
          box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
          transition: transform 0.15s ease;
        }
        .slider-thumb::-webkit-slider-thumb:hover {
          transform: scale(1.1);
        }
        .slider-thumb::-moz-range-thumb {
          width: 18px;
          height: 18px;
          border-radius: 50%;
          background: rgb(99, 102, 241);
          cursor: pointer;
          border: 2px solid white;
          box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
          transition: transform 0.15s ease;
        }
        .slider-thumb::-moz-range-thumb:hover {
          transform: scale(1.1);
        }
      `}</style>
    </div>
  );
}
