"use client";

import { motion } from "framer-motion";
import { Pencil, Trash2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import {
  pageTransition,
  pageTransitionSpec,
} from "@/animations/page-transition";
import { AdminUserDeleteDialog } from "@/components/admin/AdminUserDeleteDialog";
import { AdminUserEditDialog } from "@/components/admin/AdminUserEditDialog";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useAdminUserList } from "@/hooks/useAdmin";
import { useDebounce } from "@/hooks/useDebounce";
import { ROUTES } from "@/lib/constants";
import { formatRelativeTime } from "@/lib/utils";
import type { AdminUserListItem } from "@/types/admin.types";

const PAGE_SIZE = 25;

type StatusFilter = "all" | "active" | "inactive" | "admin";

function toIsActive(filter: StatusFilter): boolean | undefined {
  if (filter === "active") return true;
  if (filter === "inactive") return false;
  return undefined;
}

function toIsAdmin(filter: StatusFilter): boolean | undefined {
  if (filter === "admin") return true;
  return undefined;
}

export default function AdminUsersPage() {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [page, setPage] = useState(0);
  const debouncedSearch = useDebounce(search, 300);

  const { data, isLoading, error } = useAdminUserList({
    q: debouncedSearch || undefined,
    is_active: toIsActive(statusFilter),
    is_admin: toIsAdmin(statusFilter),
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  });

  const [editTarget, setEditTarget] = useState<AdminUserListItem | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<AdminUserListItem | null>(
    null,
  );

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
            {"// admin.users"}
          </p>
          <h1
            className="font-orbitron mt-1 text-2xl font-bold uppercase sm:text-3xl"
            style={{ color: "var(--text-primary)", letterSpacing: "0.16em" }}
          >
            User <span style={{ color: "var(--accent-gold)" }}>Management</span>
          </h1>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Input
            type="search"
            placeholder="Search email or name…"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(0);
            }}
            className="cosmic-input w-64"
          />
          <Select
            value={statusFilter}
            onValueChange={(v) => {
              setStatusFilter(v as StatusFilter);
              setPage(0);
            }}
          >
            <SelectTrigger className="w-40">
              <SelectValue placeholder="All users" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All users</SelectItem>
              <SelectItem value="active">Active only</SelectItem>
              <SelectItem value="inactive">Inactive only</SelectItem>
              <SelectItem value="admin">Admins only</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </header>

      {error && (
        <p
          className="font-exo2 text-sm"
          style={{ color: "var(--accent-coral)" }}
        >
          Failed to load users.
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
                <th className="px-5 py-3">User</th>
                <th className="px-5 py-3">Status</th>
                <th className="px-5 py-3">Role</th>
                <th className="px-5 py-3">Joined</th>
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
                    {"// no users match"}
                  </td>
                </tr>
              ) : (
                items.map((user) => (
                  <UserRow
                    key={user.id}
                    user={user}
                    onEdit={() => setEditTarget(user)}
                    onDelete={() => setDeleteTarget(user)}
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
              ? "0 users"
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

      <AdminUserEditDialog
        user={editTarget}
        open={editTarget !== null}
        onOpenChange={(open) => !open && setEditTarget(null)}
      />
      <AdminUserDeleteDialog
        user={deleteTarget}
        open={deleteTarget !== null}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
      />
    </motion.div>
  );
}

function UserRow({
  user,
  onEdit,
  onDelete,
}: {
  user: AdminUserListItem;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const handle = user.email.split("@")[0];
  const displayName = user.full_name?.trim() || handle;
  return (
    <tr
      style={{ borderBottom: "1px solid var(--border)" }}
      className="transition-colors hover:bg-white/5"
    >
      <td className="px-5 py-3">
        <Link
          href={ROUTES.adminUser(user.id)}
          className="block min-w-0"
        >
          <div
            className="font-exo2 truncate text-sm"
            style={{ color: "var(--text-primary)" }}
          >
            {displayName}
          </div>
          <div
            className="font-space-mono truncate text-[11px]"
            style={{ color: "var(--text-muted)" }}
          >
            {user.email}
          </div>
        </Link>
      </td>
      <td className="px-5 py-3">
        {user.is_active ? (
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
      </td>
      <td className="px-5 py-3">
        {user.is_admin ? (
          <Badge
            style={{
              background: "var(--accent-gold-dim)",
              color: "var(--accent-gold)",
              border: "1px solid var(--accent-gold)",
            }}
          >
            Admin
          </Badge>
        ) : (
          <span
            className="font-space-mono text-[11px]"
            style={{ color: "var(--text-muted)" }}
          >
            user
          </span>
        )}
      </td>
      <td className="px-5 py-3">
        <span
          className="font-space-mono text-[11px]"
          style={{ color: "var(--text-secondary)" }}
        >
          {formatRelativeTime(user.created_at)}
        </span>
      </td>
      <td className="px-5 py-3">
        <div className="flex justify-end gap-1">
          <button
            type="button"
            onClick={onEdit}
            className="cosmic-btn-ghost p-1.5"
            aria-label={`Edit ${user.email}`}
            title="Edit"
          >
            <Pencil className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={onDelete}
            className="cosmic-btn-ghost p-1.5"
            aria-label={`Delete ${user.email}`}
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
