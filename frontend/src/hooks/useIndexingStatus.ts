import { useRef } from "react";
import { useQuery } from "@tanstack/react-query";

import { notebookService } from "@/services/notebookService";
import type { DocumentUploadResponse } from "@/types/notebook.types";

// Exponential backoff; reset on status change for prompt transitions.
const BASE_POLL_INTERVAL_MS = 1500;
const MAX_POLL_INTERVAL_MS = 15000;

const ACTIVE_STATUSES: ReadonlyArray<DocumentUploadResponse["status"]> = [
  "queued",
  "indexing",
];

function isActive(doc: DocumentUploadResponse): boolean {
  return ACTIVE_STATUSES.includes(doc.status);
}

// Stable id:status signature; any change resets backoff.
function statusSignature(docs: DocumentUploadResponse[]): string {
  return docs
    .map((d) => `${d.document_id}:${d.status}`)
    .sort()
    .join("|");
}

// Polls document list with backoff while any doc is queued/indexing.
export function useIndexingStatus(notebookId: string | undefined) {
  const currentIntervalRef = useRef<number>(BASE_POLL_INTERVAL_MS);
  const prevSignatureRef = useRef<string>("");

  const query = useQuery<DocumentUploadResponse[]>({
    queryKey: ["notebook", notebookId, "documents"],
    queryFn: () => notebookService.listDocuments(notebookId as string),
    enabled: Boolean(notebookId),
    refetchInterval: (q) => {
      const docs = q.state.data;
      // Idle — stop polling and reset cadence.
      if (!docs || docs.length === 0 || !docs.some(isActive)) {
        currentIntervalRef.current = BASE_POLL_INTERVAL_MS;
        prevSignatureRef.current = "";
        return false;
      }

      const signature = statusSignature(docs);
      if (signature !== prevSignatureRef.current) {
        currentIntervalRef.current = BASE_POLL_INTERVAL_MS;
        prevSignatureRef.current = signature;
      } else {
        currentIntervalRef.current = Math.min(
          currentIntervalRef.current * 2,
          MAX_POLL_INTERVAL_MS,
        );
      }
      return currentIntervalRef.current;
    },
  });

  const documents = query.data ?? [];
  const isPolling = documents.some(isActive);
  const hasIndexed = documents.some((d) => d.status === "indexed");

  return {
    documents,
    isPolling,
    hasIndexed,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
  };
}
