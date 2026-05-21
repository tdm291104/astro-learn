import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AxiosError } from "axios";
import { toast } from "sonner";

import { astronomyService } from "@/services/astronomyService";
import { useAstronomyStore } from "@/stores/astronomyStore";

function extractError(err: unknown, fallback: string): string {
  if (err instanceof AxiosError) {
    const detail = (err.response?.data as { detail?: unknown } | undefined)
      ?.detail;
    if (typeof detail === "string") return detail;
    if (err.message) return err.message;
  }
  if (err instanceof Error) return err.message;
  return fallback;
}

// 404 with code "fits_not_found" → row already gone, treat as soft success.
function isAlreadyGone(err: unknown): boolean {
  if (!(err instanceof AxiosError)) return false;
  if (err.response?.status !== 404) return false;
  const body = err.response?.data;
  if (!body || typeof body !== "object") return false;
  const root = body as Record<string, unknown>;
  if (root.code === "fits_not_found") return true;
  const detail = root.detail;
  if (
    detail &&
    typeof detail === "object" &&
    (detail as Record<string, unknown>).code === "fits_not_found"
  ) {
    return true;
  }
  return false;
}

// Deletes FITS row + bytes; prunes local MRU and invalidates analyses cache.
export function useDeleteFitsFile() {
  const qc = useQueryClient();
  const removeRecentFile = useAstronomyStore((s) => s.removeRecentFile);

  return useMutation<void, unknown, { fileId: string; filename?: string }>({
    mutationFn: ({ fileId }) => astronomyService.deleteFits(fileId),
    onSuccess: (_data, { fileId, filename }) => {
      removeRecentFile(fileId);
      // Drop all cached AnalyzeResponse polls; cheaper than per-id walk.
      qc.invalidateQueries({ queryKey: ["astronomy", "analyses"] });
      toast.success(
        filename ? `Deleted ${filename}` : "FITS file deleted",
      );
    },
    onError: (err, { fileId, filename }) => {
      if (isAlreadyGone(err)) {
        // Stale local row; prune and show soft toast.
        removeRecentFile(fileId);
        qc.invalidateQueries({ queryKey: ["astronomy", "analyses"] });
        toast.success(
          filename
            ? `${filename} was already gone on the server — removed from your list`
            : "File was already gone on the server — removed from your list",
        );
        return;
      }
      toast.error(extractError(err, "Failed to delete FITS file"));
    },
  });
}
