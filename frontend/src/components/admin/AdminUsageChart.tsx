"use client";

import { useMemo, useState } from "react";

import type { DailyUsageItem } from "@/types/auth.types";

// Hand-rolled SVG to avoid a charting lib for a single bar series.
const CHART_HEIGHT = 200;
const TOP_PADDING = 20;
const BOTTOM_PADDING = 24;
const PLOT_HEIGHT = CHART_HEIGHT - TOP_PADDING - BOTTOM_PADDING;

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function formatDateLabel(iso: string): string {
  const parts = iso.split("-");
  if (parts.length !== 3) return iso;
  return `${parts[1]}/${parts[2]}`;
}

export function AdminUsageChart({ daily }: { daily: DailyUsageItem[] }) {
  const maxValue = useMemo(
    () => Math.max(1, ...daily.map((d) => d.total_tokens)),
    [daily],
  );
  const [hover, setHover] = useState<number | null>(null);
  const hovered = hover !== null ? daily[hover] : null;
  const labelStride = Math.max(1, Math.ceil(daily.length / 10));

  return (
    <div>
      <div
        className="relative w-full"
        style={{ height: `${CHART_HEIGHT}px` }}
        onMouseLeave={() => setHover(null)}
      >
        <svg
          viewBox={`0 0 ${Math.max(daily.length, 1)} ${CHART_HEIGHT}`}
          preserveAspectRatio="none"
          className="absolute inset-0 h-full w-full"
          aria-label="System-wide daily token usage"
        >
          {daily.length === 0 ? (
            <text
              x={0.5}
              y={CHART_HEIGHT / 2}
              textAnchor="middle"
              fontSize="8"
              fill="var(--text-muted)"
            >
              No data
            </text>
          ) : (
            daily.map((d, i) => {
              const ratio = d.total_tokens / maxValue;
              const barHeight = ratio * PLOT_HEIGHT;
              const y = TOP_PADDING + (PLOT_HEIGHT - barHeight);
              const isHover = i === hover;
              return (
                <g key={d.date}>
                  <rect
                    x={i}
                    y={0}
                    width={1}
                    height={CHART_HEIGHT}
                    fill="transparent"
                    onMouseEnter={() => setHover(i)}
                    style={{ cursor: "pointer" }}
                  />
                  <rect
                    x={i + 0.12}
                    y={y}
                    width={0.76}
                    height={Math.max(barHeight, 0.3)}
                    fill={
                      isHover ? "var(--accent-gold)" : "rgba(140,180,240,0.55)"
                    }
                    style={{ transition: "fill 120ms" }}
                  />
                </g>
              );
            })
          )}
        </svg>
        <div className="pointer-events-none absolute inset-x-0 bottom-0 flex h-5 w-full">
          {daily.map((d, i) => {
            const showLabel = i % labelStride === 0 || i === daily.length - 1;
            if (!showLabel) return <div key={d.date} className="flex-1" />;
            return (
              <div
                key={d.date}
                className="font-space-mono flex-1 text-center"
                style={{
                  fontSize: "10px",
                  color: "var(--text-muted)",
                  letterSpacing: "0.08em",
                }}
              >
                {formatDateLabel(d.date)}
              </div>
            );
          })}
        </div>
      </div>
      {hovered && (
        <p
          className="font-space-mono mt-2 text-[10px] uppercase"
          style={{
            letterSpacing: "0.12em",
            color: "var(--text-secondary)",
          }}
        >
          {formatDateLabel(hovered.date)} — {formatTokens(hovered.total_tokens)}{" "}
          tokens · prompt {formatTokens(hovered.prompt_tokens)} · completion{" "}
          {formatTokens(hovered.completion_tokens)}
        </p>
      )}
    </div>
  );
}
