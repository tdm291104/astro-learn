"use client";

import { useMemo } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { useT } from "@/hooks/useT";
import type { ModelUsageItem } from "@/types/auth.types";

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function formatUsd(n: number): string {
  if (n === 0) return "$0.00";
  if (n < 0.01) return "<$0.01";
  return `$${n.toFixed(2)}`;
}

// Shared by /admin/costs and /costs; backend response is identical.
export function ModelCostTable({
  items,
  isLoading,
  emptyHint,
}: {
  items: ModelUsageItem[];
  isLoading: boolean;
  emptyHint: string;
}) {
  const { t } = useT();
  const maxCost = useMemo(
    () => Math.max(0.0001, ...items.map((i) => i.cost_usd)),
    [items],
  );

  return (
    <div className="cosmic-card overflow-hidden">
      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead>
            <tr
              className="font-orbitron text-[10px] uppercase"
              style={{
                color: "var(--text-muted)",
                letterSpacing: "0.18em",
                borderBottom: "1px solid var(--border)",
              }}
            >
              <th className="px-5 py-3">{t("dashboard.table.model")}</th>
              <th className="px-5 py-3">{t("dashboard.table.calls")}</th>
              <th className="px-5 py-3">{t("dashboard.table.prompt")}</th>
              <th className="px-5 py-3">{t("dashboard.table.completion")}</th>
              <th className="px-5 py-3">{t("dashboard.table.total")}</th>
              <th className="px-5 py-3 text-right">{t("dashboard.table.cost")}</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && items.length === 0 ? (
              Array.from({ length: 4 }).map((_, i) => (
                <tr
                  key={i}
                  style={{ borderBottom: "1px solid var(--border)" }}
                >
                  <td className="px-5 py-3" colSpan={6}>
                    <Skeleton className="h-6 w-full" />
                  </td>
                </tr>
              ))
            ) : items.length === 0 ? (
              <tr>
                <td
                  colSpan={6}
                  className="font-space-mono px-5 py-10 text-center text-xs uppercase"
                  style={{
                    color: "var(--text-muted)",
                    letterSpacing: "0.16em",
                  }}
                >
                  {emptyHint}
                </td>
              </tr>
            ) : (
              items.map((row) => (
                <ModelRow key={row.model} row={row} maxCost={maxCost} />
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ModelRow({
  row,
  maxCost,
}: {
  row: ModelUsageItem;
  maxCost: number;
}) {
  const { t } = useT();
  const ratio = row.cost_usd / maxCost;
  const isUnknownPricing = row.total_tokens > 0 && row.cost_usd === 0;
  return (
    <tr
      style={{ borderBottom: "1px solid var(--border)" }}
      className="transition-colors hover:bg-white/5"
    >
      <td className="px-5 py-3">
        <div
          className="font-space-mono text-[12px]"
          style={{ color: "var(--text-primary)" }}
        >
          {row.model}
        </div>
        {isUnknownPricing && (
          <div
            className="font-space-mono text-[10px]"
            style={{ color: "var(--text-muted)" }}
            title={t("dashboard.table.noPricingTitle")}
          >
            {t("dashboard.table.noPricing")}
          </div>
        )}
        <div
          className="mt-1.5 h-1 w-full overflow-hidden rounded-full"
          style={{ background: "rgba(255,255,255,0.04)" }}
        >
          <div
            className="h-full rounded-full"
            style={{
              width: `${Math.max(2, ratio * 100)}%`,
              background:
                "linear-gradient(90deg, var(--accent-blue), var(--accent-gold))",
            }}
          />
        </div>
      </td>
      <td className="px-5 py-3">
        <span
          className="font-space-mono text-[12px] tabular-nums"
          style={{ color: "var(--text-secondary)" }}
        >
          {row.call_count.toLocaleString()}
        </span>
      </td>
      <td className="px-5 py-3">
        <span
          className="font-space-mono text-[12px] tabular-nums"
          style={{ color: "var(--text-secondary)" }}
        >
          {formatTokens(row.prompt_tokens)}
        </span>
      </td>
      <td className="px-5 py-3">
        <span
          className="font-space-mono text-[12px] tabular-nums"
          style={{ color: "var(--text-secondary)" }}
        >
          {formatTokens(row.completion_tokens)}
        </span>
      </td>
      <td className="px-5 py-3">
        <span
          className="font-space-mono text-[12px] tabular-nums"
          style={{ color: "var(--text-primary)" }}
        >
          {formatTokens(row.total_tokens)}
        </span>
      </td>
      <td className="px-5 py-3 text-right">
        <span
          className="font-orbitron text-sm tabular-nums"
          style={{ color: "var(--accent-gold)" }}
        >
          {formatUsd(row.cost_usd)}
        </span>
      </td>
    </tr>
  );
}
