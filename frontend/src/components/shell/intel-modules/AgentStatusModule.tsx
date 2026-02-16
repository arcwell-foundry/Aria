import { AgentAvatar } from '@/components/common/AgentAvatar';
import { useIntelGoals } from '@/hooks/useIntelPanelData';

interface AgentStatus {
  name: string;
  status: 'active' | 'idle' | 'error';
  task: string;
}

const STATUS_COLORS: Record<string, string> = {
  active: 'var(--success)',
  idle: 'var(--text-secondary)',
  error: 'var(--critical)',
};

const ALL_AGENTS = ['Hunter', 'Analyst', 'Strategist', 'Scribe', 'Operator', 'Scout'];

function AgentStatusSkeleton() {
  return (
    <div className="space-y-2">
      <div className="h-3 w-24 rounded bg-[var(--border)] animate-pulse" />
      <div className="space-y-1">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-10 rounded bg-[var(--border)] animate-pulse" />
        ))}
      </div>
    </div>
  );
}

export interface AgentStatusModuleProps {
  agents?: AgentStatus[];
}

export function AgentStatusModule({ agents: propAgents }: AgentStatusModuleProps) {
  const { data: goals, isLoading } = useIntelGoals('active');

  if (isLoading && !propAgents) return <AgentStatusSkeleton />;

  let agents: AgentStatus[];
  if (propAgents) {
    agents = propAgents;
  } else {
    const activeAgentMap = new Map<string, string>();

    if (goals) {
      for (const goal of goals) {
        if (goal.goal_agents) {
          for (const ga of goal.goal_agents) {
            const agentName = ga.agent_type.charAt(0).toUpperCase() + ga.agent_type.slice(1).toLowerCase();
            if (ga.status === 'running' || ga.status === 'pending') {
              activeAgentMap.set(agentName, goal.title);
            }
          }
        }
      }
    }

    agents = ALL_AGENTS.map((name) => {
      const task = activeAgentMap.get(name);
      if (task) {
        return { name, status: 'active' as const, task };
      }
      return { name, status: 'idle' as const, task: 'No active tasks' };
    });
  }

  return (
    <div data-aria-id="intel-agent-status" className="space-y-2">
      <h3
        className="font-sans text-[11px] font-medium uppercase tracking-wider mb-3"
        style={{ color: 'var(--text-secondary)' }}
      >
        Agent Status
      </h3>
      <div className="space-y-1">
        {agents.map((agent, i) => (
          <div
            key={i}
            className="flex items-start gap-2.5 py-1.5 rounded px-2 -mx-2"
            style={{
              backgroundColor: agent.status === 'active' ? 'var(--bg-subtle)' : 'transparent',
            }}
          >
            <div className="flex items-center gap-1.5 flex-shrink-0 mt-0.5 relative">
              <AgentAvatar agentKey={agent.name} size={18} />
              <div
                className="absolute -bottom-0.5 -right-0.5 w-2 h-2 rounded-full border border-[var(--bg-primary)]"
                style={{ backgroundColor: STATUS_COLORS[agent.status] }}
              />
            </div>
            <div className="min-w-0">
              <p className="font-mono text-[11px] font-medium" style={{ color: 'var(--text-primary)' }}>
                {agent.name}
              </p>
              <p className="font-sans text-[11px] leading-[1.4]" style={{ color: 'var(--text-secondary)' }}>
                {agent.task}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
