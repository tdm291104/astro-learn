"use client";

import Link from "next/link";
import { useMemo } from "react";

import { ROUTES } from "@/lib/constants";
import type { AdminTopUserItem } from "@/types/admin.types";

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

// Bar widths are relative to the heaviest user — no axis labels needed.
export function TopUsersChart({ items }: { items: AdminTopUserItem[] }) {
  const max = useMemo(
    () => Math.max(1, ...items.map((i) => i.total_tokens)),
    [items],
  );

  if (items.length === 0) {
    return (
      <p
        className="font-space-mono py-6 text-center text-xs uppercase"
        style={{ color: "var(--text-muted)", letterSpacing: "0.16em" }}
      >
        {"// no token activity in this window"}
      </p>
    );
  }

  return (
    <ol className="space-y-2">
      {items.map((row, idx) => {
        const ratio = row.total_tokens / max;
        const label = row.full_name?.trim() || row.email.split("@")[0];
        return (
          <li key={row.user_id}>
            <Link
              href={ROUTES.adminUser(row.user_id)}
              className="block rounded-md px-2 py-1.5 transition-colors hover:bg-white/5"
            >
              <div className="flex items-center justify-between gap-3">
                <div className="flex min-w-0 items-center gap-2">
                  <span
                    className="font-space-mono w-5 shrink-0 text-right text-[11px] tabular-nums"
                    style={{ color: "var(--text-muted)" }}
                  >
                    {String(idx + 1).padStart(2, "0")}
                  </span>
                  <span
                    className="font-exo2 truncate text-sm"
                    style={{ color: "var(--text-primary)" }}
                    title={row.email}
                  >
                    {label}
                  </span>
                </div>
                <span
                  className="font-space-mono shrink-0 text-xs tabular-nums"
                  style={{ color: "var(--accent-gold)" }}
                >
                  {formatTokens(row.total_tokens)}
                </span>
              </div>
              <div
                className="mt-1 h-1.5 w-full overflow-hidden rounded-full"
                style={{ background: "rgba(255,255,255,0.06)" }}
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
            </Link>
          </li>
        );
      })}
    </ol>
  );
}
