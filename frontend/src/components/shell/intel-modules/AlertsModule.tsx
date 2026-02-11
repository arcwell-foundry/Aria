import { AlertTriangle, Clock, UserX } from 'lucide-react';

interface Alert {
  severity: 'critical' | 'warning' | 'info';
  message: string;
  source: string;
  time: string;
}

const PLACEHOLDER_ALERTS: Alert[] = [
  {
    severity: 'critical',
    message: 'Lonza deal velocity dropped 40% — champion unresponsive',
    source: 'Analyst',
    time: '2h ago',
  },
  {
    severity: 'warning',
    message: 'Catalent RFP deadline in 3 days — proposal not started',
    source: 'Strategist',
    time: '4h ago',
  },
  {
    severity: 'info',
    message: 'BioConnect champion went silent (14 days)',
    source: 'Scout',
    time: '1d ago',
  },
];

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

export interface AlertsModuleProps {
  alerts?: Alert[];
}

export function AlertsModule({ alerts = PLACEHOLDER_ALERTS }: AlertsModuleProps) {
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
