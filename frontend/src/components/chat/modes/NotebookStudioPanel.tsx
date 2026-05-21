"use client";

import type { LucideIcon } from "lucide-react";
import { ChevronRight, Layers, ListChecks, ScrollText, Sparkles } from "lucide-react";

import { FlashcardDeck } from "@/components/notebook/FlashcardDeck";
import { QuizRunner } from "@/components/notebook/QuizRunner";
import { SummaryView } from "@/components/notebook/SummaryView";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { type NotebookTool, useUiStore } from "@/stores/uiStore";

type Tool = NotebookTool;

type ToolMeta = {
  key: Tool;
  label: string;
  description: string;
  Icon: LucideIcon;
};

const TOOLS: ToolMeta[] = [
  {
    key: "summary",
    label: "Summary",
    description: "Bulleted or prose summary across every source in the notebook.",
    Icon: ScrollText,
  },
  {
    key: "quiz",
    label: "Quiz",
    description: "Multiple-choice questions to test recall on the indexed content.",
    Icon: ListChecks,
  },
  {
    key: "flashcards",
    label: "Flashcards",
    description: "Front/back cards covering the key concepts; flip to study.",
    Icon: Layers,
  },
];

// Tool cards open study components in a modal to keep the chat composer visible.
export function NotebookStudioPanel({ notebookId }: { notebookId: string }) {
  // Shared store so a chat redirect (extra.suggest_panel) can open the
  // matching dialog without piping callbacks through every parent.
  const openTool = useUiStore((s) => s.openNotebookTool);
  const requestTool = useUiStore((s) => s.requestNotebookTool);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header
        className="shrink-0 px-4 pb-3 pt-4"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <h2
          className="font-orbitron flex items-center gap-2 text-xs font-semibold uppercase"
          style={{ color: "var(--accent-gold)", letterSpacing: "0.2em" }}
        >
          <Sparkles className="h-3.5 w-3.5" aria-hidden />
          Notebook Tools
        </h2>
        <p
          className="font-exo2 mt-1 text-[11px]"
          style={{ color: "var(--text-muted)" }}
        >
          Click a tool to generate from this notebook&apos;s sources.
        </p>
      </header>

      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-3">
        {TOOLS.map((tool) => (
          <ToolCard
            key={tool.key}
            tool={tool}
            onClick={() => requestTool(tool.key)}
          />
        ))}
      </div>

      {TOOLS.map((tool) => (
        <ToolDialog
          key={tool.key}
          tool={tool}
          notebookId={notebookId}
          open={openTool === tool.key}
          onOpenChange={(next) => {
            if (!next) requestTool(null);
          }}
        />
      ))}
    </div>
  );
}

function ToolCard({
  tool,
  onClick,
}: {
  tool: ToolMeta;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex w-full items-start gap-3 rounded-lg p-3 text-left transition-colors hover:bg-[rgba(226,201,126,0.05)]"
      style={{
        background: "rgba(255,255,255,0.02)",
        border: "1px solid var(--border)",
      }}
    >
      <span
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md transition-colors group-hover:bg-[var(--accent-gold-dim)]"
        style={{
          background: "rgba(226,201,126,0.08)",
          color: "var(--accent-gold)",
        }}
        aria-hidden
      >
        <tool.Icon className="h-4 w-4" />
      </span>
      <div className="min-w-0 flex-1">
        <p
          className="font-orbitron text-xs font-semibold uppercase"
          style={{ color: "var(--text-primary)", letterSpacing: "0.16em" }}
        >
          {tool.label}
        </p>
        <p
          className="font-exo2 mt-1 text-[11px]"
          style={{ color: "var(--text-secondary)" }}
        >
          {tool.description}
        </p>
      </div>
      <ChevronRight
        className="mt-1 h-3.5 w-3.5 shrink-0 transition-colors group-hover:text-[var(--accent-gold)]"
        style={{ color: "var(--text-muted)" }}
        aria-hidden
      />
    </button>
  );
}

function ToolDialog({
  tool,
  notebookId,
  open,
  onOpenChange,
}: {
  tool: ToolMeta;
  notebookId: string;
  open: boolean;
  onOpenChange: (next: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        // Wide modal so the study component doesn't double-scroll.
        className="flex max-h-[90vh] flex-col gap-4 sm:max-w-[min(960px,95vw)]"
      >
        <DialogHeader>
          <DialogTitle className="font-orbitron flex items-center gap-2 text-sm uppercase">
            <tool.Icon
              className="h-4 w-4"
              style={{ color: "var(--accent-gold)" }}
              aria-hidden
            />
            {tool.label}
          </DialogTitle>
          <DialogDescription className="font-exo2 text-xs">
            {tool.description}
          </DialogDescription>
        </DialogHeader>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {open && tool.key === "summary" && (
            <SummaryView notebookId={notebookId} />
          )}
          {open && tool.key === "quiz" && (
            <QuizRunner notebookId={notebookId} />
          )}
          {open && tool.key === "flashcards" && (
            <FlashcardDeck notebookId={notebookId} />
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
