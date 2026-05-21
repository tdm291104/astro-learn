import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { AxiosError } from "axios";
import { toast } from "sonner";

import { notebookService } from "@/services/notebookService";
import type {
  Notebook,
  NotebookCreateRequest,
  NotebookUpdateRequest,
} from "@/types/notebook.types";

// Centralized so invalidation always matches read keys.
export const notebookKeys = {
  all: ["notebooks"] as const,
  detail: (id: string) => ["notebook", id] as const,
};

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

export function useNotebooksQuery(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: notebookKeys.all,
    queryFn: () => notebookService.list(),
    staleTime: 30_000,
    // Opt-in to avoid per-render /notebooks calls outside notebook mode.
    enabled: options?.enabled ?? true,
  });
}

export function useNotebookQuery(id: string | undefined) {
  return useQuery({
    queryKey: id ? notebookKeys.detail(id) : ["notebook", "missing"],
    queryFn: () => notebookService.get(id as string),
    enabled: Boolean(id),
    staleTime: 30_000,
  });
}

// Optimistic create; reconciles placeholder with server row.
export function useCreateNotebookMutation() {
  const qc = useQueryClient();

  return useMutation<
    Notebook,
    unknown,
    NotebookCreateRequest,
    { previous?: Notebook[]; tempId: string }
  >({
    mutationFn: (data) => notebookService.create(data),

    onMutate: async (data) => {
      await qc.cancelQueries({ queryKey: notebookKeys.all });
      const previous = qc.getQueryData<Notebook[]>(notebookKeys.all);

      const tempId = `optimistic-${crypto.randomUUID()}`;
      const now = new Date().toISOString();
      const optimistic: Notebook = {
        id: tempId,
        owner_id: "",
        title: data.title,
        description: data.description ?? null,
        created_at: now,
        updated_at: now,
      };
      qc.setQueryData<Notebook[]>(notebookKeys.all, (prev) =>
        prev ? [optimistic, ...prev] : [optimistic],
      );
      return { previous, tempId };
    },

    onError: (err, _data, ctx) => {
      if (ctx?.previous) qc.setQueryData(notebookKeys.all, ctx.previous);
      toast.error(extractError(err, "Failed to create notebook"));
    },

    onSuccess: (created, _data, ctx) => {
      qc.setQueryData<Notebook[]>(notebookKeys.all, (prev) =>
        prev?.map((n) => (n.id === ctx?.tempId ? created : n)) ?? [created],
      );
      qc.setQueryData(notebookKeys.detail(created.id), created);
      toast.success("Notebook created");
    },
  });
}

export function useUpdateNotebookMutation() {
  const qc = useQueryClient();

  return useMutation<
    Notebook,
    unknown,
    { id: string; data: NotebookUpdateRequest },
    { previousList?: Notebook[]; previousDetail?: Notebook }
  >({
    mutationFn: ({ id, data }) => notebookService.update(id, data),

    onMutate: async ({ id, data }) => {
      await qc.cancelQueries({ queryKey: notebookKeys.all });
      await qc.cancelQueries({ queryKey: notebookKeys.detail(id) });

      const previousList = qc.getQueryData<Notebook[]>(notebookKeys.all);
      const previousDetail = qc.getQueryData<Notebook>(notebookKeys.detail(id));
      const now = new Date().toISOString();

      const patch = (n: Notebook): Notebook => ({
        ...n,
        ...(data.title !== undefined && data.title !== null
          ? { title: data.title }
          : {}),
        ...(data.description !== undefined ? { description: data.description } : {}),
        updated_at: now,
      });

      qc.setQueryData<Notebook[]>(notebookKeys.all, (prev) =>
        prev?.map((n) => (n.id === id ? patch(n) : n)),
      );
      if (previousDetail) {
        qc.setQueryData<Notebook>(
          notebookKeys.detail(id),
          patch(previousDetail),
        );
      }
      return { previousList, previousDetail };
    },

    onError: (err, { id }, ctx) => {
      if (ctx?.previousList) qc.setQueryData(notebookKeys.all, ctx.previousList);
      if (ctx?.previousDetail)
        qc.setQueryData(notebookKeys.detail(id), ctx.previousDetail);
      toast.error(extractError(err, "Failed to update notebook"));
    },

    onSuccess: (updated) => {
      qc.setQueryData<Notebook[]>(notebookKeys.all, (prev) =>
        prev?.map((n) => (n.id === updated.id ? updated : n)),
      );
      qc.setQueryData(notebookKeys.detail(updated.id), updated);
      toast.success("Notebook updated");
    },
  });
}

export function useDeleteNotebookMutation() {
  const qc = useQueryClient();

  return useMutation<
    void,
    unknown,
    string,
    { previous?: Notebook[] }
  >({
    mutationFn: (id) => notebookService.remove(id),

    onMutate: async (id) => {
      await qc.cancelQueries({ queryKey: notebookKeys.all });
      const previous = qc.getQueryData<Notebook[]>(notebookKeys.all);
      qc.setQueryData<Notebook[]>(notebookKeys.all, (prev) =>
        prev?.filter((n) => n.id !== id),
      );
      return { previous };
    },

    onError: (err, _id, ctx) => {
      if (ctx?.previous) qc.setQueryData(notebookKeys.all, ctx.previous);
      toast.error(extractError(err, "Failed to delete notebook"));
    },

    onSuccess: (_void, id) => {
      qc.removeQueries({ queryKey: notebookKeys.detail(id) });
      toast.success("Notebook deleted");
    },
  });
}
