import { create } from "zustand";
import { persist } from "zustand/middleware";

import type {
  AnalysisType,
  FitsUploadResponse,
} from "@/types/astronomy.types";

const RECENT_FILES_CAP = 10;
const RECENT_ANALYSES_CAP = 20;

export type RecentAnalysis = {
  id: string;
  type: AnalysisType;
  fileId: string;
  createdAt: string; // ISO
};

export type AstronomyTab = "fits" | "catalog";

type AstronomyStore = {
  currentTab: AstronomyTab;

  recentFiles: FitsUploadResponse[];
  selectedFileId: string | null;
  selectedHduIndex: number;

  recentAnalyses: RecentAnalysis[];
  activeAnalysisId: string | null;

  setCurrentTab: (tab: AstronomyTab) => void;

  addRecentFile: (file: FitsUploadResponse) => void;
  // Drops stale entry and clears selectedFileId if it matched.
  removeRecentFile: (id: string) => void;
  // Reconciles MRU with server: prune, refresh, append, drop dead selection.
  reconcileRecentFiles: (serverFiles: FitsUploadResponse[]) => void;
  selectFile: (id: string | null) => void;
  setHduIndex: (index: number) => void;

  addRecentAnalysis: (entry: Omit<RecentAnalysis, "createdAt">) => void;
  removeRecentAnalysis: (id: string) => void;
  setActiveAnalysis: (id: string | null) => void;

  clearAll: () => void;
};

export const useAstronomyStore = create<AstronomyStore>()(
  persist(
    (set) => ({
      currentTab: "fits",

      recentFiles: [],
      selectedFileId: null,
      selectedHduIndex: 0,

      recentAnalyses: [],
      activeAnalysisId: null,

      setCurrentTab: (tab) => set({ currentTab: tab }),

      addRecentFile: (file) =>
        set((state) => {
          // Move-to-front; avoids duplicates on re-upload.
          const filtered = state.recentFiles.filter(
            (f) => f.file_id !== file.file_id,
          );
          const next = [file, ...filtered].slice(0, RECENT_FILES_CAP);
          return {
            recentFiles: next,
            selectedFileId: file.file_id,
            selectedHduIndex: 0,
          };
        }),

      removeRecentFile: (id) =>
        set((state) => ({
          recentFiles: state.recentFiles.filter((f) => f.file_id !== id),
          selectedFileId:
            state.selectedFileId === id ? null : state.selectedFileId,
          selectedHduIndex:
            state.selectedFileId === id ? 0 : state.selectedHduIndex,
        })),

      reconcileRecentFiles: (serverFiles) =>
        set((state) => {
          const serverById = new Map(
            serverFiles.map((f) => [f.file_id, f] as const),
          );
          // Keep local order but refresh metadata.
          const preserved = state.recentFiles
            .map((f) => serverById.get(f.file_id))
            .filter((f): f is FitsUploadResponse => f !== undefined);
          const preservedIds = new Set(preserved.map((f) => f.file_id));
          // Server-only entries go to the end to preserve local ordering.
          const additions = serverFiles.filter(
            (f) => !preservedIds.has(f.file_id),
          );
          const next = [...preserved, ...additions].slice(0, RECENT_FILES_CAP);
          const liveIds = new Set(next.map((f) => f.file_id));
          const selectedSurvives =
            state.selectedFileId !== null && liveIds.has(state.selectedFileId);
          return {
            recentFiles: next,
            selectedFileId: selectedSurvives ? state.selectedFileId : null,
            selectedHduIndex: selectedSurvives ? state.selectedHduIndex : 0,
          };
        }),

      selectFile: (id) =>
        set((state) =>
          state.selectedFileId === id
            ? { selectedFileId: id }
            : { selectedFileId: id, selectedHduIndex: 0 },
        ),

      setHduIndex: (index) => set({ selectedHduIndex: index }),

      addRecentAnalysis: (entry) =>
        set((state) => {
          const filtered = state.recentAnalyses.filter((a) => a.id !== entry.id);
          const next = [
            { ...entry, createdAt: new Date().toISOString() },
            ...filtered,
          ].slice(0, RECENT_ANALYSES_CAP);
          return { recentAnalyses: next, activeAnalysisId: entry.id };
        }),

      removeRecentAnalysis: (id) =>
        set((state) => ({
          recentAnalyses: state.recentAnalyses.filter((a) => a.id !== id),
          // Clear pointer to prevent results panel refiring 404 query.
          activeAnalysisId:
            state.activeAnalysisId === id ? null : state.activeAnalysisId,
        })),

      setActiveAnalysis: (id) => set({ activeAnalysisId: id }),

      clearAll: () =>
        set({
          // Preserve currentTab (UI preference).
          recentFiles: [],
          selectedFileId: null,
          selectedHduIndex: 0,
          recentAnalyses: [],
          activeAnalysisId: null,
        }),
    }),
    { name: "astrolearn-astronomy" },
  ),
);
