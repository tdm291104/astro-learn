"use client";

import { useMemo, useState } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { useTokenUsage } from "@/hooks/useTokenUsage";
import type { DailyUsageItem } from "@/types/auth.types";

// Hand-rolled SVG avoids a charting lib; bars stretch responsively via viewBox.
const CHART_HEIGHT = 160;
const TOP_PADDING = 18;
const BOTTOM_PADDING = 22;
const PLOT_HEIGHT = CHART_HEIGHT - TOP_PADDING - BOTTOM_PADDING;

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function formatDateLabel(iso: string): string {
  // Slice instead of Date parse to avoid timezone bucket drift.
  const parts = iso.split("-");
  if (parts.length !== 3) return iso;
  return `${parts[1]}/${parts[2]}`;
}

export function TokenUsageChart({ days = 30 }: { days?: number }) {
  const { data, isLoading, error } = useTokenUsage(days);

  // Render empty axis on zero-data so first-time users see the chart slot.
  const daily: DailyUsageItem[] = useMemo(() => data?.daily ?? [], [data]);
  const maxValue = useMemo(
    () => Math.max(1, ...daily.map((d) => d.total_tokens)),
    [daily],
  );

  if (isLoading) {
    return (
      <div className="cosmic-card p-5">
        <Header />
        <Skeleton className="mt-4 h-[160px] w-full" />
      </div>
    );
  }
  if (error || !data) {
    return (
      <div className="cosmic-card p-5">
        <Header />
        <p
          className="font-exo2 mt-4 text-xs"
          style={{ color: "var(--accent-coral)" }}
        >
          Failed to load token usage.
        </p>
      </div>
    );
  }

  const totalThisWindow = daily.reduce((sum, d) => sum + d.total_tokens, 0);

  return (
    <div className="cosmic-card p-5">
      <Header
        windowDays={data.window_days}
        windowTotal={totalThisWindow}
        monthTotal={data.month_total.total_tokens}
      />
      <ChartBody
        daily={daily}
        maxValue={maxValue}
      />
      <Legend
        prompt={data.month_total.prompt_tokens}
        completion={data.month_total.completion_tokens}
      />
    </div>
  );
}

function Header({
  windowDays,
  windowTotal,
  monthTotal,
}: {
  windowDays?: number;
  windowTotal?: number;
  monthTotal?: number;
}) {
  return (
    <div className="flex items-start justify-between gap-3">
      <div>
        <p
          className="font-orbitron text-[11px] uppercase"
          style={{
            letterSpacing: "0.16em",
            color: "var(--text-muted)",
          }}
        >
          Token Usage
        </p>
        <p
          className="font-orbitron mt-1 text-2xl font-bold tabular-nums"
          style={{ color: "var(--accent-gold)" }}
        >
          {monthTotal !== undefined ? formatTokens(monthTotal) : "—"}
        </p>
        <p
          className="font-exo2 mt-0.5 text-xs"
          style={{ color: "var(--text-secondary)" }}
        >
          this month
        </p>
      </div>
      {windowDays !== undefined && windowTotal !== undefined && (
        <div className="text-right">
          <p
            className="font-space-mono text-[10px] uppercase"
            style={{
              letterSpacing: "0.16em",
              color: "var(--text-muted)",
            }}
          >
            last {windowDays}d
          </p>
          <p
            className="font-space-mono mt-1 text-sm tabular-nums"
            style={{ color: "var(--text-primary)" }}
          >
            {formatTokens(windowTotal)}
          </p>
        </div>
      )}
    </div>
  );
}

function ChartBody({
  daily,
  maxValue,
}: {
  daily: DailyUsageItem[];
  maxValue: number;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const hovered = hover !== null ? daily[hover] : null;

  // Cap to ~8 ticks to avoid overlap.
  const labelStride = Math.max(1, Math.ceil(daily.length / 8));

  return (
    <div className="mt-4">
      <div
        className="relative w-full"
        style={{ height: `${CHART_HEIGHT}px` }}
        onMouseLeave={() => setHover(null)}
      >
        <svg
          viewBox={`0 0 ${Math.max(daily.length, 1)} ${CHART_HEIGHT}`}
          preserveAspectRatio="none"
          className="absolute inset-0 h-full w-full"
          aria-label="Daily token usage chart"
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
                    x={i + 0.15}
                    y={y}
                    width={0.7}
                    height={Math.max(barHeight, 0.3)}
                    fill={
                      isHover ? "var(--accent-gold)" : "rgba(226,201,126,0.55)"
                    }
                    style={{ transition: "fill 120ms" }}
                  />
                </g>
              );
            })
          )}
        </svg>
        {/* HTML labels survive viewBox stretch (SVG text would skew). */}
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
          className="font-space-mono mt-1 text-[10px] uppercase"
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

function Legend({
  prompt,
  completion,
}: {
  prompt: number;
  completion: number;
}) {
  return (
    <div
      className="mt-4 flex flex-wrap gap-4 border-t pt-3"
      style={{ borderColor: "var(--border)" }}
    >
      <LegendItem label="Prompt" value={prompt} />
      <LegendItem label="Completion" value={completion} />
    </div>
  );
}

function LegendItem({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <p
        className="font-space-mono text-[10px] uppercase"
        style={{
          letterSpacing: "0.16em",
          color: "var(--text-muted)",
        }}
      >
        {label}
      </p>
      <p
        className="font-space-mono mt-0.5 text-sm tabular-nums"
        style={{ color: "var(--text-primary)" }}
      >
        {formatTokens(value)}
      </p>
    </div>
  );
}
