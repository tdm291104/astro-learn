"use client";

import { motion } from "framer-motion";
import { Trash2 } from "lucide-react";
import { useState } from "react";

import {
  pageTransition,
  pageTransitionSpec,
} from "@/animations/page-transition";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useAdminNotebooks, useDeleteAdminNotebook } from "@/hooks/useAdmin";
import { useDebounce } from "@/hooks/useDebounce";
import { formatRelativeTime } from "@/lib/utils";
import type { AdminNotebookItem } from "@/types/admin.types";

const PAGE_SIZE = 30;

export default function AdminNotebooksPage() {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [deleteTarget, setDeleteTarget] = useState<AdminNotebookItem | null>(
    null,
  );
  const debounced = useDebounce(search, 300);
  const { data, isLoading, error } = useAdminNotebooks({
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
            {"// admin.notebooks"}
          </p>
          <h1
            className="font-orbitron mt-1 text-2xl font-bold uppercase sm:text-3xl"
            style={{ color: "var(--text-primary)", letterSpacing: "0.16em" }}
          >
            All <span style={{ color: "var(--accent-gold)" }}>Notebooks</span>
          </h1>
        </div>
        <Input
          type="search"
          placeholder="Search title or description…"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(0);
          }}
          className="cosmic-input w-72"
        />
      </header>

      {error && (
        <p
          className="font-exo2 text-sm"
          style={{ color: "var(--accent-coral)" }}
        >
          Failed to load notebooks.
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
                <th className="px-5 py-3">Notebook</th>
                <th className="px-5 py-3">Owner</th>
                <th className="px-5 py-3">Updated</th>
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
                    <td className="px-5 py-3" colSpan={4}>
                      <Skeleton className="h-6 w-full" />
                    </td>
                  </tr>
                ))
              ) : items.length === 0 ? (
                <tr>
                  <td
                    colSpan={4}
                    className="font-space-mono px-5 py-10 text-center text-xs uppercase"
                    style={{
                      color: "var(--text-muted)",
                      letterSpacing: "0.16em",
                    }}
                  >
                    {"// no notebooks match"}
                  </td>
                </tr>
              ) : (
                items.map((nb) => (
                  <NotebookRow
                    key={nb.id}
                    notebook={nb}
                    onDelete={() => setDeleteTarget(nb)}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>

        <Pager page={page} totalPages={totalPages} total={total} onChange={setPage} />
      </div>

      <DeleteNotebookDialog
        target={deleteTarget}
        onClose={() => setDeleteTarget(null)}
      />
    </motion.div>
  );
}

function NotebookRow({
  notebook,
  onDelete,
}: {
  notebook: AdminNotebookItem;
  onDelete: () => void;
}) {
  return (
    <tr
      style={{ borderBottom: "1px solid var(--border)" }}
      className="transition-colors hover:bg-white/5"
    >
      <td className="px-5 py-3">
        <div
          className="font-exo2 text-sm"
          style={{ color: "var(--text-primary)" }}
        >
          {notebook.title}
          {notebook.is_shared && (
            <Badge
              className="ml-2"
              style={{
                background: "var(--accent-gold-dim)",
                color: "var(--accent-gold)",
                border: "1px solid var(--accent-gold)",
              }}
            >
              shared
            </Badge>
          )}
        </div>
        {notebook.description && (
          <div
            className="font-exo2 mt-0.5 max-w-md truncate text-[11px]"
            style={{ color: "var(--text-muted)" }}
          >
            {notebook.description}
          </div>
        )}
      </td>
      <td className="px-5 py-3">
        <span
          className="font-space-mono text-[12px]"
          style={{ color: "var(--text-secondary)" }}
        >
          {notebook.owner_email ?? "—"}
        </span>
      </td>
      <td className="px-5 py-3">
        <span
          className="font-space-mono text-[11px]"
          style={{ color: "var(--text-muted)" }}
        >
          {formatRelativeTime(notebook.updated_at)}
        </span>
      </td>
      <td className="px-5 py-3">
        <div className="flex justify-end">
          <button
            type="button"
            onClick={onDelete}
            className="cosmic-btn-ghost p-1.5"
            aria-label={`Delete ${notebook.title}`}
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

function DeleteNotebookDialog({
  target,
  onClose,
}: {
  target: AdminNotebookItem | null;
  onClose: () => void;
}) {
  const del = useDeleteAdminNotebook();
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
              Delete Notebook?
            </span>
          </DialogTitle>
          <DialogDescription>
            This permanently removes{" "}
            <span style={{ color: "var(--text-primary)" }}>
              &ldquo;{target.title}&rdquo;
            </span>{" "}
            along with its documents, sessions, and indexed chunks. This
            cannot be undone.
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
              await del.mutateAsync({ id: target.id, title: target.title });
              onClose();
            }}
            disabled={pending}
            className="cosmic-btn-primary"
            style={{
              background: "var(--accent-coral)",
              borderColor: "var(--accent-coral)",
            }}
          >
            {pending ? "Deleting..." : "Delete Notebook"}
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
