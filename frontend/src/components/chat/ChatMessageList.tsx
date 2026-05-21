"use client";

import { motion } from "framer-motion";
import { useCallback, useLayoutEffect, useRef } from "react";

import { staggerContainer, staggerItem } from "@/animations/stagger";
import { ChatMessageBubble } from "@/components/chat/ChatMessageBubble";
import { useT } from "@/hooks/useT";
import { useChatStore } from "@/stores/chatStore";
import type { ChatMessage } from "@/stores/chatStore";

// Within this distance from bottom, auto-scroll on new messages.
const PIN_THRESHOLD_PX = 32;

export function ChatMessageList({
  messages,
  onExampleClick,
  onConfirmWebSearch,
  streamPhase,
}: {
  messages: ChatMessage[];
  onExampleClick: (text: string) => void;
  // Re-sends a query with force_web_search=true; rendered as a Yes button
  // when the orchestrator returns extra.action="confirm_web_search".
  onConfirmWebSearch?: (query: string) => void;
  // Heartbeat phase from useChat; surfaces a pill during slow LLM stalls.
  streamPhase?: string | null;
}) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  // Defaults true so the first message scrolls into view.
  const isPinnedToBottom = useRef(true);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const pendingReasoning = useChatStore((s) => s.pendingReasoning);
  const { t } = useT();

  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const distanceFromBottom =
      el.scrollHeight - (el.scrollTop + el.clientHeight);
    isPinnedToBottom.current = distanceFromBottom <= PIN_THRESHOLD_PX;
  }, []);

  // useLayoutEffect avoids flash before paint; respect user scroll position.
  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    if (!isPinnedToBottom.current) return;
    el.scrollTop = el.scrollHeight;
  }, [messages.length, streamPhase, pendingReasoning]);

  const liveLabel = currentActivityLabel(streamPhase, pendingReasoning, t);

  if (messages.length === 0) {
    return (
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="min-h-0 flex-1 overflow-y-auto p-5"
      >
        <EmptyState onExampleClick={onExampleClick} />
      </div>
    );
  }

  return (
    <div
      ref={scrollRef}
      onScroll={handleScroll}
      className="min-h-0 flex-1 overflow-y-auto p-5"
    >
      <motion.ul
        variants={staggerContainer}
        initial="initial"
        animate="animate"
        className="space-y-3"
      >
        {messages.map((m) => (
          <motion.li key={m.id} variants={staggerItem}>
            <ChatMessageBubble
              message={m}
              onConfirmWebSearch={onConfirmWebSearch}
            />
          </motion.li>
        ))}
      </motion.ul>
      {(isStreaming || liveLabel) && (
        <ThinkingPill label={liveLabel ?? t("chat.thinking")} />
      )}
    </div>
  );
}

function ThinkingPill({ label }: { label: string }) {
  return (
    <div
      className="mt-3 flex items-center gap-2"
      role="status"
      aria-live="polite"
    >
      <span
        className="h-2 w-2 animate-pulse rounded-full"
        style={{ background: "var(--accent-gold)" }}
        aria-hidden
      />
      <span
        className="font-orbitron text-[10px] uppercase"
        style={{
          color: "var(--text-muted)",
          letterSpacing: "0.18em",
        }}
      >
        {label}
      </span>
    </div>
  );
}

// Build a friendly live label: pending reasoning > stream phase > generic.
function currentActivityLabel(
  phase: string | null | undefined,
  pending: ReturnType<typeof useChatStore.getState>["pendingReasoning"],
  t: ReturnType<typeof useT>["t"],
): string | null {
  if (pending) {
    const lastStep = pending.steps[pending.steps.length - 1];
    if (lastStep) {
      const lastTool =
        lastStep.tool_invocations[lastStep.tool_invocations.length - 1];
      if (lastTool && lastTool.result === null) {
        return t("chat.calling", { tool: lastTool.name });
      }
      return t("chat.running", { agent: lastStep.agent_name });
    }
  }
  if (phase) return phaseLabel(phase, t);
  return null;
}

function phaseLabel(
  phase: string,
  t: ReturnType<typeof useT>["t"],
): string {
  switch (phase) {
    case "planning":
      return t("chat.planning");
    case "reading_header":
      return t("chat.readingHeader");
    case "deciding":
      return t("chat.deciding");
    case "analyzing":
      return t("chat.analyzing");
    case "interpreting":
      return t("chat.interpreting");
    default:
      return t("chat.working");
  }
}

function EmptyState({
  onExampleClick,
}: {
  onExampleClick: (text: string) => void;
}) {
  const { t } = useT();
  const prompts = [
    t("chat.examples.summarize"),
    t("chat.examples.searchM31"),
    t("chat.examples.quiz"),
  ];
  return (
    <div className="mx-auto flex h-full max-w-2xl flex-col items-center justify-center gap-5 py-12 text-center">
      <span
        className="text-5xl leading-none"
        style={{ color: "var(--accent-gold)" }}
        aria-hidden
      >
        ✦
      </span>
      <div className="space-y-2">
        <h2
          className="font-orbitron text-lg font-semibold uppercase"
          style={{
            color: "var(--text-primary)",
            letterSpacing: "0.18em",
          }}
        >
          {t("chat.title")}
        </h2>
        <p
          className="font-exo2 text-sm"
          style={{ color: "var(--text-secondary)" }}
        >
          {t("chat.tagline")}
        </p>
      </div>
      <div className="flex flex-wrap items-center justify-center gap-2 pt-2">
        {prompts.map((prompt) => (
          <button
            key={prompt}
            type="button"
            onClick={() => onExampleClick(prompt)}
            className="font-exo2 rounded-full px-3.5 py-1.5 text-sm transition-colors hover:brightness-110"
            style={{
              background: "var(--accent-gold-dim)",
              border: "1px solid rgba(226,201,126,0.3)",
              color: "var(--accent-gold)",
            }}
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  );
}
