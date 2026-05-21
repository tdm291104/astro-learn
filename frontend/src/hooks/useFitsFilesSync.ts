"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { astronomyService } from "@/services/astronomyService";
import { useAstronomyStore } from "@/stores/astronomyStore";

// Reconciles persisted MRU against server list to prune stale entries.
export function useFitsFilesSync() {
  const reconcile = useAstronomyStore((s) => s.reconcileRecentFiles);
  const lastSyncedRef = useRef<unknown>(null);

  const query = useQuery({
    queryKey: ["astronomy", "files"],
    queryFn: () => astronomyService.listFits(),
    staleTime: 30_000,
  });

  useEffect(() => {
    if (!query.data) return;
    // Skip duplicate reconcile on identical refetched ref.
    if (lastSyncedRef.current === query.data) return;
    lastSyncedRef.current = query.data;
    reconcile(query.data);
  }, [query.data, reconcile]);

  return query;
}
