import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { notebookService } from "@/services/notebookService";

export function useDeleteDocument(notebookId: string) {
  const qc = useQueryClient();
  return useMutation<void, unknown, string>({
    mutationFn: (documentId) =>
      notebookService.deleteDocument(notebookId, documentId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notebook", notebookId, "documents"] });
      toast.success("Document deleted");
    },
    onError: (err) => {
      const msg = err instanceof Error ? err.message : "Delete failed";
      toast.error(msg);
    },
  });
}
