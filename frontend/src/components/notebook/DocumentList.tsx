"use client";

import { motion } from "framer-motion";
import { Eye, FileText, Loader2, Trash2 } from "lucide-react";
import { useState } from "react";

import { staggerContainer, staggerItem } from "@/animations/stagger";
import { DocumentDeleteDialog } from "@/components/notebook/DocumentDeleteDialog";
import { DocumentViewerDialog } from "@/components/notebook/DocumentViewerDialog";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { useDeleteDocument } from "@/hooks/useDeleteDocument";
import { useIndexingStatus } from "@/hooks/useIndexingStatus";
import { useT } from "@/hooks/useT";
import { formatBytes } from "@/lib/utils";
import type {
  DocumentStatus,
  DocumentUploadResponse,
} from "@/types/notebook.types";

type StatusConfig = {
  labelKey: "notebook.queued" | "notebook.indexing" | "notebook.indexed" | "notebook.failed";
  color: string;
  pulse?: boolean;
};

const STATUS_CONFIG: Record<DocumentStatus, StatusConfig> = {
  queued: {
    labelKey: "notebook.queued",
    color: "var(--text-muted)",
    pulse: true,
  },
  indexing: {
    labelKey: "notebook.indexing",
    color: "var(--accent-blue)",
    pulse: true,
  },
  indexed: {
    labelKey: "notebook.indexed",
    color: "#4caf50",
  },
  failed: {
    labelKey: "notebook.failed",
    color: "var(--accent-coral)",
  },
};

export function DocumentList({ notebookId }: { notebookId: string }) {
  const { t } = useT();
  const { documents, isLoading, isError } = useIndexingStatus(notebookId);
  const [viewing, setViewing] = useState<DocumentUploadResponse | null>(null);
  const [pendingDelete, setPendingDelete] =
    useState<DocumentUploadResponse | null>(null);
  const deleteDoc = useDeleteDocument(notebookId);

  const confirmDelete = () => {
    if (!pendingDelete) return;
    deleteDoc.mutate(pendingDelete.document_id, {
      onSuccess: () => setPendingDelete(null),
    });
  };

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-16 w-full" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div
        className="font-exo2 rounded-2xl border-2 border-dashed p-6 text-center text-sm"
        style={{
          borderColor: "rgba(255,112,67,0.25)",
          color: "var(--accent-coral)",
        }}
      >
        {t("notebook.failedLoadDocuments")}
      </div>
    );
  }

  if (documents.length === 0) {
    return (
      <div
        className="font-exo2 rounded-2xl border-2 border-dashed p-8 text-center text-sm"
        style={{
          borderColor: "rgba(226,201,126,0.18)",
          color: "var(--text-secondary)",
        }}
      >
        {t("notebook.noDocuments")}
      </div>
    );
  }

  return (
    <>
      <motion.ul
        variants={staggerContainer}
        initial="initial"
        animate="animate"
        className="space-y-2"
      >
        {documents.map((doc) => (
          <motion.li key={doc.document_id} variants={staggerItem}>
            <DocumentRow
              doc={doc}
              onOpen={() => setViewing(doc)}
              onDelete={() => setPendingDelete(doc)}
              deleting={
                deleteDoc.isPending && deleteDoc.variables === doc.document_id
              }
            />
          </motion.li>
        ))}
      </motion.ul>

      <DocumentViewerDialog
        notebookId={notebookId}
        documentId={viewing?.document_id ?? null}
        filename={viewing?.filename ?? ""}
        sizeBytes={viewing?.size_bytes ?? 0}
        onClose={() => setViewing(null)}
      />

      <DocumentDeleteDialog
        filename={pendingDelete?.filename ?? null}
        open={pendingDelete !== null}
        pending={deleteDoc.isPending}
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </>
  );
}

function DocumentRow({
  doc,
  onOpen,
  onDelete,
  deleting,
}: {
  doc: DocumentUploadResponse;
  onOpen: () => void;
  onDelete: () => void;
  deleting: boolean;
}) {
  const { t } = useT();
  const cfg = STATUS_CONFIG[doc.status];
  // Failed docs have no extractable content.
  const canOpen = doc.status !== "failed";

  return (
    <div className="cosmic-card p-4">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={canOpen ? onOpen : undefined}
          disabled={!canOpen}
          className="flex min-w-0 flex-1 items-center gap-3 text-left transition-opacity disabled:cursor-not-allowed disabled:opacity-60"
          aria-label={`View ${doc.filename}`}
        >
          <FileText
            className="h-5 w-5 shrink-0"
            style={{ color: "var(--text-muted)" }}
          />
          <div className="min-w-0 flex-1">
            <p
              className="font-exo2 truncate text-sm font-medium"
              style={{ color: "var(--text-primary)" }}
            >
              {doc.filename}
            </p>
            <p
              className="font-space-mono mt-0.5 text-[11px] uppercase"
              style={{
                color: "var(--text-muted)",
                letterSpacing: "0.12em",
              }}
            >
              {formatBytes(doc.size_bytes)}
              {doc.indexed_chunks != null
                ? ` · ${doc.indexed_chunks} ${t("notebook.chunks")}`
                : ""}
            </p>
          </div>
          {canOpen && (
            <Eye
              className="h-3.5 w-3.5 shrink-0"
              style={{ color: "var(--text-muted)" }}
              aria-hidden
            />
          )}
        </button>
        <div className="flex shrink-0 items-center gap-2">
          <span
            className="cosmic-status-dot"
            style={{
              background: cfg.color,
              animation: cfg.pulse
                ? "cosmic-pulse 1.6s ease-in-out infinite"
                : undefined,
            }}
            aria-hidden
          />
          <span
            className="font-orbitron text-[10px] uppercase"
            style={{
              color: cfg.color,
              letterSpacing: "0.18em",
            }}
          >
            {t(cfg.labelKey)}
          </span>
          <button
            type="button"
            onClick={onDelete}
            disabled={deleting}
            className="cosmic-btn-ghost"
            style={{ padding: "0.3rem 0.45rem" }}
            aria-label={`Delete ${doc.filename}`}
            title="Delete document"
          >
            {deleting ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Trash2
                className="h-3.5 w-3.5"
                style={{ color: "var(--accent-coral)" }}
              />
            )}
          </button>
        </div>
      </div>

      {doc.status === "indexing" && (
        <Progress value={null} className="mt-3" />
      )}

      {doc.status === "failed" && (
        <p
          className="font-exo2 mt-2 text-xs"
          style={{ color: "var(--accent-coral)" }}
        >
          {t("notebook.indexingFailed")}
        </p>
      )}
    </div>
  );
}
