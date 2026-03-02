/**
 * SignalAlertCard - Market intelligence alert visualization
 *
 * Renders for market intelligence alerts, competitive moves,
 * regulatory changes, clinical trial updates, patent cliffs,
 * or any proactive signal ARIA wants to surface.
 */

import { useOnAction } from '@thesysai/genui-sdk';
import { AlertTriangle, AlertCircle, Info, Search, Building2, Clock } from 'lucide-react';
import type { SignalAlertCardProps } from './schemas';

const severityConfig = {
  high: {
    icon: AlertTriangle,
    color: 'text-critical',
    bgColor: 'bg-critical/10',
    borderColor: 'border-critical/30',
    badgeColor: 'bg-critical/20 text-critical',
  },
  medium: {
    icon: AlertCircle,
    color: 'text-warning',
    bgColor: 'bg-warning/10',
    borderColor: 'border-warning/30',
    badgeColor: 'bg-warning/20 text-warning',
  },
  low: {
    icon: Info,
    color: 'text-info',
    bgColor: 'bg-info/10',
    borderColor: 'border-info/30',
    badgeColor: 'bg-info/20 text-info',
  },
};

export function SignalAlertCard({
  signal_id,
  title,
  severity,
  signal_type,
  summary,
  source,
  affected_accounts = [],
  detected_at,
}: SignalAlertCardProps) {
  const onAction = useOnAction();
  const config = severityConfig[severity];
  const SeverityIcon = config.icon;

  const handleInvestigate = () => {
    onAction(
      "Investigate Signal",
      `User wants to investigate ${signal_type} signal ${signal_id}: ${title}`
    );
  };

  return (
    <div className={`bg-elevated border rounded-xl overflow-hidden ${config.borderColor}`}>
      {/* Header with Severity */}
      <div className={`flex items-center justify-between px-4 py-3 ${config.bgColor}`}>
        <div className="flex items-center gap-2">
          <SeverityIcon className={`w-4 h-4 ${config.color}`} />
          <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${config.badgeColor}`}>
            {severity.toUpperCase()}
          </span>
          <span className="text-xs text-secondary">{signal_type}</span>
        </div>
        {detected_at && (
          <span className="flex items-center gap-1 text-xs text-secondary">
            <Clock className="w-3 h-3" />
            {detected_at}
          </span>
        )}
      </div>

      {/* Content */}
      <div className="p-4 space-y-3">
        {/* Title */}
        <h4 className="text-content font-medium text-sm">
          {title}
        </h4>

        {/* Summary */}
        <p className="text-secondary text-sm leading-relaxed">
          {summary}
        </p>

        {/* Source */}
        {source && (
          <p className="text-xs text-secondary italic">
            Source: {source}
          </p>
        )}

        {/* Affected Accounts */}
        {affected_accounts.length > 0 && (
          <div className="pt-2 border-t border-border">
            <div className="flex items-center gap-1.5 mb-2">
              <Building2 className="w-3 h-3 text-secondary" />
              <span className="text-xs text-secondary font-medium">Affected Accounts</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {affected_accounts.map((account, index) => (
                <span
                  key={`${account}-${index}`}
                  className="px-2 py-0.5 rounded bg-subtle text-xs text-content"
                >
                  {account}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="px-4 py-3 border-t border-border bg-subtle/30">
        <button
          onClick={handleInvestigate}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium bg-interactive text-white rounded-lg hover:bg-interactive-hover transition-colors"
        >
          <Search className="w-3.5 h-3.5" />
          Investigate
        </button>
      </div>
    </div>
  );
}
