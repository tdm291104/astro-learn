"use client";

import { motion } from "framer-motion";
import { Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { fadeIn, fadeTransition } from "@/animations/fade";
import { slideUp } from "@/animations/slide";
import { Progress } from "@/components/ui/progress";
import { useFitsUpload } from "@/hooks/useFitsUpload";
import { useT } from "@/hooks/useT";
import { MAX_FILE_SIZE } from "@/lib/constants";
import { cn, formatBytes } from "@/lib/utils";
import type { FitsUploadResponse } from "@/types/astronomy.types";

const ACCEPTED_EXTENSIONS = [".fits", ".fit", ".fts"] as const;
const ACCEPTED_INPUT_ATTR = ACCEPTED_EXTENSIONS.join(",");
const SUCCESS_DISPLAY_MS = 3500;

type Translator = ReturnType<typeof useT>["t"];

function validateFile(file: File, t: Translator): string | null {
  if (file.size > MAX_FILE_SIZE.fits) {
    return t("astronomy.fits.upload.tooLarge", {
      max: formatBytes(MAX_FILE_SIZE.fits),
      actual: formatBytes(file.size),
    });
  }
  const lower = file.name.toLowerCase();
  const matchesExt = ACCEPTED_EXTENSIONS.some((ext) => lower.endsWith(ext));
  if (!matchesExt) {
    return t("astronomy.fits.upload.unsupported", {
      types: ACCEPTED_EXTENSIONS.join(", "),
    });
  }
  return null;
}

export function FitsUploader({
  onUploaded,
}: {
  onUploaded?: (resp: FitsUploadResponse) => void;
}) {
  const { t } = useT();
  const upload = useFitsUpload();
  const [dragOver, setDragOver] = useState(false);
  const [recentSuccess, setRecentSuccess] = useState<FitsUploadResponse | null>(
    null,
  );
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!recentSuccess) return;
    const timer = setTimeout(() => setRecentSuccess(null), SUCCESS_DISPLAY_MS);
    return () => clearTimeout(timer);
  }, [recentSuccess]);

  const handleFile = (file: File | undefined) => {
    if (!file) return;
    const err = validateFile(file, t);
    if (err) {
      toast.error(err);
      return;
    }
    upload.mutate(
      { file },
      {
        onSuccess: (resp) => {
          setRecentSuccess(resp);
          onUploaded?.(resp);
        },
      },
    );
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    handleFile(e.dataTransfer.files?.[0]);
  };

  const onDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  };

  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    if (!dragOver) setDragOver(true);
  };

  const onDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.currentTarget.contains(e.relatedTarget as Node | null)) return;
    setDragOver(false);
  };

  const onSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    handleFile(e.target.files?.[0]);
    e.target.value = "";
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      inputRef.current?.click();
    }
  };

  const showCompactSuccess = recentSuccess && !upload.isPending;

  return (
    <motion.div
      variants={slideUp}
      initial="initial"
      animate="animate"
      transition={fadeTransition}
      className="space-y-3"
    >
      {showCompactSuccess ? (
        <CompactSuccess
          file={recentSuccess}
          onReplace={() => {
            setRecentSuccess(null);
            inputRef.current?.click();
          }}
        />
      ) : (
        <motion.div
          variants={fadeIn}
          initial="initial"
          animate="animate"
          transition={fadeTransition}
          onDrop={onDrop}
          onDragEnter={onDragEnter}
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          onClick={() => inputRef.current?.click()}
          onKeyDown={onKeyDown}
          role="button"
          tabIndex={0}
          aria-label="Upload a FITS file"
          className={cn(
            "flex cursor-pointer flex-col items-center gap-3 rounded-2xl border-2 border-dashed p-8 transition-all duration-200 focus:outline-none",
            upload.isPending && "pointer-events-none opacity-60",
          )}
          style={{
            borderColor: dragOver
              ? "rgba(79,195,247,0.6)"
              : "rgba(79,195,247,0.25)",
            background: dragOver
              ? "var(--accent-blue-dim)"
              : "rgba(79,195,247,0.02)",
          }}
        >
          <div
            className="flex h-14 w-14 items-center justify-center rounded-full text-2xl"
            style={{
              background: "var(--accent-blue-dim)",
              color: "var(--accent-blue)",
            }}
            aria-hidden
          >
            ◎
          </div>
          <div className="text-center">
            <p
              className="font-orbitron text-sm font-semibold uppercase"
              style={{
                color: "var(--text-primary)",
                letterSpacing: "0.14em",
              }}
            >
              {t("astronomy.fits.upload.title")}
            </p>
            <p
              className="font-exo2 mt-1 text-xs"
              style={{ color: "var(--text-secondary)" }}
            >
              {t("astronomy.fits.upload.browse")}
            </p>
            <p
              className="font-space-mono mt-2 text-[10px] uppercase"
              style={{
                color: "var(--text-muted)",
                letterSpacing: "0.16em",
              }}
            >
              {t("astronomy.fits.upload.formats", {
                size: formatBytes(MAX_FILE_SIZE.fits),
              })}
            </p>
          </div>
        </motion.div>
      )}

      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED_INPUT_ATTR}
        className="sr-only"
        onChange={onSelect}
        tabIndex={-1}
      />

      {upload.isPending && (
        <div className="space-y-1">
          <Progress value={upload.progress} />
          <p
            className="font-space-mono text-[11px] uppercase"
            style={{
              color: "var(--accent-blue)",
              letterSpacing: "0.14em",
            }}
          >
            {t("astronomy.fits.upload.progress", { percent: upload.progress })}
          </p>
        </div>
      )}
    </motion.div>
  );
}

function CompactSuccess({
  file,
  onReplace,
}: {
  file: FitsUploadResponse;
  onReplace: () => void;
}) {
  const { t } = useT();
  return (
    <motion.div
      variants={fadeIn}
      initial="initial"
      animate="animate"
      transition={fadeTransition}
      className="flex items-center justify-between gap-3 rounded-2xl p-4"
      style={{
        background: "var(--accent-blue-dim)",
        border: "1px solid rgba(79,195,247,0.3)",
      }}
    >
      <div className="flex min-w-0 items-center gap-3">
        <span
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-base"
          style={{
            background: "rgba(79,195,247,0.2)",
            color: "var(--accent-blue)",
          }}
          aria-hidden
        >
          ✓
        </span>
        <div className="min-w-0">
          <p
            className="font-exo2 truncate text-sm font-medium"
            style={{ color: "var(--text-primary)" }}
          >
            {file.filename}
          </p>
          <p
            className="font-space-mono mt-0.5 text-[11px] uppercase"
            style={{
              color: "var(--text-muted)",
              letterSpacing: "0.14em",
            }}
          >
            {t(
              file.hdu_count === 1
                ? "astronomy.fits.hduCount"
                : "astronomy.fits.hduCountPlural",
              { n: file.hdu_count },
            )}{" "}
            · {formatBytes(file.size_bytes)}
          </p>
        </div>
      </div>
      <button
        onClick={onReplace}
        className="cosmic-btn-outline"
        style={{ padding: "0.4rem 0.85rem" }}
      >
        <Upload className="h-3.5 w-3.5" />
        {t("astronomy.fits.upload.replace")}
      </button>
    </motion.div>
  );
}
