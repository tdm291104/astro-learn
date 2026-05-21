import { create } from "zustand";
import { persist } from "zustand/middleware";

// Persisted so refresh keeps the Q&A session per notebook.
type SessionStore = {
  currentSessionIdByNotebook: Record<string, string>;
  setSession: (notebookId: string, sessionId: string) => void;
  clearSession: (notebookId: string) => void;
  getSession: (notebookId: string) => string | undefined;
};

export const useSessionStore = create<SessionStore>()(
  persist(
    (set, get) => ({
      currentSessionIdByNotebook: {},

      setSession: (notebookId, sessionId) =>
        set((state) => ({
          currentSessionIdByNotebook: {
            ...state.currentSessionIdByNotebook,
            [notebookId]: sessionId,
          },
        })),

      clearSession: (notebookId) =>
        set((state) => {
          const next = { ...state.currentSessionIdByNotebook };
          delete next[notebookId];
          return { currentSessionIdByNotebook: next };
        }),

      getSession: (notebookId) =>
        get().currentSessionIdByNotebook[notebookId],
    }),
    { name: "astrolearn-session" },
  ),
);
