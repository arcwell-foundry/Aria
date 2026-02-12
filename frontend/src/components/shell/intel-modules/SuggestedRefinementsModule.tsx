/**
 * SuggestedRefinementsModule - Intel Panel module for draft refinements
 *
 * Shows 3-4 clickable refinement options that trigger draft regeneration.
 * Part of the ARIA Intelligence Panel for draft detail views.
 */

import { Sparkles, Loader2 } from 'lucide-react';

interface RefinementOption {
  id: string;
  label: string;
  description: string;
  prompt: string;
}

const REFINEMENT_OPTIONS: RefinementOption[] = [
  {
    id: 'concise',
    label: 'Make it more concise',
    description: 'Reduce word count while keeping key points',
    prompt: 'Make this email more concise and to the point.',
  },
  {
    id: 'roi',
    label: 'Add specific ROI metrics',
    description: 'Include concrete numbers and outcomes',
    prompt: 'Add specific ROI metrics and concrete outcomes to this email.',
  },
  {
    id: 'softer',
    label: 'Softer closing',
    description: 'Less aggressive call to action',
    prompt: 'Make the closing less aggressive and more conversational.',
  },
  {
    id: 'formal',
    label: 'More formal tone',
    description: 'Increase professional formality',
    prompt: 'Make the tone more formal and professional.',
  },
];

export interface SuggestedRefinementsModuleProps {
  onRefinement?: (prompt: string) => void;
  isLoading?: boolean;
  disabled?: boolean;
}

export function SuggestedRefinementsModule({
  onRefinement,
  isLoading = false,
  disabled = false,
}: SuggestedRefinementsModuleProps) {
  return (
    <div data-aria-id="intel-suggested-refinements" className="space-y-3">
      <h3
        className="font-sans text-[11px] font-medium uppercase tracking-wider"
        style={{ color: 'var(--text-secondary)' }}
      >
        Suggested Refinements
      </h3>

      <div className="space-y-2">
        {REFINEMENT_OPTIONS.map((option) => (
          <button
            key={option.id}
            onClick={() => onRefinement?.(option.prompt)}
            disabled={isLoading || disabled}
            className={`
              w-full text-left rounded-lg border p-2.5
              transition-all duration-200
              hover:border-[var(--accent)]/50
              disabled:opacity-50 disabled:cursor-not-allowed
            `}
            style={{
              borderColor: 'var(--border)',
              backgroundColor: 'var(--bg-subtle)',
            }}
          >
            <div className="flex items-start gap-2">
              <Sparkles
                className="w-3.5 h-3.5 mt-0.5 flex-shrink-0"
                style={{ color: 'var(--accent)' }}
              />
              <div className="min-w-0 flex-1">
                <p
                  className="font-sans text-[12px] font-medium leading-tight"
                  style={{ color: 'var(--text-primary)' }}
                >
                  {isLoading ? (
                    <span className="flex items-center gap-2">
                      <Loader2 className="w-3 h-3 animate-spin" />
                      Refining...
                    </span>
                  ) : (
                    option.label
                  )}
                </p>
                <p
                  className="font-sans text-[11px] mt-0.5 leading-tight"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  {option.description}
                </p>
              </div>
            </div>
          </button>
        ))}
      </div>

      <p
        className="font-sans text-[11px] leading-relaxed"
        style={{ color: 'var(--text-secondary)' }}
      >
        Click any option to regenerate the draft with that refinement applied.
      </p>
    </div>
  );
}
