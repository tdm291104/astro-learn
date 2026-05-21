"use client";

import { motion } from "framer-motion";
import { AlertCircle, ChevronDown } from "lucide-react";
import { useMemo, useState } from "react";

import { fadeIn, fadeTransition } from "@/animations/fade";
import { AnalysisArtifacts } from "@/components/astronomy/AnalysisArtifacts";
import { FitsInterpretationView } from "@/components/astronomy/FitsInterpretationView";
import { Skeleton } from "@/components/ui/skeleton";
import { useAnalysisStatus } from "@/hooks/useAnalysis";
import { cn } from "@/lib/utils";
import type {
  AnalysisStatus,
  AnalysisType,
  AnalyzeResponse,
} from "@/types/astronomy.types";
import { isFitsInterpretation } from "@/types/fitsInterpretation";

const STATUS_COLOR: Record<AnalysisStatus, string> = {
  pending: "var(--text-muted)",
  running: "var(--accent-blue)",
  succeeded: "#4caf50",
  failed: "var(--accent-coral)",
};

const STATUS_PULSE: Record<AnalysisStatus, boolean> = {
  pending: true,
  running: true,
  succeeded: false,
  failed: false,
};

function statusLabel(s: AnalysisStatus): string {
  return s[0].toUpperCase() + s.slice(1);
}

function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function fmt(value: unknown, digits = 4): string {
  const n = num(value);
  if (n === null) return "—";
  const abs = Math.abs(n);
  if (abs !== 0 && (abs < 1e-3 || abs >= 1e6)) return n.toExponential(2);
  return n.toFixed(digits);
}

export function AnalysisResultsCard({ analysisId }: { analysisId: string }) {
  const { data, isLoading, isError, error, refetch } =
    useAnalysisStatus(analysisId);

  return (
    <div className="cosmic-card p-5">
      <header className="mb-4 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h3
            className="font-orbitron text-sm font-semibold uppercase"
            style={{
              color: "var(--text-primary)",
              letterSpacing: "0.16em",
            }}
          >
            Analysis
          </h3>
          <p
            className="font-space-mono mt-0.5 truncate text-[11px] uppercase"
            style={{
              color: "var(--text-muted)",
              letterSpacing: "0.12em",
            }}
          >
            {analysisId}
          </p>
        </div>
        {data && <StatusBadge status={data.status} />}
      </header>

      {isLoading && !data ? (
        <PendingSkeleton label="Loading analysis..." />
      ) : isError ? (
        <FetchError
          message={error instanceof Error ? error.message : "Unknown error"}
          onRetry={() => refetch()}
        />
      ) : data ? (
        <ResultsByStatus data={data} />
      ) : null}
    </div>
  );
}

function StatusBadge({ status }: { status: AnalysisStatus }) {
  return (
    <span
      className="inline-flex shrink-0 items-center gap-2 rounded-full px-2.5 py-0.5"
      style={{
        background: "rgba(255,255,255,0.02)",
        border: "1px solid var(--border)",
      }}
    >
      <span
        className="cosmic-status-dot"
        style={{
          background: STATUS_COLOR[status],
          animation: STATUS_PULSE[status]
            ? "cosmic-pulse 1.6s ease-in-out infinite"
            : undefined,
        }}
        aria-hidden
      />
      <span
        className="font-orbitron text-[10px] uppercase"
        style={{
          color: STATUS_COLOR[status],
          letterSpacing: "0.18em",
        }}
      >
        {statusLabel(status)}
      </span>
    </span>
  );
}

function ResultsByStatus({ data }: { data: AnalyzeResponse }) {
  if (data.status === "pending" || data.status === "running") {
    return (
      <PendingSkeleton
        label={
          data.status === "pending"
            ? "Analysis queued..."
            : "Analysis running..."
        }
      />
    );
  }

  if (data.status === "failed") {
    const errorMessage =
      typeof data.results?.error === "string"
        ? data.results.error
        : "Analysis failed without an error message.";
    return (
      <div
        className="rounded-lg p-4"
        style={{
          background: "rgba(255,112,67,0.08)",
          border: "1px solid rgba(255,112,67,0.25)",
        }}
      >
        <div
          className="cosmic-label flex items-center gap-2 mb-1.5"
          style={{ color: "var(--accent-coral)" }}
        >
          <AlertCircle className="h-3 w-3" />
          Analysis Failed
        </div>
        <p
          className="font-exo2 text-sm"
          style={{ color: "var(--text-primary)" }}
        >
          {errorMessage}
        </p>
      </div>
    );
  }

  // Prefer structured interpretation; legacy runs fall through to tiles.
  const interp = data.interpretation;
  if (isFitsInterpretation(interp)) {
    return (
      <motion.div
        variants={fadeIn}
        initial="initial"
        animate="animate"
        transition={fadeTransition}
        className="space-y-4"
      >
        <FitsInterpretationView data={interp} />
        <RawDataToggle>
          <SuccessBody type={data.analysis_type} results={data.results} />
        </RawDataToggle>
        {data.artifacts.length > 0 && (
          <AnalysisArtifacts
            artifacts={data.artifacts}
            fileId={data.file_id}
          />
        )}
      </motion.div>
    );
  }

  return (
    <motion.div
      variants={fadeIn}
      initial="initial"
      animate="animate"
      transition={fadeTransition}
      className="space-y-4"
    >
      <SuccessBody type={data.analysis_type} results={data.results} />
      {data.artifacts.length > 0 && (
        <AnalysisArtifacts
          artifacts={data.artifacts}
          fileId={data.file_id}
        />
      )}
    </motion.div>
  );
}

function RawDataToggle({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div
      className="rounded-lg overflow-hidden"
      style={{ border: "1px solid var(--border)" }}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-3 py-2 text-left"
        style={{ background: "rgba(255,255,255,0.02)" }}
        aria-expanded={open}
      >
        <span
          className="font-orbitron text-xs uppercase"
          style={{
            color: "var(--text-muted)",
            letterSpacing: "0.16em",
          }}
        >
          View Raw Data
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
          className="px-3 py-3"
          style={{
            borderTop: "1px solid var(--border)",
            background: "rgba(0,0,0,0.15)",
          }}
        >
          {children}
        </div>
      )}
    </div>
  );
}

function SuccessBody({
  type,
  results,
}: {
  type: AnalysisType;
  results: Record<string, unknown>;
}) {
  switch (type) {
    case "image_stats":
      return <ImageStatsTiles results={results} />;
    case "photometry":
      return <PhotometryTable results={results} />;
    case "spectroscopy":
      return <SpectroscopyTiles results={results} />;
    case "wcs_solve":
      return <WcsSolveTiles results={results} />;
    case "custom":
      return <RawJsonView results={results} />;
    default:
      return <RawJsonView results={results} />;
  }
}

function PendingSkeleton({ label }: { label: string }) {
  return (
    <div className="space-y-3">
      <div
        className="font-space-mono flex items-center gap-2 text-xs uppercase"
        style={{
          color: "var(--accent-blue)",
          letterSpacing: "0.16em",
        }}
      >
        <span
          className="cosmic-status-dot cosmic-status-pulse"
          style={{ background: "var(--accent-blue)" }}
          aria-hidden
        />
        {label}
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-16" />
        ))}
      </div>
    </div>
  );
}

function StatTile({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div
      className="rounded-lg p-3"
      style={{
        background: "rgba(255,255,255,0.02)",
        border: "1px solid var(--border)",
      }}
    >
      <p
        className="font-space-mono text-[10px] uppercase"
        style={{
          color: "var(--text-muted)",
          letterSpacing: "0.18em",
        }}
      >
        {label}
      </p>
      <p
        className="font-space-mono mt-1 break-all text-sm tabular-nums"
        style={{ color: "var(--accent-gold)" }}
      >
        {value}
      </p>
    </div>
  );
}

function ImageStatsTiles({ results }: { results: Record<string, unknown> }) {
  const tiles: { label: string; value: React.ReactNode }[] = [
    { label: "mean", value: fmt(results.mean) },
    { label: "median", value: fmt(results.median) },
    { label: "stddev", value: fmt(results.stddev ?? results.std) },
    { label: "min", value: fmt(results.min) },
    { label: "max", value: fmt(results.max) },
    { label: "nan_count", value: fmt(results.nan_count, 0) },
  ];
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3">
      {tiles.map((t) => (
        <StatTile key={t.label} label={t.label} value={t.value} />
      ))}
    </div>
  );
}

type PhotometrySource = {
  x_centroid?: number;
  y_centroid?: number;
  peak?: number;
  flux?: number;
};

function PhotometryTable({ results }: { results: Record<string, unknown> }) {
  const sourcesRaw =
    (results.sources as unknown) ?? (results.source_list as unknown);
  const sources: PhotometrySource[] = Array.isArray(sourcesRaw)
    ? (sourcesRaw as PhotometrySource[])
    : [];

  if (sources.length === 0) {
    return (
      <p
        className="font-exo2 text-sm"
        style={{ color: "var(--text-secondary)" }}
      >
        No sources detected — adjust threshold_sigma and try again.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span
          className="font-space-mono inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] uppercase"
          style={{
            background: "var(--accent-gold-dim)",
            color: "var(--accent-gold)",
            border: "1px solid rgba(226,201,126,0.25)",
            letterSpacing: "0.14em",
          }}
        >
          {sources.length} sources
        </span>
        <p
          className="font-exo2 text-xs"
          style={{ color: "var(--text-muted)" }}
        >
          Full source list available as a JSON artifact.
        </p>
      </div>
      <div
        className="max-h-72 overflow-auto rounded-lg"
        style={{ border: "1px solid var(--border)" }}
      >
        <table className="w-full min-w-[480px] text-xs">
          <thead
            className="sticky top-0"
            style={{ background: "var(--bg-2)" }}
          >
            <tr>
              {["x", "y", "peak", "flux"].map((h, i) => (
                <th
                  key={h}
                  className="font-orbitron px-2 py-1.5 text-[10px] uppercase"
                  style={{
                    color: "var(--text-muted)",
                    letterSpacing: "0.16em",
                    textAlign: i < 2 ? "left" : "right",
                  }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sources.slice(0, 200).map((s, i) => (
              <tr
                key={i}
                style={{ borderTop: "1px solid var(--border)" }}
              >
                <td
                  className="font-space-mono px-2 py-1 tabular-nums"
                  style={{ color: "var(--text-secondary)" }}
                >
                  {fmt(s.x_centroid, 2)}
                </td>
                <td
                  className="font-space-mono px-2 py-1 tabular-nums"
                  style={{ color: "var(--text-secondary)" }}
                >
                  {fmt(s.y_centroid, 2)}
                </td>
                <td
                  className="font-space-mono px-2 py-1 text-right tabular-nums"
                  style={{ color: "var(--accent-gold)" }}
                >
                  {fmt(s.peak, 3)}
                </td>
                <td
                  className="font-space-mono px-2 py-1 text-right tabular-nums"
                  style={{ color: "var(--accent-gold)" }}
                >
                  {fmt(s.flux, 3)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {sources.length > 200 && (
          <div
            className="font-space-mono px-2 py-1.5 text-center text-[11px] uppercase"
            style={{
              borderTop: "1px solid var(--border)",
              background: "var(--bg-2)",
              color: "var(--text-muted)",
              letterSpacing: "0.14em",
            }}
          >
            Showing first 200 of {sources.length}
          </div>
        )}
      </div>
    </div>
  );
}

function SpectroscopyTiles({ results }: { results: Record<string, unknown> }) {
  const summary =
    (results.data_summary as Record<string, unknown> | undefined) ?? {};
  const tiles: { label: string; value: React.ReactNode }[] = [
    { label: "wavelength", value: fmt(results.wavelength) },
    { label: "frequency", value: fmt(results.frequency) },
    {
      label: "unit",
      value: typeof results.unit === "string" ? results.unit : "—",
    },
    {
      label: "n_samples",
      value: fmt(summary.n_samples ?? results.n_samples, 0),
    },
    { label: "min", value: fmt(summary.min ?? results.min) },
    { label: "max", value: fmt(summary.max ?? results.max) },
  ];
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3">
      {tiles.map((t) => (
        <StatTile key={t.label} label={t.label} value={t.value} />
      ))}
    </div>
  );
}

function WcsSolveTiles({ results }: { results: Record<string, unknown> }) {
  const tiles: { label: string; value: React.ReactNode }[] = [
    { label: "CRVAL1", value: fmt(results.CRVAL1 ?? results.crval1) },
    { label: "CRVAL2", value: fmt(results.CRVAL2 ?? results.crval2) },
    {
      label: "CTYPE1",
      value:
        typeof results.CTYPE1 === "string"
          ? results.CTYPE1
          : typeof results.ctype1 === "string"
            ? results.ctype1
            : "—",
    },
    {
      label: "CTYPE2",
      value:
        typeof results.CTYPE2 === "string"
          ? results.CTYPE2
          : typeof results.ctype2 === "string"
            ? results.ctype2
            : "—",
    },
    { label: "scale", value: fmt(results.scale ?? results.pixel_scale) },
    { label: "orientation", value: fmt(results.orientation ?? results.theta) },
  ];
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3">
      {tiles.map((t) => (
        <StatTile key={t.label} label={t.label} value={t.value} />
      ))}
    </div>
  );
}

function RawJsonView({ results }: { results: Record<string, unknown> }) {
  const [open, setOpen] = useState(false);
  const json = useMemo(() => JSON.stringify(results, null, 2), [results]);

  return (
    <div
      className="rounded-lg overflow-hidden"
      style={{ border: "1px solid var(--border)" }}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-3 py-2 text-left"
        style={{ background: "rgba(255,255,255,0.02)" }}
        aria-expanded={open}
      >
        <span
          className="font-orbitron text-xs uppercase"
          style={{
            color: "var(--text-primary)",
            letterSpacing: "0.16em",
          }}
        >
          Raw Results
        </span>
        <ChevronDown
          className={cn(
            "h-4 w-4 transition-transform",
            open && "rotate-180",
          )}
          style={{ color: "var(--accent-gold)" }}
        />
      </button>
      {open && (
        <pre
          className="font-space-mono max-h-80 overflow-auto px-3 py-2 text-xs"
          style={{
            background: "var(--bg-0)",
            color: "var(--text-primary)",
            borderTop: "1px solid var(--border)",
          }}
        >
          {json}
        </pre>
      )}
    </div>
  );
}

function FetchError({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div
      className="rounded-lg p-4"
      style={{
        background: "rgba(255,112,67,0.08)",
        border: "1px solid rgba(255,112,67,0.25)",
      }}
    >
      <div
        className="cosmic-label flex items-center gap-2 mb-1.5"
        style={{ color: "var(--accent-coral)" }}
      >
        <AlertCircle className="h-3 w-3" />
        Couldn&apos;t Load Analysis
      </div>
      <p
        className="font-exo2 text-sm"
        style={{ color: "var(--text-primary)" }}
      >
        {message}
      </p>
      <button onClick={onRetry} className="cosmic-btn-outline mt-3">
        Try Again
      </button>
    </div>
  );
}
