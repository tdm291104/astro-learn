import { create } from "zustand";
import { persist } from "zustand/middleware";

// Notebook studio panel tool keys; mirror backend extras (`suggest_panel`).
export type NotebookTool = "summary" | "quiz" | "flashcards";

// Sidebar etc.; theme is delegated to next-themes.
type UiStore = {
  sidebarOpen: boolean;
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  // When a chat redirect message asks for a panel: which tool, plus a
  // monotonically increasing token so consecutive opens of the SAME tool
  // still re-trigger any "open dialog" effects downstream.
  openNotebookTool: NotebookTool | null;
  openNotebookToolToken: number;
  requestNotebookTool: (tool: NotebookTool | null) => void;
};

export const useUiStore = create<UiStore>()(
  persist(
    (set) => ({
      sidebarOpen: true,
      toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
      setSidebarOpen: (open) => set({ sidebarOpen: open }),
      openNotebookTool: null,
      openNotebookToolToken: 0,
      requestNotebookTool: (tool) =>
        set((s) => ({
          openNotebookTool: tool,
          // Same-tool re-request bumps the token so subscribers can react.
          openNotebookToolToken: s.openNotebookToolToken + 1,
        })),
    }),
    {
      name: "astrolearn-ui",
      // Open-tool state is transient; don't persist across reloads.
      partialize: (s) => ({ sidebarOpen: s.sidebarOpen }),
    },
  ),
);
