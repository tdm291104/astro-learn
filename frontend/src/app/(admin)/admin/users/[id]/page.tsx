"use client";

import { motion } from "framer-motion";
import { ArrowLeft, Pencil, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import {
  pageTransition,
  pageTransitionSpec,
} from "@/animations/page-transition";
import { AdminUsageChart } from "@/components/admin/AdminUsageChart";
import { AdminUserDeleteDialog } from "@/components/admin/AdminUserDeleteDialog";
import { AdminUserEditDialog } from "@/components/admin/AdminUserEditDialog";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useAdminUserDetail } from "@/hooks/useAdmin";
import { ROUTES } from "@/lib/constants";
import { formatRelativeTime } from "@/lib/utils";
import type { AdminUserListItem } from "@/types/admin.types";

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

export default function AdminUserDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params.id;
  const { data, isLoading, error } = useAdminUserDetail(id, 30);
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const editTarget: AdminUserListItem | null = data
    ? {
        id: data.user.id,
        email: data.user.email,
        full_name: data.user.full_name,
        is_active: data.user.is_active,
        is_admin: data.user.is_admin,
        created_at: data.user.created_at,
      }
    : null;

  return (
    <motion.div
      variants={pageTransition}
      initial="initial"
      animate="animate"
      transition={pageTransitionSpec}
      className="space-y-8"
    >
      <Link
        href={ROUTES.adminUsers}
        className="font-space-mono inline-flex items-center gap-1 text-xs uppercase"
        style={{ color: "var(--text-muted)", letterSpacing: "0.14em" }}
      >
        <ArrowLeft className="h-3 w-3" />
        Back to users
      </Link>

      {error && (
        <p
          className="font-exo2 text-sm"
          style={{ color: "var(--accent-coral)" }}
        >
          Failed to load user.
        </p>
      )}

      {isLoading || !data ? (
        <Skeleton className="h-24 w-full" />
      ) : (
        <header className="cosmic-card p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h1
                className="font-orbitron text-2xl font-bold uppercase sm:text-3xl"
                style={{
                  color: "var(--text-primary)",
                  letterSpacing: "0.14em",
                }}
              >
                {data.user.full_name?.trim() ||
                  data.user.email.split("@")[0]}
              </h1>
              <p
                className="font-space-mono mt-1 text-xs"
                style={{ color: "var(--text-muted)" }}
              >
                {data.user.email}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {data.user.is_active ? (
                  <Badge
                    style={{
                      background: "rgba(120, 200, 140, 0.12)",
                      color: "rgb(120, 200, 140)",
                      border: "1px solid rgba(120, 200, 140, 0.3)",
                    }}
                  >
                    Active
                  </Badge>
                ) : (
                  <Badge
                    style={{
                      background: "rgba(220, 90, 90, 0.12)",
                      color: "var(--accent-coral)",
                      border: "1px solid rgba(220, 90, 90, 0.3)",
                    }}
                  >
                    Inactive
                  </Badge>
                )}
                {data.user.is_admin && (
                  <Badge
                    style={{
                      background: "var(--accent-gold-dim)",
                      color: "var(--accent-gold)",
                      border: "1px solid var(--accent-gold)",
                    }}
                  >
                    Admin
                  </Badge>
                )}
                <Badge
                  style={{
                    background: "rgba(255,255,255,0.04)",
                    color: "var(--text-secondary)",
                    border: "1px solid var(--border)",
                  }}
                >
                  Joined {formatRelativeTime(data.user.created_at)}
                </Badge>
              </div>
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setEditOpen(true)}
                className="cosmic-btn-ghost px-3 py-2 text-xs"
              >
                <Pencil className="mr-1 inline h-3.5 w-3.5" />
                Edit
              </button>
              <button
                type="button"
                onClick={() => setDeleteOpen(true)}
                className="cosmic-btn-ghost px-3 py-2 text-xs"
                style={{ color: "var(--accent-coral)" }}
              >
                <Trash2 className="mr-1 inline h-3.5 w-3.5" />
                Delete
              </button>
            </div>
          </div>
        </header>
      )}

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Notebooks"
          value={data ? String(data.notebooks_count) : null}
          icon="📚"
        />
        <StatCard
          label="Documents"
          value={data ? String(data.documents_count) : null}
          icon="📄"
        />
        <StatCard
          label="FITS Files"
          value={data ? String(data.fits_files_count) : null}
          icon="🔭"
        />
        <StatCard
          label="Analyses"
          value={data ? String(data.analyses_count) : null}
          icon="✦"
        />
      </section>

      <section className="cosmic-card p-5">
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
      </section>

      <AdminUserEditDialog
        user={editTarget}
        open={editOpen}
        onOpenChange={setEditOpen}
      />
      <AdminUserDeleteDialog
        user={editTarget}
        open={deleteOpen}
        onOpenChange={(open) => {
          setDeleteOpen(open);
          if (!open) {
            // Row is gone after delete; bounce to the list.
            router.push(ROUTES.adminUsers);
          }
        }}
      />
    </motion.div>
  );
}

function StatCard({
  label,
  value,
  icon,
}: {
  label: string;
  value: string | null;
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
    </div>
  );
}
