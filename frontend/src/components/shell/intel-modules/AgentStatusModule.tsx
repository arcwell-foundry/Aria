import { Bot } from 'lucide-react';

interface AgentStatus {
  name: string;
  status: 'active' | 'idle' | 'error';
  task: string;
}

const PLACEHOLDER_AGENTS: AgentStatus[] = [
  { name: 'Hunter', status: 'active', task: 'Scanning 12 job boards for expansion signals' },
  { name: 'Analyst', status: 'active', task: 'Processing Lonza Q4 financials' },
  { name: 'Strategist', status: 'idle', task: 'Waiting for Analyst output' },
  { name: 'Scribe', status: 'active', task: 'Drafting Catalent follow-up email' },
  { name: 'Operator', status: 'idle', task: 'No pending tasks' },
  { name: 'Scout', status: 'active', task: 'Monitoring 23 LinkedIn profiles' },
];

const STATUS_COLORS: Record<string, string> = {
  active: 'var(--success)',
  idle: 'var(--text-secondary)',
  error: 'var(--critical)',
};

export interface AgentStatusModuleProps {
  agents?: AgentStatus[];
}

export function AgentStatusModule({ agents = PLACEHOLDER_AGENTS }: AgentStatusModuleProps) {
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
            <div className="flex items-center gap-1.5 flex-shrink-0 mt-0.5">
              <div
                className="w-1.5 h-1.5 rounded-full"
                style={{ backgroundColor: STATUS_COLORS[agent.status] }}
              />
              <Bot size={12} style={{ color: 'var(--text-secondary)' }} />
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
