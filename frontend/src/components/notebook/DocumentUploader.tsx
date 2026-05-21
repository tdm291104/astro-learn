"use client";

import { motion } from "framer-motion";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { fadeIn, fadeTransition } from "@/animations/fade";
import { Progress } from "@/components/ui/progress";
import { useDocumentUpload } from "@/hooks/useDocumentUpload";
import { useT } from "@/hooks/useT";
import { ACCEPTED_DOCUMENT_TYPES, MAX_FILE_SIZE } from "@/lib/constants";
import { cn, formatBytes } from "@/lib/utils";

const ACCEPTED_EXTENSIONS = [".pdf", ".txt", ".md"] as const;
const ACCEPTED_INPUT_ATTR = ACCEPTED_EXTENSIONS.join(",");

export function DocumentUploader({ notebookId }: { notebookId: string }) {
  const { t } = useT();
  const upload = useDocumentUpload(notebookId);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const validate = (file: File): string | null => {
    if (file.size > MAX_FILE_SIZE.document) {
      return t("notebook.upload.tooLarge", {
        max: formatBytes(MAX_FILE_SIZE.document),
        actual: formatBytes(file.size),
      });
    }
    const lower = file.name.toLowerCase();
    const matchesExt = ACCEPTED_EXTENSIONS.some((ext) => lower.endsWith(ext));
    const matchesMime =
      !file.type ||
      (ACCEPTED_DOCUMENT_TYPES as readonly string[]).includes(file.type);
    if (!matchesExt && !matchesMime) {
      return t("notebook.upload.unsupported", {
        types: ACCEPTED_EXTENSIONS.join(", "),
      });
    }
    return null;
  };

  const handleFile = (file: File | undefined) => {
    if (!file) return;
    const err = validate(file);
    if (err) {
      toast.error(err);
      return;
    }
    upload.mutate({ file });
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

  return (
    <div className="space-y-3">
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
        aria-label="Upload a document"
        className={cn(
          "flex cursor-pointer flex-col items-center gap-3 rounded-2xl border-2 border-dashed p-10 transition-all duration-200 focus:outline-none",
          upload.isPending && "pointer-events-none opacity-60",
        )}
        style={{
          borderColor: dragOver
            ? "rgba(226,201,126,0.5)"
            : "rgba(226,201,126,0.25)",
          background: dragOver
            ? "var(--accent-gold-dim)"
            : "rgba(226,201,126,0.02)",
        }}
      >
        <div
          className="flex h-14 w-14 items-center justify-center rounded-full text-2xl"
          style={{
            background: "var(--accent-gold-dim)",
            color: "var(--accent-gold)",
          }}
          aria-hidden
        >
          ⤴
        </div>
        <div className="text-center">
          <p
            className="font-orbitron text-sm font-semibold uppercase"
            style={{
              color: "var(--text-primary)",
              letterSpacing: "0.14em",
            }}
          >
            {t("notebook.upload.title")}
          </p>
          <p
            className="font-exo2 mt-1 text-xs"
            style={{ color: "var(--text-secondary)" }}
          >
            {t("notebook.upload.browse")}
          </p>
          <p
            className="font-space-mono mt-2 text-[10px] uppercase"
            style={{
              color: "var(--text-muted)",
              letterSpacing: "0.16em",
            }}
          >
            {t("notebook.upload.formats", { size: formatBytes(MAX_FILE_SIZE.document) })}
          </p>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED_INPUT_ATTR}
          className="sr-only"
          onChange={onSelect}
          tabIndex={-1}
        />
      </motion.div>

      {upload.isPending && (
        <div className="space-y-1">
          <Progress value={upload.progress} />
          <p
            className="font-space-mono text-[11px] uppercase"
            style={{
              color: "var(--accent-gold)",
              letterSpacing: "0.14em",
            }}
          >
            {t("notebook.upload.progress", { percent: upload.progress })}
          </p>
        </div>
      )}
    </div>
  );
}
