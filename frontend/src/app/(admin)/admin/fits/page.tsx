"use client";

import { motion } from "framer-motion";
import { Trash2 } from "lucide-react";
import { useState } from "react";

import {
  pageTransition,
  pageTransitionSpec,
} from "@/animations/page-transition";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useAdminFitsFiles, useDeleteAdminFitsFile } from "@/hooks/useAdmin";
import { useDebounce } from "@/hooks/useDebounce";
import { formatBytes, formatRelativeTime } from "@/lib/utils";
import type { AdminFitsFileItem } from "@/types/admin.types";

const PAGE_SIZE = 30;

export default function AdminFitsPage() {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [deleteTarget, setDeleteTarget] = useState<AdminFitsFileItem | null>(
    null,
  );
  const debounced = useDebounce(search, 300);
  const { data, isLoading, error } = useAdminFitsFiles({
    q: debounced || undefined,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  });

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

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
            {"// admin.fits_files"}
          </p>
          <h1
            className="font-orbitron mt-1 text-2xl font-bold uppercase sm:text-3xl"
            style={{ color: "var(--text-primary)", letterSpacing: "0.16em" }}
          >
            All <span style={{ color: "var(--accent-gold)" }}>FITS Files</span>
          </h1>
        </div>
        <Input
          type="search"
          placeholder="Search filename…"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(0);
          }}
          className="cosmic-input w-72"
        />
      </header>

      <section className="grid gap-4 sm:grid-cols-3">
        <SummaryCard
          label="Total Files"
          value={data ? String(data.total) : null}
        />
        <SummaryCard
          label="Storage Used"
          value={data ? formatBytes(data.total_storage_bytes) : null}
          highlight
        />
        <SummaryCard
          label="Avg Size"
          value={
            data && data.total > 0
              ? formatBytes(Math.round(data.total_storage_bytes / data.total))
              : null
          }
        />
      </section>

      {error && (
        <p
          className="font-exo2 text-sm"
          style={{ color: "var(--accent-coral)" }}
        >
          Failed to load FITS files.
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
                <th className="px-5 py-3">Filename</th>
                <th className="px-5 py-3">Owner</th>
                <th className="px-5 py-3">Size</th>
                <th className="px-5 py-3">Status</th>
                <th className="px-5 py-3">Uploaded</th>
                <th className="px-5 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {isLoading && items.length === 0 ? (
                Array.from({ length: 5 }).map((_, i) => (
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
                    {"// no FITS files match"}
                  </td>
                </tr>
              ) : (
                items.map((fits) => (
                  <FitsRow
                    key={fits.id}
                    fits={fits}
                    onDelete={() => setDeleteTarget(fits)}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>

        <Pager
          page={page}
          totalPages={totalPages}
          total={total}
          onChange={setPage}
        />
      </div>

      <DeleteFitsDialog
        target={deleteTarget}
        onClose={() => setDeleteTarget(null)}
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

function FitsRow({
  fits,
  onDelete,
}: {
  fits: AdminFitsFileItem;
  onDelete: () => void;
}) {
  const statusTone =
    fits.status === "parsed"
      ? "rgb(120, 200, 140)"
      : fits.status === "failed"
        ? "var(--accent-coral)"
        : "var(--text-muted)";
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
          {fits.filename}
        </div>
        <div
          className="font-space-mono text-[10px]"
          style={{ color: "var(--text-muted)" }}
        >
          {fits.hdu_count} HDU{fits.hdu_count === 1 ? "" : "s"}
        </div>
      </td>
      <td className="px-5 py-3">
        <span
          className="font-space-mono text-[12px]"
          style={{ color: "var(--text-secondary)" }}
        >
          {fits.owner_email ?? "—"}
        </span>
      </td>
      <td className="px-5 py-3">
        <span
          className="font-space-mono text-[12px] tabular-nums"
          style={{ color: "var(--text-secondary)" }}
        >
          {formatBytes(fits.size_bytes)}
        </span>
      </td>
      <td className="px-5 py-3">
        <Badge
          style={{
            background: "rgba(255,255,255,0.04)",
            color: statusTone,
            border: `1px solid ${statusTone}`,
          }}
        >
          {fits.status}
        </Badge>
      </td>
      <td className="px-5 py-3">
        <span
          className="font-space-mono text-[11px]"
          style={{ color: "var(--text-muted)" }}
        >
          {formatRelativeTime(fits.created_at)}
        </span>
      </td>
      <td className="px-5 py-3">
        <div className="flex justify-end">
          <button
            type="button"
            onClick={onDelete}
            className="cosmic-btn-ghost p-1.5"
            aria-label={`Delete ${fits.filename}`}
            title="Delete"
            style={{ color: "var(--accent-coral)" }}
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </td>
    </tr>
  );
}

function DeleteFitsDialog({
  target,
  onClose,
}: {
  target: AdminFitsFileItem | null;
  onClose: () => void;
}) {
  const del = useDeleteAdminFitsFile();
  if (!target) return null;
  const pending = del.isPending;
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-[440px]">
        <DialogHeader>
          <DialogTitle>
            <span
              className="font-orbitron uppercase"
              style={{ letterSpacing: "0.16em" }}
            >
              Delete FITS File?
            </span>
          </DialogTitle>
          <DialogDescription>
            This permanently removes{" "}
            <span
              className="font-space-mono"
              style={{ color: "var(--text-primary)" }}
            >
              {target.filename}
            </span>{" "}
            along with its analyses and on-disk artefacts. This cannot be
            undone.
          </DialogDescription>
        </DialogHeader>

        <DialogFooter>
          <button
            type="button"
            onClick={onClose}
            disabled={pending}
            className="cosmic-btn-ghost"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={async () => {
              await del.mutateAsync({
                id: target.id,
                filename: target.filename,
              });
              onClose();
            }}
            disabled={pending}
            className="cosmic-btn-primary"
            style={{
              background: "var(--accent-coral)",
              borderColor: "var(--accent-coral)",
            }}
          >
            {pending ? "Deleting..." : "Delete File"}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Pager({
  page,
  totalPages,
  total,
  onChange,
}: {
  page: number;
  totalPages: number;
  total: number;
  onChange: (page: number) => void;
}) {
  return (
    <div
      className="flex flex-wrap items-center justify-between gap-3 border-t px-5 py-3"
      style={{ borderColor: "var(--border)" }}
    >
      <span
        className="font-space-mono text-[11px] uppercase"
        style={{ color: "var(--text-muted)", letterSpacing: "0.14em" }}
      >
        {total === 0
          ? "0 items"
          : `${page * PAGE_SIZE + 1}–${Math.min(
              (page + 1) * PAGE_SIZE,
              total,
            )} of ${total}`}
      </span>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => onChange(Math.max(0, page - 1))}
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
          onClick={() => onChange(page + 1 < totalPages ? page + 1 : page)}
          disabled={page + 1 >= totalPages}
          className="cosmic-btn-ghost px-3 py-1.5 text-xs"
        >
          Next
        </button>
      </div>
    </div>
  );
}
