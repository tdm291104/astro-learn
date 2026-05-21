import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AxiosError } from "axios";
import { useState } from "react";
import { toast } from "sonner";

import { useT } from "@/hooks/useT";
import { notebookService } from "@/services/notebookService";
import type { DocumentUploadResponse } from "@/types/notebook.types";

type ErrorEnvelope = {
  error?: { code?: unknown; message?: unknown };
  detail?: unknown;
};

// Reads either the AstroLearnError envelope (`error.code` + `error.message`)
// or FastAPI's default RequestValidationError shape (`detail`). Returns
// `{ code, message }`; code is "" when none was provided.
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

// Wraps upload with TanStack mutation + progress percent.
export function useDocumentUpload(notebookId: string) {
  const qc = useQueryClient();
  const [progress, setProgress] = useState(0);
  const { t } = useT();

  const mutation = useMutation<
    DocumentUploadResponse,
    unknown,
    { file: File }
  >({
    mutationFn: ({ file }) =>
      notebookService.uploadDocument(notebookId, file, setProgress),

    onSuccess: () => {
      // Hand off to the indexing-status poller.
      qc.invalidateQueries({
        queryKey: ["notebook", notebookId, "documents"],
      });
      setProgress(0);
      toast.success(t("notebook.upload.success"));
    },

    onError: (err) => {
      setProgress(0);
      const { code, message } = readErrorEnvelope(err);
      if (code === "not_astronomy_content") {
        toast.error(t("notebook.upload.notAstronomy"));
        return;
      }
      toast.error(message || t("notebook.upload.failed"));
    },
  });

  return { ...mutation, progress };
}
