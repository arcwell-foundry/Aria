/**
 * Agent Status Store — Real-time per-agent status from WebSocket events.
 *
 * Tracks which agents are active, completed, errored, or retrying.
 * Components read `changedAt` to show a 5s flash animation on status change.
 */

import { create } from 'zustand';

export interface AgentLiveStatus {
  name: string;
  status: 'active' | 'idle' | 'completed' | 'error' | 'retrying';
  task: string;
  goalId: string | null;
  stepId: string | null;
  success: boolean | null;
  resultSummary: string | null;
  changedAt: number;
}

export interface AgentStatusState {
  agents: Record<string, AgentLiveStatus>;
  setAgentActive(agent: string, task: string, goalId: string, stepId: string): void;
  setAgentCompleted(agent: string, success: boolean, summary: string | null): void;
  setAgentRetrying(agent: string, reason: string): void;
  setAgentIdle(agent: string): void;
  resetAll(): void;
}

const INITIAL_AGENTS = ['hunter', 'analyst', 'strategist', 'scribe', 'operator', 'scout'];

function createInitialAgents(): Record<string, AgentLiveStatus> {
  const agents: Record<string, AgentLiveStatus> = {};
  for (const name of INITIAL_AGENTS) {
    agents[name] = {
      name,
      status: 'idle',
      task: 'No active tasks',
      goalId: null,
      stepId: null,
      success: null,
      resultSummary: null,
      changedAt: 0,
    };
  }
  return agents;
}

export const useAgentStatusStore = create<AgentStatusState>((set) => ({
  agents: createInitialAgents(),

  setAgentActive: (agent, task, goalId, stepId) =>
    set((state) => ({
      agents: {
        ...state.agents,
        [agent.toLowerCase()]: {
          name: agent.toLowerCase(),
          status: 'active',
          task,
          goalId,
          stepId,
          success: null,
          resultSummary: null,
          changedAt: Date.now(),
        },
      },
    })),

  setAgentCompleted: (agent, success, summary) =>
    set((state) => {
      const key = agent.toLowerCase();
      const existing = state.agents[key];
      return {
        agents: {
          ...state.agents,
          [key]: {
            ...(existing ?? { name: key, goalId: null, stepId: null }),
            status: success ? 'completed' : 'error',
            task: summary ?? (success ? 'Completed' : 'Failed'),
            success,
            resultSummary: summary,
            changedAt: Date.now(),
          },
        },
      };
    }),

  setAgentRetrying: (agent, reason) =>
    set((state) => {
      const key = agent.toLowerCase();
      const existing = state.agents[key];
      return {
        agents: {
          ...state.agents,
          [key]: {
            ...(existing ?? { name: key, goalId: null, stepId: null }),
            status: 'retrying',
            task: reason,
            success: null,
            resultSummary: null,
            changedAt: Date.now(),
          },
        },
      };
    }),

  setAgentIdle: (agent) =>
    set((state) => {
      const key = agent.toLowerCase();
      return {
        agents: {
          ...state.agents,
          [key]: {
            name: key,
            status: 'idle',
            task: 'No active tasks',
            goalId: null,
            stepId: null,
            success: null,
            resultSummary: null,
            changedAt: 0,
          },
        },
      };
    }),

  resetAll: () => set({ agents: createInitialAgents() }),
}));
