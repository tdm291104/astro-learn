"use client";

import { Check, Loader2, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";

import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { useDeleteFitsFile } from "@/hooks/useDeleteFitsFile";
import { useT } from "@/hooks/useT";
import { cn, formatBytes } from "@/lib/utils";
import { useAstronomyStore } from "@/stores/astronomyStore";
import { useChatStore } from "@/stores/chatStore";

type PendingDelete = { fileId: string; filename: string };

// Selectable + deletable list of recently-uploaded FITS files.
export function FitsFileList() {
  const { t } = useT();
  const recentFiles = useAstronomyStore((s) => s.recentFiles);
  const selectedFileId = useAstronomyStore((s) => s.selectedFileId);
  const selectFile = useAstronomyStore((s) => s.selectFile);
  // Scope list strictly to files attached to the current conversation.
  const attachedIds = useChatStore((s) => s.attachedFitsFileIds);
  const deleteFile = useDeleteFitsFile();
  // Per-row pending state so deletes don't gray out the whole list.
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<PendingDelete | null>(null);

  const visibleFiles = useMemo(() => {
    const attachedSet = new Set(attachedIds);
    return recentFiles.filter((f) => attachedSet.has(f.file_id));
  }, [recentFiles, attachedIds]);

  if (visibleFiles.length === 0) return null;

  const confirmDelete = () => {
    if (!pendingDelete || pendingId) return;
    setPendingId(pendingDelete.fileId);
    deleteFile.mutate(pendingDelete, {
      onSettled: () => {
        setPendingId(null);
        setPendingDelete(null);
      },
    });
  };

  return (
    <div className="space-y-2">
      <p
        className="font-orbitron text-[10px] uppercase"
        style={{ color: "var(--text-muted)", letterSpacing: "0.18em" }}
      >
        {t("astronomy.fits.yourFiles")} ({visibleFiles.length})
      </p>
      <ul className="space-y-1.5">
        {visibleFiles.map((f) => {
          const isSelected = f.file_id === selectedFileId;
          const isDeleting = pendingId === f.file_id;
          return (
            <li
              key={f.file_id}
              className={cn(
                "flex items-center gap-2 rounded-lg px-2.5 py-2",
                isDeleting && "opacity-50",
              )}
              style={{
                background: isSelected
                  ? "var(--accent-gold-dim)"
                  : "rgba(255,255,255,0.02)",
                border: isSelected
                  ? "1px solid rgba(226,201,126,0.35)"
                  : "1px solid var(--border)",
              }}
            >
              <button
                type="button"
                onClick={() => selectFile(f.file_id)}
                disabled={isDeleting}
                className="flex min-w-0 flex-1 items-center gap-2 text-left"
                aria-pressed={isSelected}
                aria-label={`Select ${f.filename}`}
              >
                <span
                  className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full"
                  style={{
                    background: isSelected
                      ? "var(--accent-gold)"
                      : "rgba(255,255,255,0.04)",
                    color: isSelected ? "var(--bg-0)" : "var(--text-muted)",
                  }}
                  aria-hidden
                >
                  {isSelected ? <Check className="h-3 w-3" /> : null}
                </span>
                <div className="min-w-0">
                  <p
                    className="font-exo2 truncate text-xs font-medium"
                    style={{ color: "var(--text-primary)" }}
                  >
                    {f.filename}
                  </p>
                  <p
                    className="font-space-mono mt-0.5 truncate text-[10px] uppercase"
                    style={{
                      color: "var(--text-muted)",
                      letterSpacing: "0.14em",
                    }}
                  >
                    {t(
                      f.hdu_count === 1
                        ? "astronomy.fits.hduCount"
                        : "astronomy.fits.hduCountPlural",
                      { n: f.hdu_count },
                    )}{" "}
                    · {formatBytes(f.size_bytes)}
                  </p>
                </div>
              </button>
              <button
                type="button"
                onClick={() =>
                  setPendingDelete({ fileId: f.file_id, filename: f.filename })
                }
                disabled={isDeleting}
                className="shrink-0 rounded-md p-1.5 transition-colors hover:bg-[rgba(255,112,67,0.12)]"
                title={`Delete ${f.filename}`}
                aria-label={`Delete ${f.filename}`}
              >
                {isDeleting ? (
                  <Loader2
                    className="h-3.5 w-3.5 animate-spin"
                    style={{ color: "var(--text-muted)" }}
                  />
                ) : (
                  <Trash2
                    className="h-3.5 w-3.5"
                    style={{ color: "var(--accent-coral)" }}
                  />
                )}
              </button>
            </li>
          );
        })}
      </ul>

      <ConfirmDialog
        open={pendingDelete !== null}
        pending={pendingId !== null}
        title={t("astronomy.fits.deleteConfirmTitle")}
        confirmLabel={t("astronomy.fits.deleteConfirmConfirm")}
        cancelLabel={t("common.cancel")}
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
        description={t("astronomy.fits.deleteConfirmBody", {
          filename: pendingDelete?.filename ?? "",
        })}
      />
    </div>
  );
}
