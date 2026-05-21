"use client";

import { motion } from "framer-motion";
import { Download, FileText } from "lucide-react";
import { useState } from "react";

import { fadeIn, fadeTransition } from "@/animations/fade";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { astronomyService } from "@/services/astronomyService";
import { ARTIFACTS_ENABLED } from "@/lib/constants";

const IMAGE_EXT_RE = /\.(png|jpe?g|gif|webp|svg)$/i;

function isImage(filename: string): boolean {
  return IMAGE_EXT_RE.test(filename);
}

export function AnalysisArtifacts({
  artifacts,
  fileId,
}: {
  artifacts: string[];
  fileId: string;
}) {
  const [openImage, setOpenImage] = useState<string | null>(null);

  if (artifacts.length === 0) return null;

  if (!ARTIFACTS_ENABLED) {
    return (
      <div className="cosmic-card space-y-2 p-4">
        <h4
          className="font-orbitron text-sm font-semibold uppercase"
          style={{
            color: "var(--text-primary)",
            letterSpacing: "0.16em",
          }}
        >
          Artifacts
        </h4>
        <ul
          className="font-space-mono space-y-1 text-xs"
          style={{ color: "var(--text-secondary)" }}
        >
          {artifacts.map((name) => (
            <li key={name}>{name}</li>
          ))}
        </ul>
      </div>
    );
  }

  const images: string[] = [];
  const others: string[] = [];
  for (const a of artifacts) (isImage(a) ? images : others).push(a);

  return (
    <div className="cosmic-card space-y-3 p-4">
      <h4
        className="font-orbitron text-sm font-semibold uppercase"
        style={{
          color: "var(--text-primary)",
          letterSpacing: "0.16em",
        }}
      >
        Artifacts{" "}
        <span
          className="font-space-mono"
          style={{ color: "var(--text-muted)" }}
        >
          ({artifacts.length})
        </span>
      </h4>

      {images.length > 0 && (
        <motion.div
          variants={fadeIn}
          initial="initial"
          animate="animate"
          transition={fadeTransition}
          className="grid grid-cols-2 gap-3 sm:grid-cols-3"
        >
          {images.map((name) => (
            <button
              key={name}
              type="button"
              onClick={() => setOpenImage(name)}
              className="group block overflow-hidden rounded-lg transition-all duration-200 focus:outline-none"
              style={{
                background: "var(--bg-3)",
                border: "1px solid var(--border)",
              }}
              aria-label={`Open ${name}`}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={astronomyService.artifactUrl(fileId, name)}
                alt={name}
                className="aspect-square w-full object-cover transition-transform group-hover:scale-105"
                loading="lazy"
              />
              <div
                className="px-2 py-1 text-left"
                style={{ borderTop: "1px solid var(--border)" }}
              >
                <p
                  className="font-space-mono truncate text-[10px] uppercase"
                  style={{
                    color: "var(--text-muted)",
                    letterSpacing: "0.12em",
                  }}
                >
                  {name}
                </p>
              </div>
            </button>
          ))}
        </motion.div>
      )}

      {others.length > 0 && (
        <ul className="space-y-1">
          {others.map((name) => (
            <li
              key={name}
              className="flex items-center justify-between gap-2 rounded-md px-2.5 py-1.5 text-xs"
              style={{
                background: "rgba(255,255,255,0.02)",
                border: "1px solid var(--border)",
              }}
            >
              <div className="flex min-w-0 items-center gap-2">
                <FileText
                  className="h-3.5 w-3.5 shrink-0"
                  style={{ color: "var(--text-muted)" }}
                />
                <span
                  className="font-space-mono truncate"
                  style={{ color: "var(--text-primary)" }}
                >
                  {name}
                </span>
              </div>
              <a
                href={astronomyService.artifactUrl(fileId, name)}
                download={name}
                aria-label={`Download ${name}`}
                style={{ color: "var(--accent-gold)" }}
              >
                <Download className="h-3.5 w-3.5" />
              </a>
            </li>
          ))}
        </ul>
      )}

      <Dialog
        open={openImage !== null}
        onOpenChange={(open) => {
          if (!open) setOpenImage(null);
        }}
      >
        <DialogContent className="sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>
              <span
                className="font-space-mono text-sm"
                style={{ color: "var(--accent-teal)" }}
              >
                {openImage}
              </span>
            </DialogTitle>
            <DialogDescription>
              Generated analysis artifact.
            </DialogDescription>
          </DialogHeader>
          {openImage && (
            <div
              className="overflow-auto rounded-lg"
              style={{
                background: "var(--bg-0)",
                border: "1px solid var(--border)",
              }}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={astronomyService.artifactUrl(fileId, openImage)}
                alt={openImage}
                className="mx-auto max-h-[70vh] object-contain"
              />
            </div>
          )}
          <div className="flex justify-end gap-2">
            {openImage && (
              <a
                href={astronomyService.artifactUrl(fileId, openImage)}
                download={openImage}
                className="cosmic-btn-outline inline-flex"
              >
                <Download className="h-3.5 w-3.5" />
                Download
              </a>
            )}
            <DialogClose
              render={
                <button className="cosmic-btn-primary">Close</button>
              }
            />
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
