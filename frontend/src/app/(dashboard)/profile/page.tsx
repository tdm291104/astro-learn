"use client";

import { motion } from "framer-motion";
import { Loader2, LogOut, Pencil, Save, X } from "lucide-react";
import { useState } from "react";

import {
  pageTransition,
  pageTransitionSpec,
} from "@/animations/page-transition";
import { Input } from "@/components/ui/input";
import {
  useChangePasswordMutation,
  useLogout,
  useUpdateProfileMutation,
} from "@/hooks/useAuth";
import { useT } from "@/hooks/useT";
import { formatRelativeTime } from "@/lib/utils";
import { useAuthStore } from "@/stores/authStore";

export default function ProfilePage() {
  const { t } = useT();
  const logout = useLogout();

  return (
    <motion.div
      variants={pageTransition}
      initial="initial"
      animate="animate"
      transition={pageTransitionSpec}
      className="space-y-6"
    >
      <header className="space-y-2">
        <p
          className="font-space-mono text-xs uppercase"
          style={{
            color: "var(--text-muted)",
            letterSpacing: "0.2em",
          }}
        >
          {t("profile.sessionLabel")}
        </p>
        <h1
          className="font-orbitron text-xl font-bold uppercase sm:text-2xl lg:text-3xl"
          style={{
            color: "var(--text-primary)",
            letterSpacing: "0.18em",
          }}
        >
          {t("profile.title")}
        </h1>
        <p
          className="font-exo2 text-sm"
          style={{ color: "var(--text-secondary)" }}
        >
          {t("profile.subtitle")}
        </p>
      </header>

      <ProfileDetailsCard />

      <PasswordChangeCard />

      <div className="max-w-xl">
        <button
          type="button"
          onClick={() => logout()}
          className="cosmic-btn-outline"
          aria-label="Sign out of AstroLearn"
        >
          <LogOut className="h-3.5 w-3.5" />
          {t("profile.signOut")}
        </button>
      </div>
    </motion.div>
  );
}

function ProfileDetailsCard() {
  const { t } = useT();
  const user = useAuthStore((s) => s.user);
  const updateProfile = useUpdateProfileMutation();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");

  const beginEdit = () => {
    setDraft(user?.full_name ?? "");
    setEditing(true);
  };
  const cancel = () => {
    setEditing(false);
    setDraft("");
  };
  const save = () => {
    updateProfile.mutate(
      { full_name: draft },
      { onSuccess: () => setEditing(false) },
    );
  };

  return (
    <section className="cosmic-card max-w-xl overflow-hidden">
      <ProfileRow label={t("profile.email")} value={user?.email ?? "—"} mono />

      <div
        className="flex items-center justify-between gap-4 px-5 py-4"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <span
          className="font-orbitron text-[11px] uppercase"
          style={{
            color: "var(--text-muted)",
            letterSpacing: "0.18em",
          }}
        >
          {t("profile.fullName")}
        </span>
        {editing ? (
          <div className="flex flex-1 items-center justify-end gap-2">
            <Input
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder={t("profile.nameExample")}
              maxLength={255}
              className="max-w-[240px]"
              disabled={updateProfile.isPending}
            />
            <button
              type="button"
              onClick={save}
              disabled={updateProfile.isPending}
              className="cosmic-btn-primary"
              style={{ padding: "0.4rem 0.7rem" }}
              aria-label="Save name"
            >
              {updateProfile.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Save className="h-3.5 w-3.5" />
              )}
            </button>
            <button
              type="button"
              onClick={cancel}
              disabled={updateProfile.isPending}
              className="cosmic-btn-ghost"
              style={{ padding: "0.4rem 0.55rem" }}
              aria-label="Cancel"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <span
              className="font-exo2 text-sm"
              style={{ color: "var(--text-primary)" }}
            >
              {user?.full_name?.trim() || "—"}
            </span>
            <button
              type="button"
              onClick={beginEdit}
              className="cosmic-btn-ghost"
              style={{ padding: "0.3rem 0.55rem" }}
              aria-label="Edit name"
            >
              <Pencil className="h-3.5 w-3.5" />
            </button>
          </div>
        )}
      </div>

      <ProfileRow
        label={t("profile.joined")}
        value={user?.created_at ? formatRelativeTime(user.created_at) : "—"}
        mono
      />
      <ProfileRow
        label={t("profile.status")}
        value={
          user?.is_active
            ? t("profile.statusActive")
            : t("profile.statusInactive")
        }
        last
      />
    </section>
  );
}

function PasswordChangeCard() {
  const { t } = useT();
  const changePassword = useChangePasswordMutation();
  const [currentPwd, setCurrentPwd] = useState("");
  const [newPwd, setNewPwd] = useState("");
  const [confirmPwd, setConfirmPwd] = useState("");

  // Inline check so we highlight the offending field instead of a toast.
  const localError = (() => {
    if (!currentPwd || !newPwd || !confirmPwd) return null;
    if (newPwd.length < 8) return t("profile.password.tooShort");
    if (newPwd === currentPwd) return t("profile.password.unchanged");
    if (newPwd !== confirmPwd) return t("profile.password.mismatch");
    return null;
  })();

  const canSubmit =
    currentPwd.length > 0 &&
    newPwd.length >= 8 &&
    confirmPwd.length > 0 &&
    !localError &&
    !changePassword.isPending;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    changePassword.mutate(
      { current_password: currentPwd, new_password: newPwd },
      {
        onSuccess: () => {
          setCurrentPwd("");
          setNewPwd("");
          setConfirmPwd("");
        },
      },
    );
  };

  return (
    <section className="cosmic-card max-w-xl space-y-5 p-5">
      <header className="space-y-1">
        <h2
          className="font-orbitron text-sm font-semibold uppercase"
          style={{
            color: "var(--text-primary)",
            letterSpacing: "0.18em",
          }}
        >
          {t("profile.password.title")}
        </h2>
        <p
          className="font-exo2 text-xs"
          style={{ color: "var(--text-secondary)" }}
        >
          {t("profile.password.hint")}
        </p>
      </header>

      <form onSubmit={submit} className="space-y-3">
        <Field
          label={t("profile.password.current")}
          id="pwd-current"
          value={currentPwd}
          onChange={setCurrentPwd}
          autoComplete="current-password"
        />
        <Field
          label={t("profile.password.new")}
          id="pwd-new"
          value={newPwd}
          onChange={setNewPwd}
          autoComplete="new-password"
        />
        <Field
          label={t("profile.password.confirm")}
          id="pwd-confirm"
          value={confirmPwd}
          onChange={setConfirmPwd}
          autoComplete="new-password"
        />

        {localError && (
          <p
            className="font-exo2 text-xs"
            style={{ color: "var(--accent-coral)" }}
          >
            {localError}
          </p>
        )}

        <button
          type="submit"
          disabled={!canSubmit}
          className="cosmic-btn-primary"
        >
          {changePassword.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : null}
          {t("profile.password.submit")}
        </button>
      </form>
    </section>
  );
}

function Field({
  label,
  id,
  value,
  onChange,
  autoComplete,
}: {
  label: string;
  id: string;
  value: string;
  onChange: (v: string) => void;
  autoComplete: string;
}) {
  return (
    <div className="space-y-1.5">
      <label
        htmlFor={id}
        className="font-orbitron text-[11px] uppercase"
        style={{
          color: "var(--text-muted)",
          letterSpacing: "0.18em",
        }}
      >
        {label}
      </label>
      <Input
        id={id}
        type="password"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        autoComplete={autoComplete}
        maxLength={128}
      />
    </div>
  );
}

function ProfileRow({
  label,
  value,
  mono,
  last,
}: {
  label: string;
  value: string;
  mono?: boolean;
  last?: boolean;
}) {
  return (
    <div
      className="flex items-center justify-between gap-4 px-5 py-4"
      style={{
        borderBottom: last ? undefined : "1px solid var(--border)",
      }}
    >
      <span
        className="font-orbitron text-[11px] uppercase"
        style={{
          color: "var(--text-muted)",
          letterSpacing: "0.18em",
        }}
      >
        {label}
      </span>
      <span
        className={mono ? "font-space-mono text-sm" : "font-exo2 text-sm"}
        style={{ color: "var(--text-primary)" }}
      >
        {value}
      </span>
    </div>
  );
}
