/** Workflows page - Manage, create, and execute automation workflows. */

import { useState } from "react";
import { DashboardLayout } from "@/components/DashboardLayout";
import { WorkflowBuilder } from "@/components/skills/WorkflowBuilder";
import {
  useWorkflows,
  usePrebuiltWorkflows,
  useCreateWorkflow,
  useUpdateWorkflow,
  useDeleteWorkflow,
  useExecuteWorkflow,
} from "@/hooks/useWorkflows";
import type {
  WorkflowResponse,
  CreateWorkflowData,
  TriggerType,
} from "@/api/workflows";
import {
  Zap,
  Plus,
  Sun,
  Calendar,
  Radar,
  Play,
  Trash2,
  Edit3,
  ToggleLeft,
  ToggleRight,
  CheckCircle2,
  XCircle,
  Loader2,
  Clock,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function triggerIcon(type: TriggerType) {
  switch (type) {
    case "time":
      return <Clock className="w-4 h-4" />;
    case "event":
      return <Zap className="w-4 h-4" />;
    case "condition":
      return <Radar className="w-4 h-4" />;
    default:
      return <Calendar className="w-4 h-4" />;
  }
}

function triggerBadgeColor(type: TriggerType): string {
  switch (type) {
    case "time":
      return "bg-blue-500/20 text-blue-400 border-blue-500/30";
    case "event":
      return "bg-amber-500/20 text-amber-400 border-amber-500/30";
    case "condition":
      return "bg-purple-500/20 text-purple-400 border-purple-500/30";
    default:
      return "bg-slate-500/20 text-slate-400 border-slate-500/30";
  }
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function relativeTime(dateStr: string | null | undefined): string {
  if (!dateStr) return "Never";
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return `${Math.floor(days / 30)}mo ago`;
}

// ---------------------------------------------------------------------------
// Delete confirmation dialog
// ---------------------------------------------------------------------------

function DeleteConfirmDialog({
  workflowName,
  onConfirm,
  onCancel,
  isPending,
}: {
  workflowName: string;
  onConfirm: () => void;
  onCancel: () => void;
  isPending: boolean;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={onCancel} />
      <div className="relative bg-slate-800 border border-slate-700 rounded-xl p-6 max-w-md w-full mx-4 shadow-2xl">
        <h3 className="text-lg font-semibold text-white mb-2">
          Delete Workflow
        </h3>
        <p className="text-slate-400 text-sm mb-6">
          Are you sure you want to delete{" "}
          <span className="text-white font-medium">{workflowName}</span>? This
          action cannot be undone.
        </p>
        <div className="flex justify-end gap-3">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm text-slate-300 hover:text-white transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={isPending}
            className="px-4 py-2 bg-red-600 text-white text-sm rounded-lg font-medium hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
          >
            {isPending && <Loader2 className="w-4 h-4 animate-spin" />}
            {isPending ? "Deleting..." : "Delete"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Workflow card
// ---------------------------------------------------------------------------

function WorkflowCard({
  workflow,
  onEdit,
  onRun,
  onDelete,
  onToggle,
  isExecuting,
}: {
  workflow: WorkflowResponse;
  onEdit: () => void;
  onRun: () => void;
  onDelete: () => void;
  onToggle: () => void;
  isExecuting: boolean;
}) {
  return (
    <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-5 flex flex-col gap-4 hover:border-slate-600 transition-colors">
      {/* Header row */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <h3 className="text-white font-medium truncate">{workflow.name}</h3>
          {workflow.description && (
            <p className="text-slate-400 text-sm mt-1 line-clamp-2">
              {workflow.description}
            </p>
          )}
        </div>
        <button
          onClick={onToggle}
          className="flex-shrink-0 text-slate-400 hover:text-white transition-colors"
          title={workflow.enabled ? "Disable workflow" : "Enable workflow"}
        >
          {workflow.enabled ? (
            <ToggleRight className="w-6 h-6 text-emerald-400" />
          ) : (
            <ToggleLeft className="w-6 h-6" />
          )}
        </button>
      </div>

      {/* Badges & stats */}
      <div className="flex items-center gap-2 flex-wrap">
        <span
          className={`inline-flex items-center gap-1.5 text-xs px-2 py-0.5 rounded border ${triggerBadgeColor(workflow.trigger.type)}`}
        >
          {triggerIcon(workflow.trigger.type)}
          {capitalize(workflow.trigger.type)}
        </span>
        <span className="text-xs text-slate-500">
          {workflow.actions.length} action
          {workflow.actions.length !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Run stats */}
      <div className="flex items-center gap-4 text-xs text-slate-400">
        <span className="flex items-center gap-1">
          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
          {workflow.success_count}
        </span>
        <span className="flex items-center gap-1">
          <XCircle className="w-3.5 h-3.5 text-red-400" />
          {workflow.failure_count}
        </span>
        <span className="flex items-center gap-1 ml-auto">
          <Clock className="w-3.5 h-3.5" />
          {relativeTime(workflow.metadata.last_run_at)}
        </span>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 pt-2 border-t border-slate-700/50">
        <button
          onClick={onEdit}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-slate-300 hover:text-white hover:bg-slate-700 rounded-lg transition-colors"
        >
          <Edit3 className="w-3.5 h-3.5" />
          Edit
        </button>
        <button
          onClick={onRun}
          disabled={isExecuting}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-interactive hover:text-white hover:bg-interactive/20 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isExecuting ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <Play className="w-3.5 h-3.5" />
          )}
          {isExecuting ? "Running..." : "Run"}
        </button>
        <button
          onClick={onDelete}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-slate-400 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors ml-auto"
        >
          <Trash2 className="w-3.5 h-3.5" />
          Delete
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Prebuilt template card
// ---------------------------------------------------------------------------

function TemplateCard({
  template,
  onUse,
  isPending,
}: {
  template: WorkflowResponse;
  onUse: () => void;
  isPending: boolean;
}) {
  return (
    <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-5 flex flex-col gap-3 hover:border-slate-600 transition-colors">
      <div className="flex items-start gap-3">
        <div className="p-2 rounded-lg bg-interactive/10 text-interactive">
          <Sun className="w-5 h-5" />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-white font-medium truncate">{template.name}</h3>
          {template.description && (
            <p className="text-slate-400 text-sm mt-1 line-clamp-2">
              {template.description}
            </p>
          )}
        </div>
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        <span
          className={`inline-flex items-center gap-1.5 text-xs px-2 py-0.5 rounded border ${triggerBadgeColor(template.trigger.type)}`}
        >
          {triggerIcon(template.trigger.type)}
          {capitalize(template.trigger.type)}
        </span>
        <span className="text-xs text-slate-500">
          {template.actions.length} action
          {template.actions.length !== 1 ? "s" : ""}
        </span>
      </div>

      <button
        onClick={onUse}
        disabled={isPending}
        className="mt-auto w-full px-4 py-2 bg-interactive text-white text-sm rounded-lg font-medium hover:bg-interactive-hover disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
      >
        {isPending ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <Plus className="w-4 h-4" />
        )}
        {isPending ? "Creating..." : "Use Template"}
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function WorkflowsPage() {
  // State
  const [builderMode, setBuilderMode] = useState<
    "hidden" | "create" | "edit"
  >("hidden");
  const [editingWorkflowId, setEditingWorkflowId] = useState<string | null>(
    null
  );
  const [deleteTarget, setDeleteTarget] = useState<WorkflowResponse | null>(
    null
  );
  const [executingId, setExecutingId] = useState<string | null>(null);

  // Data hooks
  const { data: workflows, isLoading: workflowsLoading } = useWorkflows();
  const { data: prebuiltWorkflows, isLoading: prebuiltLoading } =
    usePrebuiltWorkflows();
  const createWorkflow = useCreateWorkflow();
  const updateWorkflow = useUpdateWorkflow();
  const deleteWorkflowMutation = useDeleteWorkflow();
  const executeWorkflow = useExecuteWorkflow();

  // Handlers
  function handleCreateNew() {
    setEditingWorkflowId(null);
    setBuilderMode("create");
  }

  function handleEdit(workflow: WorkflowResponse) {
    setEditingWorkflowId(workflow.id);
    setBuilderMode("edit");
  }

  function handleCloseBuilder() {
    setBuilderMode("hidden");
    setEditingWorkflowId(null);
  }

  function handleRun(workflow: WorkflowResponse) {
    setExecutingId(workflow.id);
    executeWorkflow.mutate(
      { workflowId: workflow.id },
      {
        onSettled: () => setExecutingId(null),
      }
    );
  }

  function handleToggle(workflow: WorkflowResponse) {
    updateWorkflow.mutate({
      workflowId: workflow.id,
      data: { enabled: !workflow.enabled },
    });
  }

  function handleDeleteConfirm() {
    if (!deleteTarget) return;
    deleteWorkflowMutation.mutate(deleteTarget.id, {
      onSuccess: () => setDeleteTarget(null),
    });
  }

  function handleUseTemplate(template: WorkflowResponse) {
    const templateData: CreateWorkflowData = {
      name: template.name,
      description: template.description,
      trigger: template.trigger,
      actions: template.actions,
      metadata: template.metadata,
      enabled: false,
    };
    createWorkflow.mutate(templateData);
  }

  const hasWorkflows = workflows && workflows.length > 0;
  const hasTemplates = prebuiltWorkflows && prebuiltWorkflows.length > 0;

  return (
    <DashboardLayout>
      <div className="p-4 lg:p-8 min-h-screen bg-slate-900">
        <div className="max-w-7xl mx-auto space-y-8">
          {/* ---- Header ---- */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-display text-white">Workflows</h1>
              <p className="mt-1 text-slate-400">
                Automate repetitive tasks with custom workflows
              </p>
            </div>
            <button
              onClick={handleCreateNew}
              className="flex items-center gap-2 px-4 py-2 bg-interactive text-white text-sm rounded-lg font-medium hover:bg-interactive-hover transition-colors"
            >
              <Plus className="w-4 h-4" />
              Create Workflow
            </button>
          </div>

          {/* ---- WorkflowBuilder overlay/section ---- */}
          {builderMode !== "hidden" && (
            <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-display text-white">
                  {builderMode === "create"
                    ? "New Workflow"
                    : "Edit Workflow"}
                </h2>
                <button
                  onClick={handleCloseBuilder}
                  className="text-slate-400 hover:text-white transition-colors text-sm"
                >
                  Cancel
                </button>
              </div>
              <WorkflowBuilder
                workflowId={editingWorkflowId}
                onClose={handleCloseBuilder}
              />
            </div>
          )}

          {/* ---- Workflow List ---- */}
          {workflowsLoading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {[1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="bg-slate-800/50 border border-slate-700 rounded-xl p-5 space-y-4"
                >
                  <div className="h-5 bg-slate-700 rounded animate-pulse w-2/3" />
                  <div className="h-4 bg-slate-700 rounded animate-pulse w-full" />
                  <div className="h-4 bg-slate-700 rounded animate-pulse w-1/2" />
                  <div className="h-8 bg-slate-700 rounded animate-pulse w-full" />
                </div>
              ))}
            </div>
          ) : hasWorkflows ? (
            <>
              <div>
                <h2 className="text-lg font-display text-white mb-4">
                  Your Workflows
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {workflows.map((wf) => (
                    <WorkflowCard
                      key={wf.id}
                      workflow={wf}
                      onEdit={() => handleEdit(wf)}
                      onRun={() => handleRun(wf)}
                      onDelete={() => setDeleteTarget(wf)}
                      onToggle={() => handleToggle(wf)}
                      isExecuting={executingId === wf.id}
                    />
                  ))}
                </div>
              </div>

              {/* Templates section (below workflows) */}
              {hasTemplates && (
                <div>
                  <h2 className="text-lg font-display text-white mb-4">
                    Pre-built Templates
                  </h2>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {prebuiltWorkflows.map((t) => (
                      <TemplateCard
                        key={t.id}
                        template={t}
                        onUse={() => handleUseTemplate(t)}
                        isPending={createWorkflow.isPending}
                      />
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : (
            /* ---- Empty State ---- */
            <div className="space-y-8">
              <div className="text-center py-12 bg-slate-800/50 border border-slate-700 rounded-xl">
                <Zap className="w-12 h-12 text-slate-600 mx-auto mb-4" />
                <h2 className="text-xl font-semibold text-white mb-2">
                  No workflows yet
                </h2>
                <p className="text-slate-400 text-sm max-w-md mx-auto mb-6">
                  Workflows automate repetitive tasks like follow-up emails,
                  report generation, and lead monitoring. Get started with a
                  template or create your own.
                </p>
                <button
                  onClick={handleCreateNew}
                  className="inline-flex items-center gap-2 px-5 py-2.5 bg-interactive text-white text-sm rounded-lg font-medium hover:bg-interactive-hover transition-colors"
                >
                  <Plus className="w-4 h-4" />
                  Create Your First Workflow
                </button>
              </div>

              {/* Prominent templates in empty state */}
              {prebuiltLoading ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {[1, 2, 3].map((i) => (
                    <div
                      key={i}
                      className="bg-slate-800/50 border border-slate-700 rounded-xl p-5 space-y-3"
                    >
                      <div className="h-5 bg-slate-700 rounded animate-pulse w-2/3" />
                      <div className="h-4 bg-slate-700 rounded animate-pulse w-full" />
                      <div className="h-10 bg-slate-700 rounded animate-pulse w-full" />
                    </div>
                  ))}
                </div>
              ) : hasTemplates ? (
                <div>
                  <h2 className="text-lg font-display text-white mb-4">
                    Get Started with Templates
                  </h2>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {prebuiltWorkflows.map((t) => (
                      <TemplateCard
                        key={t.id}
                        template={t}
                        onUse={() => handleUseTemplate(t)}
                        isPending={createWorkflow.isPending}
                      />
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          )}
        </div>
      </div>

      {/* ---- Delete Confirmation Dialog ---- */}
      {deleteTarget && (
        <DeleteConfirmDialog
          workflowName={deleteTarget.name}
          onConfirm={handleDeleteConfirm}
          onCancel={() => setDeleteTarget(null)}
          isPending={deleteWorkflowMutation.isPending}
        />
      )}
    </DashboardLayout>
  );
}
