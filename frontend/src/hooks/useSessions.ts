"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { sessionService } from "@/services/sessionService";
import type { Session } from "@/types/notebook.types";

// Centralized so invalidations stay consistent.
export const sessionKeys = {
  all: ["sessions"] as const,
  list: (notebookId?: string | null) =>
    [...sessionKeys.all, "list", notebookId ?? null] as const,
  detail: (id: string) => [...sessionKeys.all, "detail", id] as const,
};

// Recent conversations (updated_at desc) for ConversationListPanel.
export function useSessions(params?: {
  notebookId?: string | null;
  limit?: number;
}) {
  return useQuery<Session[]>({
    queryKey: sessionKeys.list(params?.notebookId),
    queryFn: () =>
      sessionService.list({
        notebookId: params?.notebookId ?? undefined,
        limit: params?.limit ?? 50,
      }),
    // staleTime 0 keeps sidebar reactive without manual invalidations.
    staleTime: 0,
  });
}

export function useDeleteSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: string) => sessionService.remove(sessionId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: sessionKeys.all });
    },
  });
}
