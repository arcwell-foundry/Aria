/**
 * AgentStatusCard - Multi-agent status dashboard
 *
 * Renders when reporting on multi-agent execution progress
 * or when user asks what ARIA is working on.
 * Shows agent cards with status indicators, progress bars, and OODA phase.
 */

import { useOnAction } from '@thesysai/genui-sdk';
import { Bot, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react';
import type { AgentStatusCardProps } from './schemas';

const statusConfig = {
  idle: {
    icon: Bot,
    color: 'text-secondary',
    bgColor: 'bg-subtle',
    dotColor: 'bg-secondary',
  },
  working: {
    icon: Loader2,
    color: 'text-interactive',
    bgColor: 'bg-interactive/5',
    dotColor: 'bg-interactive animate-pulse',
  },
  complete: {
    icon: CheckCircle2,
    color: 'text-success',
    bgColor: 'bg-success/5',
    dotColor: 'bg-success',
  },
  error: {
    icon: AlertCircle,
    color: 'text-critical',
    bgColor: 'bg-critical/5',
    dotColor: 'bg-critical',
  },
};

const oodaPhaseColors = {
  observe: 'border-info/30',
  orient: 'border-warning/30',
  decide: 'border-interactive/30',
  act: 'border-success/30',
};

export function AgentStatusCard({ agents = [] }: AgentStatusCardProps) {
  const onAction = useOnAction();

  const handleAgentClick = (agentName: string, task: string | undefined) => {
    onAction(
      `View ${agentName}`,
      `User clicked on agent ${agentName}${task ? ` working on: ${task}` : ''}`
    );
  };

  if (agents.length === 0) {
    return (
      <div className="bg-elevated border border-border rounded-xl p-4 text-center">
        <Bot className="w-8 h-8 text-secondary mx-auto mb-2" />
        <p className="text-sm text-secondary">No agents currently active</p>
      </div>
    );
  }

  return (
    <div className="bg-elevated border border-border rounded-xl p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center gap-2 pb-2 border-b border-border">
        <Bot className="w-4 h-4 text-interactive" />
        <span className="text-sm font-medium text-content">Agent Status</span>
        <span className="text-xs text-secondary ml-auto">
          {agents.filter(a => a.status === 'working').length} active
        </span>
      </div>

      {/* Agent Grid */}
      <div className="grid gap-2">
        {agents.map((agent, index) => {
          const config = statusConfig[agent.status];
          const StatusIcon = config.icon;
          const oodaBorder = agent.ooda_phase ? oodaPhaseColors[agent.ooda_phase] : '';

          return (
            <div
              key={`${agent.name}-${index}`}
              onClick={() => handleAgentClick(agent.name, agent.current_task)}
              className={`
                flex items-start gap-3 p-3 rounded-lg cursor-pointer
                transition-colors hover:bg-subtle/50
                border-l-2 ${oodaBorder}
                ${config.bgColor}
              `}
            >
              {/* Status Dot */}
              <div className={`w-2 h-2 rounded-full mt-1.5 shrink-0 ${config.dotColor}`} />

              {/* Agent Info */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-content">
                    {agent.name}
                  </span>
                  <StatusIcon
                    className={`w-3.5 h-3.5 ${config.color} ${
                      agent.status === 'working' ? 'animate-spin' : ''
                    }`}
                  />
                  {agent.ooda_phase && (
                    <span className="text-xs text-secondary uppercase">
                      {agent.ooda_phase}
                    </span>
                  )}
                </div>

                {agent.current_task && (
                  <p className="text-xs text-secondary mt-0.5 truncate">
                    {agent.current_task}
                  </p>
                )}

                {/* Progress Bar */}
                {agent.progress !== undefined && agent.progress > 0 && (
                  <div className="mt-2 h-1 bg-subtle rounded-full overflow-hidden">
                    <div
                      className={`h-full transition-all ${
                        agent.status === 'error' ? 'bg-critical' : 'bg-interactive'
                      }`}
                      style={{ width: `${Math.min(100, Math.max(0, agent.progress))}%` }}
                    />
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
