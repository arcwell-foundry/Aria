import { ArrowRight, X } from "lucide-react";
import { useState } from "react";
import type { LifecycleStage, StageTransition } from "@/api/leads";

interface StageTransitionModalProps {
  currentStage: LifecycleStage;
  companyName: string;
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (transition: StageTransition) => void;
  isLoading: boolean;
}

// Stage configuration with labels and descriptions
const stageConfig: Record<LifecycleStage, { label: string; description: string }> = {
  lead: {
    label: "Lead",
    description: "Initial contact, exploring fit",
  },
  opportunity: {
    label: "Opportunity",
    description: "Qualified prospect, active pursuit",
  },
  account: {
    label: "Account",
    description: "Customer, ongoing relationship",
  },
};

// Ordered stages for progression display
const stageOrder: LifecycleStage[] = ["lead", "opportunity", "account"];

export function StageTransitionModal({
  currentStage,
  companyName,
  isOpen,
  onClose,
  onSubmit,
  isLoading,
}: StageTransitionModalProps) {
  const [selectedStage, setSelectedStage] = useState<LifecycleStage | null>(null);
  const [reason, setReason] = useState("");

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (selectedStage && selectedStage !== currentStage) {
      onSubmit({
        new_stage: selectedStage,
        reason: reason.trim() || undefined,
      });
    }
  };

  const handleClose = () => {
    setSelectedStage(null);
    setReason("");
    onClose();
  };

  const handleStageClick = (stage: LifecycleStage) => {
    if (stage !== currentStage) {
      setSelectedStage(stage);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-slate-900/80 backdrop-blur-sm animate-in fade-in duration-200"
        onClick={handleClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-xl bg-slate-800 border border-slate-700 rounded-2xl shadow-2xl animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700">
          <div>
            <h2 className="text-lg font-semibold text-white">Change Stage</h2>
            <p className="text-sm text-slate-400 mt-0.5">{companyName}</p>
          </div>
          <button
            onClick={handleClose}
            className="p-2 rounded-lg hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-6">
          {/* Stage progression */}
          <div className="mb-6">
            <label className="block text-sm font-medium text-slate-300 mb-4">
              Select New Stage
            </label>
            <div className="flex items-center justify-between">
              {stageOrder.map((stage, index) => {
                const config = stageConfig[stage];
                const isCurrent = stage === currentStage;
                const isSelected = stage === selectedStage;

                return (
                  <div key={stage} className="flex items-center flex-1">
                    {/* Stage card */}
                    <button
                      type="button"
                      onClick={() => handleStageClick(stage)}
                      disabled={isCurrent}
                      className={`
                        relative flex-1 p-4 rounded-xl border-2 transition-all duration-200
                        ${isCurrent
                          ? "bg-slate-700/50 border-slate-600 cursor-default"
                          : isSelected
                            ? "bg-primary-500/20 border-primary-500 cursor-pointer"
                            : "bg-slate-900/50 border-slate-700 hover:bg-slate-700/50 hover:border-slate-600 cursor-pointer"
                        }
                      `}
                    >
                      {/* Step number */}
                      <div
                        className={`
                          w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold mb-3
                          ${isCurrent
                            ? "bg-slate-600 text-slate-300"
                            : isSelected
                              ? "bg-primary-500 text-white"
                              : "bg-slate-700 text-slate-400"
                          }
                        `}
                      >
                        {index + 1}
                      </div>

                      {/* Stage label */}
                      <div
                        className={`
                          text-sm font-medium mb-1
                          ${isCurrent
                            ? "text-slate-300"
                            : isSelected
                              ? "text-primary-400"
                              : "text-white"
                          }
                        `}
                      >
                        {config.label}
                      </div>

                      {/* Stage description */}
                      <div className="text-xs text-slate-500 leading-tight">
                        {config.description}
                      </div>

                      {/* Current badge */}
                      {isCurrent && (
                        <div className="absolute -top-2 -right-2 px-2 py-0.5 bg-slate-600 text-slate-300 text-xs font-medium rounded-full">
                          Current
                        </div>
                      )}
                    </button>

                    {/* Arrow between stages */}
                    {index < stageOrder.length - 1 && (
                      <div className="px-3 flex-shrink-0">
                        <ArrowRight className="w-5 h-5 text-slate-600" />
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Reason field (shows when stage selected) */}
          {selectedStage && (
            <div className="mb-6 animate-in fade-in slide-in-from-top-2 duration-200">
              <label htmlFor="transition-reason" className="block text-sm font-medium text-slate-300 mb-2">
                Reason for Change <span className="text-slate-500">(optional)</span>
              </label>
              <textarea
                id="transition-reason"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder={`Why are you moving this ${currentStage} to ${stageConfig[selectedStage].label.toLowerCase()}?`}
                rows={3}
                className="w-full px-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500/50 resize-none transition-all"
              />
            </div>
          )}

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
              disabled={!selectedStage || isLoading}
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
                  Updating...
                </span>
              ) : (
                "Confirm Change"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
