// FE mirror of backend/schemas/fits_interpretation_schema.py; see docs/api-contracts.md §1.

export type InterpResultType =
  | "image_stats"
  | "photometry"
  | "spectroscopy"
  | "wcs"
  | "custom";

export type InterpMetric = {
  label: string; // human-readable, never an internal name.
  value: string; // formatted with units.
  interpretation: string; // one-sentence astronomical meaning.
};

export type InterpResult = {
  type: InterpResultType;
  headline: string;
  metrics: InterpMetric[];
  interpretation: string;
  anomalies: string[];
};

export type InterpContext = {
  filename: string; // never the UUID file_id.
  image_type: string;
  dimensions: string; // e.g. "1024 × 1024 px".
  instrument: string | null;
  filter: string | null;
};

export type InterpDecision = {
  analysis_types: string[];
  reasoning: string;
};

// Mirror of ReflexionMeta; drives the "Reflexion N issues" badge.
export type ReflexionMeta = {
  symbolic_violations: number;
  reflection_rounds: number;
  error_count: number;
  warning_count: number;
  summary: string;
};

export type FitsInterpretation = {
  context: InterpContext;
  decision: InterpDecision;
  results: InterpResult[];
  next_steps: string[];
  // Optional for backward compat with pre-reflexion rows.
  reflexion?: ReflexionMeta | null;
};

// Structural narrowing only; contract rules are BE-side.
export function isFitsInterpretation(value: unknown): value is FitsInterpretation {
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  return (
    isObject(v.context) &&
    typeof (v.context as Record<string, unknown>).filename === "string" &&
    isObject(v.decision) &&
    Array.isArray((v.decision as Record<string, unknown>).analysis_types) &&
    Array.isArray(v.results) &&
    Array.isArray(v.next_steps)
  );
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
