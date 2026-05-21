"use client";

import { motion } from "framer-motion";

import {
  pageTransition,
  pageTransitionSpec,
} from "@/animations/page-transition";
import { AdminUsageChart } from "@/components/admin/AdminUsageChart";
import { TopUsersChart } from "@/components/admin/TopUsersChart";
import { Skeleton } from "@/components/ui/skeleton";
import { useAdminOverview } from "@/hooks/useAdmin";

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

export default function AdminOverviewPage() {
  const { data, isLoading, error } = useAdminOverview(30);

  return (
    <motion.div
      variants={pageTransition}
      initial="initial"
      animate="animate"
      transition={pageTransitionSpec}
      className="space-y-10"
    >
      <header className="space-y-3">
        <p
          className="font-space-mono text-xs uppercase"
          style={{ color: "var(--text-muted)", letterSpacing: "0.2em" }}
        >
          {"// admin.console"}
        </p>
        <h1
          className="font-orbitron text-2xl font-bold uppercase sm:text-3xl lg:text-4xl"
          style={{ color: "var(--text-primary)", letterSpacing: "0.16em" }}
        >
          System <span style={{ color: "var(--accent-gold)" }}>Overview</span>
        </h1>
        <p
          className="font-exo2 max-w-2xl text-sm md:text-base"
          style={{ color: "var(--text-secondary)" }}
        >
          User population, recent activity, and system-wide LLM token
          consumption over the last 30 days.
        </p>
      </header>

      {error && (
        <p
          className="font-exo2 text-sm"
          style={{ color: "var(--accent-coral)" }}
        >
          Failed to load admin overview.
        </p>
      )}

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Total Users"
          value={data ? String(data.total_users) : null}
          sub={data ? `${data.active_users} active` : null}
          icon="◉"
        />
        <StatCard
          label="Admins"
          value={data ? String(data.admin_users) : null}
          sub={data ? "with management access" : null}
          icon="✦"
        />
        <StatCard
          label="Active (30d)"
          value={data ? String(data.users_active_in_window) : null}
          sub={data ? "used the LLM in window" : null}
          icon="◈"
        />
        <StatCard
          label="New (30d)"
          value={data ? String(data.new_users_in_window) : null}
          sub={data ? "accounts registered" : null}
          icon="+"
        />
      </section>

      <section className="grid gap-6 lg:grid-cols-3">
        <div className="cosmic-card p-5 lg:col-span-2">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p
                className="font-orbitron text-[11px] uppercase"
                style={{
                  letterSpacing: "0.16em",
                  color: "var(--text-muted)",
                }}
              >
                Token Usage · system-wide
              </p>
              <p
                className="font-orbitron mt-1 text-2xl font-bold tabular-nums"
                style={{ color: "var(--accent-gold)" }}
              >
                {data ? formatTokens(data.month_total.total_tokens) : "—"}
              </p>
              <p
                className="font-exo2 mt-0.5 text-xs"
                style={{ color: "var(--text-secondary)" }}
              >
                this month
              </p>
            </div>
            {data && (
              <div className="text-right">
                <p
                  className="font-space-mono text-[10px] uppercase"
                  style={{
                    letterSpacing: "0.16em",
                    color: "var(--text-muted)",
                  }}
                >
                  prompt / completion
                </p>
                <p
                  className="font-space-mono mt-1 text-sm tabular-nums"
                  style={{ color: "var(--text-primary)" }}
                >
                  {formatTokens(data.month_total.prompt_tokens)} /{" "}
                  {formatTokens(data.month_total.completion_tokens)}
                </p>
              </div>
            )}
          </div>
          <div className="mt-4">
            {isLoading || !data ? (
              <Skeleton className="h-[200px] w-full" />
            ) : (
              <AdminUsageChart daily={data.daily} />
            )}
          </div>
        </div>

        <div className="cosmic-card p-5">
          <p
            className="font-orbitron text-[11px] uppercase"
            style={{
              letterSpacing: "0.16em",
              color: "var(--text-muted)",
            }}
          >
            Top Users · {data?.window_days ?? 30}d
          </p>
          <div className="mt-3">
            {isLoading || !data ? (
              <div className="space-y-2">
                {Array.from({ length: 6 }).map((_, i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            ) : (
              <TopUsersChart items={data.top_users} />
            )}
          </div>
        </div>
      </section>
    </motion.div>
  );
}

function StatCard({
  label,
  value,
  sub,
  icon,
}: {
  label: string;
  value: string | null;
  sub: string | null;
  icon: string;
}) {
  return (
    <div className="cosmic-card cosmic-card-hover relative overflow-hidden p-5">
      <span
        aria-hidden
        className="pointer-events-none absolute right-4 top-4 text-2xl opacity-25"
      >
        {icon}
      </span>
      <div className="cosmic-stat-label">{label}</div>
      <div
        className="cosmic-stat-value mt-2"
        style={{ color: value ? undefined : "var(--text-muted)" }}
      >
        {value ?? "—"}
      </div>
      {sub && (
        <div
          className="font-exo2 mt-1 text-xs"
          style={{ color: "var(--text-secondary)" }}
        >
          {sub}
        </div>
      )}
    </div>
  );
}
