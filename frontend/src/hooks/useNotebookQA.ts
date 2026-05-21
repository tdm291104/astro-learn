import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AxiosError } from "axios";
import { toast } from "sonner";

import { notebookService } from "@/services/notebookService";
import { useSessionStore } from "@/stores/sessionStore";
import type {
  FlashcardRequest,
  FlashcardResponse,
  NotebookArtifactKind,
  NotebookArtifactPayload,
  QARequest,
  QAResponse,
  QuizRequest,
  QuizResponse,
  SummarizeRequest,
  SummarizeResponse,
} from "@/types/notebook.types";

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

export const qaKeys = {
  messages: (sessionId: string) => ["session-messages", sessionId] as const,
  summary: (notebookId: string, params: SummarizeRequest) =>
    ["notebook", notebookId, "summary", params] as const,
  artifact: (notebookId: string, kind: NotebookArtifactKind) =>
    ["notebook", notebookId, "artifact", kind] as const,
};

// Loads cached artifact; null when not yet generated.
export function useNotebookArtifact<T = NotebookArtifactPayload>(
  notebookId: string,
  kind: NotebookArtifactKind,
  options?: { enabled?: boolean },
) {
  return useQuery<NotebookArtifactPayload | null, unknown, T | null>({
    queryKey: qaKeys.artifact(notebookId, kind),
    queryFn: () => notebookService.getArtifact(notebookId, kind),
    staleTime: Infinity,
    enabled: options?.enabled ?? true,
  });
}

export function useAskQuestionMutation(notebookId: string) {
  const qc = useQueryClient();
  const setSession = useSessionStore((s) => s.setSession);

  return useMutation<QAResponse, unknown, QARequest>({
    mutationFn: (body) => notebookService.askQuestion(notebookId, body),
    onSuccess: (resp) => {
      setSession(notebookId, resp.session_id);
      qc.invalidateQueries({ queryKey: qaKeys.messages(resp.session_id) });
    },
    onError: (err) => {
      toast.error(extractError(err, "Question failed"));
    },
  });
}

// Caches by notebookId+params; refreshes persisted artifact on success.
export function useSummarizeMutation(notebookId: string) {
  const qc = useQueryClient();

  return useMutation<SummarizeResponse, unknown, SummarizeRequest>({
    mutationFn: (body) => notebookService.summarize(notebookId, body),
    onSuccess: (resp, variables) => {
      qc.setQueryData(qaKeys.summary(notebookId, variables), resp);
      qc.invalidateQueries({
        queryKey: qaKeys.artifact(notebookId, "summary"),
      });
    },
    onError: (err) => {
      toast.error(extractError(err, "Summarize failed"));
    },
  });
}

export function useGenerateQuizMutation(notebookId: string) {
  const qc = useQueryClient();
  return useMutation<QuizResponse, unknown, QuizRequest>({
    mutationFn: (body) => notebookService.generateQuiz(notebookId, body),
    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: qaKeys.artifact(notebookId, "quiz"),
      });
    },
    onError: (err) => {
      toast.error(extractError(err, "Quiz generation failed"));
    },
  });
}

export function useGenerateFlashcardsMutation(notebookId: string) {
  const qc = useQueryClient();
  return useMutation<FlashcardResponse, unknown, FlashcardRequest>({
    mutationFn: (body) => notebookService.generateFlashcards(notebookId, body),
    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: qaKeys.artifact(notebookId, "flashcards"),
      });
    },
    onError: (err) => {
      toast.error(extractError(err, "Flashcard generation failed"));
    },
  });
}
