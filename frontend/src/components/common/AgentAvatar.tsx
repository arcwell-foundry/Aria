import { resolveAgent } from '@/constants/agents';

export interface AgentAvatarProps {
  /** Agent key — case-insensitive, works with both 'hunter' and 'Hunter' */
  agentKey: string;
  size?: number;
  className?: string;
}

export function AgentAvatar({ agentKey, size = 32, className = '' }: AgentAvatarProps) {
  const agent = resolveAgent(agentKey);

  if (agent.image) {
    return (
      <img
        src={agent.image}
        alt={agent.name}
        className={`rounded-full object-cover ${className}`}
        style={{ width: size, height: size }}
      />
    );
  }

  // Initials fallback for dynamic agents without headshots
  const initials = agent.name.slice(0, 2).toUpperCase();
  return (
    <div
      className={`rounded-full flex items-center justify-center font-mono text-white font-medium ${className}`}
      style={{
        width: size,
        height: size,
        backgroundColor: agent.color,
        fontSize: size * 0.4,
      }}
    >
      {initials}
    </div>
  );
}
