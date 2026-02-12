/**
 * AGENT_REGISTRY — Single source of truth for all ARIA agent metadata.
 *
 * Every component that displays agent info (cards, badges, avatars, status)
 * should import from here instead of maintaining local constants.
 */

import hunterImg from '@/assets/agents/hunter.png';
import analystImg from '@/assets/agents/analyst.png';
import strategistImg from '@/assets/agents/strategist.png';
import scribeImg from '@/assets/agents/scribe.png';
import operatorImg from '@/assets/agents/operator.png';
import scoutImg from '@/assets/agents/scout.png';

export type AgentType = 'hunter' | 'analyst' | 'strategist' | 'scribe' | 'operator' | 'scout';

export interface AgentMeta {
  type: AgentType;
  name: string;
  image: string;
  color: string;
  description: string;
}

export const AGENT_REGISTRY: Record<AgentType, AgentMeta> = {
  hunter: {
    type: 'hunter',
    name: 'Hunter',
    image: hunterImg,
    color: '#2E66FF',
    description: 'Identifies and qualifies leads',
  },
  analyst: {
    type: 'analyst',
    name: 'Analyst',
    image: analystImg,
    color: '#8B5CF6',
    description: 'Processes and enriches data',
  },
  strategist: {
    type: 'strategist',
    name: 'Strategist',
    image: strategistImg,
    color: '#F59E0B',
    description: 'Plans and coordinates goals',
  },
  scribe: {
    type: 'scribe',
    name: 'Scribe',
    image: scribeImg,
    color: '#10B981',
    description: 'Drafts communications',
  },
  operator: {
    type: 'operator',
    name: 'Operator',
    image: operatorImg,
    color: '#EF4444',
    description: 'Executes approved actions',
  },
  scout: {
    type: 'scout',
    name: 'Scout',
    image: scoutImg,
    color: '#06B6D4',
    description: 'Monitors news, social, job boards',
  },
};

export const AGENT_TYPES = Object.keys(AGENT_REGISTRY) as AgentType[];

/** Look up agent by key (case-insensitive). Returns undefined for unknown agents. */
export function getAgent(key: string): AgentMeta | undefined {
  return AGENT_REGISTRY[key.toLowerCase() as AgentType];
}

/** Get agent color by name (case-insensitive). Falls back to gray. */
export function getAgentColor(key: string): string {
  return getAgent(key)?.color ?? '#6B7280';
}

// --- Dynamic agent support ---

const DYNAMIC_COLORS = [
  '#EC4899', // Pink
  '#F97316', // Orange
  '#14B8A6', // Teal
  '#A855F7', // Violet
  '#64748B', // Slate
];

const assignedDynamic = new Map<string, AgentMeta>();

/** Get or create meta for a dynamic (non-core) agent. Uses initials fallback. */
export function getDynamicAgent(name: string): AgentMeta {
  const key = name.toLowerCase();

  // Check core registry first
  const core = AGENT_REGISTRY[key as AgentType];
  if (core) return core;

  // Return cached dynamic agent
  const cached = assignedDynamic.get(key);
  if (cached) return cached;

  // Create new dynamic agent with rotating color
  const colorIndex = assignedDynamic.size % DYNAMIC_COLORS.length;
  const meta: AgentMeta = {
    type: key as AgentType,
    name,
    image: '',
    color: DYNAMIC_COLORS[colorIndex],
    description: 'Specialized agent',
  };
  assignedDynamic.set(key, meta);
  return meta;
}

/** Resolve any agent key (core or dynamic) to its meta. */
export function resolveAgent(key: string): AgentMeta {
  return getAgent(key) ?? getDynamicAgent(key);
}
