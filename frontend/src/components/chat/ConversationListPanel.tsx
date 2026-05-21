"use client";

import { Loader2, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useT } from "@/hooks/useT";
import { cn } from "@/lib/utils";
import { useDeleteSession, useSessions } from "@/hooks/useSessions";
import { type ChatMode, useChatStore } from "@/stores/chatStore";
import type { Session, SessionMode } from "@/types/notebook.types";

const MODE_KEY: Record<SessionMode, string> = {
  general: "chat.modeGeneral",
  notebook: "chat.modeNotebook",
  fits: "chat.modeFits",
  catalog: "chat.modeCatalog",
};

function isSessionMode(value: string): value is ChatMode {
  return value === "general" || value === "notebook" || value === "fits" ||
    value === "catalog";
}

// Minimal relative-time formatter; avoids adding date-fns dependency.
function formatTimestamp(iso: string): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso;
  const diffMs = Date.now() - t;
  const diffMin = Math.round(diffMs / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffH = Math.round(diffMin / 60);
  if (diffH < 24) return `${diffH}h ago`;
  const diffD = Math.round(diffH / 24);
  if (diffD < 30) return `${diffD}d ago`;
  return new Date(t).toLocaleDateString();
}

function deriveTitle(
  session: Session,
  modeLabel: (m: SessionMode) => string,
): string {
  if (session.title && session.title.trim().length > 0) return session.title;
  return `${modeLabel(session.mode)} · ${formatTimestamp(session.created_at)}`;
}

export function ConversationListPanel({
  onSelect,
}: {
  onSelect?: () => void;
}) {
  const { data: sessions, isLoading, error, refetch } = useSessions();
  const deleteMut = useDeleteSession();
  const [pendingDelete, setPendingDelete] = useState<Session | null>(null);
  const { t } = useT();
  const modeLabel = (m: SessionMode): string =>
    t(MODE_KEY[m] as Parameters<typeof t>[0]);

  const currentSessionId = useChatStore((s) => s.sessionId);
  const loadSession = useChatStore((s) => s.loadSession);
  const clearChat = useChatStore((s) => s.clearChat);

  // Refetch on mount to pick up sessions created in other tabs.
  useEffect(() => {
    refetch();
  }, [refetch]);

  const handleOpen = async (session: Session) => {
    if (session.id === currentSessionId) {
      onSelect?.();
      return;
    }
    try {
      await loadSession(session.id);
      onSelect?.();
    } catch {
      toast.error(t("chat.failedLoadConversation"));
    }
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    const session = pendingDelete;
    try {
      await deleteMut.mutateAsync(session.id);
      if (session.id === currentSessionId) {
        // Prevent next send from 404ing on the deleted id.
        clearChat();
      }
      toast.success(t("chat.deletedConversation"));
    } catch {
      toast.error(t("chat.failedDelete"));
    } finally {
      setPendingDelete(null);
    }
  };

  const handleNew = () => {
    clearChat();
    onSelect?.();
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div
        className="flex items-center justify-between gap-2 px-4 py-3"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <h2
          className="font-orbitron text-[11px] uppercase"
          style={{
            letterSpacing: "0.16em",
            color: "var(--text-secondary)",
          }}
        >
          {t("chat.conversations")}
        </h2>
        <Button
          variant="ghost"
          size="sm"
          onClick={handleNew}
          className="h-7 gap-1.5 text-xs"
        >
          <Plus className="h-3.5 w-3.5" />
          {t("chat.newChat")}
        </Button>
      </div>

      <ScrollArea className="min-h-0 flex-1">
        <div className="flex flex-col gap-1 p-2">
          {isLoading && (
            <p
              className="px-3 py-2 text-xs"
              style={{ color: "var(--text-muted)" }}
            >
              {t("common.loading")}
            </p>
          )}
          {error && (
            <p
              className="px-3 py-2 text-xs"
              style={{ color: "var(--accent-coral)" }}
            >
              {t("chat.failedLoadConversations")}
            </p>
          )}
          {!isLoading && !error && (!sessions || sessions.length === 0) && (
            <p
              className="px-3 py-2 text-xs"
              style={{ color: "var(--text-muted)" }}
            >
              {t("chat.noConversations")}
            </p>
          )}
          {sessions?.map((session) => {
            const active = session.id === currentSessionId;
            const validMode = isSessionMode(session.mode)
              ? session.mode
              : "general";
            const deleting =
              deleteMut.isPending && deleteMut.variables === session.id;
            return (
              <div
                key={session.id}
                className={cn(
                  "group relative flex items-stretch gap-1 rounded-md transition-colors",
                )}
                style={{
                  background: active
                    ? "var(--accent-gold-dim)"
                    : "transparent",
                  border: active
                    ? "1px solid rgba(226,201,126,0.4)"
                    : "1px solid transparent",
                }}
              >
                <button
                  type="button"
                  onClick={() => handleOpen(session)}
                  className="flex min-w-0 flex-1 flex-col gap-1 px-3 py-2 text-left text-xs"
                  style={{ color: "var(--text-primary)" }}
                >
                  <span className="line-clamp-2 pr-6 font-medium">
                    {deriveTitle(session, modeLabel)}
                  </span>
                  <div
                    className="flex items-center gap-2 text-[10px] uppercase"
                    style={{
                      letterSpacing: "0.1em",
                      color: "var(--text-muted)",
                    }}
                  >
                    <span
                      className="rounded px-1.5 py-0.5"
                      style={{
                        background: "var(--surface-subtle)",
                        color: "var(--text-secondary)",
                      }}
                    >
                      {modeLabel(validMode)}
                    </span>
                    {session.fits_file_ids.length > 0 && (
                      <span>{session.fits_file_ids.length} files</span>
                    )}
                    <span>· {formatTimestamp(session.updated_at)}</span>
                  </div>
                </button>
                <button
                  type="button"
                  onClick={() => setPendingDelete(session)}
                  disabled={deleting}
                  className="absolute right-1.5 top-1.5 rounded-md p-1 opacity-0 transition-opacity hover:bg-[rgba(255,112,67,0.12)] group-hover:opacity-100 focus-visible:opacity-100 disabled:opacity-50"
                  aria-label={`Delete conversation ${deriveTitle(session, modeLabel)}`}
                  title="Delete conversation"
                >
                  {deleting ? (
                    <Loader2
                      className="h-3.5 w-3.5 animate-spin"
                      style={{ color: "var(--text-muted)" }}
                    />
                  ) : (
                    <Trash2
                      className="h-3.5 w-3.5"
                      style={{ color: "var(--accent-coral)" }}
                    />
                  )}
                </button>
              </div>
            );
          })}
        </div>
      </ScrollArea>

      <ConfirmDialog
        open={pendingDelete !== null}
        pending={deleteMut.isPending}
        title={t("chat.deleteConversationTitle")}
        confirmLabel={t("chat.deleteConversationConfirm")}
        cancelLabel={t("common.cancel")}
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
        description={t("chat.deleteConversationBody", {
          title: pendingDelete ? deriveTitle(pendingDelete, modeLabel) : "",
        })}
      />
    </div>
  );
}
