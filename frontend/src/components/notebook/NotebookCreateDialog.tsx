"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  useCreateNotebookMutation,
  useUpdateNotebookMutation,
} from "@/hooks/useNotebooks";
import { useT } from "@/hooks/useT";
import type { Notebook } from "@/types/notebook.types";

// Matches BE limits: title 1–255, description 0–2000.
const notebookFormSchema = z.object({
  title: z
    .string()
    .min(1, "Title is required")
    .max(255, "Title is too long"),
  description: z
    .string()
    .max(2000, "Description is too long")
    .optional()
    .or(z.literal("")),
});

type NotebookFormValues = z.infer<typeof notebookFormSchema>;

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  notebook?: Notebook | null;
};

export function NotebookCreateDialog({ open, onOpenChange, notebook }: Props) {
  const { t } = useT();
  const isEdit = Boolean(notebook);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<NotebookFormValues>({
    resolver: zodResolver(notebookFormSchema),
    defaultValues: { title: "", description: "" },
  });

  useEffect(() => {
    if (open) {
      reset({
        title: notebook?.title ?? "",
        description: notebook?.description ?? "",
      });
    }
  }, [open, notebook, reset]);

  const createMutation = useCreateNotebookMutation();
  const updateMutation = useUpdateNotebookMutation();
  const pending = createMutation.isPending || updateMutation.isPending;

  const onSubmit = async (data: NotebookFormValues) => {
    if (isEdit && notebook) {
      await updateMutation.mutateAsync({
        id: notebook.id,
        data: {
          title: data.title,
          description: data.description ?? null,
        },
      });
    } else {
      await createMutation.mutateAsync({
        title: data.title,
        description: data.description ?? null,
      });
    }
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>
            <span
              className="font-orbitron uppercase"
              style={{ letterSpacing: "0.16em" }}
            >
              {isEdit ? t("notebook.dialog.editTitle") : t("notebook.dialog.newTitle")}
            </span>
          </DialogTitle>
          <DialogDescription>
            {isEdit
              ? t("notebook.dialog.editDesc")
              : t("notebook.dialog.newDesc")}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor="title" className="cosmic-label">
              {t("notebook.dialog.title")}
            </Label>
            <Input
              id="title"
              autoFocus
              aria-invalid={Boolean(errors.title)}
              className="cosmic-input"
              {...register("title")}
            />
            {errors.title && (
              <p
                className="font-exo2 text-xs"
                style={{ color: "var(--accent-coral)" }}
              >
                {errors.title.message}
              </p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="description" className="cosmic-label">
              {t("notebook.dialog.description")}
            </Label>
            <Textarea
              id="description"
              rows={3}
              placeholder={t("common.optional")}
              aria-invalid={Boolean(errors.description)}
              className="cosmic-input"
              {...register("description")}
            />
            {errors.description && (
              <p
                className="font-exo2 text-xs"
                style={{ color: "var(--accent-coral)" }}
              >
                {errors.description.message}
              </p>
            )}
          </div>

          <DialogFooter>
            <button
              type="button"
              onClick={() => onOpenChange(false)}
              disabled={pending}
              className="cosmic-btn-ghost"
            >
              {t("common.cancel")}
            </button>
            <button
              type="submit"
              disabled={pending}
              className="cosmic-btn-primary"
            >
              {pending
                ? isEdit
                  ? t("common.saving")
                  : t("common.creating")
                : isEdit
                  ? t("notebook.dialog.saveChanges")
                  : t("notebook.dialog.create")}
            </button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
