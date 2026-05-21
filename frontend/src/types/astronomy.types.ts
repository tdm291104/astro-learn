// Mirrors backend/schemas/astronomy_schema.py.
import type { FitsInterpretation } from "@/types/fitsInterpretation";

export type FitsHduSummary = {
  index: number;
  name: string | null;
  type: string; // PrimaryHDU / ImageHDU / BinTableHDU / ...
  shape: number[] | null; // null for table HDUs
  n_keywords: number;
};

export type FitsUploadResponse = {
  file_id: string;
  filename: string;
  size_bytes: number;
  hdu_count: number;
  hdus: FitsHduSummary[];
  primary_headers: Record<string, unknown>;
  // Null for pre-header_summary rows.
  header_summary: Record<string, unknown> | null;
};

export type AnalysisType =
  | "image_stats"
  | "photometry"
  | "spectroscopy"
  | "wcs_solve"
  | "custom";

export type AnalysisStatus = "pending" | "running" | "succeeded" | "failed";

export type AnalyzeRequest = {
  file_id: string;
  hdu_index?: number; // backend default 0
  analysis_type: AnalysisType;
  params?: Record<string, unknown>;
};

export type AnalyzeResponse = {
  analysis_id: string;
  file_id: string;
  analysis_type: AnalysisType;
  status: AnalysisStatus;
  results: Record<string, unknown>;
  // Relative filenames; URL via API_ENDPOINTS.fitsArtifact.
  artifacts: string[];
  // Null when analysis ran outside chat; FE falls back to per-type tiles.
  interpretation: FitsInterpretation | null;
  generated_at: string;
};

export type CatalogSource = "simbad" | "ned" | "vizier";

export type CatalogSearchRequest = {
  query: string;
  source?: CatalogSource; // default "simbad"
  radius_arcsec?: number | null; // 0–3600
  limit?: number; // 1–200, default 20
};

export type CatalogObject = {
  name: string;
  ra_deg: number | null;
  dec_deg: number | null;
  object_type: string | null;
  references: string[];
  extra: Record<string, unknown>;
};

export type CatalogSearchResponse = {
  query: string;
  source: CatalogSource;
  results: CatalogObject[];
  // Null on empty results or commentary LLM failure.
  commentary: string | null;
};

export type ReportFormat = "pdf" | "markdown" | "html";

export type ReportRequest = {
  analysis_id: string;
  title?: string | null;
  format?: ReportFormat; // default "markdown"
  include_plots?: boolean; // default true
};

export type ReportResponse = {
  report_id: string;
  title: string;
  format: ReportFormat;
  url: string; // signed download URL or relative path
  generated_at: string;
};


export type SampleFitsItem = {
  file_id: string;
  display_name: string;
  description: string;
  instrument: string;
  size_mb: number;
  expected_anomalies: number;
  seeded: boolean;
};

export type SampleFitsListResponse = {
  items: SampleFitsItem[];
};

// Mirrors backend ReflexionDataAnalystAgent.final_output.
export type ReflexionAuditOutput = {
  results: { summary?: string; [key: string]: unknown };
  tool_calls: Array<{
    tool: string;
    input: Record<string, unknown>;
    output: Record<string, unknown>;
  }>;
  reflection_rounds: number;
  max_reflections: number;
  symbolic_violations: Array<{
    rule_id: string;
    severity: "info" | "warning" | "error";
    message: string;
    hdu_index: number | null;
  }>;
  consistency_issues: string[];
  artifacts: unknown[];
};
