"use client";

import { Download, FileText } from "lucide-react";
import { useMemo } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useT } from "@/hooks/useT";
import { API_ENDPOINTS } from "@/lib/constants";
import { formatBytes } from "@/lib/utils";
import { useAuthStore } from "@/stores/authStore";

type Props = {
  notebookId: string;
  documentId: string | null;
  filename: string;
  sizeBytes: number;
  onClose: () => void;
};

export function DocumentViewerDialog({
  notebookId,
  documentId,
  filename,
  sizeBytes,
  onClose,
}: Props) {
  const { t } = useT();
  const open = documentId !== null;
  const token = useAuthStore((s) => s.token);

  // ?token= → proxy rewrites to Bearer header (iframes can't set headers).
  const fileUrl = useMemo(() => {
    if (!documentId || !token) return null;
    const path = API_ENDPOINTS.notebookDocumentFile(notebookId, documentId);
    return `/api/proxy${path}?token=${encodeURIComponent(token)}`;
  }, [notebookId, documentId, token]);

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent
        className="flex h-[95vh] w-[95vw] flex-col p-4 sm:!max-w-[min(95vw,calc(95vh*0.78))]"
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileText className="h-4 w-4" style={{ color: "var(--accent-gold)" }} />
            <span
              className="font-orbitron truncate uppercase"
              style={{ letterSpacing: "0.14em" }}
            >
              {filename}
            </span>
          </DialogTitle>
          <DialogDescription>
            <span className="flex items-center justify-between gap-3">
              <span
                className="font-space-mono text-[11px] uppercase"
                style={{ color: "var(--text-muted)", letterSpacing: "0.14em" }}
              >
                {formatBytes(sizeBytes)}
              </span>
              {fileUrl && (
                <a
                  href={fileUrl}
                  download={filename}
                  className="font-orbitron inline-flex items-center gap-1.5 text-[11px] uppercase"
                  style={{
                    color: "var(--accent-blue)",
                    letterSpacing: "0.16em",
                  }}
                >
                  <Download className="h-3 w-3" /> {t("common.download")}
                </a>
              )}
            </span>
          </DialogDescription>
        </DialogHeader>

        {fileUrl ? (
          <iframe
            key={fileUrl}
            src={fileUrl}
            title={filename}
            className="min-h-0 w-full flex-1 rounded-md border"
            style={{
              borderColor: "var(--border)",
              background: "var(--bg-0)",
            }}
          />
        ) : (
          <p
            className="font-exo2 py-6 text-center text-sm"
            style={{ color: "var(--text-muted)" }}
          >
            {t("document.viewerSignInRequired")}
          </p>
        )}
      </DialogContent>
    </Dialog>
  );
}
