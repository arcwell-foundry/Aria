/**
 * ApprovalCard - Generic approval request visualization
 *
 * Renders for any action requiring user sign-off:
 * pending actions, recommendations, or configuration changes.
 * Shows title, context, impact assessment, urgency, and Approve/Reject buttons.
 */

import { useOnAction } from '@thesysai/genui-sdk';
import { Check, X, AlertTriangle, Clock } from 'lucide-react';
import type { ApprovalCardProps } from './schemas';

const urgencyConfig = {
  immediate: {
    color: 'text-critical',
    bgColor: 'bg-critical/10',
    label: 'Immediate',
    icon: AlertTriangle,
  },
  today: {
    color: 'text-warning',
    bgColor: 'bg-warning/10',
    label: 'Today',
    icon: Clock,
  },
  this_week: {
    color: 'text-info',
    bgColor: 'bg-info/10',
    label: 'This Week',
    icon: Clock,
  },
  no_rush: {
    color: 'text-secondary',
    bgColor: 'bg-subtle',
    label: 'No Rush',
    icon: null,
  },
};

export function ApprovalCard({
  item_id,
  item_type,
  title,
  description,
  impact,
  urgency = 'no_rush',
}: ApprovalCardProps) {
  const onAction = useOnAction();
  const config = urgencyConfig[urgency];

  const handleApprove = () => {
    onAction(
      "Approve",
      `User approved ${item_type} ${item_id}: ${title}`
    );
  };

  const handleReject = () => {
    onAction(
      "Reject",
      `User rejected ${item_type} ${item_id}: ${title}`
    );
  };

  return (
    <div className="bg-elevated border border-border rounded-xl overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-subtle/30">
        <div className="flex items-center gap-2">
          <span className="text-xs text-secondary uppercase tracking-wide">
            {item_type}
          </span>
        </div>
        {urgency !== 'no_rush' && (
          <span className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${config.bgColor} ${config.color}`}>
            {config.icon && <config.icon className="w-3 h-3" />}
            {config.label}
          </span>
        )}
      </div>

      {/* Content */}
      <div className="p-4 space-y-3">
        {/* Title */}
        <h4 className="text-content font-medium text-base">
          {title}
        </h4>

        {/* Description */}
        <p className="text-secondary text-sm leading-relaxed">
          {description}
        </p>

        {/* Impact */}
        {impact && (
          <div className="p-3 bg-subtle/50 rounded-lg border-l-2 border-interactive/50">
            <p className="text-xs text-secondary mb-1 font-medium">Impact</p>
            <p className="text-sm text-content">{impact}</p>
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 px-4 py-3 border-t border-border bg-subtle/30">
        <button
          onClick={handleApprove}
          className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium bg-interactive text-white rounded-lg hover:bg-interactive-hover transition-colors"
        >
          <Check className="w-4 h-4" />
          Approve
        </button>
        <button
          onClick={handleReject}
          className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-critical hover:bg-critical/10 rounded-lg transition-colors"
        >
          <X className="w-4 h-4" />
          Reject
        </button>
      </div>
    </div>
  );
}
