"use client";

import { Plus } from "lucide-react";
import { useMemo } from "react";

import { AgentStatusBadge } from "@/components/agents/AgentStatusBadge";
import { useNotebooksQuery } from "@/hooks/useNotebooks";
import { useT } from "@/hooks/useT";
import { useAstronomyStore } from "@/stores/astronomyStore";
import { useChatStore } from "@/stores/chatStore";

const TITLE_TRUNC = 30;

function truncate(s: string, max: number): string {
  return s.length <= max ? s : `${s.slice(0, max - 1)}…`;
}

// Status strip showing current scope + connection state above the chat.
export function ContextBar() {
  const { t } = useT();
  const mode = useChatStore((s) => s.mode);
  const notebookId = useChatStore((s) => s.notebookId);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const isReconnecting = useChatStore((s) => s.isReconnecting);
  const clearChat = useChatStore((s) => s.clearChat);

  // Only notebook mode needs the list.
  const { data: notebooks } = useNotebooksQuery({ enabled: mode === "notebook" });
  const selectedFileId = useAstronomyStore((s) => s.selectedFileId);
  const recentFiles = useAstronomyStore((s) => s.recentFiles);

  const scopeLabel = useMemo(() => {
    if (mode === "notebook") {
      if (!notebookId) return t("chat.context.noNotebook");
      const nb = notebooks?.find((n) => n.id === notebookId);
      return nb ? truncate(nb.title, TITLE_TRUNC) : truncate(notebookId, TITLE_TRUNC);
    }
    if (mode === "fits") {
      if (!selectedFileId) return t("chat.context.noFits");
      const f = recentFiles.find((rf) => rf.file_id === selectedFileId);
      return f ? truncate(f.filename, TITLE_TRUNC) : truncate(selectedFileId, TITLE_TRUNC);
    }
    if (mode === "catalog") return t("chat.context.catalog");
    return t("chat.context.general");
  }, [mode, notebookId, notebooks, selectedFileId, recentFiles, t]);

  return (
    <div
      className="flex items-center justify-between gap-3 px-5 py-3"
      style={{ borderBottom: "1px solid var(--border)" }}
    >
      <div className="flex min-w-0 items-center gap-2.5">
        <span
          className="font-orbitron text-[10px] uppercase"
          style={{ color: "var(--text-muted)", letterSpacing: "0.2em" }}
        >
          {t("chat.context.label")}
        </span>
        <span
          className="font-exo2 truncate text-xs"
          style={{ color: "var(--text-primary)" }}
        >
          {scopeLabel}
        </span>
      </div>

      <div className="flex shrink-0 items-center gap-2">
        {isReconnecting && (
          <span
            className="font-orbitron inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-[10px] uppercase"
            style={{
              border: "1px solid var(--accent-coral)",
              color: "var(--accent-coral)",
              letterSpacing: "0.18em",
              animation: "cosmic-pulse 1.6s ease-in-out infinite",
            }}
            role="status"
            aria-live="polite"
          >
            {t("chat.reconnecting")}
          </span>
        )}
        {!isReconnecting && isStreaming && (
          <AgentStatusBadge status="running" />
        )}
        <button
          type="button"
          onClick={clearChat}
          className="font-orbitron inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[11px] uppercase transition-colors hover:bg-[var(--accent-gold-dim)]"
          style={{
            border: "1px solid var(--border)",
            color: "var(--text-secondary)",
            letterSpacing: "0.16em",
          }}
          aria-label={t("chat.newChatLabel")}
          disabled={isStreaming || isReconnecting}
        >
          <Plus className="h-3 w-3" />
          {t("chat.newChatButton")}
        </button>
      </div>
    </div>
  );
}
