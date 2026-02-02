import { useState, useEffect, useCallback } from "react";
import type { GoalType } from "@/api/goals";

interface CreateGoalModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: { title: string; description?: string; goal_type: GoalType }) => void;
  isLoading?: boolean;
}

const goalTypes: { value: GoalType; label: string; description: string }[] = [
  {
    value: "lead_gen",
    label: "Lead Generation",
    description: "Find and qualify new prospects",
  },
  {
    value: "research",
    label: "Research",
    description: "Scientific and market research",
  },
  {
    value: "outreach",
    label: "Outreach",
    description: "Email and communication campaigns",
  },
  {
    value: "analysis",
    label: "Analysis",
    description: "Data analysis and reporting",
  },
  {
    value: "custom",
    label: "Custom",
    description: "Define your own goal type",
  },
];

interface CreateGoalFormProps {
  onClose: () => void;
  onSubmit: (data: { title: string; description?: string; goal_type: GoalType }) => void;
  isLoading: boolean;
}

function CreateGoalForm({ onClose, onSubmit, isLoading }: CreateGoalFormProps) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [goalType, setGoalType] = useState<GoalType>("lead_gen");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;

    onSubmit({
      title: title.trim(),
      description: description.trim() || undefined,
      goal_type: goalType,
    });
  };

  return (
    <form onSubmit={handleSubmit}>
      <div className="px-6 py-5 space-y-5">
        {/* Title */}
        <div>
          <label htmlFor="title" className="block text-sm font-medium text-slate-300 mb-1.5">
            Goal Title <span className="text-red-400">*</span>
          </label>
          <input
            id="title"
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g., Find 50 biotech leads in Boston"
            className="w-full px-4 py-2.5 bg-slate-900 border border-slate-700 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all"
            required
            disabled={isLoading}
          />
        </div>

        {/* Description */}
        <div>
          <label htmlFor="description" className="block text-sm font-medium text-slate-300 mb-1.5">
            Description
          </label>
          <textarea
            id="description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Describe what you want to achieve..."
            rows={3}
            className="w-full px-4 py-2.5 bg-slate-900 border border-slate-700 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all resize-none"
            disabled={isLoading}
          />
        </div>

        {/* Goal Type */}
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">Goal Type</label>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {goalTypes.map((type) => (
              <button
                key={type.value}
                type="button"
                onClick={() => setGoalType(type.value)}
                disabled={isLoading}
                className={`p-3 text-left rounded-lg border transition-all ${
                  goalType === type.value
                    ? "bg-primary-600/20 border-primary-500 text-white"
                    : "bg-slate-900 border-slate-700 text-slate-400 hover:border-slate-600 hover:text-slate-300"
                } disabled:opacity-50`}
              >
                <span className="block text-sm font-medium">{type.label}</span>
                <span className="block text-xs mt-0.5 opacity-75">{type.description}</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-700">
        <button
          type="button"
          onClick={onClose}
          disabled={isLoading}
          className="px-4 py-2 text-sm font-medium text-slate-400 hover:text-white hover:bg-slate-700 rounded-lg transition-colors disabled:opacity-50"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={!title.trim() || isLoading}
          className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium bg-primary-600 hover:bg-primary-500 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
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
              Creating...
            </>
          ) : (
            <>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 4v16m8-8H4"
                />
              </svg>
              Create Goal
            </>
          )}
        </button>
      </div>
    </form>
  );
}

export function CreateGoalModal({
  isOpen,
  onClose,
  onSubmit,
  isLoading = false,
}: CreateGoalModalProps) {
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

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={isLoading ? undefined : onClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-lg mx-4 bg-slate-800 border border-slate-700 rounded-2xl shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700">
          <h2 className="text-xl font-semibold text-white">Create New Goal</h2>
          <button
            onClick={onClose}
            disabled={isLoading}
            className="p-2 text-slate-400 hover:text-white hover:bg-slate-700 rounded-lg transition-colors disabled:opacity-50"
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

        {/* Form - key forces remount when modal opens, resetting all state */}
        <CreateGoalForm
          key={isOpen ? "open" : "closed"}
          onClose={onClose}
          onSubmit={onSubmit}
          isLoading={isLoading}
        />
      </div>
    </div>
  );
}
