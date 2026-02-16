import { AlertTriangle, Clock, UserX } from 'lucide-react';
import { useSignals, formatRelativeTime } from '@/hooks/useIntelPanelData';

interface Alert {
  severity: 'critical' | 'warning' | 'info';
  message: string;
  source: string;
  time: string;
}

const SEVERITY_COLORS: Record<string, string> = {
  critical: 'var(--critical)',
  warning: 'var(--warning)',
  info: 'var(--info)',
};

const SEVERITY_ICONS: Record<string, typeof AlertTriangle> = {
  critical: AlertTriangle,
  warning: Clock,
  info: UserX,
};

function mapSignalToSeverity(signalType: string): 'critical' | 'warning' | 'info' {
  const critical = ['deal_risk', 'champion_silent', 'deadline_approaching', 'competitor_threat'];
  const warning = ['price_change', 'engagement_drop', 'timeline_risk', 'budget_risk'];
  if (critical.includes(signalType)) return 'critical';
  if (warning.includes(signalType)) return 'warning';
  return 'info';
}

function AlertsSkeleton() {
  return (
    <div className="space-y-2">
      <div className="h-3 w-24 rounded bg-[var(--border)] animate-pulse" />
      <div className="h-16 rounded-lg bg-[var(--border)] animate-pulse" />
      <div className="h-16 rounded-lg bg-[var(--border)] animate-pulse" />
      <div className="h-16 rounded-lg bg-[var(--border)] animate-pulse" />
    </div>
  );
}

export interface AlertsModuleProps {
  alerts?: Alert[];
}

export function AlertsModule({ alerts: propAlerts }: AlertsModuleProps) {
  const { data: signals, isLoading } = useSignals({ limit: 5 });

  if (isLoading && !propAlerts) return <AlertsSkeleton />;

  const alerts: Alert[] = propAlerts ?? (signals ?? []).map((s) => ({
    severity: mapSignalToSeverity(s.signal_type),
    message: s.content,
    source: s.source ?? 'ARIA',
    time: formatRelativeTime(s.created_at),
  }));

  if (alerts.length === 0) {
    return (
      <div data-aria-id="intel-alerts" className="space-y-2">
        <h3
          className="font-sans text-[11px] font-medium uppercase tracking-wider mb-3"
          style={{ color: 'var(--text-secondary)' }}
        >
          Pipeline Alerts
        </h3>
        <div
          className="rounded-lg border p-4"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
        >
          <p className="font-sans text-[12px]" style={{ color: 'var(--text-secondary)' }}>
            No active alerts. ARIA is monitoring your pipeline.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div data-aria-id="intel-alerts" className="space-y-2">
      <h3
        className="font-sans text-[11px] font-medium uppercase tracking-wider mb-3"
        style={{ color: 'var(--text-secondary)' }}
      >
        Pipeline Alerts
      </h3>
      {alerts.map((alert, i) => {
        const Icon = SEVERITY_ICONS[alert.severity] || AlertTriangle;
        return (
          <div
            key={i}
            className="rounded-lg border p-3"
            style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
          >
            <div className="flex items-start gap-2">
              <Icon
                size={14}
                className="mt-0.5 flex-shrink-0"
                style={{ color: SEVERITY_COLORS[alert.severity] }}
              />
              <div className="min-w-0">
                <p className="font-sans text-[13px] leading-[1.5]" style={{ color: 'var(--text-primary)' }}>
                  {alert.message}
                </p>
                <p className="font-mono text-[10px] mt-1" style={{ color: 'var(--text-secondary)' }}>
                  {alert.source} · {alert.time}
                </p>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
