import { useMutation } from "@tanstack/react-query";
import { AxiosError } from "axios";
import { toast } from "sonner";

import { astronomyService } from "@/services/astronomyService";
import type { ReportRequest, ReportResponse } from "@/types/astronomy.types";

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

// POST report; download itself is an anchor in the UI.
export function useReportMutation() {
  return useMutation<ReportResponse, unknown, ReportRequest>({
    mutationFn: (body) => astronomyService.generateReport(body),

    onSuccess: () => {
      toast.success("Report generated");
    },

    onError: (err) => {
      toast.error(extractError(err, "Report generation failed"));
    },
  });
}
