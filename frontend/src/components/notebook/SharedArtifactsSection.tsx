"use client";

import { motion } from "framer-motion";
import {
  BookOpen,
  ChevronLeft,
  ChevronRight,
  FileText,
  Layers,
  Sparkles,
} from "lucide-react";
import { useState } from "react";

import { fadeInUp, fadeTransition } from "@/animations/fade";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useSharedArtifact } from "@/hooks/useSharedArtifact";
import { useT } from "@/hooks/useT";
import type { TranslationKey } from "@/lib/i18n/messages";
import { formatRelativeTime } from "@/lib/utils";
import type {
  Flashcard,
  FlashcardResponse,
  NotebookArtifactKind,
  NotebookArtifactPayload,
  QuizItem,
  QuizResponse,
  SummarizeResponse,
} from "@/types/notebook.types";

type TabKey = NotebookArtifactKind;

const TABS: { key: TabKey; labelKey: TranslationKey; icon: typeof Sparkles }[] = [
  { key: "summary", labelKey: "notebook.summary", icon: Sparkles },
  { key: "quiz", labelKey: "notebook.quiz", icon: BookOpen },
  { key: "flashcards", labelKey: "notebook.flashcards", icon: Layers },
];

export function SharedArtifactsSection({ token }: { token: string }) {
  const { t } = useT();
  const [tab, setTab] = useState<TabKey>("summary");

  return (
    <section className="mt-10">
      <div className="mb-4 flex items-baseline justify-between">
        <h2
          className="font-orbitron text-sm font-semibold uppercase"
          style={{ color: "var(--text-primary)", letterSpacing: "0.18em" }}
        >
          {t("share.ownerMaterials")}
        </h2>
        <span
          className="font-space-mono text-[11px] uppercase"
          style={{ color: "var(--text-muted)", letterSpacing: "0.16em" }}
        >
          {t("share.readOnly")}
        </span>
      </div>

      <Tabs value={tab} onValueChange={(v) => setTab(v as TabKey)}>
        <TabsList className="grid w-full grid-cols-3">
          {TABS.map(({ key, labelKey, icon: Icon }) => (
            <TabsTrigger key={key} value={key} className="gap-2">
              <Icon className="h-3.5 w-3.5" />
              {t(labelKey)}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="summary" className="mt-4">
          <ArtifactPane token={token} kind="summary">
            {(a) => <SummaryRenderer artifact={a} />}
          </ArtifactPane>
        </TabsContent>
        <TabsContent value="quiz" className="mt-4">
          <ArtifactPane token={token} kind="quiz">
            {(a) => <QuizRenderer artifact={a} />}
          </ArtifactPane>
        </TabsContent>
        <TabsContent value="flashcards" className="mt-4">
          <ArtifactPane token={token} kind="flashcards">
            {(a) => <FlashcardsRenderer artifact={a} />}
          </ArtifactPane>
        </TabsContent>
      </Tabs>
    </section>
  );
}

function ArtifactPane({
  token,
  kind,
  children,
}: {
  token: string;
  kind: NotebookArtifactKind;
  children: (artifact: NotebookArtifactPayload) => React.ReactNode;
}) {
  const { data, isLoading, isError } = useSharedArtifact(token, kind);

  if (isLoading) return <Skeleton className="h-40 w-full rounded-2xl" />;
  if (isError) return <EmptyPane label="Couldn't load this material." />;
  if (!data) return <EmptyPane label="The owner hasn't generated this yet." />;

  return (
    <motion.div
      variants={fadeInUp}
      initial="initial"
      animate="animate"
      transition={fadeTransition}
    >
      <div className="cosmic-card p-5">
        <p
          className="font-space-mono mb-4 text-[10px] uppercase"
          style={{ color: "var(--text-muted)", letterSpacing: "0.16em" }}
        >
          Generated {formatRelativeTime(data.updated_at)}
        </p>
        {children(data)}
      </div>
    </motion.div>
  );
}

function EmptyPane({ label }: { label: string }) {
  return (
    <div
      className="font-exo2 rounded-2xl border-2 border-dashed py-12 text-center text-sm"
      style={{
        borderColor: "rgba(226,201,126,0.18)",
        color: "var(--text-muted)",
      }}
    >
      <FileText
        className="mx-auto mb-2 h-5 w-5 opacity-60"
        style={{ color: "var(--text-muted)" }}
      />
      {label}
    </div>
  );
}

// --- Summary ----------------------------------------------------------------

function asSummary(payload: unknown): SummarizeResponse | null {
  if (!payload || typeof payload !== "object") return null;
  const p = payload as { summary?: unknown; source_document_count?: unknown };
  if (
    typeof p.summary === "string" ||
    (Array.isArray(p.summary) && p.summary.every((s) => typeof s === "string"))
  ) {
    return {
      summary: p.summary as string | string[],
      source_document_count:
        typeof p.source_document_count === "number"
          ? p.source_document_count
          : 0,
    };
  }
  return null;
}

function SummaryRenderer({ artifact }: { artifact: NotebookArtifactPayload }) {
  const result = asSummary(artifact.payload);
  if (!result) return <EmptyPane label="Summary payload looks malformed." />;

  if (typeof result.summary === "string") {
    return (
      <p
        className="font-exo2 whitespace-pre-wrap text-sm leading-relaxed"
        style={{ color: "var(--text-primary)" }}
      >
        {result.summary}
      </p>
    );
  }

  return (
    <ul className="space-y-2">
      {result.summary.map((bullet, i) => (
        <li key={i} className="flex gap-3">
          <span
            className="font-space-mono mt-1 shrink-0 text-[10px]"
            style={{ color: "var(--accent-gold)" }}
          >
            {String(i + 1).padStart(2, "0")}
          </span>
          <span
            className="font-exo2 text-sm leading-relaxed"
            style={{ color: "var(--text-primary)" }}
          >
            {bullet}
          </span>
        </li>
      ))}
    </ul>
  );
}

// --- Quiz -------------------------------------------------------------------

function asQuiz(payload: unknown): QuizResponse | null {
  if (!payload || typeof payload !== "object") return null;
  const p = payload as { questions?: unknown };
  if (!Array.isArray(p.questions)) return null;
  return { questions: p.questions as QuizItem[] };
}

function QuizRenderer({ artifact }: { artifact: NotebookArtifactPayload }) {
  const quiz = asQuiz(artifact.payload);
  const [revealed, setRevealed] = useState<Set<number>>(new Set());

  if (!quiz || quiz.questions.length === 0)
    return <EmptyPane label="No quiz questions in this notebook." />;

  const toggle = (i: number) => {
    setRevealed((cur) => {
      const next = new Set(cur);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  };

  return (
    <ol className="space-y-5">
      {quiz.questions.map((q, i) => {
        const isOpen = revealed.has(i);
        return (
          <li key={i} className="space-y-3">
            <div className="flex items-baseline gap-3">
              <span
                className="font-space-mono shrink-0 text-xs"
                style={{ color: "var(--accent-gold)" }}
              >
                Q{String(i + 1).padStart(2, "0")}
              </span>
              <p
                className="font-exo2 text-sm font-medium"
                style={{ color: "var(--text-primary)" }}
              >
                {q.question}
              </p>
            </div>
            <ul className="ml-7 space-y-1.5">
              {q.options.map((opt, j) => {
                const isCorrect = isOpen && j === q.correct_index;
                return (
                  <li
                    key={j}
                    className="rounded-md border px-3 py-2 text-sm transition-colors"
                    style={{
                      borderColor: isCorrect
                        ? "rgba(120,200,140,0.45)"
                        : "var(--border)",
                      background: isCorrect
                        ? "rgba(120,200,140,0.10)"
                        : "transparent",
                      color: isCorrect
                        ? "rgb(120,200,140)"
                        : "var(--text-primary)",
                    }}
                  >
                    <span
                      className="font-space-mono mr-2 text-xs"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {String.fromCharCode(65 + j)}.
                    </span>
                    {opt}
                  </li>
                );
              })}
            </ul>
            <div className="ml-7 flex items-center gap-3">
              <button
                type="button"
                onClick={() => toggle(i)}
                className="cosmic-btn-ghost"
                style={{ padding: "0.3rem 0.7rem", fontSize: "0.75rem" }}
              >
                {isOpen ? "Hide answer" : "Reveal answer"}
              </button>
              {isOpen && q.explanation && (
                <p
                  className="font-exo2 text-xs italic"
                  style={{ color: "var(--text-secondary)" }}
                >
                  {q.explanation}
                </p>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

// --- Flashcards -------------------------------------------------------------

function asFlashcards(payload: unknown): Flashcard[] | null {
  if (!payload || typeof payload !== "object") return null;
  const p = payload as FlashcardResponse;
  if (!Array.isArray(p.cards)) return null;
  return p.cards;
}

function FlashcardsRenderer({
  artifact,
}: {
  artifact: NotebookArtifactPayload;
}) {
  const cards = asFlashcards(artifact.payload);
  const [index, setIndex] = useState(0);
  const [flipped, setFlipped] = useState(false);

  if (!cards || cards.length === 0)
    return <EmptyPane label="No flashcards in this notebook." />;

  const card = cards[Math.min(index, cards.length - 1)];
  const goPrev = () => {
    setFlipped(false);
    setIndex((i) => (i - 1 + cards.length) % cards.length);
  };
  const goNext = () => {
    setFlipped(false);
    setIndex((i) => (i + 1) % cards.length);
  };

  return (
    <div className="space-y-4">
      <button
        type="button"
        onClick={() => setFlipped((f) => !f)}
        className="block min-h-[180px] w-full rounded-xl border px-6 py-8 text-center transition-colors"
        style={{
          borderColor: flipped
            ? "rgba(110,170,240,0.32)"
            : "rgba(226,201,126,0.32)",
          background: flipped
            ? "rgba(110,170,240,0.06)"
            : "rgba(226,201,126,0.06)",
        }}
        aria-label="Flip card"
      >
        <span
          className="font-orbitron block text-[10px] uppercase"
          style={{
            color: flipped ? "var(--accent-blue)" : "var(--accent-gold)",
            letterSpacing: "0.22em",
          }}
        >
          {flipped ? "Back" : "Front"}
        </span>
        <p
          className="font-exo2 mt-3 text-base leading-relaxed"
          style={{ color: "var(--text-primary)" }}
        >
          {flipped ? card.back : card.front}
        </p>
      </button>

      <div className="flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={goPrev}
          className="cosmic-btn-ghost inline-flex items-center gap-1"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
          Prev
        </button>
        <span
          className="font-space-mono text-[11px] uppercase"
          style={{ color: "var(--text-muted)", letterSpacing: "0.16em" }}
        >
          {index + 1} / {cards.length}
        </span>
        <button
          type="button"
          onClick={goNext}
          className="cosmic-btn-ghost inline-flex items-center gap-1"
        >
          Next
          <ChevronRight className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}
