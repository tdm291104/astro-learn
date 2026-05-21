"use client";

import { motion } from "framer-motion";
import { RefreshCw, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { fadeInUp, fadeTransition } from "@/animations/fade";
import { staggerContainer, staggerItem } from "@/animations/stagger";
import { Skeleton } from "@/components/ui/skeleton";
import { Slider } from "@/components/ui/slider";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  useNotebookArtifact,
  useSummarizeMutation,
} from "@/hooks/useNotebookQA";
import { useT } from "@/hooks/useT";
import type {
  SummarizeRequest,
  SummarizeResponse,
  SummarizeStyle,
} from "@/types/notebook.types";

const DEFAULT_BULLETS = 7;
const MIN_BULLETS = 3;
const MAX_BULLETS = 20;

// Narrow artifact.payload (typed unknown) to SummarizeResponse.
function asSummary(payload: unknown): SummarizeResponse | null {
  if (!payload || typeof payload !== "object") return null;
  const p = payload as { summary?: unknown; source_document_count?: unknown };
  if (
    typeof p.summary === "string" ||
    (Array.isArray(p.summary) && p.summary.every((s) => typeof s === "string"))
  ) {
    return {
      summary: p.summary as string | string[],
      source_document_count:
        typeof p.source_document_count === "number"
          ? p.source_document_count
          : 0,
    };
  }
  return null;
}

export function SummaryView({ notebookId }: { notebookId: string }) {
  const [style, setStyle] = useState<SummarizeStyle>("bullets");
  const [maxBullets, setMaxBullets] = useState(DEFAULT_BULLETS);

  // Persisted artifact avoids re-running the LLM on remount.
  const artifactQuery = useNotebookArtifact(notebookId, "summary");
  const summarize = useSummarizeMutation(notebookId);

  // Seed param controls once; ref guards against revalidation overwriting tweaks.
  const seeded = useRef(false);
  useEffect(() => {
    if (seeded.current || artifactQuery.isLoading) return;
    seeded.current = true;
    const params = (artifactQuery.data?.params ?? {}) as {
      style?: SummarizeStyle;
      max_bullets?: number;
    };
    if (params.style) setStyle(params.style);
    if (typeof params.max_bullets === "number") setMaxBullets(params.max_bullets);
  }, [artifactQuery.data, artifactQuery.isLoading]);

  const requestParams: SummarizeRequest =
    style === "bullets"
      ? { style: "bullets", max_bullets: maxBullets }
      : { style: "paragraph" };

  // Prefer fresh mutation result; fall back to persisted artifact.
  const mutationResult = summarize.data;
  const persistedResult = asSummary(artifactQuery.data?.payload);
  const result = mutationResult ?? persistedResult;
  const isPending = summarize.isPending;
  const isLoadingPersisted = artifactQuery.isLoading;

  const handleGenerate = () => {
    if (isPending) return;
    summarize.mutate(requestParams);
  };

  return (
    <div className="space-y-5">
      <Controls
        style={style}
        onStyleChange={setStyle}
        maxBullets={maxBullets}
        onMaxBulletsChange={setMaxBullets}
        onGenerate={handleGenerate}
        isPending={isPending}
        hasResult={Boolean(result)}
      />

      {isPending || isLoadingPersisted ? (
        <SummarySkeleton style={style} />
      ) : result ? (
        <SummaryResult result={result} style={style} />
      ) : (
        <EmptyState />
      )}
    </div>
  );
}

function Controls({
  style,
  onStyleChange,
  maxBullets,
  onMaxBulletsChange,
  onGenerate,
  isPending,
  hasResult,
}: {
  style: SummarizeStyle;
  onStyleChange: (s: SummarizeStyle) => void;
  maxBullets: number;
  onMaxBulletsChange: (n: number) => void;
  onGenerate: () => void;
  isPending: boolean;
  hasResult: boolean;
}) {
  const { t } = useT();
  return (
    <div className="cosmic-card flex flex-col gap-4 p-5 sm:flex-row sm:items-end sm:justify-between">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="space-y-1.5">
          <label className="cosmic-label">{t("notebook.summary_.style")}</label>
          <Tabs
            value={style}
            onValueChange={(v) => onStyleChange(v as SummarizeStyle)}
          >
            <TabsList className="border-0 bg-transparent p-0">
              <TabsTrigger value="bullets" className="cosmic-tab-pill">
                {t("notebook.summary_.styleBullets")}
              </TabsTrigger>
              <TabsTrigger value="paragraph" className="cosmic-tab-pill">
                {t("notebook.summary_.styleParagraph")}
              </TabsTrigger>
            </TabsList>
          </Tabs>
        </div>

        {style === "bullets" && (
          <div className="space-y-1.5 sm:ml-6 sm:w-56">
            <label
              htmlFor="max-bullets"
              className="cosmic-label flex items-center justify-between"
            >
              <span>{t("notebook.summary_.maxBullets")}</span>
              <span
                className="font-space-mono text-xs"
                style={{ color: "var(--accent-gold)" }}
              >
                {maxBullets}
              </span>
            </label>
            <Slider
              id="max-bullets"
              min={MIN_BULLETS}
              max={MAX_BULLETS}
              step={1}
              value={maxBullets}
              onValueChange={(v) =>
                onMaxBulletsChange(typeof v === "number" ? v : v[0])
              }
              aria-label="Maximum bullets"
            />
          </div>
        )}
      </div>

      <button
        onClick={onGenerate}
        disabled={isPending}
        className="cosmic-btn-primary self-start sm:self-auto"
      >
        {hasResult ? (
          <RefreshCw className={`h-4 w-4 ${isPending ? "animate-spin" : ""}`} />
        ) : (
          <Sparkles className="h-4 w-4" />
        )}
        {isPending
          ? t("common.generating")
          : hasResult
            ? t("notebook.summary_.regenerate")
            : t("notebook.summary_.generate")}
      </button>
    </div>
  );
}

function SummaryResult({
  result,
  style,
}: {
  result: SummarizeResponse;
  style: SummarizeStyle;
}) {
  if (style === "bullets") {
    const bullets = Array.isArray(result.summary)
      ? result.summary
      : [result.summary];
    return (
      <div className="space-y-3">
        <SourceCount count={result.source_document_count} />
        <motion.ul
          variants={staggerContainer}
          initial="initial"
          animate="animate"
          className="cosmic-card space-y-3 p-6"
        >
          {bullets.map((b, i) => (
            <motion.li
              key={i}
              variants={staggerItem}
              className="font-exo2 flex gap-3 text-sm leading-relaxed"
              style={{ color: "var(--text-primary)" }}
            >
              <span
                aria-hidden
                className="mt-2 inline-block h-1.5 w-1.5 shrink-0 rounded-full"
                style={{ background: "var(--accent-gold)" }}
              />
              <span>{b}</span>
            </motion.li>
          ))}
        </motion.ul>
      </div>
    );
  }

  const paragraph = Array.isArray(result.summary)
    ? result.summary.join("\n\n")
    : result.summary;

  return (
    <div className="space-y-3">
      <SourceCount count={result.source_document_count} />
      <motion.div
        variants={fadeInUp}
        initial="initial"
        animate="animate"
        transition={fadeTransition}
        className="cosmic-card p-6"
      >
        <p
          className="font-exo2 whitespace-pre-wrap text-sm leading-relaxed"
          style={{ color: "var(--text-primary)" }}
        >
          {paragraph}
        </p>
      </motion.div>
    </div>
  );
}

function SourceCount({ count }: { count: number }) {
  const { t } = useT();
  return (
    <p
      className="font-space-mono text-[11px] uppercase"
      style={{
        color: "var(--text-muted)",
        letterSpacing: "0.16em",
      }}
    >
      {count === 1
        ? t("notebook.summary_.sourceCount", { n: count })
        : t("notebook.summary_.sourceCountPlural", { n: count })}
    </p>
  );
}

function SummarySkeleton({ style }: { style: SummarizeStyle }) {
  const lines = style === "bullets" ? 5 : 3;
  return (
    <div className="cosmic-card space-y-2 p-6">
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className="space-y-1.5">
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-5/6" />
        </div>
      ))}
    </div>
  );
}

function EmptyState() {
  const { t } = useT();
  return (
    <div
      className="flex flex-col items-center gap-3 rounded-2xl border-2 border-dashed p-12 text-center"
      style={{
        borderColor: "rgba(226,201,126,0.18)",
        background: "rgba(226,201,126,0.02)",
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
        ✦
      </div>
      <div className="space-y-1">
        <h3
          className="font-orbitron text-base font-semibold uppercase"
          style={{
            color: "var(--text-primary)",
            letterSpacing: "0.16em",
          }}
        >
          {t("notebook.summary_.empty")}
        </h3>
        <p
          className="font-exo2 text-sm"
          style={{ color: "var(--text-secondary)" }}
        >
          {t("notebook.summary_.emptyHint")}
        </p>
      </div>
    </div>
  );
}
