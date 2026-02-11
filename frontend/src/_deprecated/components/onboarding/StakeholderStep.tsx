import { useState, useEffect } from "react";
import { Plus, X } from "lucide-react";
import {
  saveStakeholders,
  getStakeholders,
  type StakeholderInput,
  type RelationshipType,
  type Stakeholder,
} from "@/api/stakeholders";

interface StakeholderStepProps {
  onComplete: (stakeholderData: { stakeholders: Stakeholder[] }) => void;
}

const RELATIONSHIP_TYPES: { value: RelationshipType; label: string }[] = [
  { value: "champion", label: "Champion" },
  { value: "decision_maker", label: "Decision Maker" },
  { value: "influencer", label: "Influencer" },
  { value: "end_user", label: "End User" },
  { value: "blocker", label: "Blocker" },
  { value: "other", label: "Other" },
];

// Empty stakeholder template
const emptyStakeholder: StakeholderInput = {
  name: "",
  title: "",
  company: "",
  email: "",
  relationship_type: "other",
  notes: "",
};

export function StakeholderStep({ onComplete }: StakeholderStepProps) {
  const [stakeholders, setStakeholders] = useState<StakeholderInput[]>([
    { ...emptyStakeholder },
  ]);
  const [isSaving, setIsSaving] = useState(false);
  const [showZeroConfirm, setShowZeroConfirm] = useState(false);
  const [hasFetched, setHasFetched] = useState(false);

  // Load existing stakeholders on mount
  useEffect(() => {
    const loadExisting = async () => {
      try {
        const existing = await getStakeholders();
        if (existing.length > 0) {
          setStakeholders(existing.map(s => ({ ...s, id: undefined })));
        }
      } catch {
        // Silently fail - we'll start fresh
      } finally {
        setHasFetched(true);
      }
    };
    loadExisting();
  }, []);

  const addStakeholder = () => {
    setStakeholders(prev => [...prev, { ...emptyStakeholder }]);
  };

  const removeStakeholder = (index: number) => {
    setStakeholders(prev => prev.filter((_, i) => i !== index));
  };

  const updateStakeholder = (
    index: number,
    field: keyof StakeholderInput,
    value: string
  ) => {
    setStakeholders(prev =>
      prev.map((s, i) =>
        i === index ? { ...s, [field]: value } : s
      )
    );
  };

  const getValidStakeholders = (): StakeholderInput[] => {
    // Filter to only stakeholders with at least a name
    return stakeholders.filter(s => s.name.trim().length > 0);
  };

  const handleContinue = async () => {
    const validStakeholders = getValidStakeholders();

    // If no stakeholders and haven't shown confirm yet
    if (validStakeholders.length === 0 && !showZeroConfirm) {
      setShowZeroConfirm(true);
      return;
    }

    setIsSaving(true);
    try {
      const result = await saveStakeholders({
        stakeholders: validStakeholders,
      });

      onComplete({
        stakeholders: validStakeholders.map((s, i) => ({
          ...s,
          id: result.stakeholder_ids[i] || `local-${i}`,
        })),
      });
    } catch {
      // Silently fail - allow continuing anyway
      onComplete({
        stakeholders: validStakeholders.map((s, i) => ({
          ...s,
          id: `local-${i}`,
        })),
      });
    } finally {
      setIsSaving(false);
    }
  };

  const handleCancelZero = () => {
    setShowZeroConfirm(false);
  };

  const handleConfirmZero = () => {
    // Continue with zero stakeholders
    onComplete({ stakeholders: [] });
  };

  // Don't render until we've fetched existing data
  if (!hasFetched) {
    return null;
  }

  return (
    <div className="flex flex-col gap-8 max-w-2xl animate-in fade-in slide-in-from-bottom-4 duration-400">
      {/* Header */}
      <div className="flex flex-col gap-3">
        <h1 className="text-[32px] leading-[1.2] text-content font-display">
          Map your key relationships
        </h1>
        <p className="font-sans text-[15px] leading-relaxed text-secondary">
          Who are the people that matter most to your work? ARIA will track
          these relationships over time.
        </p>
      </div>

      {/* Zero stakeholder confirmation */}
      {showZeroConfirm && (
        <div
          className="rounded-xl bg-primary border border-border px-5 py-4 w-full animate-in fade-in slide-in-from-top-2 duration-300"
          role="alert"
          aria-live="polite"
        >
          <p className="font-sans text-[15px] leading-relaxed text-content mb-4">
            No stakeholders to add right now? That&apos;s fine — I&apos;ll build
            your relationship map from email and CRM data.
          </p>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={handleCancelZero}
              className="font-sans text-[13px] font-medium text-interactive hover:text-interactive-hover transition-colors duration-150 cursor-pointer focus:outline-none focus:ring-2 focus:ring-interactive focus:ring-offset-2 rounded px-2 py-1"
            >
              Go back
            </button>
            <button
              type="button"
              onClick={handleConfirmZero}
              className="font-sans text-[13px] font-medium text-content hover:text-interactive transition-colors duration-150 cursor-pointer focus:outline-none focus:ring-2 focus:ring-interactive focus:ring-offset-2 rounded px-2 py-1"
            >
              Continue anyway
            </button>
          </div>
        </div>
      )}

      {/* Stakeholder cards */}
      <div className="flex flex-col gap-4">
        {stakeholders.map((stakeholder, index) => (
          <StakeholderCard
            key={index}
            stakeholder={stakeholder}
            index={index}
            onUpdate={updateStakeholder}
            onRemove={
              stakeholders.length > 1 ? () => removeStakeholder(index) : undefined
            }
          />
        ))}
      </div>

      {/* Add stakeholder button */}
      <button
        type="button"
        onClick={addStakeholder}
        className="font-sans text-[13px] font-medium text-interactive hover:text-interactive-hover transition-colors duration-150 cursor-pointer focus:outline-none focus:ring-2 focus:ring-interactive focus:ring-offset-2 rounded px-2 py-1 flex items-center gap-2 w-fit"
      >
        <Plus size={16} strokeWidth={1.5} aria-hidden="true" />
        Add person
      </button>

      {/* ARIA presence text */}
      <p className="font-sans text-[13px] leading-relaxed text-secondary italic">
        Even 3-5 key contacts give me a strong foundation. I&apos;ll discover more
        from your email and CRM later.
      </p>

      {/* Continue button */}
      <button
        type="button"
        onClick={handleContinue}
        disabled={isSaving}
        className={`
          bg-interactive text-white rounded-lg px-5 py-2.5
          font-sans font-medium text-[15px]
          hover:bg-interactive-hover active:bg-interactive-hover
          transition-colors duration-150
          focus:outline-none focus:ring-2 focus:ring-interactive focus:ring-offset-2
          disabled:opacity-50 disabled:cursor-not-allowed
          cursor-pointer flex items-center justify-center gap-2
          min-h-[44px] w-fit
        `}
      >
        {isSaving ? "Saving..." : "Continue"}
      </button>
    </div>
  );
}

interface StakeholderCardProps {
  stakeholder: StakeholderInput;
  index: number;
  onUpdate: (index: number, field: keyof StakeholderInput, value: string) => void;
  onRemove?: () => void;
}

function StakeholderCard({ stakeholder, index, onUpdate, onRemove }: StakeholderCardProps) {
  return (
    <div className="bg-elevated border border-border rounded-xl p-5 relative">
      {/* Remove button */}
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          className="absolute top-4 right-4 text-secondary hover:text-critical transition-colors duration-150 cursor-pointer focus:outline-none focus:ring-2 focus:ring-interactive focus:ring-offset-2 rounded p-1"
          aria-label="Remove this person"
        >
          <X size={18} strokeWidth={1.5} />
        </button>
      )}

      <div className="flex flex-col gap-4">
        {/* Name (required) */}
        <div className="flex flex-col gap-1.5">
          <label
            htmlFor={`stakeholder-${index}-name`}
            className="font-sans text-[13px] font-medium text-secondary"
          >
            Name <span aria-hidden="true">*</span>
            <span className="sr-only">(required)</span>
          </label>
          <input
            type="text"
            id={`stakeholder-${index}-name`}
            value={stakeholder.name}
            onChange={(e) => onUpdate(index, "name", e.target.value)}
            placeholder="e.g., Sarah Johnson"
            className="bg-subtle text-content placeholder:text-secondary/50 border border-border rounded-lg px-4 py-3 text-[15px] font-sans focus:outline-none focus:ring-1 focus:border-interactive focus:ring-interactive transition-colors duration-150"
            aria-required="true"
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          {/* Title */}
          <div className="flex flex-col gap-1.5">
            <label
              htmlFor={`stakeholder-${index}-title`}
              className="font-sans text-[13px] font-medium text-secondary"
            >
              Title
            </label>
            <input
              type="text"
              id={`stakeholder-${index}-title`}
              value={stakeholder.title}
              onChange={(e) => onUpdate(index, "title", e.target.value)}
              placeholder="e.g., VP of R&D"
              className="bg-subtle text-content placeholder:text-secondary/50 border border-border rounded-lg px-4 py-3 text-[15px] font-sans focus:outline-none focus:ring-1 focus:border-interactive focus:ring-interactive transition-colors duration-150"
            />
          </div>

          {/* Relationship Type */}
          <div className="flex flex-col gap-1.5">
            <label
              htmlFor={`stakeholder-${index}-relationship`}
              className="font-sans text-[13px] font-medium text-secondary"
            >
              Relationship
            </label>
            <select
              id={`stakeholder-${index}-relationship`}
              value={stakeholder.relationship_type}
              onChange={(e) =>
                onUpdate(index, "relationship_type", e.target.value)
              }
              className="bg-subtle text-content border border-border rounded-lg px-4 py-3 text-[15px] font-sans focus:outline-none focus:ring-1 focus:border-interactive focus:ring-interactive transition-colors duration-150 cursor-pointer"
            >
              {RELATIONSHIP_TYPES.map((type) => (
                <option key={type.value} value={type.value}>
                  {type.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Company */}
        <div className="flex flex-col gap-1.5">
          <label
            htmlFor={`stakeholder-${index}-company`}
            className="font-sans text-[13px] font-medium text-secondary"
          >
            Company
          </label>
          <input
            type="text"
            id={`stakeholder-${index}-company`}
            value={stakeholder.company}
            onChange={(e) => onUpdate(index, "company", e.target.value)}
            placeholder="e.g., Pfizer"
            className="bg-subtle text-content placeholder:text-secondary/50 border border-border rounded-lg px-4 py-3 text-[15px] font-sans focus:outline-none focus:ring-1 focus:border-interactive focus:ring-interactive transition-colors duration-150"
          />
        </div>

        {/* Email */}
        <div className="flex flex-col gap-1.5">
          <label
            htmlFor={`stakeholder-${index}-email`}
            className="font-sans text-[13px] font-medium text-secondary"
          >
            Email
          </label>
          <input
            type="email"
            id={`stakeholder-${index}-email`}
            value={stakeholder.email}
            onChange={(e) => onUpdate(index, "email", e.target.value)}
            placeholder="e.g., sarah@company.com"
            className="bg-subtle text-content placeholder:text-secondary/50 border border-border rounded-lg px-4 py-3 text-[15px] font-sans focus:outline-none focus:ring-1 focus:border-interactive focus:ring-interactive transition-colors duration-150"
          />
        </div>

        {/* Notes */}
        <div className="flex flex-col gap-1.5">
          <label
            htmlFor={`stakeholder-${index}-notes`}
            className="font-sans text-[13px] font-medium text-secondary"
          >
            Notes <span className="text-secondary font-normal">(optional)</span>
          </label>
          <textarea
            id={`stakeholder-${index}-notes`}
            value={stakeholder.notes}
            onChange={(e) => onUpdate(index, "notes", e.target.value)}
            placeholder="Any context about this relationship..."
            rows={2}
            className="bg-subtle text-content placeholder:text-secondary/50 border border-border rounded-lg px-4 py-3 text-[15px] font-sans focus:outline-none focus:ring-1 focus:border-interactive focus:ring-interactive transition-colors duration-150 resize-none"
          />
        </div>
      </div>
    </div>
  );
}
