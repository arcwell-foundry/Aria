/**
 * GoalPlanCard - Execution plan visualization for ARIA goals
 *
 * Renders when ARIA proposes a multi-step plan for user review.
 * Shows numbered steps with agent assignments, progress indicators,
 * and Approve/Modify action buttons.
 */

import { useOnAction } from '@thesysai/genui-sdk';
import { CheckCircle2, Circle, Clock, Loader2, XCircle } from 'lucide-react';
import type { GoalPlanCardProps } from './schemas';

const statusIcons = {
  pending: Circle,
  in_progress: Loader2,
  complete: CheckCircle2,
  failed: XCircle,
};

const statusColors = {
  pending: 'text-secondary',
  in_progress: 'text-interactive',
  complete: 'text-success',
  failed: 'text-critical',
};

const oodaPhaseColors = {
  observe: 'bg-info/20 text-info',
  orient: 'bg-warning/20 text-warning',
  decide: 'bg-interactive/20 text-interactive',
  act: 'bg-success/20 text-success',
};

export function GoalPlanCard({
  goal_name,
  goal_id,
  description,
  steps = [],
  estimated_duration,
  ooda_phase,
}: GoalPlanCardProps) {
  const onAction = useOnAction();

  const handleApprove = () => {
    onAction("Approve Plan", `User approved goal ${goal_id}: ${goal_name}`);
  };

  const handleModify = () => {
    onAction("Modify Plan", `User requested modifications to goal ${goal_id}: ${goal_name}`);
  };

  return (
    <div className="bg-elevated border border-border rounded-xl p-4 space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <h3 className="text-content font-semibold text-base truncate">
            {goal_name}
          </h3>
          <p className="text-secondary text-sm mt-1 line-clamp-2">
            {description}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {ooda_phase && (
            <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${oodaPhaseColors[ooda_phase]}`}>
              {ooda_phase}
            </span>
          )}
          {estimated_duration && (
            <span className="flex items-center gap-1 text-xs text-secondary">
              <Clock className="w-3 h-3" />
              {estimated_duration}
            </span>
          )}
        </div>
      </div>

      {/* Steps */}
      {steps.length > 0 && (
        <div className="space-y-2">
          {steps.map((step) => {
            const StatusIcon = statusIcons[step.status || 'pending'];
            const statusColor = statusColors[step.status || 'pending'];

            return (
              <div
                key={step.step_number}
                className="flex items-start gap-3 p-2 rounded-lg bg-subtle/50"
              >
                <StatusIcon
                  className={`w-4 h-4 mt-0.5 shrink-0 ${statusColor} ${
                    step.status === 'in_progress' ? 'animate-spin' : ''
                  }`}
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-secondary font-medium">
                      Step {step.step_number}
                    </span>
                    {step.assigned_agent && (
                      <span className="px-1.5 py-0.5 rounded bg-interactive/10 text-interactive text-xs">
                        {step.assigned_agent}
                      </span>
                    )}
                  </div>
                  <p className="text-content text-sm mt-0.5">
                    {step.description}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-2 pt-2 border-t border-border">
        <button
          onClick={handleApprove}
          className="px-4 py-2 text-sm font-medium bg-interactive text-white rounded-lg hover:bg-interactive-hover transition-colors"
        >
          Approve
        </button>
        <button
          onClick={handleModify}
          className="px-4 py-2 text-sm font-medium bg-elevated text-content border border-border rounded-lg hover:bg-subtle transition-colors"
        >
          Modify
        </button>
      </div>
    </div>
  );
}
