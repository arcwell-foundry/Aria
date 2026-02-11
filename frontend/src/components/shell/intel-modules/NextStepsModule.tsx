import { CheckCircle2, Circle, Clock } from 'lucide-react';

interface Step {
  label: string;
  status: 'done' | 'pending' | 'not_started';
  deadline?: string;
}

const PLACEHOLDER_STEPS: Step[] = [
  { label: 'Schedule technical review', status: 'done' },
  { label: 'Send updated proposal', status: 'pending', deadline: 'Feb 15' },
  { label: 'Introduce VP Engineering', status: 'not_started' },
  { label: 'Negotiate contract terms', status: 'not_started' },
];

const STATUS_ICONS: Record<string, typeof Circle> = {
  done: CheckCircle2,
  pending: Clock,
  not_started: Circle,
};

const STATUS_COLORS: Record<string, string> = {
  done: 'var(--success)',
  pending: 'var(--warning)',
  not_started: 'var(--text-secondary)',
};

export interface NextStepsModuleProps {
  steps?: Step[];
}

export function NextStepsModule({ steps = PLACEHOLDER_STEPS }: NextStepsModuleProps) {
  return (
    <div data-aria-id="intel-next-steps" className="space-y-2">
      <h3
        className="font-sans text-[11px] font-medium uppercase tracking-wider mb-3"
        style={{ color: 'var(--text-secondary)' }}
      >
        Next Steps
      </h3>
      <div className="space-y-1">
        {steps.map((step, i) => {
          const Icon = STATUS_ICONS[step.status] || Circle;
          return (
            <div key={i} className="flex items-center gap-2 py-1.5">
              <Icon
                size={14}
                className="flex-shrink-0"
                style={{ color: STATUS_COLORS[step.status] }}
              />
              <span
                className="font-sans text-[13px] flex-1"
                style={{
                  color: step.status === 'done' ? 'var(--text-secondary)' : 'var(--text-primary)',
                  textDecoration: step.status === 'done' ? 'line-through' : 'none',
                }}
              >
                {step.label}
              </span>
              {step.deadline && (
                <span className="font-mono text-[10px]" style={{ color: 'var(--text-secondary)' }}>
                  {step.deadline}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
