import { useState, useEffect, useCallback, useRef } from "react";
import {
  X,
  ChevronRight,
  ChevronLeft,
  Sparkles,
  Check,
  Clock,
  Users,
  Brain,
  ChevronDown,
  ChevronUp,
  Loader2,
} from "lucide-react";
import { useCreateWithARIA, useCreateGoal, useGoalTemplates } from "@/hooks/useGoals";
import type { GoalType, GoalTemplate, ARIAGoalSuggestion } from "@/api/goals";

interface GoalCreationWizardProps {
  isOpen: boolean;
  onClose: () => void;
  onGoalCreated?: () => void;
}

type WizardStep = 1 | 2;

// ---------- Step Indicator ----------

function StepIndicator({ currentStep }: { currentStep: WizardStep }) {
  return (
    <div className="flex items-center justify-center gap-2 pt-5 pb-2">
      {[1, 2].map((step) => (
        <div
          key={step}
          className={`w-2.5 h-2.5 rounded-full transition-all ${
            step <= currentStep
              ? "bg-primary-500"
              : "border border-slate-500 bg-transparent"
          }`}
        />
      ))}
    </div>
  );
}

// ---------- Template Card ----------

function TemplateCard({
  template,
  onSelect,
}: {
  template: GoalTemplate;
  onSelect: (template: GoalTemplate) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(template)}
      className="flex-shrink-0 w-56 bg-slate-700/50 border border-slate-600 rounded-xl p-4 hover:border-slate-500 transition-all text-left"
    >
      <span className="inline-block px-2 py-0.5 text-xs font-medium rounded-full bg-primary-600/20 text-primary-400 border border-primary-500/30 mb-2">
        {template.category}
      </span>
      <h4 className="text-sm font-medium text-white truncate">{template.title}</h4>
      <p className="text-xs text-slate-400 mt-1 line-clamp-2">{template.description}</p>
    </button>
  );
}

// ---------- SMART Score Bar ----------

function SmartScoreBar({ score }: { score: number }) {
  const clampedScore = Math.max(0, Math.min(100, score));
  const color =
    clampedScore >= 80
      ? "bg-green-500"
      : clampedScore >= 50
        ? "bg-amber-500"
        : "bg-red-500";

  const label =
    clampedScore >= 80
      ? "Excellent"
      : clampedScore >= 50
        ? "Needs Improvement"
        : "Weak";

  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-sm font-medium text-slate-300">SMART Score</span>
        <span className="text-sm font-semibold text-white">
          {clampedScore}/100 &middot;{" "}
          <span
            className={
              clampedScore >= 80
                ? "text-green-400"
                : clampedScore >= 50
                  ? "text-amber-400"
                  : "text-red-400"
            }
          >
            {label}
          </span>
        </span>
      </div>
      <div className="w-full h-2 bg-slate-700 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${color}`}
          style={{ width: `${clampedScore}%` }}
        />
      </div>
    </div>
  );
}

// ---------- Sub-task Item ----------

function SubTaskItem({
  task,
  checked,
  onToggle,
}: {
  task: { title: string; description: string };
  checked: boolean;
  onToggle: () => void;
}) {
  return (
    <label className="flex items-start gap-3 cursor-pointer group">
      <div className="pt-0.5">
        <div
          onClick={onToggle}
          className={`w-5 h-5 rounded border flex items-center justify-center transition-all cursor-pointer ${
            checked
              ? "bg-primary-600 border-primary-500"
              : "border-slate-600 bg-slate-800 group-hover:border-slate-500"
          }`}
        >
          {checked && <Check className="w-3.5 h-3.5 text-white" />}
        </div>
      </div>
      <div className="flex-1 min-w-0">
        <span
          className={`text-sm font-medium transition-colors ${
            checked ? "text-white" : "text-slate-500 line-through"
          }`}
        >
          {task.title}
        </span>
        <p className="text-xs text-slate-500 mt-0.5">{task.description}</p>
      </div>
    </label>
  );
}

// ---------- Main Wizard Component ----------

export function GoalCreationWizard({
  isOpen,
  onClose,
  onGoalCreated,
}: GoalCreationWizardProps) {
  const [step, setStep] = useState<WizardStep>(1);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [selectedGoalType, setSelectedGoalType] = useState<GoalType>("custom");

  // Step 2 editable state
  const [refinedTitle, setRefinedTitle] = useState("");
  const [refinedDescription, setRefinedDescription] = useState("");
  const [selectedSubTasks, setSelectedSubTasks] = useState<boolean[]>([]);
  const [reasoningExpanded, setReasoningExpanded] = useState(false);

  const titleInputRef = useRef<HTMLInputElement>(null);

  const createWithARIA = useCreateWithARIA();
  const createGoal = useCreateGoal();
  const { data: templates, isLoading: templatesLoading } = useGoalTemplates();

  // Whether a critical mutation is in progress (blocks ESC)
  const isBusy = createGoal.isPending;

  // Reset state when modal opens
  useEffect(() => {
    if (isOpen) {
      setStep(1);
      setTitle("");
      setDescription("");
      setSelectedGoalType("custom");
      setRefinedTitle("");
      setRefinedDescription("");
      setSelectedSubTasks([]);
      setReasoningExpanded(false);
      createWithARIA.reset();
      createGoal.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  // Autofocus title input
  useEffect(() => {
    if (isOpen && step === 1) {
      // Use a small delay to ensure DOM is ready
      const timer = setTimeout(() => {
        titleInputRef.current?.focus();
      }, 100);
      return () => clearTimeout(timer);
    }
  }, [isOpen, step]);

  // ESC to close (unless busy)
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape" && !isBusy) {
        onClose();
      }
    },
    [onClose, isBusy]
  );

  useEffect(() => {
    if (isOpen) {
      document.addEventListener("keydown", handleKeyDown);
      return () => document.removeEventListener("keydown", handleKeyDown);
    }
  }, [isOpen, handleKeyDown]);

  // Populate step 2 fields when ARIA data arrives
  useEffect(() => {
    if (createWithARIA.data) {
      const suggestion: ARIAGoalSuggestion = createWithARIA.data;
      setRefinedTitle(suggestion.refined_title);
      setRefinedDescription(suggestion.refined_description);
      setSelectedSubTasks(suggestion.sub_tasks.map(() => true));
    }
  }, [createWithARIA.data]);

  // ---------- Handlers ----------

  function handleTemplateSelect(template: GoalTemplate) {
    setTitle(template.title);
    setDescription(template.description);
    setSelectedGoalType(template.goal_type);
  }

  function handleContinue() {
    if (!title.trim()) return;
    setStep(2);
    createWithARIA.mutate({
      title: title.trim(),
      description: description.trim() || undefined,
    });
  }

  function handleBack() {
    setStep(1);
  }

  function toggleSubTask(index: number) {
    setSelectedSubTasks((prev) => {
      const next = [...prev];
      next[index] = !next[index];
      return next;
    });
  }

  function handleCreateGoal() {
    createGoal.mutate(
      {
        title: refinedTitle.trim() || title.trim(),
        description: refinedDescription.trim() || undefined,
        goal_type: selectedGoalType,
      },
      {
        onSuccess: () => {
          onGoalCreated?.();
          onClose();
        },
      }
    );
  }

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/60 backdrop-blur-sm"
        onClick={isBusy ? undefined : onClose}
      />

      {/* Container */}
      <div className="relative z-10 w-full max-w-2xl mx-4 mt-20 mb-10 bg-slate-800 border border-slate-700 rounded-2xl shadow-2xl">
        {/* Close button */}
        <button
          onClick={onClose}
          disabled={isBusy}
          className="absolute top-4 right-4 p-2 text-slate-400 hover:text-white hover:bg-slate-700 rounded-lg transition-colors disabled:opacity-50 z-10"
          aria-label="Close"
        >
          <X className="w-5 h-5" />
        </button>

        {/* Step indicator */}
        <StepIndicator currentStep={step} />

        {/* Step content */}
        {step === 1 ? (
          <Step1UserInput
            title={title}
            setTitle={setTitle}
            description={description}
            setDescription={setDescription}
            titleInputRef={titleInputRef}
            templates={templates ?? []}
            templatesLoading={templatesLoading}
            onTemplateSelect={handleTemplateSelect}
            onContinue={handleContinue}
          />
        ) : (
          <Step2ARIASuggestions
            ariaPending={createWithARIA.isPending}
            ariaError={createWithARIA.isError}
            suggestion={createWithARIA.data ?? null}
            refinedTitle={refinedTitle}
            setRefinedTitle={setRefinedTitle}
            refinedDescription={refinedDescription}
            setRefinedDescription={setRefinedDescription}
            selectedSubTasks={selectedSubTasks}
            onToggleSubTask={toggleSubTask}
            reasoningExpanded={reasoningExpanded}
            setReasoningExpanded={setReasoningExpanded}
            onBack={handleBack}
            onCreateGoal={handleCreateGoal}
            isCreating={createGoal.isPending}
            onRetry={() =>
              createWithARIA.mutate({
                title: title.trim(),
                description: description.trim() || undefined,
              })
            }
          />
        )}
      </div>
    </div>
  );
}

// ---------- Step 1: User Input ----------

interface Step1Props {
  title: string;
  setTitle: (v: string) => void;
  description: string;
  setDescription: (v: string) => void;
  titleInputRef: React.RefObject<HTMLInputElement | null>;
  templates: GoalTemplate[];
  templatesLoading: boolean;
  onTemplateSelect: (t: GoalTemplate) => void;
  onContinue: () => void;
}

function Step1UserInput({
  title,
  setTitle,
  description,
  setDescription,
  titleInputRef,
  templates,
  templatesLoading,
  onTemplateSelect,
  onContinue,
}: Step1Props) {
  return (
    <div className="px-6 pb-6 pt-2">
      <h2 className="text-xl font-semibold text-white mb-1">Create a New Goal</h2>
      <p className="text-sm text-slate-400 mb-5">
        Describe what you want to achieve and ARIA will help you refine it.
      </p>

      {/* Title input */}
      <div className="mb-4">
        <label
          htmlFor="wizard-title"
          className="block text-sm font-medium text-slate-300 mb-1.5"
        >
          Goal Title <span className="text-red-400">*</span>
        </label>
        <input
          ref={titleInputRef}
          id="wizard-title"
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="e.g., Find 50 biotech leads in Boston"
          className="w-full px-4 py-2.5 bg-slate-900 border border-slate-700 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all"
          onKeyDown={(e) => {
            if (e.key === "Enter" && title.trim()) {
              e.preventDefault();
              onContinue();
            }
          }}
        />
      </div>

      {/* Description textarea */}
      <div className="mb-5">
        <label
          htmlFor="wizard-desc"
          className="block text-sm font-medium text-slate-300 mb-1.5"
        >
          Description{" "}
          <span className="text-slate-500 font-normal">(optional)</span>
        </label>
        <textarea
          id="wizard-desc"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Add context or constraints for ARIA to consider..."
          rows={3}
          className="w-full px-4 py-2.5 bg-slate-900 border border-slate-700 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all resize-none"
        />
      </div>

      {/* Templates */}
      <div className="mb-6">
        <h3 className="text-sm font-medium text-slate-300 mb-2">
          Or start from a template
        </h3>
        {templatesLoading ? (
          <div className="flex items-center gap-2 text-sm text-slate-500 py-4">
            <Loader2 className="w-4 h-4 animate-spin" />
            Loading templates...
          </div>
        ) : templates.length === 0 ? (
          <p className="text-sm text-slate-500 py-2">No templates available.</p>
        ) : (
          <div className="flex gap-3 overflow-x-auto pb-2 -mx-1 px-1 scrollbar-thin scrollbar-track-transparent scrollbar-thumb-slate-700">
            {templates.map((template, idx) => (
              <TemplateCard
                key={`${template.title}-${idx}`}
                template={template}
                onSelect={onTemplateSelect}
              />
            ))}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="flex justify-end">
        <button
          type="button"
          onClick={onContinue}
          disabled={!title.trim()}
          className="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-medium bg-primary-600 hover:bg-primary-500 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Continue
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}

// ---------- Step 2: ARIA Suggestions ----------

interface Step2Props {
  ariaPending: boolean;
  ariaError: boolean;
  suggestion: ARIAGoalSuggestion | null;
  refinedTitle: string;
  setRefinedTitle: (v: string) => void;
  refinedDescription: string;
  setRefinedDescription: (v: string) => void;
  selectedSubTasks: boolean[];
  onToggleSubTask: (i: number) => void;
  reasoningExpanded: boolean;
  setReasoningExpanded: (v: boolean) => void;
  onBack: () => void;
  onCreateGoal: () => void;
  isCreating: boolean;
  onRetry: () => void;
}

function Step2ARIASuggestions({
  ariaPending,
  ariaError,
  suggestion,
  refinedTitle,
  setRefinedTitle,
  refinedDescription,
  setRefinedDescription,
  selectedSubTasks,
  onToggleSubTask,
  reasoningExpanded,
  setReasoningExpanded,
  onBack,
  onCreateGoal,
  isCreating,
  onRetry,
}: Step2Props) {
  // Loading state
  if (ariaPending) {
    return (
      <div className="px-6 pb-8 pt-4 flex flex-col items-center justify-center min-h-[300px]">
        <div className="animate-pulse flex flex-col items-center gap-4">
          <div className="relative">
            <Sparkles className="w-10 h-10 text-primary-400" />
            <div className="absolute inset-0 w-10 h-10 rounded-full bg-primary-400/20 animate-ping" />
          </div>
          <p className="text-slate-300 text-sm font-medium">
            ARIA is analyzing your goal...
          </p>
          <p className="text-slate-500 text-xs">
            Refining, scoring, and generating sub-tasks
          </p>
        </div>
      </div>
    );
  }

  // Error state
  if (ariaError) {
    return (
      <div className="px-6 pb-8 pt-4 flex flex-col items-center justify-center min-h-[300px] gap-4">
        <p className="text-red-400 text-sm">
          Failed to get ARIA suggestions. Please try again.
        </p>
        <div className="flex gap-3">
          <button
            type="button"
            onClick={onBack}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-slate-400 hover:text-white hover:bg-slate-700 rounded-lg transition-colors"
          >
            <ChevronLeft className="w-4 h-4" />
            Back
          </button>
          <button
            type="button"
            onClick={onRetry}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium bg-primary-600 hover:bg-primary-500 text-white rounded-lg transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  // No data yet (shouldn't normally happen, but guard)
  if (!suggestion) return null;

  return (
    <div className="px-6 pb-6 pt-2">
      <div className="flex items-center gap-2 mb-4">
        <Sparkles className="w-5 h-5 text-primary-400" />
        <h2 className="text-xl font-semibold text-white">ARIA&apos;s Suggestions</h2>
      </div>

      <div className="bg-slate-900/50 rounded-xl p-5 border border-slate-700 space-y-5">
        {/* Refined Title */}
        <div>
          <label
            htmlFor="refined-title"
            className="block text-sm font-medium text-slate-300 mb-1.5"
          >
            Refined Title
          </label>
          <input
            id="refined-title"
            type="text"
            value={refinedTitle}
            onChange={(e) => setRefinedTitle(e.target.value)}
            className="w-full px-4 py-2.5 bg-slate-800 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all"
            disabled={isCreating}
          />
        </div>

        {/* Refined Description */}
        <div>
          <label
            htmlFor="refined-desc"
            className="block text-sm font-medium text-slate-300 mb-1.5"
          >
            Refined Description
          </label>
          <textarea
            id="refined-desc"
            value={refinedDescription}
            onChange={(e) => setRefinedDescription(e.target.value)}
            rows={3}
            className="w-full px-4 py-2.5 bg-slate-800 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all resize-none"
            disabled={isCreating}
          />
        </div>

        {/* SMART Score */}
        <SmartScoreBar score={suggestion.smart_score} />

        {/* Sub-tasks */}
        {suggestion.sub_tasks.length > 0 && (
          <div>
            <h3 className="text-sm font-medium text-slate-300 mb-2">
              Suggested Sub-tasks
            </h3>
            <div className="space-y-2.5">
              {suggestion.sub_tasks.map((task, idx) => (
                <SubTaskItem
                  key={`${task.title}-${idx}`}
                  task={task}
                  checked={selectedSubTasks[idx] ?? true}
                  onToggle={() => onToggleSubTask(idx)}
                />
              ))}
            </div>
          </div>
        )}

        {/* Agent Assignments & Timeline row */}
        <div className="flex flex-wrap items-center gap-4">
          {/* Agent Assignments */}
          {suggestion.agent_assignments.length > 0 && (
            <div className="flex items-center gap-2">
              <Users className="w-4 h-4 text-slate-400" />
              <span className="text-xs text-slate-400 mr-1">Agents:</span>
              <div className="flex flex-wrap gap-1.5">
                {suggestion.agent_assignments.map((agent) => (
                  <span
                    key={agent}
                    className="inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-full bg-primary-600/20 text-primary-400 border border-primary-500/30"
                  >
                    {agent}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Timeline */}
          {suggestion.suggested_timeline_days > 0 && (
            <div className="flex items-center gap-1.5 text-slate-400">
              <Clock className="w-4 h-4" />
              <span className="text-xs">
                {suggestion.suggested_timeline_days} day
                {suggestion.suggested_timeline_days !== 1 ? "s" : ""}
              </span>
            </div>
          )}
        </div>

        {/* ARIA's Reasoning (collapsible) */}
        {suggestion.reasoning && (
          <div>
            <button
              type="button"
              onClick={() => setReasoningExpanded(!reasoningExpanded)}
              className="flex items-center gap-2 text-sm font-medium text-slate-400 hover:text-slate-300 transition-colors"
            >
              <Brain className="w-4 h-4" />
              ARIA&apos;s Reasoning
              {reasoningExpanded ? (
                <ChevronUp className="w-4 h-4" />
              ) : (
                <ChevronDown className="w-4 h-4" />
              )}
            </button>
            {reasoningExpanded && (
              <p className="mt-2 text-sm text-slate-400 leading-relaxed bg-slate-800/50 rounded-lg p-3 border border-slate-700">
                {suggestion.reasoning}
              </p>
            )}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between mt-5">
        <button
          type="button"
          onClick={onBack}
          disabled={isCreating}
          className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-slate-400 hover:text-white hover:bg-slate-700 rounded-lg transition-colors disabled:opacity-50"
        >
          <ChevronLeft className="w-4 h-4" />
          Back
        </button>
        <button
          type="button"
          onClick={onCreateGoal}
          disabled={isCreating || !refinedTitle.trim()}
          className="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-medium bg-primary-600 hover:bg-primary-500 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isCreating ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Creating...
            </>
          ) : (
            <>
              <Sparkles className="w-4 h-4" />
              Create Goal
            </>
          )}
        </button>
      </div>
    </div>
  );
}
