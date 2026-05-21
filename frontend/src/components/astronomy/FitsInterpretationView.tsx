"use client";

import { AlertTriangle, ArrowRight, ShieldCheck, Sparkles } from "lucide-react";

import type {
  FitsInterpretation,
  InterpMetric,
  InterpResult,
  ReflexionMeta,
} from "@/types/fitsInterpretation";

// Renders structured FitsInterpretation from FitsAnalystAgent (see docs/api-contracts.md §1).
export function FitsInterpretationView({
  data,
}: {
  data: FitsInterpretation;
}) {
  return (
    <div className="space-y-4">
      <ContextChips context={data.context} />
      {data.reflexion && <ReflexionBadge meta={data.reflexion} />}
      <DecisionBlock decision={data.decision} />
      <div className="space-y-3">
        {data.results.map((result, idx) => (
          <ResultCard key={`${result.type}-${idx}`} result={result} />
        ))}
      </div>
      {data.next_steps.length > 0 && <NextStepsList items={data.next_steps} />}
    </div>
  );
}


// Symbolic critic chip: green when clean, amber/red when violations were flagged.
function ReflexionBadge({ meta }: { meta: ReflexionMeta }) {
  const total = meta.symbolic_violations;
  const clean = total === 0;
  const tone = clean
    ? {
        bg: "rgba(120, 200, 140, 0.12)",
        fg: "rgb(120, 200, 140)",
        border: "rgba(120, 200, 140, 0.35)",
      }
    : meta.error_count > 0
      ? {
          bg: "rgba(220, 90, 90, 0.10)",
          fg: "var(--accent-coral)",
          border: "rgba(220, 90, 90, 0.35)",
        }
      : {
          bg: "var(--accent-gold-dim)",
          fg: "var(--accent-gold)",
          border: "var(--accent-gold)",
        };

  const label = clean
    ? "Reflexion ✓ no issues"
    : `Reflexion · ${total} issue${total === 1 ? "" : "s"}` +
      (meta.error_count > 0 ? ` (${meta.error_count} error)` : "") +
      (meta.warning_count > 0 && meta.error_count === 0
        ? ` (${meta.warning_count} warning${meta.warning_count === 1 ? "" : "s"})`
        : "");

  return (
    <div
      className="font-space-mono inline-flex items-center gap-2 rounded-md px-2.5 py-1 text-[11px] uppercase"
      style={{
        background: tone.bg,
        color: tone.fg,
        border: `1px solid ${tone.border}`,
        letterSpacing: "0.12em",
      }}
      title={
        meta.summary ||
        (clean
          ? "Symbolic FITS checker found no rule violations."
          : `Symbolic checker flagged ${total} rule violation(s).`)
      }
    >
      <ShieldCheck className="h-3 w-3" />
      <span>{label}</span>
      {meta.reflection_rounds > 0 && (
        <span style={{ opacity: 0.7 }}>· {meta.reflection_rounds} round</span>
      )}
    </div>
  );
}


function ContextChips({ context }: { context: FitsInterpretation["context"] }) {
  // Nullable fields drop silently to keep the row compact.
  const chips: Array<{ label: string; value: string }> = [
    { label: "File", value: context.filename },
    { label: "Type", value: context.image_type },
    { label: "Size", value: context.dimensions },
  ];
  if (context.instrument) chips.push({ label: "Instrument", value: context.instrument });
  if (context.filter) chips.push({ label: "Filter", value: context.filter });

  return (
    <div className="flex flex-wrap items-center gap-2">
      {chips.map((c) => (
        <span
          key={c.label}
          className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1"
          style={{
            background: "rgba(255,255,255,0.02)",
            border: "1px solid var(--border)",
          }}
        >
          <span
            className="font-orbitron text-[9px] uppercase"
            style={{
              color: "var(--text-muted)",
              letterSpacing: "0.18em",
            }}
          >
            {c.label}
          </span>
          <span
            className="font-exo2 text-xs"
            style={{ color: "var(--text-primary)" }}
          >
            {c.value}
          </span>
        </span>
      ))}
    </div>
  );
}


function DecisionBlock({
  decision,
}: {
  decision: FitsInterpretation["decision"];
}) {
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
        Analysis Plan
      </div>
      <p
        className="font-exo2 text-sm"
        style={{ color: "var(--text-primary)" }}
      >
        <span className="font-medium">
          {decision.analysis_types.join(", ")}
        </span>
        {" — "}
        <span style={{ color: "var(--text-secondary)" }}>
          {decision.reasoning}
        </span>
      </p>
    </div>
  );
}


function ResultCard({ result }: { result: InterpResult }) {
  return (
    <article
      className="rounded-lg p-4"
      style={{
        background: "rgba(255,255,255,0.02)",
        border: "1px solid var(--border)",
      }}
    >
      <header className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h4
          className="font-orbitron text-xs uppercase"
          style={{
            color: "var(--accent-gold)",
            letterSpacing: "0.18em",
          }}
        >
          {result.type.replace("_", " ")}
        </h4>
      </header>
      <p
        className="font-exo2 mb-3 text-sm font-medium"
        style={{ color: "var(--text-primary)" }}
      >
        {result.headline}
      </p>
      {result.metrics.length > 0 && <MetricGrid metrics={result.metrics} />}
      <p
        className="font-exo2 mt-3 text-sm"
        style={{ color: "var(--text-secondary)" }}
      >
        {result.interpretation}
      </p>
      {result.anomalies.length > 0 && (
        <AnomalyList anomalies={result.anomalies} />
      )}
    </article>
  );
}


function MetricGrid({ metrics }: { metrics: InterpMetric[] }) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3">
      {metrics.map((metric, idx) => (
        <div
          key={`${metric.label}-${idx}`}
          className="rounded-md p-3"
          style={{
            background: "rgba(255,255,255,0.02)",
            border: "1px solid var(--border)",
          }}
          // Browser-native tooltip keeps the tile compact.
          title={metric.interpretation}
        >
          <p
            className="font-space-mono text-[10px] uppercase"
            style={{
              color: "var(--text-muted)",
              letterSpacing: "0.16em",
            }}
          >
            {metric.label}
          </p>
          <p
            className="font-space-mono mt-1 break-words text-sm tabular-nums"
            style={{ color: "var(--accent-gold)" }}
          >
            {metric.value}
          </p>
        </div>
      ))}
    </div>
  );
}


function AnomalyList({ anomalies }: { anomalies: string[] }) {
  return (
    <div
      className="mt-3 rounded-md p-2.5"
      style={{
        background: "rgba(255,112,67,0.08)",
        border: "1px solid rgba(255,112,67,0.25)",
      }}
    >
      <div
        className="cosmic-label flex items-center gap-1.5 mb-1"
        style={{ color: "var(--accent-coral)" }}
      >
        <AlertTriangle className="h-3 w-3" />
        Anomalies
      </div>
      <ul
        className="font-exo2 list-inside list-disc text-xs"
        style={{ color: "var(--text-primary)" }}
      >
        {anomalies.map((a, idx) => (
          <li key={idx}>{a}</li>
        ))}
      </ul>
    </div>
  );
}


function NextStepsList({ items }: { items: string[] }) {
  return (
    <div
      className="rounded-lg p-3"
      style={{
        background: "rgba(255,255,255,0.02)",
        border: "1px solid var(--border)",
      }}
    >
      <div
        className="cosmic-label flex items-center gap-1.5 mb-2"
        style={{ color: "var(--accent-blue)" }}
      >
        <ArrowRight className="h-3 w-3" />
        Next Steps
      </div>
      <ul className="space-y-1.5">
        {items.map((step, idx) => (
          <li
            key={idx}
            className="font-exo2 flex items-start gap-2 text-sm"
            style={{ color: "var(--text-primary)" }}
          >
            <span
              className="mt-1.5 inline-block h-1 w-1 shrink-0 rounded-full"
              style={{ background: "var(--accent-blue)" }}
              aria-hidden
            />
            <span>{step}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
