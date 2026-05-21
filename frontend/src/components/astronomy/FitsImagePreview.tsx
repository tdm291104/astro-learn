"use client";

import { Image as ImageIcon, Loader2, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";

import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { astronomyService } from "@/services/astronomyService";

// Poll the thumbnail URL until the Celery worker renders it post-upload.
const INITIAL_DELAY_MS = 1500;
const RETRY_DELAY_MS = 2500;
const MAX_RETRIES = 8;

export function FitsImagePreview({
  fileId,
  filename,
}: {
  fileId: string;
  filename: string;
}) {
  // `attempt` doubles as a cache-busting nonce on the URL.
  const [attempt, setAttempt] = useState(0);
  const [status, setStatus] = useState<
    "pending" | "loaded" | "exhausted" | "errored"
  >("pending");
  const [lightboxOpen, setLightboxOpen] = useState(false);

  // Reset polling when the selected file changes.
  useEffect(() => {
    setAttempt(0);
    setStatus("pending");
  }, [fileId]);

  useEffect(() => {
    if (status !== "pending") return;
    if (attempt >= MAX_RETRIES) {
      setStatus("exhausted");
      return;
    }
    const delay = attempt === 0 ? INITIAL_DELAY_MS : RETRY_DELAY_MS;
    const t = setTimeout(() => setAttempt((a) => a + 1), delay);
    return () => clearTimeout(t);
  }, [status, attempt]);

  const baseUrl = astronomyService.artifactUrl(fileId, "thumbnail.png");
  // Attempt counter bypasses browser cache; proxy ignores unknown params.
  const sep = baseUrl.includes("?") ? "&" : "?";
  const probeUrl = `${baseUrl}${sep}_a=${attempt}`;

  return (
    <div className="space-y-2">
      <div
        className="rounded-lg overflow-hidden"
        style={{
          background: "var(--bg-0)",
          border: "1px solid var(--border)",
        }}
      >
        {status === "loaded" ? (
          <button
            type="button"
            onClick={() => setLightboxOpen(true)}
            className="block w-full"
            aria-label={`Open ${filename} thumbnail at full size`}
          >
            <img
              src={baseUrl}
              alt={`${filename} thumbnail`}
              className="block max-h-72 w-full object-contain"
              style={{ background: "var(--bg-0)" }}
            />
          </button>
        ) : status === "exhausted" || status === "errored" ? (
          <ExhaustedState onRetry={() => {
            setAttempt(0);
            setStatus("pending");
          }} />
        ) : (
          <PendingState
            attempt={attempt}
            probeUrl={probeUrl}
            onLoaded={() => setStatus("loaded")}
            onError={() => {
              if (attempt + 1 >= MAX_RETRIES) {
                setStatus("exhausted");
              } else {
                setAttempt((a) => a + 1);
              }
            }}
          />
        )}
      </div>
      <p
        className="font-space-mono text-[10px] uppercase"
        style={{
          color: "var(--text-muted)",
          letterSpacing: "0.14em",
        }}
      >
        {status === "loaded"
          ? "ZScale stretch · click to enlarge"
          : status === "exhausted" || status === "errored"
            ? "Preview not available — retry?"
            : `Preparing preview… (${attempt + 1}/${MAX_RETRIES})`}
      </p>

      <Dialog open={lightboxOpen} onOpenChange={setLightboxOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle className="font-orbitron text-sm uppercase">
              {filename}
            </DialogTitle>
          </DialogHeader>
          <img
            src={baseUrl}
            alt={`${filename} full preview`}
            className="max-h-[70vh] w-full object-contain"
            style={{ background: "var(--bg-0)" }}
          />
        </DialogContent>
      </Dialog>
    </div>
  );
}

function PendingState({
  attempt,
  probeUrl,
  onLoaded,
  onError,
}: {
  attempt: number;
  probeUrl: string;
  onLoaded: () => void;
  onError: () => void;
}) {
  return (
    <div className="relative flex aspect-square w-full items-center justify-center">
      {/* Hidden probe; resolves once the worker produces the file. */}
      <img
        // Key recreates the element each retry so load/error fires fresh.
        key={attempt}
        src={probeUrl}
        alt=""
        aria-hidden
        className="sr-only"
        onLoad={onLoaded}
        onError={onError}
      />
      <div className="flex flex-col items-center gap-2 px-6 py-10 text-center">
        <Loader2
          className="h-6 w-6 animate-spin"
          style={{ color: "var(--accent-blue)" }}
        />
        <p
          className="font-exo2 text-xs"
          style={{ color: "var(--text-secondary)" }}
        >
          Preparing FITS preview…
        </p>
      </div>
    </div>
  );
}

function ExhaustedState({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center gap-2 px-6 py-10 text-center">
      <ImageIcon
        className="h-6 w-6"
        style={{ color: "var(--text-muted)" }}
        aria-hidden
      />
      <p
        className="font-exo2 text-xs"
        style={{ color: "var(--text-secondary)" }}
      >
        Preview not generated yet. The ingest worker may still be running
        or the file has no image HDU.
      </p>
      <button
        type="button"
        onClick={onRetry}
        className="cosmic-btn-outline mt-2"
        style={{ padding: "0.35rem 0.75rem" }}
      >
        <RefreshCw className="h-3 w-3" />
        Retry
      </button>
    </div>
  );
}
