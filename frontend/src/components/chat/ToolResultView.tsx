"use client";

import {
  ChevronDown,
  ChevronRight,
  Database,
  ExternalLink,
  FileSearch,
  FileText,
  Globe,
  MapPin,
  Telescope,
} from "lucide-react";
import { useMemo, useState } from "react";

import { useT } from "@/hooks/useT";
import { cn } from "@/lib/utils";

type Props = {
  toolName: string;
  rawContent: string;
};

// Top-level dispatcher. Parses `rawContent` once and routes to a specialised
// renderer based on `toolName`; falls back to pretty-printed JSON.
export function ToolResultView({ toolName, rawContent }: Props) {
  const parsed = useMemo(() => safeParse(rawContent), [rawContent]);

  if (parsed === undefined) {
    return <PlainText text={rawContent} />;
  }

  if (toolName === "vector_search" && Array.isArray(parsed)) {
    return <VectorSearchView chunks={parsed} />;
  }

  if (
    (toolName === "simbad_query" ||
      toolName === "ned_query" ||
      toolName === "vizier_query") &&
    isObject(parsed)
  ) {
    return <CatalogResultsView data={parsed} />;
  }

  if (toolName === "web_search" && (Array.isArray(parsed) || isObject(parsed))) {
    return <WebSearchView data={parsed} />;
  }

  if (toolName === "pdf_parser" && isObject(parsed)) {
    return <PdfParserView data={parsed} />;
  }

  if (toolName === "fits_reader" && isObject(parsed)) {
    return <FitsReaderView data={parsed} />;
  }

  if (toolName === "run_fits_analysis" && isObject(parsed)) {
    return <FitsAnalysisView data={parsed} />;
  }

  return <PrettyJson value={parsed} />;
}

// --- Helpers ----------------------------------------------------------------

function safeParse(s: string): unknown {
  try {
    return JSON.parse(s);
  } catch {
    return undefined;
  }
}

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function clamp(text: string, max: number): string {
  if (text.length <= max) return text;
  return text.slice(0, max).trim() + "…";
}

// --- vector_search ----------------------------------------------------------

type Chunk = {
  chunk_id?: string;
  document_id?: string;
  text?: string;
  score?: number;
  metadata?: { page?: number; char_offset?: number };
};

function VectorSearchView({ chunks }: { chunks: unknown[] }) {
  const { t } = useT();
  if (chunks.length === 0) {
    return <EmptyState label={t("chat.tools_.vector.empty")} />;
  }
  return (
    <div className="space-y-2">
      <ResultHeader
        icon={<FileSearch className="h-3.5 w-3.5" />}
        label={t(
          chunks.length === 1
            ? "chat.tools_.vector.count"
            : "chat.tools_.vector.countPlural",
          { n: chunks.length },
        )}
      />
      <ul className="space-y-1.5">
        {chunks.slice(0, 8).map((raw, i) => (
          <ChunkCard key={i} index={i} chunk={raw as Chunk} />
        ))}
      </ul>
      {chunks.length > 8 && (
        <p
          className="font-exo2 px-1 text-[11px] italic"
          style={{ color: "var(--text-muted)" }}
        >
          {t("chat.tools_.vector.more", { n: chunks.length - 8 })}
        </p>
      )}
    </div>
  );
}

function ChunkCard({ index, chunk }: { index: number; chunk: Chunk }) {
  const { t } = useT();
  const [open, setOpen] = useState(false);
  const text = (chunk.text ?? "").replace(/\s+/g, " ").trim();
  const page = chunk.metadata?.page;
  const score = typeof chunk.score === "number" ? chunk.score : null;
  const docTag = chunk.document_id ? chunk.document_id.slice(0, 6) : null;

  return (
    <li
      className="rounded-md px-3 py-2"
      style={{
        background: "rgba(110,170,240,0.06)",
        border: "1px solid rgba(110,170,240,0.18)",
      }}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span
          className="font-orbitron text-[10px] uppercase"
          style={{
            color: "var(--accent-blue)",
            letterSpacing: "0.14em",
          }}
        >
          #{String(index + 1).padStart(2, "0")}
        </span>
        {page != null && (
          <Pill icon={<FileText className="h-2.5 w-2.5" />} label={`page ${page}`} />
        )}
        {score != null && (
          <Pill
            label={`score ${score.toFixed(2)}`}
            tone={score >= 0.75 ? "gold" : "muted"}
          />
        )}
        {docTag && (
          <Pill label={`doc ${docTag}`} mono tone="muted" />
        )}
      </div>
      <p
        className={cn(
          "font-exo2 mt-1.5 text-[12px] leading-relaxed",
          !open && "line-clamp-3",
        )}
        style={{ color: "var(--text-primary)" }}
      >
        {text || t("chat.tools_.vector.empty_")}
      </p>
      {text.length > 200 && (
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="font-orbitron mt-1 text-[10px] uppercase"
          style={{
            color: "var(--accent-blue)",
            letterSpacing: "0.14em",
          }}
        >
          {open ? t("chat.tools_.vector.showLess") : t("chat.tools_.vector.showMore")}
        </button>
      )}
    </li>
  );
}

// --- Catalog (simbad/ned/vizier) -------------------------------------------

function CatalogResultsView({ data }: { data: Record<string, unknown> }) {
  const { t } = useT();
  const results = Array.isArray(data.results) ? data.results : [];
  const source = String(data.source ?? "catalog");
  const query = String(data.query ?? "");

  if (results.length === 0)
    return <EmptyState label={t("chat.tools_.catalog.empty", { source })} />;

  const headerLabel = query
    ? t("chat.tools_.catalog.countQuery", {
        n: results.length,
        source,
        query,
      })
    : t(
        results.length === 1
          ? "chat.tools_.catalog.count"
          : "chat.tools_.catalog.countPlural",
        { n: results.length, source },
      );

  return (
    <div className="space-y-2">
      <ResultHeader
        icon={<Telescope className="h-3.5 w-3.5" />}
        label={headerLabel}
      />
      <ul className="space-y-1.5">
        {results.slice(0, 20).map((row, i) => {
          const r = row as {
            name?: string;
            object_type?: string;
            ra_deg?: number | null;
            dec_deg?: number | null;
          };
          return (
            <li
              key={i}
              className="flex flex-wrap items-baseline gap-2 rounded-md px-3 py-1.5"
              style={{
                background: "rgba(77,208,225,0.06)",
                border: "1px solid rgba(77,208,225,0.18)",
              }}
            >
              <span
                className="font-space-mono text-xs"
                style={{ color: "var(--accent-teal)" }}
              >
                {r.name ?? t("chat.tools_.catalog.unnamed")}
              </span>
              {r.object_type && (
                <span
                  className="font-exo2 text-[11px]"
                  style={{ color: "var(--text-secondary)" }}
                >
                  {r.object_type}
                </span>
              )}
              {r.ra_deg != null && r.dec_deg != null && (
                <span
                  className="font-space-mono ml-auto text-[10px] tabular-nums"
                  style={{ color: "var(--text-muted)" }}
                >
                  <MapPin className="mr-0.5 inline h-2.5 w-2.5" />
                  {r.ra_deg.toFixed(3)}°, {r.dec_deg.toFixed(3)}°
                </span>
              )}
            </li>
          );
        })}
      </ul>
      {results.length > 20 && (
        <p
          className="font-exo2 px-1 text-[11px] italic"
          style={{ color: "var(--text-muted)" }}
        >
          + {results.length - 20} more rows
        </p>
      )}
    </div>
  );
}

// --- web_search -------------------------------------------------------------

function WebSearchView({ data }: { data: unknown }) {
  const { t } = useT();
  const items = (Array.isArray(data)
    ? data
    : (isObject(data) && Array.isArray(data.results) ? data.results : [])
  ) as { title?: string; url?: string; snippet?: string }[];

  if (items.length === 0) return <EmptyState label={t("chat.tools_.web.empty")} />;

  return (
    <div className="space-y-2">
      <ResultHeader
        icon={<Globe className="h-3.5 w-3.5" />}
        label={t(
          items.length === 1
            ? "chat.tools_.web.count"
            : "chat.tools_.web.countPlural",
          { n: items.length },
        )}
      />
      <ul className="space-y-1.5">
        {items.slice(0, 10).map((it, i) => (
          <li
            key={i}
            className="rounded-md px-3 py-2"
            style={{
              background: "rgba(110,170,240,0.05)",
              border: "1px solid rgba(110,170,240,0.18)",
            }}
          >
            {it.url ? (
              <a
                href={it.url}
                target="_blank"
                rel="noopener noreferrer"
                className="font-exo2 inline-flex items-center gap-1 text-xs font-medium hover:underline"
                style={{ color: "var(--accent-blue)" }}
              >
                <ExternalLink className="h-3 w-3" />
                {it.title || it.url}
              </a>
            ) : (
              <span className="font-exo2 text-xs font-medium">
                {it.title ?? t("chat.tools_.web.noTitle")}
              </span>
            )}
            {it.snippet && (
              <p
                className="font-exo2 mt-1 text-[11px] leading-relaxed"
                style={{ color: "var(--text-secondary)" }}
              >
                {clamp(it.snippet, 240)}
              </p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

// --- pdf_parser -------------------------------------------------------------

function PdfParserView({ data }: { data: Record<string, unknown> }) {
  const { t } = useT();
  const pageCount = Number(data.page_count ?? 0);
  const pages = Array.isArray(data.pages) ? data.pages : [];
  const fullText = typeof data.full_text === "string" ? data.full_text : "";
  return (
    <div className="space-y-2">
      <ResultHeader
        icon={<FileText className="h-3.5 w-3.5" />}
        label={t("chat.tools_.pdf.header", {
          pages: pageCount,
          extracted: pages.length,
        })}
      />
      {fullText && (
        <details
          className="rounded-md px-3 py-2"
          style={{
            background: "rgba(255,255,255,0.02)",
            border: "1px solid var(--border)",
          }}
        >
          <summary
            className="font-orbitron cursor-pointer text-[10px] uppercase"
            style={{
              color: "var(--text-secondary)",
              letterSpacing: "0.14em",
            }}
          >
            {t("chat.tools_.pdf.showText")}
          </summary>
          <p
            className="font-exo2 mt-2 max-h-60 overflow-auto whitespace-pre-wrap text-[11px] leading-relaxed"
            style={{ color: "var(--text-secondary)" }}
          >
            {clamp(fullText, 8000)}
          </p>
        </details>
      )}
    </div>
  );
}

// --- fits_reader ------------------------------------------------------------

function FitsReaderView({ data }: { data: Record<string, unknown> }) {
  const { t } = useT();
  const items: { label: string; value: string }[] = [];
  if (data.hdu_count != null)
    items.push({ label: t("chat.tools_.fits.hdus"), value: String(data.hdu_count) });
  if (data.hdu_index != null)
    items.push({ label: t("chat.tools_.fits.hduIndex"), value: String(data.hdu_index) });
  if (data.hdu_type)
    items.push({ label: t("chat.tools_.fits.type"), value: String(data.hdu_type) });
  if (data.name)
    items.push({ label: t("chat.tools_.fits.name"), value: String(data.name) });
  if (Array.isArray(data.shape))
    items.push({
      label: t("chat.tools_.fits.shape"),
      value: (data.shape as number[]).join(" × "),
    });
  if (data.n_keywords != null)
    items.push({ label: t("chat.tools_.fits.keywords"), value: String(data.n_keywords) });

  return (
    <div className="space-y-2">
      <ResultHeader
        icon={<Database className="h-3.5 w-3.5" />}
        label={t("chat.tools_.fits.metadata")}
      />
      <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {items.map((it) => (
          <li
            key={it.label}
            className="rounded-md px-3 py-1.5"
            style={{
              background: "rgba(255,255,255,0.02)",
              border: "1px solid var(--border)",
            }}
          >
            <p
              className="font-orbitron text-[9px] uppercase"
              style={{
                color: "var(--text-muted)",
                letterSpacing: "0.16em",
              }}
            >
              {it.label}
            </p>
            <p
              className="font-space-mono mt-0.5 text-xs"
              style={{ color: "var(--text-primary)" }}
            >
              {it.value}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}

// --- run_fits_analysis ------------------------------------------------------

function FitsAnalysisView({ data }: { data: Record<string, unknown> }) {
  const { t } = useT();
  const analysisType = String(data.analysis_type ?? "analysis");
  const statusRaw = String(data.status ?? "");
  const results = (isObject(data.results) ? data.results : {}) as Record<string, unknown>;
  const artifacts = Array.isArray(data.artifacts) ? data.artifacts : [];
  const isError = statusRaw === "failed" || Boolean((data as { error?: unknown }).error);

  return (
    <div className="space-y-2">
      <ResultHeader
        icon={<Telescope className="h-3.5 w-3.5" />}
        label={
          isError
            ? t("chat.tools_.analysis.failed", { type: analysisType })
            : t("chat.tools_.analysis.status", {
                type: analysisType.replace(/_/g, " "),
                status: statusRaw || "done",
              })
        }
      />
      {isError && (
        <p
          className="font-exo2 text-xs"
          style={{ color: "var(--accent-coral)" }}
        >
          {String((data as { error?: unknown }).error ?? "Analysis failed.")}
        </p>
      )}
      <FitsAnalysisBody analysisType={analysisType} results={results} />
      {artifacts.length > 0 && (
        <p
          className="font-space-mono text-[10px] uppercase"
          style={{ color: "var(--text-muted)", letterSpacing: "0.14em" }}
        >
          {t(
            artifacts.length === 1
              ? "chat.tools_.analysis.artifactsOne"
              : "chat.tools_.analysis.artifacts",
            { n: artifacts.length },
          )}
        </p>
      )}
    </div>
  );
}

function FitsAnalysisBody({
  analysisType,
  results,
}: {
  analysisType: string;
  results: Record<string, unknown>;
}) {
  const { t } = useT();
  if (analysisType === "image_stats") {
    return <StatGrid stats={pickNumeric(results, ["min", "max", "mean", "stddev", "median", "n_pixels"])} />;
  }
  if (analysisType === "photometry") {
    const sources = Array.isArray(results.sources) ? results.sources.length : 0;
    const stats = pickNumeric(results, ["zero_point", "fwhm", "background"]);
    return (
      <div className="space-y-2">
        {sources > 0 && (
          <p
            className="font-orbitron text-[11px] uppercase"
            style={{ color: "var(--accent-gold)", letterSpacing: "0.16em" }}
          >
            {t("chat.tools_.analysis.sources", { n: sources })}
          </p>
        )}
        {stats.length > 0 && <StatGrid stats={stats} />}
      </div>
    );
  }
  if (analysisType === "wcs_solve") {
    const wcs = (isObject(results.wcs) ? results.wcs : results) as Record<string, unknown>;
    return (
      <StatGrid
        stats={pickNumeric(wcs, [
          "CRVAL1",
          "CRVAL2",
          "CRPIX1",
          "CRPIX2",
          "CDELT1",
          "CDELT2",
          "CROTA2",
        ])}
      />
    );
  }
  if (analysisType === "spectroscopy") {
    return (
      <StatGrid
        stats={pickNumeric(results, [
          "wavelength_min",
          "wavelength_max",
          "peak_flux",
          "n_lines",
        ])}
      />
    );
  }
  // Unknown analysis type — show top-level scalars as a grid + fall back to JSON for objects.
  const scalars = pickScalars(results, 8);
  return scalars.length > 0 ? <StatGrid stats={scalars} /> : <PrettyJson value={results} />;
}

function StatGrid({
  stats,
}: {
  stats: { label: string; value: string }[];
}) {
  if (stats.length === 0) return null;
  return (
    <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3">
      {stats.map((s) => (
        <li
          key={s.label}
          className="rounded-md px-3 py-1.5"
          style={{
            background: "rgba(255,255,255,0.02)",
            border: "1px solid var(--border)",
          }}
        >
          <p
            className="font-orbitron text-[9px] uppercase"
            style={{ color: "var(--text-muted)", letterSpacing: "0.16em" }}
          >
            {s.label}
          </p>
          <p
            className="font-space-mono mt-0.5 text-xs tabular-nums"
            style={{ color: "var(--text-primary)" }}
          >
            {s.value}
          </p>
        </li>
      ))}
    </ul>
  );
}

function fmtNumber(n: number): string {
  if (!Number.isFinite(n)) return String(n);
  if (Math.abs(n) >= 10_000 || (Math.abs(n) < 0.001 && n !== 0)) return n.toExponential(3);
  return Number(n.toFixed(4)).toString();
}

function pickNumeric(
  obj: Record<string, unknown>,
  keys: string[],
): { label: string; value: string }[] {
  return keys
    .filter((k) => typeof obj[k] === "number")
    .map((k) => ({ label: k, value: fmtNumber(obj[k] as number) }));
}

function pickScalars(
  obj: Record<string, unknown>,
  limit: number,
): { label: string; value: string }[] {
  const out: { label: string; value: string }[] = [];
  for (const [k, v] of Object.entries(obj)) {
    if (out.length >= limit) break;
    if (typeof v === "number") out.push({ label: k, value: fmtNumber(v) });
    else if (typeof v === "string" && v.length < 80) out.push({ label: k, value: v });
    else if (typeof v === "boolean") out.push({ label: k, value: String(v) });
  }
  return out;
}

// --- Generic fallbacks ------------------------------------------------------

function PrettyJson({ value }: { value: unknown }) {
  const { t } = useT();
  const [open, setOpen] = useState(false);
  const text = JSON.stringify(value, null, 2);
  const preview = clamp(text, 240);
  return (
    <div className="space-y-1.5">
      <ResultHeader
        icon={<Database className="h-3.5 w-3.5" />}
        label={
          Array.isArray(value)
            ? t("chat.tools_.json.array", { n: value.length })
            : t("chat.tools_.json.object")
        }
      />
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1 text-[10px] uppercase"
        style={{
          color: "var(--accent-blue)",
          letterSpacing: "0.14em",
        }}
      >
        {open ? (
          <ChevronDown className="h-3 w-3" />
        ) : (
          <ChevronRight className="h-3 w-3" />
        )}
        {open ? t("chat.tools_.hideJson") : t("chat.tools_.showJson")}
      </button>
      <pre
        className="font-space-mono max-h-72 overflow-auto rounded-md px-3 py-2 text-[11px] leading-relaxed"
        style={{
          background: "var(--bg-0)",
          border: "1px solid var(--border)",
          color: "var(--text-secondary)",
        }}
      >
        {open ? text : preview}
      </pre>
    </div>
  );
}

function PlainText({ text }: { text: string }) {
  return (
    <pre
      className="font-space-mono max-h-72 overflow-auto whitespace-pre-wrap rounded-md px-3 py-2 text-[11px] leading-relaxed"
      style={{
        background: "var(--bg-0)",
        border: "1px solid var(--border)",
        color: "var(--text-primary)",
      }}
    >
      {text}
    </pre>
  );
}

// --- Shared bits ------------------------------------------------------------

function ResultHeader({
  icon,
  label,
}: {
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <div className="flex items-center gap-1.5">
      <span style={{ color: "var(--accent-blue)" }}>{icon}</span>
      <span
        className="font-orbitron text-[10px] uppercase"
        style={{
          color: "var(--text-secondary)",
          letterSpacing: "0.16em",
        }}
      >
        {label}
      </span>
    </div>
  );
}

function EmptyState({ label }: { label: string }) {
  return (
    <p
      className="font-exo2 px-1 text-[12px] italic"
      style={{ color: "var(--text-muted)" }}
    >
      {label}
    </p>
  );
}

function Pill({
  icon,
  label,
  tone = "default",
  mono = false,
}: {
  icon?: React.ReactNode;
  label: string;
  tone?: "default" | "gold" | "muted";
  mono?: boolean;
}) {
  const color =
    tone === "gold"
      ? "var(--accent-gold)"
      : tone === "muted"
        ? "var(--text-muted)"
        : "var(--accent-teal)";
  const bg =
    tone === "gold"
      ? "rgba(226,201,126,0.10)"
      : tone === "muted"
        ? "rgba(255,255,255,0.03)"
        : "rgba(77,208,225,0.08)";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] uppercase",
        mono ? "font-space-mono" : "font-orbitron",
      )}
      style={{
        color,
        background: bg,
        letterSpacing: mono ? "0.06em" : "0.14em",
      }}
    >
      {icon}
      {label}
    </span>
  );
}
