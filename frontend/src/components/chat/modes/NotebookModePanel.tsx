"use client";

import { ArrowLeft, FileText, Plus } from "lucide-react";
import { useEffect, useState } from "react";

import { DocumentList } from "@/components/notebook/DocumentList";
import { DocumentUploader } from "@/components/notebook/DocumentUploader";
import { NotebookCreateDialog } from "@/components/notebook/NotebookCreateDialog";
import { ShareDialog } from "@/components/notebook/ShareDialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useNotebooksQuery } from "@/hooks/useNotebooks";
import { useT } from "@/hooks/useT";
import { cn, formatRelativeTime } from "@/lib/utils";
import { useChatStore } from "@/stores/chatStore";

type View = "list" | "detail";

// Notebook-mode rail toggles between list and detail views.
export function NotebookModePanel() {
  const notebookId = useChatStore((s) => s.notebookId);
  const setNotebookId = useChatStore((s) => s.setNotebookId);

  // Start in detail when arriving via ?nb=... links.
  const [view, setView] = useState<View>(notebookId ? "detail" : "list");

  // Bounce to list when notebook gets cleared externally.
  useEffect(() => {
    if (!notebookId && view === "detail") {
      setView("list");
    }
  }, [notebookId, view]);

  const { data: notebooks, isLoading } = useNotebooksQuery({ enabled: true });
  const activeNotebook = notebookId
    ? notebooks?.find((n) => n.id === notebookId) ?? null
    : null;

  const handleSelect = (id: string | null) => {
    setNotebookId(id);
    if (id) setView("detail");
  };

  if (view === "detail" && activeNotebook) {
    return (
      <DetailView
        notebook={activeNotebook}
        onBack={() => setView("list")}
      />
    );
  }

  return (
    <ListView
      notebooks={notebooks ?? []}
      isLoading={isLoading}
      activeNotebookId={notebookId}
      onSelect={handleSelect}
      // Clicking the active notebook again opens detail.
      onOpenActive={() => {
        if (notebookId) setView("detail");
      }}
    />
  );
}


function ListView({
  notebooks,
  isLoading,
  activeNotebookId,
  onSelect,
  onOpenActive,
}: {
  notebooks: ReturnType<typeof useNotebooksQuery>["data"] extends infer T
    ? T extends undefined
      ? never
      : NonNullable<T>
    : never;
  isLoading: boolean;
  activeNotebookId: string | null;
  onSelect: (id: string | null) => void;
  onOpenActive: () => void;
}) {
  const { t } = useT();
  const [createOpen, setCreateOpen] = useState(false);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header
        className="flex shrink-0 items-center justify-between gap-2 px-4 pb-3 pt-4"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <div>
          <h2
            className="font-orbitron text-xs font-semibold uppercase"
            style={{ color: "var(--accent-gold)", letterSpacing: "0.2em" }}
          >
            {t("chat.notebooks.title")}
          </h2>
          <p
            className="font-exo2 mt-0.5 text-[11px]"
            style={{ color: "var(--text-muted)" }}
          >
            {t("chat.notebooks.subtitle")}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setCreateOpen(true)}
          className="cosmic-btn-ghost"
          aria-label={t("chat.notebooks.newLabel")}
        >
          <Plus className="h-3.5 w-3.5" />
          {t("chat.notebooks.newButton")}
        </button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
        {isLoading ? (
          <div className="space-y-2 px-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : !notebooks || notebooks.length === 0 ? (
          <div className="px-3 py-8 text-center">
            <p
              className="font-exo2 mb-3 text-xs"
              style={{ color: "var(--text-muted)" }}
            >
              {t("chat.notebooks.empty")}
            </p>
            <button
              type="button"
              onClick={() => setCreateOpen(true)}
              className="cosmic-btn-primary"
            >
              <Plus className="h-3.5 w-3.5" />
              {t("chat.notebooks.create")}
            </button>
          </div>
        ) : (
          <ul className="space-y-1">
            <li>
              <button
                type="button"
                onClick={() => onSelect(null)}
                className={cn(
                  "block w-full rounded-md px-3 py-2 text-left transition-colors",
                  activeNotebookId === null
                    ? "bg-[var(--accent-gold-dim)]"
                    : "hover:bg-white/[0.03]",
                )}
                style={{
                  borderLeft:
                    activeNotebookId === null
                      ? "2px solid var(--accent-gold)"
                      : "2px solid transparent",
                }}
              >
                <span
                  className="font-exo2 text-sm italic"
                  style={{
                    color:
                      activeNotebookId === null
                        ? "var(--accent-gold)"
                        : "var(--text-secondary)",
                  }}
                >
                  {t("chat.notebooks.noSelection")}
                </span>
              </button>
            </li>
            {notebooks.map((nb) => {
              const active = nb.id === activeNotebookId;
              return (
                <li key={nb.id}>
                  <button
                    type="button"
                    onClick={() => {
                      if (active) {
                        onOpenActive();
                      } else {
                        onSelect(nb.id);
                      }
                    }}
                    className={cn(
                      "block w-full rounded-md px-3 py-2 text-left transition-colors",
                      active
                        ? "bg-[var(--accent-gold-dim)]"
                        : "hover:bg-white/[0.03]",
                    )}
                    style={{
                      borderLeft: active
                        ? "2px solid var(--accent-gold)"
                        : "2px solid transparent",
                    }}
                    aria-label={
                      active
                        ? `Open ${nb.title} details`
                        : `Select ${nb.title}`
                    }
                  >
                    <div
                      className="font-exo2 truncate text-sm"
                      style={{
                        color: active
                          ? "var(--accent-gold)"
                          : "var(--text-primary)",
                        fontWeight: active ? 600 : 400,
                      }}
                    >
                      {nb.title}
                    </div>
                    <div
                      className="font-space-mono mt-0.5 truncate text-[10px] uppercase"
                      style={{
                        color: "var(--text-muted)",
                        letterSpacing: "0.12em",
                      }}
                    >
                      {t("chat.notebooks.updated", { time: formatRelativeTime(nb.updated_at) })}
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <NotebookCreateDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
      />
    </div>
  );
}


function DetailView({
  notebook,
  onBack,
}: {
  notebook: NonNullable<ReturnType<typeof useNotebooksQuery>["data"]>[number];
  onBack: () => void;
}) {
  const { t } = useT();
  return (
    <div className="flex h-full min-h-0 flex-col">
      <header
        className="shrink-0 px-4 pb-3 pt-3"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <div className="mb-2 flex items-center justify-between gap-2">
          <button
            type="button"
            onClick={onBack}
            className="cosmic-btn-ghost"
            aria-label={t("chat.notebooks.backLabel")}
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            {t("chat.notebooks.backButton")}
          </button>
          <ShareDialog notebookId={notebook.id} />
        </div>
        <h2
          className="font-orbitron truncate text-sm font-semibold uppercase"
          style={{
            color: "var(--text-primary)",
            letterSpacing: "0.16em",
          }}
          title={notebook.title}
        >
          {notebook.title}
        </h2>
        {notebook.description && (
          <p
            className="font-exo2 mt-1 text-xs"
            style={{ color: "var(--text-secondary)" }}
          >
            {notebook.description}
          </p>
        )}
        <p
          className="font-space-mono mt-1.5 text-[10px] uppercase"
          style={{
            color: "var(--text-muted)",
            letterSpacing: "0.16em",
          }}
        >
          {t("chat.notebooks.updated", { time: formatRelativeTime(notebook.updated_at) })}
        </p>
      </header>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-3 py-3">
        <section className="space-y-2">
          <h3
            className="font-orbitron text-[10px] font-semibold uppercase"
            style={{
              color: "var(--accent-gold)",
              letterSpacing: "0.2em",
            }}
          >
            {t("chat.notebooks.addSources")}
          </h3>
          <DocumentUploader notebookId={notebook.id} />
        </section>

        <section className="space-y-2">
          <h3
            className="font-orbitron flex items-center gap-1.5 text-[10px] font-semibold uppercase"
            style={{
              color: "var(--accent-gold)",
              letterSpacing: "0.2em",
            }}
          >
            <FileText className="h-3 w-3" aria-hidden />
            {t("chat.notebooks.sources")}
          </h3>
          <DocumentList notebookId={notebook.id} />
        </section>
      </div>
    </div>
  );
}
