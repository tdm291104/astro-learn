"use client";

import { Loader2 } from "lucide-react";
import type { ReactNode } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

type Variant = "danger" | "primary";

type Props = {
  open: boolean;
  title: string;
  description: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: Variant;
  pending?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

// Reusable confirm modal — replaces window.confirm across the app.
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  variant = "danger",
  pending = false,
  onConfirm,
  onCancel,
}: Props) {
  const confirmStyle =
    variant === "danger"
      ? {
          background: "var(--accent-coral)",
          borderColor: "var(--accent-coral)",
        }
      : undefined;

  return (
    <Dialog open={open} onOpenChange={(v) => !v && !pending && onCancel()}>
      <DialogContent className="sm:max-w-[440px]">
        <DialogHeader>
          <DialogTitle>
            <span
              className="font-orbitron uppercase"
              style={{ letterSpacing: "0.16em" }}
            >
              {title}
            </span>
          </DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>

        <DialogFooter>
          <button
            type="button"
            onClick={onCancel}
            disabled={pending}
            className="cosmic-btn-ghost"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={pending}
            className="cosmic-btn-primary inline-flex items-center gap-2"
            style={confirmStyle}
          >
            {pending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            {pending ? `${confirmLabel}…` : confirmLabel}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
