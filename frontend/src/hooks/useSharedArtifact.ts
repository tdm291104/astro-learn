import { useQuery } from "@tanstack/react-query";

import { notebookService } from "@/services/notebookService";
import type {
  NotebookArtifactKind,
  NotebookArtifactPayload,
} from "@/types/notebook.types";

// Artifacts are owner-generated and don't change without owner action.
export function useSharedArtifact(
  token: string,
  kind: NotebookArtifactKind,
  enabled = true,
) {
  return useQuery<NotebookArtifactPayload | null>({
    queryKey: ["shared-notebook", token, "artifact", kind],
    queryFn: () => notebookService.getSharedArtifact(token, kind),
    enabled: enabled && Boolean(token),
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
}
