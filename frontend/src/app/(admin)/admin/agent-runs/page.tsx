"use client";

import { motion } from "framer-motion";
import { useState } from "react";

import {
  pageTransition,
  pageTransitionSpec,
} from "@/animations/page-transition";
import { AdminAgentRunDialog } from "@/components/admin/AdminAgentRunDialog";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useAdminAgentRuns } from "@/hooks/useAdmin";
import { formatRelativeTime } from "@/lib/utils";
import type { AdminAgentRunItem } from "@/types/admin.types";

const PAGE_SIZE = 30;

const STATUS_TONE: Record<string, { bg: string; fg: string; border: string }> = {
  succeeded: {
    bg: "rgba(120, 200, 140, 0.12)",
    fg: "rgb(120, 200, 140)",
    border: "rgba(120, 200, 140, 0.3)",
  },
  failed: {
    bg: "rgba(220, 90, 90, 0.12)",
    fg: "var(--accent-coral)",
    border: "rgba(220, 90, 90, 0.3)",
  },
  running: {
    bg: "rgba(110, 170, 240, 0.12)",
    fg: "rgb(140, 200, 255)",
    border: "rgba(110, 170, 240, 0.3)",
  },
  pending: {
    bg: "rgba(226, 201, 126, 0.10)",
    fg: "var(--accent-gold)",
    border: "rgba(226, 201, 126, 0.3)",
  },
  cancelled: {
    bg: "rgba(255,255,255,0.04)",
    fg: "var(--text-muted)",
    border: "var(--border)",
  },
};

function StatusBadge({ status }: { status: string }) {
  const tone = STATUS_TONE[status] ?? STATUS_TONE.cancelled;
  return (
    <Badge
      style={{
        background: tone.bg,
        color: tone.fg,
        border: `1px solid ${tone.border}`,
      }}
    >
      {status}
    </Badge>
  );
}

export default function AdminAgentRunsPage() {
  const [status, setStatus] = useState<string>("all");
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);

  const { data, isLoading, error } = useAdminAgentRuns({
    status: status === "all" ? undefined : status,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  });

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const counts = data?.status_counts ?? {};

  return (
    <motion.div
      variants={pageTransition}
      initial="initial"
      animate="animate"
      transition={pageTransitionSpec}
      className="space-y-6"
    >
      <header className="space-y-3">
        <p
          className="font-space-mono text-xs uppercase"
          style={{ color: "var(--text-muted)", letterSpacing: "0.2em" }}
        >
          {"// admin.agent_runs"}
        </p>
        <h1
          className="font-orbitron text-2xl font-bold uppercase sm:text-3xl"
          style={{ color: "var(--text-primary)", letterSpacing: "0.16em" }}
        >
          Agent <span style={{ color: "var(--accent-gold)" }}>Runs</span>
        </h1>
      </header>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {(
          ["pending", "running", "succeeded", "failed", "cancelled"] as const
        ).map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => {
              setStatus(s);
              setPage(0);
            }}
            className="cosmic-card cosmic-card-hover p-4 text-left transition-transform"
            style={{
              borderColor:
                status === s ? "var(--accent-gold)" : "var(--border)",
              borderWidth: status === s ? 1 : undefined,
            }}
          >
            <div className="cosmic-stat-label">{s}</div>
            <div
              className="cosmic-stat-value mt-1"
              style={{
                color:
                  STATUS_TONE[s]?.fg ?? "var(--text-primary)",
                fontSize: "1.5rem",
              }}
            >
              {counts[s] ?? 0}
            </div>
          </button>
        ))}
      </section>

      <div className="flex flex-wrap items-center gap-3">
        <Select
          value={status}
          onValueChange={(v) => {
            setStatus(typeof v === "string" ? v : "all");
            setPage(0);
          }}
        >
          <SelectTrigger className="w-44">
            <SelectValue placeholder="All statuses" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="pending">Pending</SelectItem>
            <SelectItem value="running">Running</SelectItem>
            <SelectItem value="succeeded">Succeeded</SelectItem>
            <SelectItem value="failed">Failed</SelectItem>
            <SelectItem value="cancelled">Cancelled</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {error && (
        <p
          className="font-exo2 text-sm"
          style={{ color: "var(--accent-coral)" }}
        >
          Failed to load agent runs.
        </p>
      )}

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
                <th className="px-5 py-3">Agent</th>
                <th className="px-5 py-3">User</th>
                <th className="px-5 py-3">Status</th>
                <th className="px-5 py-3">Duration</th>
                <th className="px-5 py-3">When</th>
              </tr>
            </thead>
            <tbody>
              {isLoading && items.length === 0 ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <tr
                    key={i}
                    style={{ borderBottom: "1px solid var(--border)" }}
                  >
                    <td className="px-5 py-3" colSpan={5}>
                      <Skeleton className="h-6 w-full" />
                    </td>
                  </tr>
                ))
              ) : items.length === 0 ? (
                <tr>
                  <td
                    colSpan={5}
                    className="font-space-mono px-5 py-10 text-center text-xs uppercase"
                    style={{
                      color: "var(--text-muted)",
                      letterSpacing: "0.16em",
                    }}
                  >
                    {"// no runs match"}
                  </td>
                </tr>
              ) : (
                items.map((run) => (
                  <RunRow
                    key={run.id}
                    run={run}
                    onOpen={() => setSelected(run.id)}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>

        <div
          className="flex flex-wrap items-center justify-between gap-3 border-t px-5 py-3"
          style={{ borderColor: "var(--border)" }}
        >
          <span
            className="font-space-mono text-[11px] uppercase"
            style={{ color: "var(--text-muted)", letterSpacing: "0.14em" }}
          >
            {total === 0
              ? "0 runs"
              : `${page * PAGE_SIZE + 1}–${Math.min(
                  (page + 1) * PAGE_SIZE,
                  total,
                )} of ${total}`}
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="cosmic-btn-ghost px-3 py-1.5 text-xs"
            >
              Prev
            </button>
            <span
              className="font-space-mono text-[11px]"
              style={{ color: "var(--text-secondary)" }}
            >
              {page + 1} / {totalPages}
            </span>
            <button
              type="button"
              onClick={() =>
                setPage((p) => (p + 1 < totalPages ? p + 1 : p))
              }
              disabled={page + 1 >= totalPages}
              className="cosmic-btn-ghost px-3 py-1.5 text-xs"
            >
              Next
            </button>
          </div>
        </div>
      </div>

      <AdminAgentRunDialog
        runId={selected}
        open={selected !== null}
        onOpenChange={(open) => !open && setSelected(null)}
      />
    </motion.div>
  );
}

function RunRow({
  run,
  onOpen,
}: {
  run: AdminAgentRunItem;
  onOpen: () => void;
}) {
  return (
    <tr
      style={{ borderBottom: "1px solid var(--border)" }}
      className="cursor-pointer transition-colors hover:bg-white/5"
      onClick={onOpen}
    >
      <td className="px-5 py-3">
        <div
          className="font-exo2 text-sm"
          style={{ color: "var(--text-primary)" }}
        >
          {run.agent_name}
        </div>
        {run.current_step && (
          <div
            className="font-space-mono text-[11px]"
            style={{ color: "var(--text-muted)" }}
          >
            {run.current_step}
          </div>
        )}
      </td>
      <td className="px-5 py-3">
        <span
          className="font-space-mono text-[12px]"
          style={{ color: "var(--text-secondary)" }}
        >
          {run.user_email ?? "—"}
        </span>
      </td>
      <td className="px-5 py-3">
        <StatusBadge status={run.status} />
      </td>
      <td className="px-5 py-3">
        <span
          className="font-space-mono text-[12px] tabular-nums"
          style={{ color: "var(--text-secondary)" }}
        >
          {run.duration_ms !== null
            ? `${(run.duration_ms / 1000).toFixed(2)}s`
            : "—"}
        </span>
      </td>
      <td className="px-5 py-3">
        <span
          className="font-space-mono text-[11px]"
          style={{ color: "var(--text-muted)" }}
        >
          {formatRelativeTime(run.created_at)}
        </span>
      </td>
    </tr>
  );
}
