"use client";

import { motion } from "framer-motion";
import { AlertCircle, Download, FileText, Loader2 } from "lucide-react";
import { useState } from "react";

import { fadeIn, fadeTransition } from "@/animations/fade";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAnalysisStatus } from "@/hooks/useAnalysis";
import { useReportMutation } from "@/hooks/useReport";
import { astronomyService } from "@/services/astronomyService";
import type {
  ReportFormat,
  ReportResponse,
} from "@/types/astronomy.types";

const FORMAT_OPTIONS: { value: ReportFormat; label: string }[] = [
  { value: "markdown", label: "Markdown" },
  { value: "html", label: "HTML" },
  { value: "pdf", label: "PDF" },
];

function relativeTime(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  if (Number.isNaN(ms)) return "";
  const secs = Math.round(ms / 1000);
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

export function ReportPanel({ analysisId }: { analysisId: string }) {
  const { data: analysis } = useAnalysisStatus(analysisId);

  const [title, setTitle] = useState("");
  const [format, setFormat] = useState<ReportFormat>("markdown");
  const [includePlots, setIncludePlots] = useState(true);
  const [report, setReport] = useState<ReportResponse | null>(null);

  const mutation = useReportMutation();

  if (!analysis || analysis.status !== "succeeded") {
    return null;
  }

  const handleGenerate = () => {
    mutation.mutate(
      {
        analysis_id: analysisId,
        title: title.trim() ? title.trim() : null,
        format,
        include_plots: includePlots,
      },
      {
        onSuccess: (resp) => setReport(resp),
      },
    );
  };

  const handleReset = () => {
    setReport(null);
    mutation.reset();
  };

  return (
    <div className="cosmic-card p-5">
      <header className="mb-4">
        <h3
          className="font-orbitron text-sm font-semibold uppercase"
          style={{
            color: "var(--text-primary)",
            letterSpacing: "0.16em",
          }}
        >
          Generate Report
        </h3>
        <p
          className="font-exo2 mt-0.5 text-xs"
          style={{ color: "var(--text-secondary)" }}
        >
          Render the analysis as a downloadable document.
        </p>
      </header>

      {report ? (
        <SuccessCard report={report} onAnother={handleReset} />
      ) : (
        <div className="space-y-3">
          <div className="space-y-1">
            <Label htmlFor="report-title" className="cosmic-label">
              Title
            </Label>
            <Input
              id="report-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Analysis Report"
              className="cosmic-input h-9"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label className="cosmic-label">Format</Label>
              <Select
                value={format}
                onValueChange={(v) => setFormat(v as ReportFormat)}
              >
                <SelectTrigger className="cosmic-input h-9 w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {FORMAT_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex items-end">
              <Label
                className="font-exo2 flex cursor-pointer items-center gap-2 text-sm"
                style={{ color: "var(--text-primary)" }}
              >
                <Checkbox
                  checked={includePlots}
                  onCheckedChange={(v) => setIncludePlots(v === true)}
                />
                Include plots
              </Label>
            </div>
          </div>

          <button
            type="button"
            onClick={handleGenerate}
            disabled={mutation.isPending}
            className="cosmic-btn-primary w-full"
          >
            {mutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <FileText className="h-4 w-4" />
            )}
            {mutation.isPending ? "Generating..." : "Generate Report"}
          </button>

          {mutation.isError && (
            <div
              className="rounded-lg p-3"
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
                Report Generation Failed
              </div>
              <p
                className="font-exo2 text-sm"
                style={{ color: "var(--text-primary)" }}
              >
                {mutation.error instanceof Error
                  ? mutation.error.message
                  : "Unknown error"}
              </p>
              <button
                onClick={handleGenerate}
                disabled={mutation.isPending}
                className="cosmic-btn-outline mt-3"
              >
                Try Again
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function SuccessCard({
  report,
  onAnother,
}: {
  report: ReportResponse;
  onAnother: () => void;
}) {
  return (
    <motion.div
      variants={fadeIn}
      initial="initial"
      animate="animate"
      transition={fadeTransition}
      className="space-y-3 rounded-lg p-3"
      style={{
        background: "var(--accent-gold-dim)",
        border: "1px solid rgba(226,201,126,0.3)",
      }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p
            className="font-exo2 truncate text-sm font-medium"
            style={{ color: "var(--text-primary)" }}
          >
            {report.title}
          </p>
          <p
            className="font-space-mono mt-0.5 text-[11px] uppercase"
            style={{
              color: "var(--text-muted)",
              letterSpacing: "0.14em",
            }}
          >
            Generated {relativeTime(report.generated_at)}
          </p>
        </div>
        <span
          className="font-space-mono shrink-0 rounded-full px-2.5 py-0.5 text-[10px] uppercase"
          style={{
            background: "rgba(226,201,126,0.2)",
            color: "var(--accent-gold)",
            border: "1px solid rgba(226,201,126,0.3)",
            letterSpacing: "0.16em",
          }}
        >
          {report.format}
        </span>
      </div>
      <div className="flex flex-wrap gap-2">
        <a
          href={astronomyService.reportDownloadUrl(report.report_id)}
          download
          className="cosmic-btn-primary inline-flex"
          style={{ padding: "0.5rem 1rem" }}
        >
          <Download className="h-3.5 w-3.5" />
          Download
        </a>
        <button onClick={onAnother} className="cosmic-btn-ghost">
          Generate Another
        </button>
      </div>
    </motion.div>
  );
}
