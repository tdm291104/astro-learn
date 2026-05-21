import { create } from "zustand";
import { persist } from "zustand/middleware";

// UI-only; entities live in TanStack Query.
type NotebookStore = {
  currentNotebookId: string | null;
  setCurrentNotebook: (id: string | null) => void;
};

export const useNotebookStore = create<NotebookStore>()(
  persist(
    (set) => ({
      currentNotebookId: null,
      setCurrentNotebook: (id) => set({ currentNotebookId: id }),
    }),
    { name: "astrolearn-notebook" },
  ),
);
