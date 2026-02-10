import { useState, useCallback } from "react";
import {
  DragDropContext,
  Droppable,
  Draggable,
} from "react-beautiful-dnd";
import type { DropResult } from "react-beautiful-dnd";
import {
  Sun,
  Calendar,
  Radar,
  Zap,
  Plus,
  Trash2,
  GripVertical,
  Clock,
  Mail,
  Bell,
  ListTodo,
  ChevronDown,
  Check,
  X,
  Shield,
  Settings,
} from "lucide-react";
import type {
  WorkflowResponse,
  CreateWorkflowData,
  WorkflowTrigger,
  WorkflowAction,
  ActionType,
  TriggerType,
  WorkflowMetadata,
} from "@/api/workflows";

// --- Constants ---

const TRIGGER_TYPES: { value: TriggerType; label: string; icon: typeof Clock }[] = [
  { value: "time", label: "Scheduled (Cron)", icon: Clock },
  { value: "event", label: "Event-Based", icon: Zap },
  { value: "condition", label: "Condition-Based", icon: Radar },
];

const EVENT_TYPES = [
  "calendar_event_ended",
  "email_received",
  "signal_detected",
] as const;

const CONDITION_OPERATORS = [
  { value: "lt", label: "Less than" },
  { value: "gt", label: "Greater than" },
  { value: "eq", label: "Equals" },
  { value: "contains", label: "Contains" },
] as const;

const TIMEZONES = [
  "UTC",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "Europe/London",
  "Europe/Berlin",
  "Europe/Paris",
  "Asia/Tokyo",
  "Asia/Shanghai",
  "Australia/Sydney",
] as const;

const ACTION_TYPES: {
  value: ActionType;
  label: string;
  icon: typeof Zap;
  description: string;
}[] = [
  { value: "run_skill", label: "Run Skill", icon: Zap, description: "Execute an ARIA skill" },
  { value: "send_notification", label: "Send Notification", icon: Bell, description: "Send a Slack or in-app notification" },
  { value: "create_task", label: "Create Task", icon: ListTodo, description: "Create a new task" },
  { value: "draft_email", label: "Draft Email", icon: Mail, description: "Draft an email using a skill" },
];

const FAILURE_POLICIES = [
  { value: "stop", label: "Stop workflow" },
  { value: "skip", label: "Skip this step" },
  { value: "retry", label: "Retry once" },
] as const;

function getActionIcon(actionType: ActionType) {
  switch (actionType) {
    case "run_skill":
      return Zap;
    case "send_notification":
      return Bell;
    case "create_task":
      return ListTodo;
    case "draft_email":
      return Mail;
  }
}

function getActionLabel(actionType: ActionType): string {
  switch (actionType) {
    case "run_skill":
      return "Run Skill";
    case "send_notification":
      return "Send Notification";
    case "create_task":
      return "Create Task";
    case "draft_email":
      return "Draft Email";
  }
}

function getActionConfigSummary(action: WorkflowAction): string {
  const config = action.config;
  switch (action.action_type) {
    case "run_skill":
      return config.skill_id ? `Skill: ${String(config.skill_id)}` : "No skill configured";
    case "send_notification":
      return config.channel ? `Via ${String(config.channel)}` : "No channel set";
    case "create_task":
      return config.title ? String(config.title) : "No title set";
    case "draft_email":
      return config.subject_template ? String(config.subject_template) : "No subject set";
  }
}

function generateStepId(): string {
  return `step_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

// --- Sub-components ---

interface TriggerConfigProps {
  trigger: WorkflowTrigger;
  onChange: (trigger: WorkflowTrigger) => void;
}

function TriggerConfig({ trigger, onChange }: TriggerConfigProps) {
  return (
    <div className="space-y-4">
      {/* Trigger type selector */}
      <div>
        <label className="block text-xs font-medium text-slate-400 mb-1.5">Trigger Type</label>
        <div className="grid grid-cols-3 gap-2">
          {TRIGGER_TYPES.map(({ value, label, icon: Icon }) => (
            <button
              key={value}
              type="button"
              onClick={() => onChange({ ...trigger, type: value })}
              className={`flex items-center gap-2 px-3 py-2 text-xs font-medium rounded-lg border transition-colors ${
                trigger.type === value
                  ? "bg-primary-500/15 text-primary-400 border-primary-500/30"
                  : "bg-slate-800/50 text-slate-400 border-slate-700 hover:border-slate-600"
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Time trigger config */}
      {trigger.type === "time" && (
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">Cron Expression</label>
            <input
              type="text"
              value={trigger.cron_expression ?? ""}
              onChange={(e) => onChange({ ...trigger, cron_expression: e.target.value })}
              placeholder="0 9 * * 1-5"
              className="w-full px-3 py-2 text-sm text-white bg-slate-900/50 border border-slate-700 rounded-lg placeholder:text-slate-600 focus:outline-none focus:border-primary-500/50 focus:ring-1 focus:ring-primary-500/20"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">Timezone</label>
            <select
              value={trigger.timezone ?? "UTC"}
              onChange={(e) => onChange({ ...trigger, timezone: e.target.value })}
              className="w-full px-3 py-2 text-sm text-white bg-slate-900/50 border border-slate-700 rounded-lg focus:outline-none focus:border-primary-500/50 focus:ring-1 focus:ring-primary-500/20 appearance-none"
            >
              {TIMEZONES.map((tz) => (
                <option key={tz} value={tz}>{tz}</option>
              ))}
            </select>
          </div>
        </div>
      )}

      {/* Event trigger config */}
      {trigger.type === "event" && (
        <div>
          <label className="block text-xs font-medium text-slate-400 mb-1.5">Event Type</label>
          <select
            value={trigger.event_type ?? ""}
            onChange={(e) => onChange({ ...trigger, event_type: e.target.value })}
            className="w-full px-3 py-2 text-sm text-white bg-slate-900/50 border border-slate-700 rounded-lg focus:outline-none focus:border-primary-500/50 focus:ring-1 focus:ring-primary-500/20 appearance-none"
          >
            <option value="">Select event type...</option>
            {EVENT_TYPES.map((et) => (
              <option key={et} value={et}>{et.replace(/_/g, " ")}</option>
            ))}
          </select>
        </div>
      )}

      {/* Condition trigger config */}
      {trigger.type === "condition" && (
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">Field</label>
            <input
              type="text"
              value={(trigger.condition_field as string) ?? ""}
              onChange={(e) => onChange({ ...trigger, condition_field: e.target.value })}
              placeholder="e.g. deal.amount"
              className="w-full px-3 py-2 text-sm text-white bg-slate-900/50 border border-slate-700 rounded-lg placeholder:text-slate-600 focus:outline-none focus:border-primary-500/50 focus:ring-1 focus:ring-primary-500/20"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">Operator</label>
            <select
              value={(trigger.condition_operator as string) ?? ""}
              onChange={(e) => onChange({ ...trigger, condition_operator: e.target.value })}
              className="w-full px-3 py-2 text-sm text-white bg-slate-900/50 border border-slate-700 rounded-lg focus:outline-none focus:border-primary-500/50 focus:ring-1 focus:ring-primary-500/20 appearance-none"
            >
              <option value="">Select...</option>
              {CONDITION_OPERATORS.map((op) => (
                <option key={op.value} value={op.value}>{op.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">Value</label>
            <input
              type="text"
              value={trigger.condition_value != null ? String(trigger.condition_value) : ""}
              onChange={(e) => onChange({ ...trigger, condition_value: e.target.value })}
              placeholder="e.g. 10000"
              className="w-full px-3 py-2 text-sm text-white bg-slate-900/50 border border-slate-700 rounded-lg placeholder:text-slate-600 focus:outline-none focus:border-primary-500/50 focus:ring-1 focus:ring-primary-500/20"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">Entity (optional)</label>
            <input
              type="text"
              value={trigger.event_filter?.entity != null ? String(trigger.event_filter.entity) : ""}
              onChange={(e) =>
                onChange({
                  ...trigger,
                  event_filter: { ...trigger.event_filter, entity: e.target.value },
                })
              }
              placeholder="e.g. lead"
              className="w-full px-3 py-2 text-sm text-white bg-slate-900/50 border border-slate-700 rounded-lg placeholder:text-slate-600 focus:outline-none focus:border-primary-500/50 focus:ring-1 focus:ring-primary-500/20"
            />
          </div>
        </div>
      )}
    </div>
  );
}

interface ActionConfigPanelProps {
  action: WorkflowAction;
  onChange: (action: WorkflowAction) => void;
}

function ActionConfigPanel({ action, onChange }: ActionConfigPanelProps) {
  const updateConfig = (key: string, value: unknown) => {
    onChange({ ...action, config: { ...action.config, [key]: value } });
  };

  switch (action.action_type) {
    case "run_skill":
      return (
        <div className="space-y-3">
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">Skill ID</label>
            <input
              type="text"
              value={(action.config.skill_id as string) ?? ""}
              onChange={(e) => updateConfig("skill_id", e.target.value)}
              placeholder="e.g. meeting_prep"
              className="w-full px-3 py-2 text-sm text-white bg-slate-900/50 border border-slate-700 rounded-lg placeholder:text-slate-600 focus:outline-none focus:border-primary-500/50 focus:ring-1 focus:ring-primary-500/20"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">Template</label>
            <input
              type="text"
              value={(action.config.template as string) ?? ""}
              onChange={(e) => updateConfig("template", e.target.value)}
              placeholder="Optional template override"
              className="w-full px-3 py-2 text-sm text-white bg-slate-900/50 border border-slate-700 rounded-lg placeholder:text-slate-600 focus:outline-none focus:border-primary-500/50 focus:ring-1 focus:ring-primary-500/20"
            />
          </div>
        </div>
      );

    case "send_notification":
      return (
        <div className="space-y-3">
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">Channel</label>
            <select
              value={(action.config.channel as string) ?? ""}
              onChange={(e) => updateConfig("channel", e.target.value)}
              className="w-full px-3 py-2 text-sm text-white bg-slate-900/50 border border-slate-700 rounded-lg focus:outline-none focus:border-primary-500/50 focus:ring-1 focus:ring-primary-500/20 appearance-none"
            >
              <option value="">Select channel...</option>
              <option value="slack">Slack</option>
              <option value="in_app">In-App</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">Message Template</label>
            <textarea
              value={(action.config.message_template as string) ?? ""}
              onChange={(e) => updateConfig("message_template", e.target.value)}
              placeholder="Notification message..."
              rows={3}
              className="w-full px-3 py-2 text-sm text-white bg-slate-900/50 border border-slate-700 rounded-lg placeholder:text-slate-600 focus:outline-none focus:border-primary-500/50 focus:ring-1 focus:ring-primary-500/20 resize-none"
            />
          </div>
        </div>
      );

    case "create_task":
      return (
        <div className="space-y-3">
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">Task Title</label>
            <input
              type="text"
              value={(action.config.title as string) ?? ""}
              onChange={(e) => updateConfig("title", e.target.value)}
              placeholder="Task title"
              className="w-full px-3 py-2 text-sm text-white bg-slate-900/50 border border-slate-700 rounded-lg placeholder:text-slate-600 focus:outline-none focus:border-primary-500/50 focus:ring-1 focus:ring-primary-500/20"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">Description</label>
            <textarea
              value={(action.config.description as string) ?? ""}
              onChange={(e) => updateConfig("description", e.target.value)}
              placeholder="Task description..."
              rows={3}
              className="w-full px-3 py-2 text-sm text-white bg-slate-900/50 border border-slate-700 rounded-lg placeholder:text-slate-600 focus:outline-none focus:border-primary-500/50 focus:ring-1 focus:ring-primary-500/20 resize-none"
            />
          </div>
        </div>
      );

    case "draft_email":
      return (
        <div className="space-y-3">
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">Subject Template</label>
            <input
              type="text"
              value={(action.config.subject_template as string) ?? ""}
              onChange={(e) => updateConfig("subject_template", e.target.value)}
              placeholder="Email subject template"
              className="w-full px-3 py-2 text-sm text-white bg-slate-900/50 border border-slate-700 rounded-lg placeholder:text-slate-600 focus:outline-none focus:border-primary-500/50 focus:ring-1 focus:ring-primary-500/20"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">Body Skill</label>
            <input
              type="text"
              value={(action.config.body_skill as string) ?? ""}
              onChange={(e) => updateConfig("body_skill", e.target.value)}
              placeholder="Skill ID to generate body"
              className="w-full px-3 py-2 text-sm text-white bg-slate-900/50 border border-slate-700 rounded-lg placeholder:text-slate-600 focus:outline-none focus:border-primary-500/50 focus:ring-1 focus:ring-primary-500/20"
            />
          </div>
        </div>
      );
  }
}

interface ActionItemProps {
  action: WorkflowAction;
  index: number;
  onChange: (action: WorkflowAction) => void;
  onRemove: () => void;
}

function ActionItem({ action, index, onChange, onRemove }: ActionItemProps) {
  const [expanded, setExpanded] = useState(false);
  const Icon = getActionIcon(action.action_type);

  return (
    <Draggable draggableId={action.step_id} index={index}>
      {(provided, snapshot) => (
        <div
          ref={provided.innerRef}
          {...provided.draggableProps}
          className={`bg-slate-800/70 border rounded-lg transition-all ${
            snapshot.isDragging
              ? "border-primary-500/40 shadow-lg shadow-primary-500/10"
              : "border-slate-700"
          }`}
        >
          {/* Action header row */}
          <div className="flex items-center gap-2 p-3">
            {/* Drag handle */}
            <div
              {...provided.dragHandleProps}
              className="flex items-center justify-center w-6 h-6 text-slate-500 hover:text-slate-300 cursor-grab active:cursor-grabbing"
            >
              <GripVertical className="w-4 h-4" />
            </div>

            {/* Step number */}
            <span className="flex items-center justify-center w-5 h-5 text-[10px] font-semibold text-primary-400 bg-primary-500/10 rounded-full border border-primary-500/20">
              {index + 1}
            </span>

            {/* Action icon & label */}
            <Icon className="w-4 h-4 text-primary-400" />
            <span className="text-sm font-medium text-white">{getActionLabel(action.action_type)}</span>

            {/* Config summary */}
            <span className="text-xs text-slate-500 truncate flex-1">{getActionConfigSummary(action)}</span>

            {/* Approval toggle */}
            <button
              type="button"
              onClick={() => onChange({ ...action, requires_approval: !action.requires_approval })}
              title={action.requires_approval ? "Approval required" : "No approval needed"}
              className={`flex items-center gap-1 px-2 py-1 text-[10px] font-medium rounded-full border transition-colors ${
                action.requires_approval
                  ? "bg-warning/10 text-warning border-warning/20"
                  : "bg-slate-900/50 text-slate-500 border-slate-700 hover:border-slate-600"
              }`}
            >
              <Shield className="w-3 h-3" />
              {action.requires_approval ? "Approval" : "Auto"}
            </button>

            {/* Expand/collapse config */}
            <button
              type="button"
              onClick={() => setExpanded(!expanded)}
              className="flex items-center justify-center w-7 h-7 text-slate-500 hover:text-slate-300 rounded-md hover:bg-slate-700/50 transition-colors"
              title="Configure"
            >
              {expanded ? <ChevronDown className="w-4 h-4 rotate-180" /> : <Settings className="w-4 h-4" />}
            </button>

            {/* Remove button */}
            <button
              type="button"
              onClick={onRemove}
              className="flex items-center justify-center w-7 h-7 text-slate-500 hover:text-critical rounded-md hover:bg-critical/10 transition-colors"
              title="Remove action"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>

          {/* Expanded config */}
          {expanded && (
            <div className="px-3 pb-3 pt-1 border-t border-slate-700/50">
              <ActionConfigPanel action={action} onChange={onChange} />

              {/* Failure policy */}
              <div className="mt-3">
                <label className="block text-xs font-medium text-slate-400 mb-1.5">On Failure</label>
                <select
                  value={action.on_failure ?? "stop"}
                  onChange={(e) => onChange({ ...action, on_failure: e.target.value as WorkflowAction["on_failure"] })}
                  className="w-full px-3 py-2 text-sm text-white bg-slate-900/50 border border-slate-700 rounded-lg focus:outline-none focus:border-primary-500/50 focus:ring-1 focus:ring-primary-500/20 appearance-none"
                >
                  {FAILURE_POLICIES.map((fp) => (
                    <option key={fp.value} value={fp.value}>{fp.label}</option>
                  ))}
                </select>
              </div>
            </div>
          )}
        </div>
      )}
    </Draggable>
  );
}

interface ActionPickerProps {
  onSelect: (actionType: ActionType) => void;
  onClose: () => void;
}

function ActionPicker({ onSelect, onClose }: ActionPickerProps) {
  return (
    <div className="bg-slate-800/90 border border-slate-700 rounded-xl p-3 shadow-xl backdrop-blur-sm">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-slate-400">Add Action</span>
        <button
          type="button"
          onClick={onClose}
          className="text-slate-500 hover:text-slate-300 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
      <div className="grid grid-cols-2 gap-2">
        {ACTION_TYPES.map(({ value, label, icon: ActionIcon, description }) => (
          <button
            key={value}
            type="button"
            onClick={() => {
              onSelect(value);
              onClose();
            }}
            className="flex flex-col items-start gap-1 p-3 text-left bg-slate-900/50 border border-slate-700 rounded-lg hover:border-primary-500/30 hover:bg-primary-500/5 transition-colors"
          >
            <div className="flex items-center gap-2">
              <ActionIcon className="w-4 h-4 text-primary-400" />
              <span className="text-sm font-medium text-white">{label}</span>
            </div>
            <span className="text-[11px] text-slate-500">{description}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

interface TemplateCardProps {
  workflow: WorkflowResponse;
  onUse: () => void;
}

function TemplateCard({ workflow, onUse }: TemplateCardProps) {
  const triggerIcon = workflow.trigger.type === "time" ? Sun
    : workflow.trigger.type === "event" ? Calendar
    : Radar;
  const TriggerIcon = triggerIcon;

  return (
    <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-4 hover:border-slate-600 transition-colors">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <TriggerIcon className="w-4 h-4 text-primary-400 flex-shrink-0" />
            <h4 className="text-sm font-semibold text-white truncate" style={{ fontFamily: "var(--font-display)" }}>
              {workflow.name}
            </h4>
          </div>
          <p className="mt-1 text-xs text-slate-400 line-clamp-2">{workflow.description}</p>
          <div className="mt-2 flex items-center gap-2 flex-wrap">
            <span className="inline-flex items-center px-2 py-0.5 text-[10px] font-medium text-slate-400 bg-slate-900/50 rounded-full border border-slate-700">
              {workflow.actions.length} action{workflow.actions.length !== 1 ? "s" : ""}
            </span>
            <span className="inline-flex items-center px-2 py-0.5 text-[10px] font-medium text-primary-400 bg-primary-500/10 rounded-full border border-primary-500/20">
              {workflow.metadata.category}
            </span>
          </div>
        </div>
        <button
          type="button"
          onClick={onUse}
          className="flex-shrink-0 flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-primary-400 bg-primary-500/10 border border-primary-500/20 rounded-lg hover:bg-primary-500/20 transition-colors"
        >
          <Check className="w-3.5 h-3.5" />
          Use Template
        </button>
      </div>
    </div>
  );
}

// --- Main component ---

interface WorkflowBuilderProps {
  workflow?: WorkflowResponse;
  prebuiltWorkflows?: WorkflowResponse[];
  onSave: (data: CreateWorkflowData) => void;
  onCancel: () => void;
  saving?: boolean;
}

const DEFAULT_METADATA: WorkflowMetadata = {
  category: "productivity",
  icon: "zap",
  color: "primary",
};

export function WorkflowBuilder({
  workflow,
  prebuiltWorkflows,
  onSave,
  onCancel,
  saving = false,
}: WorkflowBuilderProps) {
  const isEdit = !!workflow;

  const [name, setName] = useState(workflow?.name ?? "");
  const [description, setDescription] = useState(workflow?.description ?? "");
  const [trigger, setTrigger] = useState<WorkflowTrigger>(
    workflow?.trigger ?? { type: "time" }
  );
  const [actions, setActions] = useState<WorkflowAction[]>(
    workflow?.actions ?? []
  );
  const [metadata, setMetadata] = useState<WorkflowMetadata>(
    workflow?.metadata ?? { ...DEFAULT_METADATA }
  );
  const [showActionPicker, setShowActionPicker] = useState(false);

  const handleDragEnd = useCallback(
    (result: DropResult) => {
      if (!result.destination) return;
      const src = result.source.index;
      const dst = result.destination.index;
      if (src === dst) return;

      const reordered = [...actions];
      const [moved] = reordered.splice(src, 1);
      reordered.splice(dst, 0, moved);
      setActions(reordered);
    },
    [actions]
  );

  const addAction = useCallback((actionType: ActionType) => {
    const newAction: WorkflowAction = {
      step_id: generateStepId(),
      action_type: actionType,
      config: {},
      requires_approval: false,
      on_failure: "stop",
    };
    setActions((prev) => [...prev, newAction]);
  }, []);

  const updateAction = useCallback((index: number, updated: WorkflowAction) => {
    setActions((prev) => {
      const next = [...prev];
      next[index] = updated;
      return next;
    });
  }, []);

  const removeAction = useCallback((index: number) => {
    setActions((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const loadTemplate = useCallback((templateWorkflow: WorkflowResponse) => {
    setName(templateWorkflow.name);
    setDescription(templateWorkflow.description);
    setTrigger(templateWorkflow.trigger);
    setActions(
      templateWorkflow.actions.map((a) => ({
        ...a,
        step_id: generateStepId(),
      }))
    );
    setMetadata(templateWorkflow.metadata);
  }, []);

  const handleSave = () => {
    const data: CreateWorkflowData = {
      name,
      description,
      trigger,
      actions,
      metadata,
    };
    onSave(data);
  };

  const isValid = name.trim().length > 0 && actions.length > 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-primary-500/10 border border-primary-500/20">
            <Zap className="w-5 h-5 text-primary-400" />
          </div>
          <h2
            className="text-lg font-semibold text-white"
            style={{ fontFamily: "var(--font-display)" }}
          >
            {isEdit ? "Edit Workflow" : "Create Workflow"}
          </h2>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-slate-400 bg-slate-800/50 border border-slate-700 rounded-lg hover:text-white hover:border-slate-600 transition-colors"
          >
            <X className="w-4 h-4" />
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={!isValid || saving}
            className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-white bg-primary-500/20 border border-primary-500/30 rounded-lg hover:bg-primary-500/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Check className="w-4 h-4" />
            {saving ? "Saving..." : "Save Workflow"}
          </button>
        </div>
      </div>

      {/* Name & Description */}
      <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-5 space-y-4">
        <div>
          <label className="block text-xs font-medium text-slate-400 mb-1.5">Workflow Name</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Morning Intelligence Brief"
            className="w-full px-3 py-2 text-sm text-white bg-slate-900/50 border border-slate-700 rounded-lg placeholder:text-slate-600 focus:outline-none focus:border-primary-500/50 focus:ring-1 focus:ring-primary-500/20"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-400 mb-1.5">Description</label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Describe what this workflow does..."
            rows={2}
            className="w-full px-3 py-2 text-sm text-white bg-slate-900/50 border border-slate-700 rounded-lg placeholder:text-slate-600 focus:outline-none focus:border-primary-500/50 focus:ring-1 focus:ring-primary-500/20 resize-none"
          />
        </div>
      </div>

      {/* Trigger */}
      <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-5">
        <div className="flex items-center gap-2 mb-4">
          <Clock className="w-4 h-4 text-primary-400" />
          <h3
            className="text-sm font-semibold text-white"
            style={{ fontFamily: "var(--font-display)" }}
          >
            Trigger
          </h3>
        </div>
        <TriggerConfig trigger={trigger} onChange={setTrigger} />
      </div>

      {/* Actions */}
      <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Settings className="w-4 h-4 text-primary-400" />
            <h3
              className="text-sm font-semibold text-white"
              style={{ fontFamily: "var(--font-display)" }}
            >
              Actions
            </h3>
            {actions.length > 0 && (
              <span className="inline-flex items-center px-1.5 py-0.5 text-[10px] font-medium text-slate-400 bg-slate-900/50 rounded-full border border-slate-700">
                {actions.length}
              </span>
            )}
          </div>
        </div>

        {/* Draggable actions list */}
        <DragDropContext onDragEnd={handleDragEnd}>
          <Droppable droppableId="workflow-actions">
            {(provided) => (
              <div
                ref={provided.innerRef}
                {...provided.droppableProps}
                className="space-y-2"
              >
                {actions.map((action, index) => (
                  <ActionItem
                    key={action.step_id}
                    action={action}
                    index={index}
                    onChange={(updated) => updateAction(index, updated)}
                    onRemove={() => removeAction(index)}
                  />
                ))}
                {provided.placeholder}
              </div>
            )}
          </Droppable>
        </DragDropContext>

        {/* Empty state */}
        {actions.length === 0 && !showActionPicker && (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <Settings className="w-8 h-8 text-slate-600 mb-2" />
            <p className="text-sm text-slate-500">No actions added yet</p>
            <p className="text-xs text-slate-600 mt-1">Add actions to define what this workflow does</p>
          </div>
        )}

        {/* Add action button / picker */}
        <div className="mt-3">
          {showActionPicker ? (
            <ActionPicker
              onSelect={addAction}
              onClose={() => setShowActionPicker(false)}
            />
          ) : (
            <button
              type="button"
              onClick={() => setShowActionPicker(true)}
              className="flex items-center gap-2 w-full px-4 py-2.5 text-sm font-medium text-slate-400 bg-slate-900/30 border border-dashed border-slate-700 rounded-lg hover:text-primary-400 hover:border-primary-500/30 hover:bg-primary-500/5 transition-colors"
            >
              <Plus className="w-4 h-4" />
              Add Action
            </button>
          )}
        </div>
      </div>

      {/* Pre-built Templates */}
      {prebuiltWorkflows && prebuiltWorkflows.length > 0 && (
        <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4">
            <Sun className="w-4 h-4 text-primary-400" />
            <h3
              className="text-sm font-semibold text-white"
              style={{ fontFamily: "var(--font-display)" }}
            >
              Start from Template
            </h3>
          </div>
          <div className="space-y-2">
            {prebuiltWorkflows.map((template) => (
              <TemplateCard
                key={template.id}
                workflow={template}
                onUse={() => loadTemplate(template)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
