"use client";

import { motion } from "framer-motion";
import { History, LayoutGrid, PanelLeft } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

import {
  pageTransition,
  pageTransitionSpec,
} from "@/animations/page-transition";
import { ChatModeTabs } from "@/components/chat/ChatModeTabs";
import { ChatWindow } from "@/components/chat/ChatWindow";
import { ConversationListPanel } from "@/components/chat/ConversationListPanel";
import { AdminRedirect } from "@/components/common/AdminRedirect";
import { PageLoader } from "@/components/common/PageLoader";
import {
  CatalogModePanel,
  useCatalogModeState,
} from "@/components/chat/modes/CatalogModePanel";
import {
  FitsArtifactsPanel,
  FitsModePanel,
} from "@/components/chat/modes/FitsModePanel";
import { NotebookModePanel } from "@/components/chat/modes/NotebookModePanel";
import { NotebookStudioPanel } from "@/components/chat/modes/NotebookStudioPanel";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { useT } from "@/hooks/useT";
import { sessionService } from "@/services/sessionService";
import { type ChatMode, useChatStore } from "@/stores/chatStore";

const VALID_MODES: ReadonlySet<ChatMode> = new Set([
  "general",
  "notebook",
  "fits",
  "catalog",
]);

function isChatMode(value: string | null): value is ChatMode {
  return value !== null && VALID_MODES.has(value as ChatMode);
}

// Unified chat workspace; mode tabs swap rail + artifacts columns.
export default function ChatPage() {
  return (
    <AdminRedirect>
      <Suspense fallback={<PageLoader />}>
        <ChatWorkspace />
      </Suspense>
    </AdminRedirect>
  );
}

function ChatWorkspace() {
  const { t } = useT();
  const router = useRouter();
  const searchParams = useSearchParams();

  const mode = useChatStore((s) => s.mode);
  const setMode = useChatStore((s) => s.setMode);
  const notebookId = useChatStore((s) => s.notebookId);
  const setNotebookId = useChatStore((s) => s.setNotebookId);
  const sessionId = useChatStore((s) => s.sessionId);
  const syncSessionMeta = useChatStore((s) => s.syncSessionMeta);
  const loadSession = useChatStore((s) => s.loadSession);

  // URL → store hydration runs once; cid wins over mode/nb.
  const hydrationStarted = useRef(false);
  const [hydrated, setHydrated] = useState(false);
  useEffect(() => {
    if (hydrationStarted.current) return;
    hydrationStarted.current = true;
    const urlMode = searchParams.get("mode");
    const urlNb = searchParams.get("nb");
    const urlCid = searchParams.get("cid");
    if (urlCid) {
      // Strip bad cid on failure so stale share links don't trap the user.
      loadSession(urlCid)
        .catch(() => {
          const params = new URLSearchParams(searchParams.toString());
          params.delete("cid");
          const next = params.toString();
          router.replace(next ? `?${next}` : "?", { scroll: false });
        })
        .finally(() => setHydrated(true));
      return;
    }
    // Auto-resume most recent matching conversation; best-effort.
    if (isChatMode(urlMode) && urlMode !== mode) setMode(urlMode);
    if (urlNb && urlNb !== notebookId) setNotebookId(urlNb);
    const resolvedMode: ChatMode = isChatMode(urlMode) ? urlMode : mode;
    const shouldAutoResume =
      resolvedMode === "notebook" && Boolean(urlNb);
    if (shouldAutoResume) {
      sessionService
        .list({ notebookId: urlNb ?? undefined, limit: 1 })
        .then((rows) => {
          if (rows.length === 0) return;
          return loadSession(rows[0].id);
        })
        .catch(() => {
          // Fall through to fresh-chat state on failure.
        })
        .finally(() => setHydrated(true));
      return;
    }
    setHydrated(true);
  }, [searchParams, mode, notebookId, setMode, setNotebookId, loadSession, router]);

  // Store → URL sync; gated by hydration so initial render doesn't strip params.
  useEffect(() => {
    if (!hydrated) return;
    const params = new URLSearchParams(searchParams.toString());
    if (mode === "general") {
      params.delete("mode");
    } else {
      params.set("mode", mode);
    }
    if (mode === "notebook" && notebookId) {
      params.set("nb", notebookId);
    } else {
      params.delete("nb");
    }
    if (sessionId) {
      params.set("cid", sessionId);
    } else {
      // Drop stale cid after clearChat so refresh doesn't reload a deleted row.
      params.delete("cid");
    }
    const next = params.toString();
    const current = searchParams.toString();
    if (next !== current) {
      router.replace(next ? `?${next}` : "?", { scroll: false });
    }
  }, [mode, notebookId, sessionId, router, searchParams, hydrated]);

  // Persist mode/notebook to BE so reload restores context.
  useEffect(() => {
    if (!hydrated) return;
    if (!sessionId) return;
    syncSessionMeta({
      mode,
      notebookId: mode === "notebook" ? notebookId : null,
    });
  }, [mode, notebookId, sessionId, syncSessionMeta, hydrated]);

  const catalog = useCatalogModeState();

  const hasLeftRail = mode !== "general";
  // Notebook artifacts only shown when a notebook is selected.
  const hasArtifacts =
    mode === "fits" || (mode === "notebook" && notebookId !== null);

  // Below lg collapse to chat-only; rail + artifacts move into Sheets.
  const isDesktop = useMediaQuery("(min-width: 1024px)");
  const [toolsOpen, setToolsOpen] = useState(false);
  const [artifactsOpen, setArtifactsOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);

  // Auto-close non-history sheets on resize to desktop.
  useEffect(() => {
    if (isDesktop) {
      setToolsOpen(false);
      setArtifactsOpen(false);
    }
  }, [isDesktop]);

  // Grid columns built lazily so general mode takes full width.
  const cols: string[] = [];
  if (isDesktop && hasLeftRail) {
    const leftCol =
      mode === "catalog"
        ? "minmax(480px, 1.3fr)"
        : mode === "notebook"
          ? "minmax(300px, 380px)"
          : "minmax(260px, 320px)";
    cols.push(leftCol);
  }
  cols.push("minmax(0, 1fr)");
  if (isDesktop && hasArtifacts) {
    cols.push(
      mode === "notebook" ? "minmax(280px, 340px)" : "minmax(0, 1.1fr)",
    );
  }

  // Built once, reused inline (desktop) or inside Sheet (mobile).
  const railContent = (() => {
    if (mode === "notebook") return <NotebookModePanel />;
    if (mode === "fits") return <FitsModePanel />;
    if (mode === "catalog")
      return (
        <CatalogModePanel
          query={catalog.query}
          source={catalog.source}
          radius={catalog.radius}
          onQueryChange={catalog.setQuery}
          onSourceChange={catalog.setSource}
          onRadiusChange={catalog.setRadius}
        />
      );
    return null;
  })();

  const artifactsContent = (() => {
    if (mode === "fits") return <FitsArtifactsPanel />;
    if (mode === "notebook" && notebookId)
      return <NotebookStudioPanel notebookId={notebookId} />;
    return null;
  })();

  return (
    <motion.div
      variants={pageTransition}
      initial="initial"
      animate="animate"
      transition={pageTransitionSpec}
      className="-mx-4 -my-6 flex flex-col sm:-mx-6 sm:-my-8 lg:-mx-8 lg:-my-10"
      style={{ height: "calc(100svh - 4rem)" }}
    >
      <div
        className="flex shrink-0 items-center gap-2 border-b px-4 py-3"
        style={{ borderColor: "var(--border)" }}
      >
        <div className="min-w-0 flex-1">
          <ChatModeTabs />
        </div>
        <button
          type="button"
          onClick={() => setHistoryOpen(true)}
          className="cosmic-btn-ghost shrink-0"
          aria-label={t("chat.historyLabel")}
        >
          <History className="h-3.5 w-3.5" />
          {t("chat.history")}
        </button>
        {!isDesktop && hasLeftRail && (
          <button
            type="button"
            onClick={() => setToolsOpen(true)}
            className="cosmic-btn-ghost shrink-0"
            aria-label={t("chat.toolsLabel")}
          >
            <PanelLeft className="h-3.5 w-3.5" />
            {t("chat.tools")}
          </button>
        )}
        {!isDesktop && hasArtifacts && (
          <button
            type="button"
            onClick={() => setArtifactsOpen(true)}
            className="cosmic-btn-ghost shrink-0"
            aria-label={t("chat.artifactsLabel")}
          >
            <LayoutGrid className="h-3.5 w-3.5" />
            {t("chat.artifacts")}
          </button>
        )}
      </div>

      <div
        className="grid min-h-0 flex-1 overflow-hidden"
        style={{ gridTemplateColumns: cols.join(" ") }}
      >
        {isDesktop && hasLeftRail && (
          <aside
            // h-full so inner scroll containers have a defined height.
            className="h-full min-h-0 overflow-hidden"
            style={{ borderRight: "1px solid var(--border)" }}
          >
            {railContent}
          </aside>
        )}

        <section className="min-h-0 overflow-hidden">
          <ChatWindow />
        </section>

        {isDesktop && hasArtifacts && (
          <aside
            className="h-full min-h-0 overflow-hidden"
            style={{ borderLeft: "1px solid var(--border)" }}
          >
            {artifactsContent}
          </aside>
        )}
      </div>

      {/* Mobile drawers — only mount when needed. */}
      {!isDesktop && hasLeftRail && (
        <Sheet open={toolsOpen} onOpenChange={setToolsOpen}>
          <SheetContent side="left" className="w-[88vw] max-w-sm p-0">
            <SheetHeader className="sr-only">
              <SheetTitle>{t("chat.toolsTitle")}</SheetTitle>
            </SheetHeader>
            <div className="h-full min-h-0 overflow-hidden">{railContent}</div>
          </SheetContent>
        </Sheet>
      )}

      {!isDesktop && hasArtifacts && (
        <Sheet open={artifactsOpen} onOpenChange={setArtifactsOpen}>
          <SheetContent side="right" className="w-[92vw] max-w-md p-0">
            <SheetHeader className="sr-only">
              <SheetTitle>{t("chat.artifactsTitle")}</SheetTitle>
            </SheetHeader>
            <div className="h-full min-h-0 overflow-y-auto">
              {artifactsContent}
            </div>
          </SheetContent>
        </Sheet>
      )}

      <Sheet open={historyOpen} onOpenChange={setHistoryOpen}>
        <SheetContent side="left" className="w-[88vw] max-w-sm p-0">
          <SheetHeader className="sr-only">
            <SheetTitle>{t("chat.historyTitle")}</SheetTitle>
          </SheetHeader>
          <ConversationListPanel onSelect={() => setHistoryOpen(false)} />
        </SheetContent>
      </Sheet>
    </motion.div>
  );
}
