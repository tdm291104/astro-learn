"use client";

import { motion } from "framer-motion";
import { useState } from "react";

import {
  pageTransition,
  pageTransitionSpec,
} from "@/animations/page-transition";
import { ModelCostTable } from "@/components/dashboard/ModelCostTable";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAdminCostBreakdown } from "@/hooks/useAdmin";

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

export default function AdminCostsPage() {
  const [days, setDays] = useState(30);
  const { data, isLoading, error } = useAdminCostBreakdown(days);

  const items = data?.items ?? [];

  return (
    <motion.div
      variants={pageTransition}
      initial="initial"
      animate="animate"
      transition={pageTransitionSpec}
      className="space-y-6"
    >
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p
            className="font-space-mono text-xs uppercase"
            style={{ color: "var(--text-muted)", letterSpacing: "0.2em" }}
          >
            {"// admin.cost_breakdown"}
          </p>
          <h1
            className="font-orbitron mt-1 text-2xl font-bold uppercase sm:text-3xl"
            style={{ color: "var(--text-primary)", letterSpacing: "0.16em" }}
          >
            LLM <span style={{ color: "var(--accent-gold)" }}>Costs</span>
          </h1>
          <p
            className="font-exo2 mt-2 max-w-2xl text-sm"
            style={{ color: "var(--text-secondary)" }}
          >
            System-wide token usage broken down by model with an estimated
            USD spend. Prices are best-effort lookups against the model
            name LiteLLM reported — unknown models show $0 so the chart
            never overstates.
          </p>
        </div>
        <Select
          value={String(days)}
          onValueChange={(v) =>
            setDays(typeof v === "string" ? Number(v) : 30)
          }
        >
          <SelectTrigger className="w-32">
            <SelectValue placeholder="30 days" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="7">7 days</SelectItem>
            <SelectItem value="30">30 days</SelectItem>
            <SelectItem value="60">60 days</SelectItem>
            <SelectItem value="90">90 days</SelectItem>
          </SelectContent>
        </Select>
      </header>

      {error && (
        <p
          className="font-exo2 text-sm"
          style={{ color: "var(--accent-coral)" }}
        >
          Failed to load cost breakdown.
        </p>
      )}

      <section className="grid gap-4 sm:grid-cols-3">
        <SummaryCard
          label="Estimated Cost"
          value={data ? formatUsd(data.total_cost_usd) : null}
          highlight
        />
        <SummaryCard
          label="Total Tokens"
          value={data ? formatTokens(data.total_tokens) : null}
        />
        <SummaryCard
          label="Models Seen"
          value={data ? String(data.items.length) : null}
        />
      </section>

      <ModelCostTable
        items={items}
        isLoading={isLoading}
        emptyHint="// no LLM activity in this window"
      />
    </motion.div>
  );
}

function SummaryCard({
  label,
  value,
  highlight,
}: {
  label: string;
  value: string | null;
  highlight?: boolean;
}) {
  return (
    <div className="cosmic-card relative overflow-hidden p-5">
      <div className="cosmic-stat-label">{label}</div>
      <div
        className="cosmic-stat-value mt-2"
        style={{
          color: value
            ? highlight
              ? "var(--accent-gold)"
              : undefined
            : "var(--text-muted)",
        }}
      >
        {value ?? "—"}
      </div>
    </div>
  );
}
