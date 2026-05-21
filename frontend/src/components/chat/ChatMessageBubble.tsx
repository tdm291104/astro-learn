"use client";

import {
  AlertTriangle,
  BookOpen,
  Brain,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Globe,
  Layers,
  ListChecks,
  ScrollText,
  Sparkles,
  Wrench,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { ToolResultView } from "@/components/chat/ToolResultView";
import { useT } from "@/hooks/useT";
import {
  type AggregatedReasoning,
  type AggregatedReasoningStep,
  type CatalogGrounding,
  type ChatMessage,
  type ChatMode,
  useChatStore,
} from "@/stores/chatStore";
import { type NotebookTool, useUiStore } from "@/stores/uiStore";
import type { Citation } from "@/types/notebook.types";

export function ChatMessageBubble({
  message,
  onConfirmWebSearch,
}: {
  message: ChatMessage;
  onConfirmWebSearch?: (query: string) => void;
}) {
  // System "→ Running:" pills are leftover free-text notices the store still
  // shows (the structured plan/step messages get folded into the assistant).
  if (message.role === "system" && message.isStep) {
    return <StepIndicator message={message} />;
  }
  switch (message.role) {
    case "user":
      return <UserBubble message={message} />;
    case "assistant":
      return (
        <AssistantBubble
          message={message}
          onConfirmWebSearch={onConfirmWebSearch}
        />
      );
    case "system":
    default:
      return <SystemPill message={message} />;
  }
}

function ReasoningDisclosure({ trail }: { trail: AggregatedReasoning }) {
  const [open, setOpen] = useState(false);
  const { t } = useT();
  const totalTools = trail.steps.reduce(
    (sum, s) => sum + s.tool_invocations.length,
    0,
  );
  if (trail.steps.length === 0 && !trail.plan_summary) return null;
  const stepText = t(
    trail.steps.length === 1 ? "chat.stepCount" : "chat.stepCountPlural",
    { n: trail.steps.length },
  );
  const toolText =
    totalTools > 0
      ? ` · ${t(
          totalTools === 1 ? "chat.toolCallCount" : "chat.toolCallCountPlural",
          { n: totalTools },
        )}`
      : "";

  return (
    <div className="mb-1.5">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-[11px] transition-colors hover:bg-white/5"
        style={{ color: "var(--text-muted)" }}
        aria-expanded={open}
      >
        {open ? (
          <ChevronDown className="h-3 w-3" />
        ) : (
          <ChevronRight className="h-3 w-3" />
        )}
        <Brain className="h-3 w-3" style={{ color: "var(--accent-gold)" }} />
        <span
          className="font-orbitron uppercase"
          style={{ letterSpacing: "0.14em" }}
        >
          {t("chat.thoughtProcess")}
        </span>
        <span className="font-exo2" style={{ color: "var(--text-muted)" }}>
          {stepText}
          {toolText}
        </span>
      </button>
      {open && (
        <div
          className="mt-2 space-y-3 rounded-lg border-l-2 py-2 pl-3 pr-1"
          style={{ borderColor: "rgba(226,201,126,0.32)" }}
        >
          {trail.plan_summary && (
            <p
              className="font-exo2 text-[12px] italic leading-relaxed"
              style={{ color: "var(--text-secondary)" }}
            >
              {trail.plan_summary}
            </p>
          )}
          <ol className="space-y-2.5">
            {trail.steps.map((step, i) => (
              <ReasoningStep key={i} index={i} step={step} />
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}

function ReasoningStep({
  index,
  step,
}: {
  index: number;
  step: AggregatedReasoningStep;
}) {
  return (
    <li className="space-y-1">
      <div className="flex items-baseline gap-2">
        <span
          className="font-space-mono shrink-0 text-[10px] tabular-nums"
          style={{ color: "var(--accent-gold)" }}
        >
          {String(index + 1).padStart(2, "0")}
        </span>
        <span
          className="font-orbitron text-[11px] uppercase"
          style={{
            color: "var(--accent-blue)",
            letterSpacing: "0.14em",
          }}
        >
          {step.agent_name}
        </span>
      </div>
      {step.rationale && (
        <p
          className="font-exo2 ml-5 text-[12px] leading-relaxed"
          style={{ color: "var(--text-primary)" }}
        >
          {step.rationale}
        </p>
      )}
      {step.tool_invocations.length > 0 && (
        <ul className="ml-5 space-y-1.5">
          {step.tool_invocations.map((inv, j) => (
            <ToolInvocationRow key={j} invocation={inv} />
          ))}
        </ul>
      )}
    </li>
  );
}

function ToolInvocationRow({
  invocation,
}: {
  invocation: AggregatedReasoningStep["tool_invocations"][number];
}) {
  const [open, setOpen] = useState(false);
  const argsSummary = invocation.arguments
    ? Object.entries(invocation.arguments)
        .slice(0, 2)
        .map(([k, v]) => `${k}=${shortVal(v)}`)
        .join(", ")
    : "";
  const hasResult = Boolean(invocation.result);
  return (
    <li>
      <button
        type="button"
        onClick={() => hasResult && setOpen((o) => !o)}
        className="flex w-full items-center gap-1.5 rounded-md px-1.5 py-1 text-left transition-colors hover:bg-white/5"
        disabled={!hasResult}
        aria-expanded={open}
      >
        {hasResult ? (
          open ? (
            <ChevronDown className="h-3 w-3" style={{ color: "var(--accent-blue)" }} />
          ) : (
            <ChevronRight className="h-3 w-3" style={{ color: "var(--accent-blue)" }} />
          )
        ) : (
          <Wrench className="h-3 w-3" style={{ color: "var(--accent-blue)" }} />
        )}
        <span
          className="font-space-mono text-[11px]"
          style={{ color: "var(--accent-blue)" }}
        >
          {invocation.name}
        </span>
        {argsSummary && (
          <span
            className="font-exo2 truncate text-[11px]"
            style={{ color: "var(--text-muted)" }}
          >
            ({argsSummary})
          </span>
        )}
      </button>
      {open && hasResult && (
        <div className="mt-1.5 pl-5">
          <ToolResultView
            toolName={invocation.name}
            rawContent={invocation.result ?? ""}
          />
        </div>
      )}
    </li>
  );
}

function shortVal(v: unknown): string {
  if (typeof v === "string") return v.length > 24 ? `"${v.slice(0, 24)}…"` : `"${v}"`;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  if (Array.isArray(v)) return `[${v.length}]`;
  if (v && typeof v === "object") return "{…}";
  return String(v);
}

function StepIndicator({ message }: { message: ChatMessage }) {
  return (
    <div className="flex justify-center py-1">
      <span
        className="font-space-mono text-[11px] italic"
        style={{
          color: "var(--text-muted)",
          letterSpacing: "0.06em",
        }}
      >
        {message.content}
      </span>
    </div>
  );
}

function UserBubble({ message }: { message: ChatMessage }) {
  return (
    <div className="flex justify-end">
      <div
        className="max-w-[85%] rounded-2xl px-4 py-2.5"
        style={{
          background: "var(--accent-gold-dim)",
          border: "1px solid rgba(226,201,126,0.2)",
        }}
      >
        <p
          className="font-exo2 whitespace-pre-wrap text-sm"
          style={{ color: "var(--text-primary)" }}
        >
          {message.content}
        </p>
      </div>
    </div>
  );
}

function errorKindLabel(kind: string | undefined): string {
  switch (kind) {
    case "timeout":
      return "Response timed out";
    case "llm_failure":
      return "Connection issue";
    case "empty_reply":
      return "No reply received";
    default:
      return "Response issue";
  }
}


function AssistantBubble({
  message,
  onConfirmWebSearch,
}: {
  message: ChatMessage;
  onConfirmWebSearch?: (query: string) => void;
}) {
  const hasContent = message.content.trim().length > 0;
  // Coral styling flags degraded fallback replies.
  const isError = message.isError === true;
  const bubbleStyle = isError
    ? {
        background: "rgba(255,112,67,0.08)",
        border: "1px solid rgba(255,112,67,0.35)",
        color: "var(--text-primary)",
      }
    : {
        background: "var(--bg-3)",
        border: "1px solid var(--border)",
        color: "var(--text-primary)",
      };
  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] space-y-2">
        {message.agentName && (
          <p
            className="font-orbitron px-1 text-[10px] uppercase"
            style={{
              color: "var(--text-muted)",
              letterSpacing: "0.18em",
            }}
          >
            {message.agentName}
          </p>
        )}
        {hasContent && (
          <div
            className="font-exo2 rounded-2xl px-4 py-2.5 text-sm"
            style={bubbleStyle}
          >
            {isError && (
              <div
                className="cosmic-label mb-1.5 flex items-center gap-1.5"
                style={{ color: "var(--accent-coral)" }}
              >
                <AlertTriangle className="h-3 w-3" />
                <span>{errorKindLabel(message.errorKind)}</span>
              </div>
            )}
            {message.aggregatedReasoning && (
              <ReasoningDisclosure trail={message.aggregatedReasoning} />
            )}
            <p className="whitespace-pre-wrap">{message.content}</p>
          </div>
        )}
        {message.citations && message.citations.length > 0 && (
          <CitationChips citations={message.citations} />
        )}
        {message.catalogGrounding && (
          <CatalogGroundingFooter grounding={message.catalogGrounding} />
        )}
        {message.confirmWebSearch && (
          <ConfirmWebSearchPrompt
            query={message.confirmWebSearch.query}
            onConfirm={onConfirmWebSearch}
          />
        )}
        {message.suggestPanel && (
          <SuggestPanelHint
            messageId={message.id}
            panel={message.suggestPanel.panel}
            autoOpen={message.suggestPanel.autoOpen}
          />
        )}
        {message.suggestMode && (
          <SuggestModeBanner targetMode={message.suggestMode.targetMode} />
        )}
      </div>
    </div>
  );
}

function SuggestModeBanner({ targetMode }: { targetMode: ChatMode }) {
  const setMode = useChatStore((s) => s.setMode);
  const { t } = useT();
  const label = t(`chat.modes.${targetMode}` as Parameters<typeof t>[0]);
  return (
    <button
      type="button"
      onClick={() => setMode(targetMode)}
      className="font-orbitron inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[10px] uppercase transition-colors hover:brightness-110"
      style={{
        background: "rgba(96,165,250,0.08)",
        border: "1px solid rgba(96,165,250,0.35)",
        color: "rgb(96,165,250)",
        letterSpacing: "0.14em",
      }}
    >
      <ChevronRight className="h-3 w-3" aria-hidden />
      {t("chat.suggestMode.switchTo", { mode: label })}
    </button>
  );
}

function SuggestPanelHint({
  messageId,
  panel,
  autoOpen,
}: {
  messageId: string;
  panel: NotebookTool;
  autoOpen: boolean;
}) {
  const requestTool = useUiStore((s) => s.requestNotebookTool);
  const { t } = useT();
  const autoOpenedRef = useRef<string | null>(null);

  // Auto-open once per assistant message — keyed by message id so refreshing
  // the chat doesn't keep re-opening the dialog after the user closes it.
  useEffect(() => {
    if (!autoOpen) return;
    if (autoOpenedRef.current === messageId) return;
    autoOpenedRef.current = messageId;
    requestTool(panel);
  }, [autoOpen, messageId, panel, requestTool]);

  const Icon = PANEL_ICON[panel];
  const label = t(`chat.suggestPanel.${panel}` as Parameters<typeof t>[0]);
  return (
    <button
      type="button"
      onClick={() => requestTool(panel)}
      className="font-orbitron inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[10px] uppercase transition-colors hover:brightness-110"
      style={{
        background: "var(--accent-gold-dim)",
        border: "1px solid rgba(226,201,126,0.45)",
        color: "var(--accent-gold)",
        letterSpacing: "0.14em",
      }}
    >
      <Icon className="h-3 w-3" aria-hidden />
      {label}
    </button>
  );
}

const PANEL_ICON: Record<NotebookTool, typeof ScrollText> = {
  summary: ScrollText,
  quiz: ListChecks,
  flashcards: Layers,
};

function ConfirmWebSearchPrompt({
  query,
  onConfirm,
}: {
  query: string;
  onConfirm?: (query: string) => void;
}) {
  const [decided, setDecided] = useState<"yes" | "no" | null>(null);
  const { t } = useT();

  if (decided === "no") {
    return (
      <p
        className="font-exo2 px-1 text-[11px]"
        style={{ color: "var(--text-muted)" }}
      >
        {t("chat.confirmWebSearch.declined")}
      </p>
    );
  }

  if (decided === "yes") {
    return (
      <p
        className="font-exo2 px-1 text-[11px]"
        style={{ color: "var(--text-muted)" }}
      >
        {t("chat.confirmWebSearch.searching")}
      </p>
    );
  }

  return (
    <div
      className="flex flex-wrap items-center gap-2 rounded-xl px-3 py-2"
      style={{
        background: "rgba(96,165,250,0.06)",
        border: "1px solid rgba(96,165,250,0.25)",
      }}
    >
      <Globe
        className="h-3.5 w-3.5"
        style={{ color: "rgb(96,165,250)" }}
        aria-hidden
      />
      <span
        className="font-exo2 text-[12px]"
        style={{ color: "var(--text-secondary)" }}
      >
        {t("chat.confirmWebSearch.message")}
      </span>
      <div className="ml-auto flex items-center gap-1.5">
        <button
          type="button"
          onClick={() => {
            setDecided("yes");
            onConfirm?.(query);
          }}
          disabled={!onConfirm}
          className="font-orbitron rounded-md px-2.5 py-1 text-[10px] uppercase transition-colors disabled:cursor-not-allowed disabled:opacity-40"
          style={{
            background: "var(--accent-gold-dim)",
            border: "1px solid rgba(226,201,126,0.45)",
            color: "var(--accent-gold)",
            letterSpacing: "0.14em",
          }}
        >
          {t("chat.confirmWebSearch.yes")}
        </button>
        <button
          type="button"
          onClick={() => setDecided("no")}
          className="font-orbitron rounded-md px-2.5 py-1 text-[10px] uppercase transition-colors"
          style={{
            background: "transparent",
            border: "1px solid var(--border)",
            color: "var(--text-muted)",
            letterSpacing: "0.14em",
          }}
        >
          {t("chat.confirmWebSearch.no")}
        </button>
      </div>
    </div>
  );
}

function CatalogGroundingFooter({ grounding }: { grounding: CatalogGrounding }) {
  const [open, setOpen] = useState(false);
  const hasWeb = (grounding.web_sources?.length ?? 0) > 0;
  return (
    <div className="space-y-1.5">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 transition-colors"
        style={{
          background: open
            ? "rgba(226,201,126,0.12)"
            : "rgba(226,201,126,0.05)",
          border: "1px solid rgba(226,201,126,0.25)",
        }}
        aria-expanded={open}
        aria-label="Toggle catalog sources"
      >
        <Sparkles
          className="h-3 w-3"
          style={{ color: "var(--accent-gold)" }}
          aria-hidden
        />
        <span
          className="font-orbitron text-[10px] uppercase"
          style={{
            color: "var(--accent-gold)",
            letterSpacing: "0.16em",
          }}
        >
          Grounded in {grounding.row_count}{" "}
          {grounding.row_count === 1 ? "row" : "rows"}
          {hasWeb ? ` + ${grounding.web_sources!.length} web` : ""}
        </span>
        {open ? (
          <ChevronDown
            className="h-3 w-3"
            style={{ color: "var(--accent-gold)" }}
          />
        ) : (
          <ChevronRight
            className="h-3 w-3"
            style={{ color: "var(--accent-gold)" }}
          />
        )}
      </button>
      {open && (
        <div
          className="space-y-2 rounded-md px-3 py-2.5"
          style={{
            background: "rgba(226,201,126,0.04)",
            border: "1px solid rgba(226,201,126,0.18)",
          }}
        >
          <p
            className="font-space-mono text-[10px] uppercase"
            style={{
              color: "var(--text-muted)",
              letterSpacing: "0.16em",
            }}
          >
            From {grounding.source} search — &ldquo;{grounding.query}&rdquo;
          </p>
          {grounding.rows.length > 0 ? (
            <ul className="space-y-1">
              {grounding.rows.map((row, idx) => (
                <li
                  key={`${row.name}-${idx}`}
                  className="font-exo2 flex flex-wrap items-baseline gap-2 text-xs"
                >
                  <span
                    className="font-space-mono"
                    style={{ color: "var(--accent-teal)" }}
                  >
                    {row.name}
                  </span>
                  {row.object_type && (
                    <span style={{ color: "var(--text-secondary)" }}>
                      {row.object_type}
                    </span>
                  )}
                  {row.ra_deg !== null && row.dec_deg !== null && (
                    <span
                      className="font-space-mono text-[10px] tabular-nums"
                      style={{ color: "var(--text-muted)" }}
                    >
                      RA {row.ra_deg.toFixed(4)}° · Dec {row.dec_deg.toFixed(4)}°
                    </span>
                  )}
                </li>
              ))}
              {grounding.row_count > grounding.rows.length && (
                <li
                  className="font-exo2 text-[11px] italic"
                  style={{ color: "var(--text-muted)" }}
                >
                  …and {grounding.row_count - grounding.rows.length} more rows in
                  the full search result.
                </li>
              )}
            </ul>
          ) : (
            <p
              className="font-exo2 text-xs italic"
              style={{ color: "var(--text-muted)" }}
            >
              Row metadata wasn&apos;t included with this answer.
            </p>
          )}
          {hasWeb && (
            <div className="space-y-1 border-t pt-2"
              style={{ borderColor: "rgba(226,201,126,0.18)" }}
            >
              <p
                className="font-space-mono flex items-center gap-1.5 text-[10px] uppercase"
                style={{
                  color: "var(--text-muted)",
                  letterSpacing: "0.16em",
                }}
              >
                <Globe className="h-3 w-3" aria-hidden /> Web sources
              </p>
              <ul className="space-y-1">
                {grounding.web_sources!.map((src, idx) => (
                  <li key={`${src.url}-${idx}`}>
                    <a
                      href={src.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-exo2 inline-flex items-center gap-1 text-xs hover:underline"
                      style={{ color: "var(--accent-blue)" }}
                    >
                      <ExternalLink className="h-3 w-3 shrink-0" aria-hidden />
                      <span>{src.title}</span>
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function CitationChips({ citations }: { citations: Citation[] }) {
  const [open, setOpen] = useState<number | null>(null);
  const { t } = useT();
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-1.5">
        <BookOpen
          className="h-3 w-3"
          style={{ color: "var(--accent-teal)" }}
          aria-hidden
        />
        <span
          className="font-orbitron text-[10px] uppercase"
          style={{
            color: "var(--text-muted)",
            letterSpacing: "0.18em",
          }}
        >
          {t("chat.sources", { n: citations.length })}
        </span>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {citations.map((c, idx) => {
          const isOpen = open === idx;
          const chunkSuffix = c.chunk_id ? `·${c.chunk_id.slice(-4)}` : "";
          const docLabel = c.document_id
            ? c.document_id.slice(0, 8)
            : "source";
          return (
            <button
              key={`${c.document_id}-${c.chunk_id || idx}`}
              type="button"
              onClick={() => setOpen(isOpen ? null : idx)}
              className="flex max-w-full items-center gap-1 rounded-md px-2 py-1 text-left transition-colors"
              style={{
                background: isOpen
                  ? "rgba(77,208,225,0.15)"
                  : "rgba(77,208,225,0.06)",
                border: "1px solid rgba(77,208,225,0.25)",
              }}
              aria-expanded={isOpen}
              aria-label={`Source ${idx + 1}: ${c.snippet.slice(0, 80)}`}
            >
              <span
                className="font-orbitron text-[10px] uppercase"
                style={{
                  color: "var(--accent-teal)",
                  letterSpacing: "0.14em",
                }}
              >
                #{idx + 1}
              </span>
              <span
                className="font-space-mono truncate text-[10px]"
                style={{ color: "var(--text-muted)", maxWidth: "120px" }}
                title={`${c.document_id}${chunkSuffix}`}
              >
                {docLabel}
                {chunkSuffix}
              </span>
              {c.score > 0 && (
                <span
                  className="font-space-mono text-[10px] tabular-nums"
                  style={{ color: "var(--accent-gold)" }}
                >
                  {c.score.toFixed(2)}
                </span>
              )}
            </button>
          );
        })}
      </div>
      {open !== null && citations[open] && (
        <div
          className="font-exo2 rounded-md px-3 py-2 text-xs"
          style={{
            background: "rgba(77,208,225,0.04)",
            border: "1px solid rgba(77,208,225,0.18)",
            color: "var(--text-secondary)",
          }}
        >
          <p className="whitespace-pre-wrap leading-relaxed">
            {citations[open].snippet}
          </p>
        </div>
      )}
    </div>
  );
}


function SystemPill({ message }: { message: ChatMessage }) {
  // Catch-all for non-step system messages.
  const [open, setOpen] = useState(false);
  return (
    <div
      className="rounded-lg border border-dashed px-3 py-2 text-xs"
      style={{
        borderColor: "var(--border)",
        background: "rgba(255,255,255,0.02)",
        color: "var(--text-muted)",
      }}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-1 text-left"
        aria-expanded={open}
      >
        {open ? (
          <ChevronDown className="h-3 w-3" />
        ) : (
          <ChevronRight className="h-3 w-3" />
        )}
        <span
          className="font-orbitron text-[10px] uppercase"
          style={{
            color: "var(--text-secondary)",
            letterSpacing: "0.18em",
          }}
        >
          System
        </span>
      </button>
      {open && (
        <p
          className="font-exo2 mt-2 whitespace-pre-wrap"
          style={{ color: "var(--text-secondary)" }}
        >
          {message.content}
        </p>
      )}
    </div>
  );
}
