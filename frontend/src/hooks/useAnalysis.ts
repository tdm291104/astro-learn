import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AxiosError } from "axios";
import { toast } from "sonner";

import { astronomyService } from "@/services/astronomyService";
import { useAstronomyStore } from "@/stores/astronomyStore";
import type {
  AnalysisStatus,
  AnalyzeRequest,
  AnalyzeResponse,
} from "@/types/astronomy.types";

// Exponential backoff; reset on status change so terminal state surfaces fast.
const BASE_POLL_INTERVAL_MS = 2000;
const MAX_POLL_INTERVAL_MS = 15000;
const ACTIVE_STATUSES: ReadonlyArray<AnalysisStatus> = ["pending", "running"];

export const analysisKeys = {
  detail: (id: string) => ["astronomy", "analysis", id] as const,
};

function extractError(err: unknown, fallback: string): string {
  if (err instanceof AxiosError) {
    const detail = (err.response?.data as { detail?: unknown } | undefined)
      ?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d) =>
          typeof d === "object" && d && "msg" in d ? String(d.msg) : "",
        )
        .filter(Boolean)
        .join(", ");
    }
    if (err.message) return err.message;
  }
  if (err instanceof Error) return err.message;
  return fallback;
}

// Seeds detail cache so the polling hook avoids an extra GET.
export function useAnalyzeMutation() {
  const qc = useQueryClient();
  const addRecentAnalysis = useAstronomyStore((s) => s.addRecentAnalysis);

  return useMutation<AnalyzeResponse, unknown, AnalyzeRequest>({
    mutationFn: (body) => astronomyService.analyze(body),

    onSuccess: (resp) => {
      qc.setQueryData(analysisKeys.detail(resp.analysis_id), resp);
      addRecentAnalysis({
        id: resp.analysis_id,
        type: resp.analysis_type,
        fileId: resp.file_id,
      });
    },

    onError: (err) => {
      toast.error(extractError(err, "Analysis request failed"));
    },
  });
}

// Polls analysis detail with exponential backoff while pending/running.
export function useAnalysisStatus(analysisId: string | null | undefined) {
  const currentIntervalRef = useRef<number>(BASE_POLL_INTERVAL_MS);
  const prevStatusRef = useRef<AnalysisStatus | "">("");
  const removeRecentAnalysis = useAstronomyStore(
    (s) => s.removeRecentAnalysis,
  );

  const query = useQuery<AnalyzeResponse>({
    queryKey: analysisId
      ? analysisKeys.detail(analysisId)
      : ["astronomy", "analysis", "_"],
    queryFn: () => astronomyService.getAnalysis(analysisId as string),
    enabled: Boolean(analysisId),
    // Treat 404 as terminal so the prune effect can run without retries.
    retry: (failureCount, err) => {
      if (err instanceof AxiosError && err.response?.status === 404) {
        return false;
      }
      return failureCount < 3;
    },
    refetchInterval: (q) => {
      const data = q.state.data;
      if (!data) {
        currentIntervalRef.current = BASE_POLL_INTERVAL_MS;
        prevStatusRef.current = "";
        return BASE_POLL_INTERVAL_MS;
      }
      if (!ACTIVE_STATUSES.includes(data.status)) {
        currentIntervalRef.current = BASE_POLL_INTERVAL_MS;
        prevStatusRef.current = "";
        return false;
      }
      if (data.status !== prevStatusRef.current) {
        // Status flipped; reset to fast cadence.
        currentIntervalRef.current = BASE_POLL_INTERVAL_MS;
        prevStatusRef.current = data.status;
      } else {
        currentIntervalRef.current = Math.min(
          currentIntervalRef.current * 2,
          MAX_POLL_INTERVAL_MS,
        );
      }
      return currentIntervalRef.current;
    },
  });

  // On 404, evict the stale row so Recent stops re-firing requests.
  useEffect(() => {
    if (!analysisId) return;
    if (
      query.isError &&
      query.error instanceof AxiosError &&
      query.error.response?.status === 404
    ) {
      removeRecentAnalysis(analysisId);
    }
  }, [analysisId, query.isError, query.error, removeRecentAnalysis]);

  return query;
}
