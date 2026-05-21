"use client";

import { motion } from "framer-motion";
import Link from "next/link";

import {
  pageTransition,
  pageTransitionSpec,
} from "@/animations/page-transition";
import { AdminRedirect } from "@/components/common/AdminRedirect";
import { TokenUsageChart } from "@/components/dashboard/TokenUsageChart";
import { useNotebooksQuery } from "@/hooks/useNotebooks";
import { useT } from "@/hooks/useT";
import { useUserStats } from "@/hooks/useUserStats";
import { ROUTES } from "@/lib/constants";
import { formatRelativeTime } from "@/lib/utils";
import { useAstronomyStore } from "@/stores/astronomyStore";
import { useAuthStore } from "@/stores/authStore";
import type { Notebook } from "@/types/notebook.types";
import type { RecentAnalysis } from "@/stores/astronomyStore";

const ANALYSIS_TYPE_LABEL: Record<RecentAnalysis["type"], string> = {
  image_stats: "image stats",
  photometry: "photometry",
  spectroscopy: "spectroscopy",
  wcs_solve: "WCS solve",
  custom: "custom",
};

export default function DashboardPage() {
  const { t } = useT();
  const userEmail = useAuthStore((s) => s.user?.email);
  const observerLabel = userEmail ? userEmail.split("@")[0] : "Observer";

  const stats = useUserStats();
  const { data: notebooks } = useNotebooksQuery();
  const recentAnalyses = useAstronomyStore((s) => s.recentAnalyses);

  const pad2 = (n: number) => String(n).padStart(2, "0");
  // Em-dash placeholder per-stat so fast queries aren't held back by slow ones.
  const fmt = (n: number, loading: boolean) => (loading ? "—" : pad2(n));

  return (
    <AdminRedirect>
      {/* Negative margins claim full viewport-minus-navbar height. */}
      <motion.div
        variants={pageTransition}
        initial="initial"
        animate="animate"
        transition={pageTransitionSpec}
        className="-mx-4 -my-6 flex flex-col overflow-hidden sm:-mx-6 sm:-my-8 lg:-mx-8 lg:-my-10"
        style={{ height: "calc(100svh - 4rem)" }}
      >
        <header
          className="shrink-0 border-b px-4 py-4 sm:px-6 sm:py-5"
          style={{ borderColor: "var(--border)" }}
        >
          <p
            className="font-space-mono text-[10px] uppercase"
            style={{ color: "var(--text-muted)", letterSpacing: "0.2em" }}
          >
            {t("dashboard.sessionStart")}
          </p>
          <h1
            className="font-orbitron mt-1 text-xl font-bold uppercase sm:text-2xl"
            style={{
              color: "var(--text-primary)",
              letterSpacing: "0.16em",
            }}
          >
            {t("dashboard.welcome")}{" "}
            <span style={{ color: "var(--accent-gold)" }}>{observerLabel}</span>
          </h1>
        </header>

        <div className="grid min-h-0 flex-1 grid-cols-1 gap-0 lg:grid-cols-[2fr_1fr]">
          <section
            className="min-h-0 overflow-y-auto px-4 py-5 sm:px-6 sm:py-6"
            style={{ borderRight: "1px solid var(--border)" }}
          >
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <StatCard
                label={t("dashboard.cards.notebooks")}
                value={fmt(stats.notebooksCount, stats.notebooksLoading)}
                sub={
                  stats.notebooksLoading
                    ? t("common.loading")
                    : t("dashboard.cards.notebooksCount", {
                        n: stats.notebooksCount,
                      })
                }
                icon="📚"
                href={ROUTES.notebooks}
              />
              <StatCard
                label={t("dashboard.cards.documents")}
                value={fmt(stats.documentsCount, stats.documentsLoading)}
                sub={
                  stats.documentsLoading
                    ? t("common.loading")
                    : t("dashboard.cards.documentsCount", {
                        n: stats.documentsCount,
                      })
                }
                icon="📄"
                href={ROUTES.notebooks}
              />
              <StatCard
                label={t("dashboard.cards.fitsAnalyzed")}
                value={fmt(stats.fitsAnalyzedCount, stats.fitsAnalyzedLoading)}
                sub={
                  stats.fitsUploadedLoading
                    ? t("common.loading")
                    : t("dashboard.cards.fitsUploaded", {
                        n: stats.fitsUploadedCount,
                      })
                }
                icon="🔭"
                href={`${ROUTES.chat}?mode=fits`}
              />
              <TokenUsageCard
                tokens={stats.tokens ?? { used: 0, remaining: null }}
                loading={stats.tokensLoading}
              />
            </div>

            <div className="mt-5">
              <TokenUsageChart days={30} />
            </div>
          </section>

          <section className="min-h-0 overflow-y-auto px-4 py-5 sm:px-6 sm:py-6">
            <RecentActivityCard
              analyses={recentAnalyses}
              notebooks={notebooks ?? []}
            />
          </section>
        </div>
      </motion.div>
    </AdminRedirect>
  );
}

function StatCard({
  label,
  value,
  sub,
  icon,
  subMuted,
  href,
}: {
  label: string;
  // Pass "—" while loading; dim styling differentiates from settled state.
  value: string;
  sub?: string;
  icon: string;
  subMuted?: boolean;
  href?: string;
}) {
  const isPlaceholder = value === "—";
  const body = (
    <>
      <span
        aria-hidden
        className="pointer-events-none absolute right-4 top-4 text-2xl opacity-25"
      >
        {icon}
      </span>
      <div className="cosmic-stat-label">{label}</div>
      <div
        className="cosmic-stat-value mt-2"
        style={{
          color: isPlaceholder ? "var(--text-muted)" : undefined,
        }}
      >
        {value}
      </div>
      {sub && (
        <div
          className={
            subMuted
              ? "font-space-mono mt-1 text-[10px] uppercase"
              : "font-exo2 mt-1 text-xs"
          }
          style={{
            color: subMuted ? "var(--text-muted)" : "var(--text-secondary)",
            letterSpacing: subMuted ? "0.16em" : undefined,
          }}
        >
          {sub}
        </div>
      )}
    </>
  );

  const cardClass =
    "cosmic-card cosmic-card-hover relative overflow-hidden p-4";

  if (href) {
    return (
      <Link href={href} className={`${cardClass} block`}>
        {body}
      </Link>
    );
  }
  return <div className={cardClass}>{body}</div>;
}

function TokenUsageCard({
  tokens,
  loading,
}: {
  tokens: { used: number; remaining: number | null };
  loading: boolean;
}) {
  const { t } = useT();
  return (
    <StatCard
      label={t("dashboard.cards.tokens")}
      value={loading ? "—" : tokens.used.toLocaleString()}
      sub={
        loading
          ? t("common.loading")
          : tokens.remaining === null
            ? t("dashboard.tokens.noCap")
            : t("dashboard.tokens.remaining", {
                n: tokens.remaining.toLocaleString(),
              })
      }
      icon="✦"
    />
  );
}

function RecentActivityCard({
  analyses,
  notebooks,
}: {
  analyses: readonly RecentAnalysis[];
  notebooks: readonly Notebook[];
}) {
  const { t } = useT();
  // Chronologically interleave analyses + notebooks.
  type FeedItem = { key: string; text: string; iso: string; ts: number };
  const items: FeedItem[] = [];
  for (const a of analyses) {
    items.push({
      key: `a-${a.id}`,
      text: t("dashboard.activity.ranAnalysis", {
        type: ANALYSIS_TYPE_LABEL[a.type],
      }),
      iso: a.createdAt,
      ts: new Date(a.createdAt).getTime(),
    });
  }
  for (const nb of notebooks) {
    items.push({
      key: `n-${nb.id}`,
      text: t("dashboard.activity.updatedNotebook", { title: nb.title }),
      iso: nb.updated_at,
      ts: new Date(nb.updated_at).getTime(),
    });
  }
  items.sort((a, b) => b.ts - a.ts);

  return (
    <div className="cosmic-card">
      <div
        className="sticky top-0 z-10 border-b px-5 py-3"
        style={{
          background: "var(--bg-1)",
          borderColor: "var(--border)",
        }}
      >
        <h3
          className="font-orbitron text-xs font-semibold uppercase"
          style={{ color: "var(--accent-gold)", letterSpacing: "0.2em" }}
        >
          {t("dashboard.activity.title")}
        </h3>
      </div>
      <div className="px-5 py-3">
        {items.length === 0 ? (
          <p
            className="font-space-mono py-4 text-center text-xs uppercase"
            style={{ color: "var(--text-muted)", letterSpacing: "0.16em" }}
          >
            {t("dashboard.activity.empty")}
          </p>
        ) : (
          <ul>
            {items.map((it, i) => (
              <li
                key={it.key}
                className="flex items-start gap-3 py-2.5"
                style={{
                  borderBottom:
                    i < items.length - 1
                      ? "1px solid var(--border)"
                      : undefined,
                }}
              >
                <span
                  className="mt-1.5 inline-block h-2 w-2 shrink-0 rounded-full"
                  style={{ background: "var(--accent-blue)" }}
                  aria-hidden
                />
                <div className="min-w-0 flex-1">
                  <div
                    className="font-exo2 truncate text-sm"
                    style={{ color: "var(--text-primary)" }}
                  >
                    {it.text}
                  </div>
                  <div
                    className="font-space-mono mt-0.5 text-[11px] uppercase"
                    style={{
                      color: "var(--text-muted)",
                      letterSpacing: "0.14em",
                    }}
                  >
                    {formatRelativeTime(it.iso)}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
