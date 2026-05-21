"use client";

import { useEffect, useState } from "react";

import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useUpdateAdminUser } from "@/hooks/useAdmin";
import { useAuthStore } from "@/stores/authStore";
import type { AdminUserListItem } from "@/types/admin.types";

export function AdminUserEditDialog({
  user,
  open,
  onOpenChange,
}: {
  user: AdminUserListItem | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const updateUser = useUpdateAdminUser();
  const currentUserId = useAuthStore((s) => s.user?.id);
  const isSelf = user?.id === currentUserId;

  const [fullName, setFullName] = useState("");
  const [isActive, setIsActive] = useState(true);
  const [isAdmin, setIsAdmin] = useState(false);

  // Re-seed form on user change so prior edits don't bleed across dialogs.
  useEffect(() => {
    if (!user) return;
    setFullName(user.full_name ?? "");
    setIsActive(user.is_active);
    setIsAdmin(user.is_admin);
  }, [user]);

  if (!user) return null;

  const pending = updateUser.isPending;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await updateUser.mutateAsync({
      id: user.id,
      payload: {
        full_name: fullName,
        is_active: isActive,
        is_admin: isAdmin,
      },
    });
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>
            <span
              className="font-orbitron uppercase"
              style={{ letterSpacing: "0.16em" }}
            >
              Edit User
            </span>
          </DialogTitle>
          <DialogDescription>
            <span
              className="font-space-mono text-xs"
              style={{ color: "var(--text-muted)" }}
            >
              {user.email}
            </span>
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor="admin-edit-name" className="cosmic-label">
              Full Name
            </Label>
            <Input
              id="admin-edit-name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="cosmic-input"
              placeholder="(blank to clear)"
            />
          </div>

          <div className="flex items-start gap-3">
            <Checkbox
              id="admin-edit-active"
              checked={isActive}
              onCheckedChange={(v) => setIsActive(Boolean(v))}
              disabled={isSelf}
            />
            <div>
              <Label
                htmlFor="admin-edit-active"
                className="font-exo2 cursor-pointer text-sm"
              >
                Active
              </Label>
              <p
                className="font-exo2 text-xs"
                style={{ color: "var(--text-muted)" }}
              >
                {isSelf
                  ? "You cannot deactivate your own account."
                  : "Disabled users cannot log in."}
              </p>
            </div>
          </div>

          <div className="flex items-start gap-3">
            <Checkbox
              id="admin-edit-admin"
              checked={isAdmin}
              onCheckedChange={(v) => setIsAdmin(Boolean(v))}
              disabled={isSelf}
            />
            <div>
              <Label
                htmlFor="admin-edit-admin"
                className="font-exo2 cursor-pointer text-sm"
              >
                Admin
              </Label>
              <p
                className="font-exo2 text-xs"
                style={{ color: "var(--text-muted)" }}
              >
                {isSelf
                  ? "You cannot revoke your own admin role."
                  : "Grants access to /admin and user management."}
              </p>
            </div>
          </div>

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
              type="submit"
              disabled={pending}
              className="cosmic-btn-primary"
            >
              {pending ? "Saving..." : "Save Changes"}
            </button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
