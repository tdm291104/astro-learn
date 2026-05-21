import { useQuery } from "@tanstack/react-query";

import { notebookService } from "@/services/notebookService";
import type { DocumentContentResponse } from "@/types/notebook.types";

// Cached forever (Infinity) — files are immutable once uploaded.
export function useDocumentContent(
  notebookId: string | undefined,
  documentId: string | undefined,
  enabled: boolean,
) {
  return useQuery<DocumentContentResponse>({
    queryKey: ["notebook", notebookId, "document", documentId, "content"],
    queryFn: () =>
      notebookService.getDocumentContent(notebookId as string, documentId as string),
    enabled: enabled && Boolean(notebookId) && Boolean(documentId),
    staleTime: Infinity,
  });
}
