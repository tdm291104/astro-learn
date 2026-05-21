"use client";

import { X } from "lucide-react";
import { useMemo } from "react";

import { useAstronomyStore } from "@/stores/astronomyStore";
import { useChatStore } from "@/stores/chatStore";
import type { AnalysisType } from "@/types/astronomy.types";

const TYPE_LABEL: Record<AnalysisType, string> = {
  image_stats: "stats",
  photometry: "photometry",
  spectroscopy: "spectro",
  wcs_solve: "wcs",
  custom: "custom",
};

function shortId(id: string): string {
  return id.length > 12 ? `${id.slice(0, 8)}…` : id;
}

function relativeTime(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  if (Number.isNaN(ms)) return "";
  const secs = Math.round(ms / 1000);
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.round(hrs / 24);
  return `${days}d ago`;
}

export function AnalysisHistoryList() {
  const recent = useAstronomyStore((s) => s.recentAnalyses);
  const activeId = useAstronomyStore((s) => s.activeAnalysisId);
  const setActive = useAstronomyStore((s) => s.setActiveAnalysis);
  const removeEntry = useAstronomyStore((s) => s.removeRecentAnalysis);
  // Filter display to current conversation; full MRU stays in astronomyStore.
  const attachedIds = useChatStore((s) => s.attachedFitsFileIds);
  const visible = useMemo(() => {
    const attachedSet = new Set(attachedIds);
    return recent.filter((a) => attachedSet.has(a.fileId));
  }, [recent, attachedIds]);

  if (visible.length === 0) {
    return (
      <div
        className="font-exo2 rounded-2xl border-2 border-dashed p-4 text-center text-xs"
        style={{
          borderColor: "var(--border)",
          color: "var(--text-muted)",
        }}
      >
        No analyses yet — run one to see it here.
      </div>
    );
  }

  return (
    <div className="cosmic-card overflow-hidden">
      <div
        className="border-b px-4 py-3"
        style={{ borderColor: "var(--border)" }}
      >
        <h3
          className="font-orbitron text-sm font-semibold uppercase"
          style={{
            color: "var(--text-primary)",
            letterSpacing: "0.16em",
          }}
        >
          Recent Analyses
        </h3>
        <p
          className="font-exo2 mt-0.5 text-xs"
          style={{ color: "var(--text-muted)" }}
        >
          Cleared on logout — this list is per-session.
        </p>
      </div>
      <ul>
        {visible.map((entry) => {
          const isActive = entry.id === activeId;
          return (
            <li
              key={entry.id}
              className="group relative flex items-stretch"
              style={{
                background: isActive
                  ? "var(--accent-gold-dim)"
                  : "transparent",
                borderBottom: "1px solid var(--border)",
              }}
            >
              <button
                type="button"
                onClick={() => setActive(entry.id)}
                className="flex flex-1 items-center justify-between gap-3 px-4 py-2.5 text-left transition-colors"
                aria-current={isActive ? "true" : undefined}
              >
                <div className="flex min-w-0 items-center gap-2">
                  <span
                    className="font-space-mono shrink-0 rounded-full px-2 py-0.5 text-[10px] uppercase"
                    style={{
                      background: "rgba(79,195,247,0.1)",
                      color: "var(--accent-blue)",
                      border: "1px solid rgba(79,195,247,0.2)",
                      letterSpacing: "0.14em",
                    }}
                  >
                    {TYPE_LABEL[entry.type]}
                  </span>
                  <span
                    className="font-space-mono truncate text-xs"
                    style={{
                      color: isActive
                        ? "var(--accent-gold)"
                        : "var(--text-secondary)",
                    }}
                  >
                    {shortId(entry.id)}
                  </span>
                </div>
                <span
                  className="font-space-mono shrink-0 text-[11px] uppercase"
                  style={{
                    color: "var(--text-muted)",
                    letterSpacing: "0.12em",
                  }}
                >
                  {relativeTime(entry.createdAt)}
                </span>
              </button>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  removeEntry(entry.id);
                }}
                className="flex items-center px-3 opacity-0 transition-opacity hover:opacity-100 group-hover:opacity-70 focus:opacity-100"
                style={{ color: "var(--text-muted)" }}
                aria-label={`Remove analysis ${shortId(entry.id)} from history`}
                title="Remove from history (does not delete the backend run)"
              >
                <X className="size-3.5" />
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
