import { create } from "zustand";

import type { AgentStatus } from "@/types/agent.types";

// Ephemeral by design; persistence would surface stale "running" badges.
type ActiveRun = {
  agent_name: string;
  status: AgentStatus;
};

type AgentStore = {
  activeRuns: Record<string, ActiveRun>;
  setRun: (id: string, data: ActiveRun) => void;
  updateStatus: (id: string, status: AgentStatus) => void;
  removeRun: (id: string) => void;
};

export const useAgentStore = create<AgentStore>((set) => ({
  activeRuns: {},

  setRun: (id, data) =>
    set((state) => ({
      activeRuns: { ...state.activeRuns, [id]: data },
    })),

  updateStatus: (id, status) =>
    set((state) => {
      const existing = state.activeRuns[id];
      if (!existing) return {};
      return {
        activeRuns: {
          ...state.activeRuns,
          [id]: { ...existing, status },
        },
      };
    }),

  removeRun: (id) =>
    set((state) => {
      const next = { ...state.activeRuns };
      delete next[id];
      return { activeRuns: next };
    }),
}));
