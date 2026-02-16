import { CheckCircle2, Circle, Clock } from 'lucide-react';
import { useIntelGoalsDashboard } from '@/hooks/useIntelPanelData';

interface Step {
  label: string;
  status: 'done' | 'pending' | 'not_started';
  deadline?: string;
}

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

function mapMilestoneStatus(status: string): 'done' | 'pending' | 'not_started' {
  if (status === 'complete') return 'done';
  if (status === 'in_progress') return 'pending';
  return 'not_started';
}

function NextStepsSkeleton() {
  return (
    <div className="space-y-2">
      <div className="h-3 w-20 rounded bg-[var(--border)] animate-pulse" />
      <div className="space-y-1">
        <div className="h-8 rounded bg-[var(--border)] animate-pulse" />
        <div className="h-8 rounded bg-[var(--border)] animate-pulse" />
        <div className="h-8 rounded bg-[var(--border)] animate-pulse" />
      </div>
    </div>
  );
}

export interface NextStepsModuleProps {
  steps?: Step[];
}

export function NextStepsModule({ steps: propSteps }: NextStepsModuleProps) {
  const { data: dashboard, isLoading } = useIntelGoalsDashboard();

  if (isLoading && !propSteps) return <NextStepsSkeleton />;

  let steps: Step[];
  if (propSteps) {
    steps = propSteps;
  } else if (dashboard && dashboard.length > 0) {
    steps = dashboard
      .filter((g) => g.status === 'active' || g.status === 'draft')
      .flatMap((goal) => {
        if (goal.goal_milestones && goal.goal_milestones.length > 0) {
          return goal.goal_milestones.slice(0, 3).map((m) => ({
            label: m.title,
            status: mapMilestoneStatus(m.status),
            deadline: m.due_date ? new Date(m.due_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : undefined,
          }));
        }
        return [{
          label: goal.title,
          status: mapMilestoneStatus(goal.status === 'active' ? 'in_progress' : 'pending'),
          deadline: undefined,
        }];
      })
      .slice(0, 6);
  } else {
    steps = [];
  }

  if (steps.length === 0) {
    return (
      <div data-aria-id="intel-next-steps" className="space-y-2">
        <h3
          className="font-sans text-[11px] font-medium uppercase tracking-wider mb-3"
          style={{ color: 'var(--text-secondary)' }}
        >
          Next Steps
        </h3>
        <div
          className="rounded-lg border p-4"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
        >
          <p className="font-sans text-[12px]" style={{ color: 'var(--text-secondary)' }}>
            No active goals or milestones. Ask ARIA to help set a goal.
          </p>
        </div>
      </div>
    );
  }

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
