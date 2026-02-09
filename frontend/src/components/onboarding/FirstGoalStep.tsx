import { useState, useEffect } from "react";
import { ArrowRight, Loader2, Target, Sparkles } from "lucide-react";
import {
  getFirstGoalSuggestions,
  validateGoalSmart,
  createFirstGoal,
  completeStep,
} from "@/api/onboarding";

interface FirstGoalStepProps {
  onComplete: (goalData: {
    title: string;
    description: string | undefined;
    goal_type: string;
  }) => void;
}

interface GoalSuggestion {
  title: string;
  description: string;
  category: string;
  urgency: string;
  reason: string;
  goal_type: string;
}

interface GoalTemplate {
  title: string;
  description: string;
  category: string;
  goal_type: string;
  applicable_roles: string[];
}

interface SuggestionsResponse {
  suggestions: GoalSuggestion[];
  templates: Record<string, GoalTemplate[]>;
  enrichment_context: {
    company: { name: string; classification: Record<string, unknown> } | null;
    connected_integrations: string[];
  } | null;
}

type InputMode = "suggested" | "templates" | "freeform";

export function FirstGoalStep({ onComplete }: FirstGoalStepProps) {
  const [inputMode, setInputMode] = useState<InputMode>("suggested");
  const [suggestions, setSuggestions] = useState<SuggestionsResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreating, setIsCreating] = useState(false);
  const [selectedGoal, setSelectedGoal] = useState<{
    title: string;
    description: string;
    goal_type: string;
  } | null>(null);
  const [freeformInput, setFreeformInput] = useState("");
  const [validationResult, setValidationResult] = useState<{
    is_smart: boolean;
    score: number;
    feedback: string[];
    refined_version: string | null;
  } | null>(null);
  const [isValidating, setIsValidating] = useState(false);

  useEffect(() => {
    loadSuggestions();
  }, []);

  const loadSuggestions = async () => {
    setIsLoading(true);
    try {
      const response = await getFirstGoalSuggestions();
      setSuggestions(response);
    } catch {
      // Continue with default state on error
    } finally {
      setIsLoading(false);
    }
  };

  const handleSelectSuggestion = (suggestion: GoalSuggestion) => {
    setSelectedGoal({
      title: suggestion.title,
      description: suggestion.description,
      goal_type: suggestion.goal_type,
    });
    setValidationResult(null);
  };

  const handleSelectTemplate = (template: GoalTemplate) => {
    setSelectedGoal({
      title: template.title,
      description: template.description,
      goal_type: template.goal_type,
    });
    setValidationResult(null);
  };

  const handleFreeformSubmit = async () => {
    if (!freeformInput.trim()) return;

    setIsValidating(true);
    setValidationResult(null);

    try {
      const result = await validateGoalSmart({
        title: freeformInput,
        description: undefined,
      });

      setValidationResult(result);

      if (result.is_smart) {
        setSelectedGoal({
          title: freeformInput,
          description: "",
          goal_type: "custom",
        });
      }
    } finally {
      setIsValidating(false);
    }
  };

  const handleUseRefinedVersion = () => {
    if (validationResult?.refined_version) {
      setSelectedGoal({
        title: validationResult.refined_version,
        description: "",
        goal_type: "custom",
      });
      setValidationResult(null);
      setFreeformInput("");
    }
  };

  const handleEditGoal = () => {
    // Allow editing of selected goal
    if (selectedGoal) {
      setFreeformInput(selectedGoal.title);
      setSelectedGoal(null);
      setInputMode("freeform");
    }
  };

  const getAssignedAgents = (goalType: string): string[] => {
    const agentMap: Record<string, string[]> = {
      lead_gen: ["Hunter", "Analyst"],
      research: ["Analyst", "Scout"],
      outreach: ["Scribe", "Hunter"],
      analysis: ["Analyst"],
      custom: ["Analyst", "Scribe"],
    };
    return agentMap[goalType] || ["Analyst"];
  };

  const handleActivate = async () => {
    if (!selectedGoal) return;

    setIsCreating(true);
    try {
      // Create the goal via API
      await createFirstGoal({
        title: selectedGoal.title,
        description: selectedGoal.description,
        goal_type: selectedGoal.goal_type,
      });

      // Complete the onboarding step
      await completeStep("first_goal", {
        goal: selectedGoal,
      });

      // Notify parent
      onComplete(selectedGoal);
    } catch {
      setIsCreating(false);
    }
  };

  return (
    <div className="flex flex-col gap-8 max-w-2xl animate-in fade-in slide-in-from-bottom-4 duration-400">
      {/* Header */}
      <div className="flex flex-col gap-3">
        <h1 className="text-[32px] leading-[1.2] text-content font-display">
          What should ARIA focus on first?
        </h1>
        <p className="font-sans text-[15px] leading-relaxed text-secondary">
          Set your first goal and ARIA will start working on it immediately.
        </p>
      </div>

      {/* Loading State */}
      {isLoading && (
        <div className="flex flex-col items-center justify-center gap-4 py-12">
          <Loader2 size={32} strokeWidth={1.5} className="text-interactive animate-spin" />
          <p className="font-sans text-[13px] text-secondary">
            I'm analyzing what we've learned to suggest the best goals for you...
          </p>
        </div>
      )}

      {/* Input Mode Selector - shown when no goal selected */}
      {!isLoading && !selectedGoal && (
        <div className="flex flex-col gap-6">
          {/* Mode Tabs */}
          <div className="flex items-center gap-2 border-b border-border">
            <button
              type="button"
              onClick={() => setInputMode("suggested")}
              className={`font-sans text-[13px] font-medium px-4 py-2 border-b-2 transition-colors duration-150 ${
                inputMode === "suggested"
                  ? "text-interactive border-interactive"
                  : "text-secondary border-transparent hover:text-content"
              }`}
            >
              Suggested for You
            </button>
            <button
              type="button"
              onClick={() => setInputMode("templates")}
              className={`font-sans text-[13px] font-medium px-4 py-2 border-b-2 transition-colors duration-150 ${
                inputMode === "templates"
                  ? "text-interactive border-interactive"
                  : "text-secondary border-transparent hover:text-content"
              }`}
            >
              Goal Templates
            </button>
            <button
              type="button"
              onClick={() => setInputMode("freeform")}
              className={`font-sans text-[13px] font-medium px-4 py-2 border-b-2 transition-colors duration-150 ${
                inputMode === "freeform"
                  ? "text-interactive border-interactive"
                  : "text-secondary border-transparent hover:text-content"
              }`}
            >
              Describe Your Own
            </button>
          </div>

          {/* Suggested Goals */}
          {inputMode === "suggested" && suggestions && (
            <div className="flex flex-col gap-4">
              {suggestions.suggestions.length > 0 ? (
                suggestions.suggestions.map((suggestion, index) => (
                  <button
                    key={index}
                    type="button"
                    onClick={() => handleSelectSuggestion(suggestion)}
                    className="bg-elevated border border-border rounded-xl p-5 text-left hover:border-interactive hover:shadow-sm transition-all duration-200 group"
                  >
                    <div className="flex items-start gap-3">
                      <Target size={20} strokeWidth={1.5} className="text-interactive shrink-0 mt-0.5" />
                      <div className="flex flex-col gap-2 flex-1">
                        <h3 className="font-sans text-[15px] font-medium text-content group-hover:text-interactive transition-colors">
                          {suggestion.title}
                        </h3>
                        <p className="font-sans text-[13px] text-secondary leading-relaxed">
                          {suggestion.description}
                        </p>
                        <p className="font-sans text-[13px] text-interactive italic">
                          "{suggestion.reason}"
                        </p>
                      </div>
                      <ArrowRight size={16} strokeWidth={1.5} className="text-border group-hover:text-interactive transition-colors shrink-0 mt-2" />
                    </div>
                  </button>
                ))
              ) : (
                <div className="bg-elevated border border-border rounded-xl p-6 text-center">
                  <Sparkles size={24} strokeWidth={1.5} className="text-secondary mx-auto mb-3" />
                  <p className="font-sans text-[13px] text-secondary">
                    Complete more onboarding steps to get personalized suggestions,
                    or choose from templates or describe your own goal.
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Goal Templates */}
          {inputMode === "templates" && suggestions && (
            <div className="flex flex-col gap-6">
              {Object.entries(suggestions.templates).map(([category, templates]) => (
                <div key={category} className="flex flex-col gap-3">
                  <h3 className="font-sans text-[13px] font-medium text-content capitalize">
                    {category.replace(/_/g, " ")}
                  </h3>
                  <div className="grid grid-cols-2 gap-3">
                    {templates.map((template, index) => (
                      <button
                        key={index}
                        type="button"
                        onClick={() => handleSelectTemplate(template)}
                        className="bg-elevated border border-border rounded-lg p-4 text-left hover:border-interactive hover:shadow-sm transition-all duration-200 group"
                      >
                        <div className="flex flex-col gap-1">
                          <h4 className="font-sans text-[13px] font-medium text-content group-hover:text-interactive transition-colors">
                            {template.title}
                          </h4>
                          <p className="font-sans text-[11px] text-secondary line-clamp-2">
                            {template.description}
                          </p>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Free-form Input */}
          {inputMode === "freeform" && (
            <div className="flex flex-col gap-4">
              <div className="bg-elevated border border-border rounded-xl p-5">
                <label
                  htmlFor="goal-input"
                  className="font-sans text-[13px] font-medium text-secondary mb-2 block"
                >
                  Describe your goal in your own words
                </label>
                <textarea
                  id="goal-input"
                  value={freeformInput}
                  onChange={(e) => setFreeformInput(e.target.value)}
                  placeholder="e.g., 'Help me prepare for the Pfizer meeting on Friday' or 'I need to build pipeline in the Northeast territory this quarter'"
                  rows={3}
                  className="w-full bg-subtle text-content placeholder:text-secondary/50 border border-border rounded-lg px-4 py-3 text-[15px] font-sans focus:outline-none focus:ring-1 focus:border-interactive focus:ring-interactive resize-none"
                />
                <button
                  type="button"
                  onClick={handleFreeformSubmit}
                  disabled={!freeformInput.trim() || isValidating}
                  className="mt-4 bg-interactive text-white rounded-lg px-5 py-2.5 font-sans font-medium text-[13px] hover:bg-interactive-hover active:bg-interactive-hover transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-interactive focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer flex items-center justify-center gap-2 min-h-[44px]"
                >
                  {isValidating ? (
                    <>
                      <Loader2 size={14} strokeWidth={1.5} className="animate-spin" />
                      <span>Analyzing...</span>
                    </>
                  ) : (
                    "Continue"
                  )}
                </button>
              </div>

              {/* SMART Validation Result */}
              {validationResult && (
                <div className={`rounded-xl border p-5 ${
                  validationResult.is_smart
                    ? "bg-primary border-success"
                    : "bg-primary border-warning"
                }`}>
                  <h4 className="font-sans text-[13px] font-medium mb-3">
                    {validationResult.is_smart
                      ? "Your goal looks great!"
                      : "Let me help refine this"}
                  </h4>

                  {!validationResult.is_smart && validationResult.refined_version && (
                    <div className="flex flex-col gap-3 mb-3">
                      <p className="font-sans text-[13px] text-secondary">
                        Based on what you said, here's a more specific version:
                      </p>
                      <div className="bg-elevated border border-border rounded-lg p-3">
                        <p className="font-sans text-[13px] text-content">
                          {validationResult.refined_version}
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={handleUseRefinedVersion}
                        className="text-interactive font-sans text-[13px] font-medium hover:text-interactive-hover transition-colors cursor-pointer"
                      >
                        Use this version →
                      </button>
                    </div>
                  )}

                  {validationResult.feedback.length > 0 && (
                    <ul className="flex flex-col gap-1">
                      {validationResult.feedback.map((item, index) => (
                        <li key={index} className="font-sans text-[13px] text-secondary">
                          • {item}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Goal Preview */}
      {selectedGoal && (
        <div className="flex flex-col gap-6 animate-in fade-in slide-in-from-bottom-2 duration-300">
          <div className="bg-elevated border border-border rounded-xl p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-sans text-[18px] font-medium text-content">
                Goal Preview
              </h3>
              <button
                type="button"
                onClick={handleEditGoal}
                className="font-sans text-[13px] text-interactive hover:text-interactive-hover transition-colors cursor-pointer"
              >
                Edit
              </button>
            </div>

            <div className="flex flex-col gap-4">
              <div>
                <label className="font-sans text-[11px] font-medium text-secondary uppercase tracking-wide">
                  Title
                </label>
                <p className="font-sans text-[15px] text-content mt-1">
                  {selectedGoal.title}
                </p>
              </div>

              {selectedGoal.description && (
                <div>
                  <label className="font-sans text-[11px] font-medium text-secondary uppercase tracking-wide">
                    Description
                  </label>
                  <p className="font-sans text-[13px] text-secondary mt-1 leading-relaxed">
                    {selectedGoal.description}
                  </p>
                </div>
              )}

              <div className="pt-4 border-t border-border">
                <p className="font-sans text-[13px] text-secondary">
                  <span className="font-medium">ARIA will assign:</span>{" "}
                  {getAssignedAgents(selectedGoal.goal_type).join(", ")} to work on this
                </p>
              </div>
            </div>
          </div>

          {/* ARIA Presence */}
          <div className="flex flex-col gap-2 bg-primary border border-border rounded-xl p-5">
            <p className="font-sans text-[13px] text-content">
              This goal shapes my first 24 hours. I'll have results in your morning briefing.
            </p>
          </div>

          {/* Activate Button - momentous styling */}
          <button
            type="button"
            onClick={handleActivate}
            disabled={isCreating}
            className="bg-interactive text-white rounded-xl px-6 py-4 font-sans font-medium text-[15px] hover:bg-interactive-hover active:bg-interactive-hover transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-interactive focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer flex items-center justify-center gap-3 min-h-[56px] shadow-sm"
          >
            {isCreating ? (
              <>
                <Loader2 size={18} strokeWidth={1.5} className="animate-spin" />
                <span>Activating ARIA...</span>
              </>
            ) : (
              <>
                <Sparkles size={18} strokeWidth={1.5} />
                <span>Activate ARIA</span>
              </>
            )}
          </button>
        </div>
      )}
    </div>
  );
}
