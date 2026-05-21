"use client";

import { motion } from "framer-motion";
import { useState } from "react";

import {
  pageTransition,
  pageTransitionSpec,
} from "@/animations/page-transition";
import { AdminRedirect } from "@/components/common/AdminRedirect";
import { ModelCostTable } from "@/components/dashboard/ModelCostTable";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useCostBreakdown } from "@/hooks/useCostBreakdown";
import { useT } from "@/hooks/useT";

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

export default function CostsPage() {
  const { t } = useT();
  const [days, setDays] = useState(30);
  const { data, isLoading, error } = useCostBreakdown(days);

  const items = data?.items ?? [];

  return (
    <AdminRedirect>
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
              {t("costs.sessionLabel")}
            </p>
            <h1
              className="font-orbitron mt-1 text-2xl font-bold uppercase sm:text-3xl"
              style={{
                color: "var(--text-primary)",
                letterSpacing: "0.16em",
              }}
            >
              {t("costs.title")
                .split(" ")
                .map((word, i, arr) =>
                  i === arr.length - 1 ? (
                    <span key={i} style={{ color: "var(--accent-gold)" }}>
                      {word}
                    </span>
                  ) : (
                    <span key={i}>{word} </span>
                  ),
                )}
            </h1>
            <p
              className="font-exo2 mt-2 max-w-2xl text-sm"
              style={{ color: "var(--text-secondary)" }}
            >
              {t("costs.description")}
            </p>
          </div>
          <Select
            value={String(days)}
            onValueChange={(v) =>
              setDays(typeof v === "string" ? Number(v) : 30)
            }
          >
            <SelectTrigger className="w-32">
              <SelectValue placeholder={t("costs.period30d")} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="7">{t("costs.period7d")}</SelectItem>
              <SelectItem value="30">{t("costs.period30d")}</SelectItem>
              <SelectItem value="60">{t("costs.period60d")}</SelectItem>
              <SelectItem value="90">{t("costs.period90d")}</SelectItem>
            </SelectContent>
          </Select>
        </header>

        {error && (
          <p
            className="font-exo2 text-sm"
            style={{ color: "var(--accent-coral)" }}
          >
            {t("costs.error")}
          </p>
        )}

        <section className="grid gap-4 sm:grid-cols-3">
          <SummaryCard
            label={t("costs.cards.estimatedCost")}
            value={data ? formatUsd(data.total_cost_usd) : null}
            highlight
          />
          <SummaryCard
            label={t("costs.cards.totalTokens")}
            value={data ? formatTokens(data.total_tokens) : null}
          />
          <SummaryCard
            label={t("costs.cards.modelsUsed")}
            value={data ? String(data.items.length) : null}
          />
        </section>

        <ModelCostTable
          items={items}
          isLoading={isLoading}
          emptyHint={t("costs.tableEmpty")}
        />
      </motion.div>
    </AdminRedirect>
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
