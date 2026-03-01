import { useEffect, useState } from 'react';
import { AgentAvatar } from '@/components/common/AgentAvatar';
import { useIntelGoals } from '@/hooks/useIntelPanelData';
import { useAgentStatusStore } from '@/stores/agentStatusStore';
import type { AgentLiveStatus } from '@/stores/agentStatusStore';

interface AgentStatus {
  name: string;
  status: 'active' | 'idle' | 'error' | 'completed' | 'retrying';
  task: string;
}

const STATUS_COLORS: Record<string, string> = {
  active: 'var(--success)',
  idle: 'var(--text-secondary)',
  error: 'var(--critical)',
  completed: 'var(--success)',
  retrying: '#F59E0B',
};

const STATUS_ANIMATIONS: Record<string, string> = {
  active: 'animate-pulse',
  retrying: 'animate-pulse',
  completed: '',
  error: '',
  idle: '',
};

const ALL_AGENTS = ['Hunter', 'Analyst', 'Strategist', 'Scribe', 'Operator', 'Scout'];

/** Threshold in ms for "just changed" flash */
const FLASH_DURATION = 5000;

function formatElapsed(startedAt: number | null, now: number): string {
  if (!startedAt) return '';
  const elapsed = Math.max(0, Math.floor((now - startedAt) / 1000));
  const mins = Math.floor(elapsed / 60);
  const secs = elapsed % 60;
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

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

function isFlashing(live: AgentLiveStatus, now: number): boolean {
  if (!live.changedAt) return false;
  return now - live.changedAt < FLASH_DURATION;
}

function getFlashStyle(live: AgentLiveStatus, now: number): React.CSSProperties | undefined {
  if (!isFlashing(live, now)) return undefined;
  if (live.status === 'completed') {
    return { boxShadow: '0 0 6px 1px rgba(34, 197, 94, 0.4)' };
  }
  if (live.status === 'error') {
    return { boxShadow: '0 0 6px 1px rgba(239, 68, 68, 0.4)' };
  }
  return undefined;
}

export interface AgentStatusModuleProps {
  agents?: AgentStatus[];
}

export function AgentStatusModule({ agents: propAgents }: AgentStatusModuleProps) {
  const { data: goals, isLoading } = useIntelGoals('active');
  const liveAgents = useAgentStatusStore((s) => s.agents);
  const [now, setNow] = useState(() => Date.now());

  // Tick every second to update flash animations
  useEffect(() => {
    const interval = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(interval);
  }, []);

  if (isLoading && !propAgents) return <AgentStatusSkeleton />;

  let agents: AgentStatus[];
  if (propAgents) {
    agents = propAgents;
  } else {
    // Build from API goals data
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

    // Merge: live WebSocket status takes precedence when agent is not idle
    agents = ALL_AGENTS.map((name) => {
      const key = name.toLowerCase();
      const live = liveAgents[key];

      // Live WS status takes precedence when agent is active/completed/error/retrying
      if (live && live.status !== 'idle') {
        return { name, status: live.status, task: live.task };
      }

      // Fall back to API-derived status
      const apiTask = activeAgentMap.get(name);
      if (apiTask) {
        return { name, status: 'active' as const, task: apiTask };
      }

      return { name, status: 'idle' as const, task: 'Standing by' };
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
        {agents.map((agent) => {
          const key = agent.name.toLowerCase();
          const live = liveAgents[key];
          const dotAnimation = STATUS_ANIMATIONS[agent.status] ?? '';
          const flashStyle = live ? getFlashStyle(live, now) : undefined;

          return (
            <div
              key={key}
              className="flex items-start gap-2.5 py-1.5 rounded px-2 -mx-2 transition-shadow duration-300"
              style={{
                backgroundColor: agent.status === 'active' || agent.status === 'retrying'
                  ? 'var(--bg-subtle)'
                  : 'transparent',
                ...flashStyle,
              }}
            >
              <div className="flex items-center gap-1.5 flex-shrink-0 mt-0.5 relative">
                <AgentAvatar agentKey={agent.name} size={18} />
                <div
                  className={`absolute -bottom-0.5 -right-0.5 w-2 h-2 rounded-full border border-[var(--bg-primary)] ${dotAnimation}`}
                  style={{ backgroundColor: STATUS_COLORS[agent.status] }}
                />
              </div>
              <div className="min-w-0 flex-1">
                <p className="font-mono text-[11px] font-medium" style={{ color: 'var(--text-primary)' }}>
                  {agent.name}
                </p>
                <p className="font-sans text-[11px] leading-[1.4]" style={{ color: 'var(--text-secondary)' }}>
                  {agent.task}
                </p>
              </div>
              {(agent.status === 'active' || agent.status === 'retrying') && live?.startedAt && (
                <span
                  className="font-mono text-[10px] tabular-nums shrink-0 mt-0.5"
                  style={{ color: STATUS_COLORS[agent.status] }}
                >
                  {formatElapsed(live.startedAt, now)}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
