"use client";

import { ChevronDown } from "lucide-react";
import { useMemo, useState } from "react";

import { AnalysisHistoryList } from "@/components/astronomy/AnalysisHistoryList";
import { AnalysisResultsCard } from "@/components/astronomy/AnalysisResultsCard";
import { FitsFileList } from "@/components/astronomy/FitsFileList";
import { FitsHduTable } from "@/components/astronomy/FitsHduTable";
import { FitsHeaderViewer } from "@/components/astronomy/FitsHeaderViewer";
import { FitsImagePreview } from "@/components/astronomy/FitsImagePreview";
import { FitsUploader } from "@/components/astronomy/FitsUploader";
import { ReportPanel } from "@/components/astronomy/ReportPanel";
import { useFitsFilesSync } from "@/hooks/useFitsFilesSync";
import { cn } from "@/lib/utils";
import { useAstronomyStore } from "@/stores/astronomyStore";

type RailSection = "upload" | "inspect" | "history";

// FITS mode rail: upload + inspect; analysis is driven from chat composer.
export function FitsModePanel() {
  // Prune stale MRU entries before user clicks a non-existent file.
  useFitsFilesSync();

  const recentFiles = useAstronomyStore((s) => s.recentFiles);
  const selectedFileId = useAstronomyStore((s) => s.selectedFileId);
  const selectedHduIndex = useAstronomyStore((s) => s.selectedHduIndex);
  const setHduIndex = useAstronomyStore((s) => s.setHduIndex);

  const selectedFile = useMemo(
    () =>
      selectedFileId
        ? recentFiles.find((f) => f.file_id === selectedFileId) ?? null
        : null,
    [selectedFileId, recentFiles],
  );

  const [open, setOpen] = useState<RailSection | null>("upload");
  const toggle = (key: RailSection) =>
    setOpen((cur) => (cur === key ? null : key));

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header
        className="shrink-0 px-4 pb-3 pt-4"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <h2
          className="font-orbitron text-xs font-semibold uppercase"
          style={{ color: "var(--accent-gold)", letterSpacing: "0.2em" }}
        >
          FITS Analysis
        </h2>
        <p
          className="font-exo2 mt-0.5 text-[11px]"
          style={{ color: "var(--text-muted)" }}
        >
          Upload a file, inspect headers, then ask the assistant to analyse it.
        </p>
      </header>

      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto px-3 py-3">
        <RailSectionShell
          label="Upload"
          glyph="◎"
          open={open === "upload"}
          onToggle={() => toggle("upload")}
        >
          <div className="space-y-4">
            <FitsUploader />
            <FitsFileList />
          </div>
        </RailSectionShell>

        <RailSectionShell
          label="Inspect"
          glyph="◐"
          open={open === "inspect"}
          onToggle={() => toggle("inspect")}
        >
          {selectedFile ? (
            <div className="space-y-3">
              {/* Thumbnail is rendered by the ingest worker shortly after
                  upload. Component polls the artifact endpoint with bounded
                  retries while ingest is in flight. */}
              <FitsImagePreview
                fileId={selectedFile.file_id}
                filename={selectedFile.filename}
              />
              <FitsHduTable
                file={selectedFile}
                selectedHdu={selectedHduIndex}
                onSelectHdu={setHduIndex}
              />
              <FitsHeaderViewer headers={selectedFile.primary_headers} />
            </div>
          ) : (
            <p
              className="font-exo2 text-xs"
              style={{ color: "var(--text-muted)" }}
            >
              Upload a file to inspect its HDUs and headers.
            </p>
          )}
        </RailSectionShell>

        <RailSectionShell
          label="History"
          glyph="◉"
          open={open === "history"}
          onToggle={() => toggle("history")}
        >
          <AnalysisHistoryList />
        </RailSectionShell>
      </div>
    </div>
  );
}

// Local copy of the StudioPanel accordion idiom — duplicated rather than
// extracted because the two surfaces have slightly different empty-state
// affordances and we want to keep the rail self-contained.
function RailSectionShell({
  label,
  glyph,
  open,
  onToggle,
  children,
}: {
  label: string;
  glyph: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <div
      className="rounded-lg"
      style={{
        background: open ? "rgba(255,255,255,0.02)" : "transparent",
        border: "1px solid var(--border)",
      }}
    >
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between gap-2 rounded-lg px-3 py-2.5 text-left"
        aria-expanded={open}
      >
        <span className="flex items-center gap-2">
          <span
            className="text-base leading-none"
            style={{ color: "var(--accent-gold)" }}
            aria-hidden
          >
            {glyph}
          </span>
          <span
            className="font-orbitron text-xs font-semibold uppercase"
            style={{
              color: "var(--text-primary)",
              letterSpacing: "0.16em",
            }}
          >
            {label}
          </span>
        </span>
        <ChevronDown
          className={cn(
            "h-4 w-4 transition-transform",
            open && "rotate-180",
          )}
          style={{ color: "var(--text-muted)" }}
        />
      </button>
      {open && (
        <div
          className="border-t px-3 py-3"
          style={{ borderColor: "var(--border)" }}
        >
          {children}
        </div>
      )}
    </div>
  );
}

// Right-side artifact column for FITS mode. Pure polling against
// activeAnalysisId so clicking a History entry always shows THAT entry's
// results — no stream-driven override. The BE persists the validated
// interpretation onto every analysis row in the run, so the polled
// AnalyzeResponse carries it and AnalysisResultsCard short-circuits to
// FitsInterpretationView. The cache race (poll fires once at status=
// succeeded before persist completes) is closed by useChat invalidating
// the analysis cache when extra.fits_interpretation arrives.
export function FitsArtifactsPanel() {
  const activeAnalysisId = useAstronomyStore((s) => s.activeAnalysisId);

  if (!activeAnalysisId) {
    return (
      <div className="flex h-full items-center justify-center px-6">
        <div
          className="font-exo2 max-w-sm rounded-2xl border-2 border-dashed p-8 text-center text-sm"
          style={{
            borderColor: "rgba(79,195,247,0.18)",
            background: "rgba(79,195,247,0.02)",
            color: "var(--text-secondary)",
          }}
        >
          Upload a FITS file and ask the assistant to analyse it — the
          interpretation will appear here.
        </div>
      </div>
    );
  }

  return (
    // h-full + block layout. flex-col made children stretch to fit and
    // defeated overflow-y-auto; plain block + space-y stacks naturally and
    // the wrapper becomes the scroll container.
    <div className="h-full min-h-0 space-y-4 overflow-y-auto p-5">
      <AnalysisResultsCard analysisId={activeAnalysisId} />
      <ReportPanel analysisId={activeAnalysisId} />
    </div>
  );
}
