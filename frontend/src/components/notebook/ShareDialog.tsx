"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AxiosError } from "axios";
import {
  Check,
  Copy,
  EyeOff,
  Link2Off,
  Loader2,
  Share2,
  Trash2,
} from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { useT } from "@/hooks/useT";
import { notebookService } from "@/services/notebookService";
import type {
  NotebookShareResponse,
  ShareSettings,
} from "@/types/notebook.types";

const _COPIED_RESET_MS = 2000;

function extractError(err: unknown, fallback: string): string {
  if (err instanceof AxiosError) {
    const detail = (err.response?.data as { detail?: unknown } | undefined)
      ?.detail;
    if (typeof detail === "string") return detail;
    if (err.message) return err.message;
  }
  if (err instanceof Error) return err.message;
  return fallback;
}

export function ShareDialog({ notebookId }: { notebookId: string }) {
  const { t } = useT();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [revokeOpen, setRevokeOpen] = useState(false);

  // Idempotent — re-opening returns the same token.
  const link = useMutation<NotebookShareResponse, unknown, void>({
    mutationFn: () => notebookService.createShareLink(notebookId),
    onError: (err) =>
      toast.error(extractError(err, "Could not create share link")),
  });

  useEffect(() => {
    if (open && !link.data && !link.isPending) link.mutate();
  }, [open, link]);

  const settingsQuery = useQuery<ShareSettings>({
    queryKey: ["notebook", notebookId, "share-settings"],
    queryFn: () => notebookService.getShareSettings(notebookId),
    enabled: open,
    staleTime: 30_000,
  });

  const updateSettings = useMutation<
    ShareSettings,
    unknown,
    { show_filenames: boolean }
  >({
    mutationFn: (body) => notebookService.updateShareSettings(notebookId, body),
    onSuccess: (data) => {
      qc.setQueryData(["notebook", notebookId, "share-settings"], data);
    },
    onError: (err) =>
      toast.error(extractError(err, "Could not update visibility")),
  });

  const revoke = useMutation<void, unknown, void>({
    mutationFn: () => notebookService.revokeShareLink(notebookId),
    onSuccess: () => {
      toast.success(t("notebook.share_.revoked"));
      // Reset local state — link no longer valid.
      link.reset();
      qc.invalidateQueries({
        queryKey: ["notebook", notebookId, "share-settings"],
      });
      setRevokeOpen(false);
      setOpen(false);
    },
    onError: (err) =>
      toast.error(extractError(err, "Could not revoke link")),
  });

  const shareUrl = link.data
    ? `${typeof window !== "undefined" ? window.location.origin : ""}${link.data.share_path}`
    : "";

  const handleCopy = async () => {
    if (!shareUrl) return;
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      window.setTimeout(() => setCopied(false), _COPIED_RESET_MS);
    } catch {
      toast.error(t("notebook.share_.copyFailed"));
    }
  };

  const showFilenames = settingsQuery.data?.show_filenames ?? false;

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="cosmic-btn-outline inline-flex items-center gap-1.5"
        aria-label={t("notebook.share_.button")}
      >
        <Share2 className="h-3.5 w-3.5" />
        <span
          className="font-orbitron text-xs uppercase"
          style={{ letterSpacing: "0.14em" }}
        >
          {t("notebook.share")}
        </span>
      </button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle
              className="font-orbitron uppercase"
              style={{ letterSpacing: "0.16em" }}
            >
              {t("notebook.share_.title")}
            </DialogTitle>
            <DialogDescription className="font-exo2">
              {t("notebook.share_.description")}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 pt-2">
            {/* Link section */}
            {link.isPending && (
              <div
                className="flex items-center gap-2"
                role="status"
                aria-live="polite"
              >
                <Loader2
                  className="h-4 w-4 animate-spin"
                  style={{ color: "var(--accent-gold)" }}
                />
                <span
                  className="font-exo2 text-sm"
                  style={{ color: "var(--text-secondary)" }}
                >
                  {t("notebook.share_.generating")}
                </span>
              </div>
            )}

            {link.isError && (
              <button
                type="button"
                onClick={() => link.mutate()}
                className="cosmic-btn-outline w-full"
              >
                {t("common.tryAgain")}
              </button>
            )}

            {shareUrl && (
              <div className="flex items-stretch gap-2">
                <Input
                  readOnly
                  value={shareUrl}
                  onFocus={(e) => e.currentTarget.select()}
                  aria-label={t("notebook.share_.linkLabel")}
                  className="cosmic-input h-9 flex-1 truncate"
                />
                <button
                  type="button"
                  onClick={handleCopy}
                  className="cosmic-btn-primary inline-flex items-center gap-1.5 px-3"
                  aria-label={copied ? t("notebook.share_.copied") : t("notebook.share_.copy")}
                >
                  {copied ? (
                    <Check className="h-3.5 w-3.5" />
                  ) : (
                    <Copy className="h-3.5 w-3.5" />
                  )}
                  <span
                    className="font-orbitron text-xs uppercase"
                    style={{ letterSpacing: "0.14em" }}
                  >
                    {copied ? t("notebook.share_.copied") : t("common.copy")}
                  </span>
                </button>
              </div>
            )}

            {/* Visibility toggle */}
            <div
              className="rounded-lg border p-3"
              style={{ borderColor: "var(--border)" }}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="space-y-1">
                  <p
                    className="font-orbitron text-[11px] uppercase"
                    style={{
                      color: "var(--text-primary)",
                      letterSpacing: "0.14em",
                    }}
                  >
                    {t("notebook.share_.filenames")}
                  </p>
                  <p
                    className="font-exo2 text-xs"
                    style={{ color: "var(--text-secondary)" }}
                  >
                    {showFilenames
                      ? t("notebook.share_.filenamesShown")
                      : t("notebook.share_.filenamesHidden")}
                  </p>
                </div>
                <Switch
                  checked={showFilenames}
                  disabled={settingsQuery.isLoading || updateSettings.isPending}
                  onCheckedChange={(checked) =>
                    updateSettings.mutate({ show_filenames: Boolean(checked) })
                  }
                  aria-label="Toggle filename visibility"
                />
              </div>
              {!showFilenames && (
                <p
                  className="font-space-mono mt-2 inline-flex items-center gap-1.5 text-[10px] uppercase"
                  style={{
                    color: "var(--text-muted)",
                    letterSpacing: "0.14em",
                  }}
                >
                  <EyeOff className="h-3 w-3" />
                  {t("notebook.share_.filenamesNote")}
                </p>
              )}
            </div>
          </div>

          <DialogFooter className="sm:justify-between">
            {shareUrl ? (
              <button
                type="button"
                onClick={() => setRevokeOpen(true)}
                disabled={revoke.isPending}
                className="cosmic-btn-ghost inline-flex items-center gap-1.5"
                style={{ color: "var(--accent-coral)" }}
              >
                <Link2Off className="h-3.5 w-3.5" />
                {t("notebook.share_.revoke")}
              </button>
            ) : (
              <span />
            )}
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="cosmic-btn-ghost"
            >
              {t("common.done")}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={revokeOpen}
        pending={revoke.isPending}
        title={t("notebook.share_.revokeTitle")}
        confirmLabel={t("notebook.share_.revokeButton")}
        onConfirm={() => revoke.mutate()}
        onCancel={() => setRevokeOpen(false)}
        description={
          <span className="inline-flex items-start gap-2">
            <Trash2
              className="mt-0.5 h-3.5 w-3.5 shrink-0"
              style={{ color: "var(--accent-coral)" }}
            />
            <span>{t("notebook.share_.revokeWarning")}</span>
          </span>
        }
      />
    </>
  );
}
