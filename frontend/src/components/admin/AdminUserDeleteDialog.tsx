"use client";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useDeleteAdminUser } from "@/hooks/useAdmin";
import type { AdminUserListItem } from "@/types/admin.types";

// Delete cascades to notebooks/sessions/agents via ORM relationships.
export function AdminUserDeleteDialog({
  user,
  open,
  onOpenChange,
}: {
  user: AdminUserListItem | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const deleteUser = useDeleteAdminUser();
  if (!user) return null;
  const pending = deleteUser.isPending;

  const handleConfirm = async () => {
    await deleteUser.mutateAsync({ id: user.id, email: user.email });
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[440px]">
        <DialogHeader>
          <DialogTitle>
            <span
              className="font-orbitron uppercase"
              style={{ letterSpacing: "0.16em" }}
            >
              Delete User?
            </span>
          </DialogTitle>
          <DialogDescription>
            This permanently removes{" "}
            <span
              className="font-space-mono"
              style={{ color: "var(--text-primary)" }}
            >
              {user.email}
            </span>{" "}
            along with their notebooks, sessions, and analyses. This cannot be
            undone.
          </DialogDescription>
        </DialogHeader>

        <DialogFooter>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            disabled={pending}
            className="cosmic-btn-ghost"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={pending}
            className="cosmic-btn-primary"
            style={{
              background: "var(--accent-coral)",
              borderColor: "var(--accent-coral)",
            }}
          >
            {pending ? "Deleting..." : "Delete Account"}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
