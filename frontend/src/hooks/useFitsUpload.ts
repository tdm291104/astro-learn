import { useMutation } from "@tanstack/react-query";
import { AxiosError } from "axios";
import { useState } from "react";
import { toast } from "sonner";

import { useT } from "@/hooks/useT";
import { astronomyService } from "@/services/astronomyService";
import { sessionService } from "@/services/sessionService";
import { useAstronomyStore } from "@/stores/astronomyStore";
import { useChatStore } from "@/stores/chatStore";
import type { FitsUploadResponse } from "@/types/astronomy.types";

type ErrorEnvelope = {
  error?: { code?: unknown; message?: unknown };
  detail?: unknown;
};

function readErrorEnvelope(err: unknown): { code: string; message: string } {
  if (err instanceof AxiosError) {
    const data = err.response?.data as ErrorEnvelope | undefined;
    const env = data?.error;
    if (env && typeof env === "object") {
      const code = typeof env.code === "string" ? env.code : "";
      const message = typeof env.message === "string" ? env.message : "";
      if (code || message) return { code, message };
    }
    const detail = data?.detail;
    if (typeof detail === "string") return { code: "", message: detail };
    if (Array.isArray(detail)) {
      const message = detail
        .map((d) =>
          typeof d === "object" && d && "msg" in d ? String(d.msg) : "",
        )
        .filter(Boolean)
        .join(", ");
      if (message) return { code: "", message };
    }
    if (err.message) return { code: "", message: err.message };
  }
  if (err instanceof Error) return { code: "", message: err.message };
  return { code: "", message: "" };
}

// Wraps upload with progress percent + MRU push.
export function useFitsUpload() {
  const [progress, setProgress] = useState(0);
  const addRecentFile = useAstronomyStore((s) => s.addRecentFile);
  const { t } = useT();

  const mutation = useMutation<FitsUploadResponse, unknown, { file: File }>({
    mutationFn: ({ file }) => astronomyService.uploadFits(file, setProgress),

    onSuccess: async (resp) => {
      addRecentFile(resp);
      setProgress(0);
      toast.success(
        t("astronomy.fits.upload.success", { filename: resp.filename }),
      );

      // Bind to current session only in fits mode; library-only otherwise.
      const { sessionId, mode, ensureSessionId, addAttachedFitsFileId } =
        useChatStore.getState();
      if (mode !== "fits") return;
      try {
        const targetId = sessionId ?? (await ensureSessionId());
        await sessionService.attachFile(targetId, resp.file_id);
        addAttachedFitsFileId(resp.file_id);
      } catch {
        // Soft-fail; library still has it, reconciles on next load.
      }
    },

    onError: (err) => {
      setProgress(0);
      const { code, message } = readErrorEnvelope(err);
      if (code === "not_astronomy_content_fits") {
        toast.error(t("astronomy.fits.upload.notAstronomy"));
        return;
      }
      toast.error(message || t("astronomy.fits.upload.failed"));
    },
  });

  return { ...mutation, progress };
}
