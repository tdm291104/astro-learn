"use client";

import { motion } from "framer-motion";
import { AlertCircle, ChevronRight, Sparkles } from "lucide-react";
import { useState } from "react";

import { staggerContainer, staggerItem } from "@/animations/stagger";
import { Skeleton } from "@/components/ui/skeleton";
import { useCatalogSearch } from "@/hooks/useCatalogSearch";
import { cn } from "@/lib/utils";
import type {
  CatalogObject,
  CatalogSource,
} from "@/types/astronomy.types";

function fmtDeg(value: number | null): string {
  if (value === null) return "—";
  return value.toFixed(5);
}

export function CatalogResultsTable({
  query,
  source,
  radius,
  limit = 20,
}: {
  query: string;
  source: CatalogSource;
  radius?: number | null;
  limit?: number;
}) {
  const {
    data,
    isLoading,
    isFetching,
    isError,
    error,
    refetch,
    isQueryTooShort,
    debouncedQuery,
  } = useCatalogSearch({ query, source, radiusArcsec: radius, limit });

  if (isQueryTooShort || (!debouncedQuery && !data)) {
    return (
      <div
        className="font-exo2 rounded-2xl border-2 border-dashed p-8 text-center text-sm"
        style={{
          borderColor: "rgba(77,208,225,0.18)",
          background: "rgba(77,208,225,0.02)",
          color: "var(--text-secondary)",
        }}
      >
        Type at least 2 characters to search.
      </div>
    );
  }

  if ((isLoading || isFetching) && !data) {
    return <SkeletonRows />;
  }

  if (isError) {
    return (
      <div
        className="rounded-2xl p-4"
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
          Catalog Search Failed
        </div>
        <p
          className="font-exo2 text-sm"
          style={{ color: "var(--text-primary)" }}
        >
          {error instanceof Error ? error.message : "Unknown error"}
        </p>
        <button onClick={() => refetch()} className="cosmic-btn-outline mt-3">
          Try Again
        </button>
      </div>
    );
  }

  if (!data || data.results.length === 0) {
    return (
      <div
        className="font-exo2 rounded-2xl border-2 border-dashed p-8 text-center text-sm"
        style={{
          borderColor: "rgba(226,201,126,0.18)",
          color: "var(--text-secondary)",
        }}
      >
        No matches in {source.toUpperCase()}.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {data.commentary && <CommentaryCallout text={data.commentary} />}
      <div className="cosmic-card overflow-hidden">
      <div
        className="flex items-center justify-between border-b px-4 py-3"
        style={{ borderColor: "var(--border)" }}
      >
        <h3
          className="font-orbitron text-sm font-semibold uppercase"
          style={{
            color: "var(--text-primary)",
            letterSpacing: "0.16em",
          }}
        >
          Results{" "}
          <span
            className="font-space-mono"
            style={{ color: "var(--text-muted)" }}
          >
            ({data.results.length})
          </span>
        </h3>
        <p
          className="font-space-mono text-[11px] uppercase"
          style={{
            color: "var(--text-muted)",
            letterSpacing: "0.16em",
          }}
        >
          via {source.toUpperCase()}
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm">
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border)" }}>
              <th className="w-8 px-3 py-2"></th>
              {[
                { label: "Name", align: "left" },
                { label: "Type", align: "left" },
                { label: "RA (°)", align: "right" },
                { label: "Dec (°)", align: "right" },
                { label: "Refs", align: "right" },
              ].map((c) => (
                <th
                  key={c.label}
                  className="font-orbitron px-3 py-2 text-xs uppercase"
                  style={{
                    color: "var(--text-muted)",
                    letterSpacing: "0.16em",
                    textAlign: c.align as "left" | "right",
                  }}
                >
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <motion.tbody
            variants={staggerContainer}
            initial="initial"
            animate="animate"
          >
            {data.results.map((row, i) => (
              <ResultRow key={`${row.name}-${i}`} row={row} />
            ))}
          </motion.tbody>
        </table>
      </div>
      </div>
    </div>
  );
}

function CommentaryCallout({ text }: { text: string }) {
  return (
    <div
      className="rounded-lg p-3"
      style={{
        background: "rgba(226,201,126,0.06)",
        border: "1px solid rgba(226,201,126,0.22)",
      }}
    >
      <div
        className="cosmic-label flex items-center gap-1.5 mb-1.5"
        style={{ color: "var(--accent-gold)" }}
      >
        <Sparkles className="h-3 w-3" />
        Context
      </div>
      <p
        className="font-exo2 text-sm"
        style={{ color: "var(--text-primary)" }}
      >
        {text}
      </p>
    </div>
  );
}

function ResultRow({ row }: { row: CatalogObject }) {
  const [expanded, setExpanded] = useState(false);
  const hasDetail =
    row.references.length > 0 || Object.keys(row.extra).length > 0;

  return (
    <>
      <motion.tr
        variants={staggerItem}
        onClick={() => hasDetail && setExpanded((v) => !v)}
        className={cn(hasDetail && "cursor-pointer transition-colors")}
        style={{ borderBottom: "1px solid var(--border)" }}
        aria-expanded={hasDetail ? expanded : undefined}
      >
        <td className="px-3 py-2" style={{ color: "var(--text-muted)" }}>
          {hasDetail && (
            <ChevronRight
              className={cn(
                "h-3.5 w-3.5 transition-transform",
                expanded && "rotate-90",
              )}
            />
          )}
        </td>
        <td
          className="font-space-mono px-3 py-2 font-medium"
          style={{ color: "var(--accent-teal)" }}
        >
          {row.name}
        </td>
        <td
          className="font-exo2 px-3 py-2 text-xs"
          style={{ color: "var(--text-secondary)" }}
        >
          {row.object_type ?? "—"}
        </td>
        <td
          className="font-space-mono px-3 py-2 text-right tabular-nums"
          style={{ color: "var(--text-secondary)" }}
        >
          {fmtDeg(row.ra_deg)}
        </td>
        <td
          className="font-space-mono px-3 py-2 text-right tabular-nums"
          style={{ color: "var(--text-secondary)" }}
        >
          {fmtDeg(row.dec_deg)}
        </td>
        <td
          className="font-space-mono px-3 py-2 text-right tabular-nums"
          style={{ color: "var(--accent-gold)" }}
        >
          {row.references.length}
        </td>
      </motion.tr>
      {expanded && hasDetail && (
        <tr style={{ background: "rgba(255,255,255,0.02)" }}>
          <td></td>
          <td colSpan={5} className="px-3 py-3">
            <ResultDetail row={row} />
          </td>
        </tr>
      )}
    </>
  );
}

function ResultDetail({ row }: { row: CatalogObject }) {
  return (
    <div className="space-y-3 text-xs">
      {row.references.length > 0 && (
        <div>
          <p className="cosmic-label">References</p>
          <ul
            className="font-space-mono mt-1 list-inside list-disc space-y-0.5"
            style={{ color: "var(--text-primary)" }}
          >
            {row.references.map((ref, i) => (
              <li key={i}>{ref}</li>
            ))}
          </ul>
        </div>
      )}
      {Object.keys(row.extra).length > 0 && (
        <div>
          <p className="cosmic-label">Extra</p>
          <pre
            className="font-space-mono mt-1 overflow-auto rounded p-2"
            style={{
              background: "var(--bg-0)",
              color: "var(--text-primary)",
              border: "1px solid var(--border)",
            }}
          >
            {JSON.stringify(row.extra, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

function SkeletonRows() {
  return (
    <div className="space-y-2">
      {Array.from({ length: 5 }).map((_, i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  );
}
