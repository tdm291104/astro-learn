"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowRight,
  CheckCircle2,
  RotateCcw,
  Settings2,
  Sparkles,
  Trophy,
  XCircle,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { fadeInUp, fadeTransition } from "@/animations/fade";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Slider } from "@/components/ui/slider";
import {
  useGenerateQuizMutation,
  useNotebookArtifact,
} from "@/hooks/useNotebookQA";
import { useT } from "@/hooks/useT";
import { cn } from "@/lib/utils";
import type {
  QuizDifficulty,
  QuizItem,
  QuizRequest,
  QuizResponse,
} from "@/types/notebook.types";

// Narrow a persisted artifact payload back into QuizResponse shape.
function asQuiz(payload: unknown): QuizResponse | null {
  if (!payload || typeof payload !== "object") return null;
  const p = payload as { questions?: unknown };
  if (!Array.isArray(p.questions)) return null;
  return { questions: p.questions as QuizItem[] };
}

const DEFAULT_QUESTIONS = 5;
const MIN_QUESTIONS = 1;
const MAX_QUESTIONS = 30;
const DIFFICULTIES: QuizDifficulty[] = ["easy", "medium", "hard"];

type Screen = "config" | "running" | "results";

export function QuizRunner({ notebookId }: { notebookId: string }) {
  const [screen, setScreen] = useState<Screen>("config");
  const [config, setConfig] = useState<Required<QuizRequest>>({
    n_questions: DEFAULT_QUESTIONS,
    difficulty: "medium",
  });
  const [quiz, setQuiz] = useState<QuizResponse | null>(null);

  const generate = useGenerateQuizMutation(notebookId);
  // Persisted artifact lets reopen skip the config screen.
  const artifactQuery = useNotebookArtifact(notebookId, "quiz");

  const seeded = useRef(false);
  useEffect(() => {
    if (seeded.current || artifactQuery.isLoading) return;
    seeded.current = true;
    const art = artifactQuery.data;
    if (!art) return;
    const params = (art.params ?? {}) as {
      n_questions?: number;
      difficulty?: QuizDifficulty;
    };
    if (typeof params.n_questions === "number") {
      setConfig((c) => ({ ...c, n_questions: params.n_questions! }));
    }
    if (params.difficulty) {
      setConfig((c) => ({ ...c, difficulty: params.difficulty! }));
    }
    const cachedQuiz = asQuiz(art.payload);
    if (cachedQuiz && cachedQuiz.questions.length > 0) {
      setQuiz(cachedQuiz);
      setScreen("running");
    }
  }, [artifactQuery.data, artifactQuery.isLoading]);

  const startQuiz = (req: QuizRequest) => {
    generate.mutate(req, {
      onSuccess: (resp) => {
        setQuiz(resp);
        setScreen("running");
      },
    });
  };

  const handleGenerate = () => startQuiz(config);

  return (
    <div className="relative">
      <AnimatePresence mode="wait" initial={false}>
        {screen === "config" && (
          <motion.div
            key="config"
            variants={fadeInUp}
            initial="initial"
            animate="animate"
            exit="exit"
            transition={fadeTransition}
          >
            {generate.isPending ? (
              <ConfigSkeleton />
            ) : (
              <ConfigScreen
                config={config}
                onChange={setConfig}
                onGenerate={handleGenerate}
              />
            )}
          </motion.div>
        )}

        {screen === "running" && quiz && (
          <motion.div
            key="running"
            variants={fadeInUp}
            initial="initial"
            animate="animate"
            exit="exit"
            transition={fadeTransition}
          >
            <RunningScreen
              quiz={quiz}
              onComplete={() => setScreen("results")}
            />
          </motion.div>
        )}

        {screen === "results" && quiz && (
          <motion.div
            key="results"
            variants={fadeInUp}
            initial="initial"
            animate="animate"
            exit="exit"
            transition={fadeTransition}
          >
            <ResultsScreen
              quiz={quiz}
              answers={resultsRef.current}
              onRetrySame={() => {
                resultsRef.current = [];
                startQuiz(config);
              }}
              onNewConfig={() => {
                resultsRef.current = [];
                setQuiz(null);
                setScreen("config");
              }}
              isRegenerating={generate.isPending}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

const resultsRef: { current: number[] } = { current: [] };

function ConfigScreen({
  config,
  onChange,
  onGenerate,
}: {
  config: Required<QuizRequest>;
  onChange: (c: Required<QuizRequest>) => void;
  onGenerate: () => void;
}) {
  const { t } = useT();
  const difficultyLabels: Record<QuizDifficulty, string> = {
    easy: t("notebook.quiz_.easy"),
    medium: t("notebook.quiz_.medium"),
    hard: t("notebook.quiz_.hard"),
  };
  return (
    <div className="cosmic-card space-y-6 p-6">
      <header className="space-y-1">
        <h2
          className="font-orbitron flex items-center gap-2 text-lg font-semibold uppercase"
          style={{
            color: "var(--text-primary)",
            letterSpacing: "0.14em",
          }}
        >
          <Settings2
            className="h-4 w-4"
            style={{ color: "var(--accent-gold)" }}
          />
          {t("notebook.quiz_.settings")}
        </h2>
        <p
          className="font-exo2 text-sm"
          style={{ color: "var(--text-secondary)" }}
        >
          {t("notebook.quiz_.settingsHint")}
        </p>
      </header>

      <div className="space-y-5">
        <div className="space-y-2">
          <label
            htmlFor="n-questions"
            className="cosmic-label flex items-center justify-between"
          >
            <span>{t("notebook.quiz_.questions")}</span>
            <span
              className="font-space-mono text-xs"
              style={{ color: "var(--accent-gold)" }}
            >
              {config.n_questions}
            </span>
          </label>
          <Slider
            id="n-questions"
            min={MIN_QUESTIONS}
            max={MAX_QUESTIONS}
            step={1}
            value={config.n_questions}
            onValueChange={(v) =>
              onChange({
                ...config,
                n_questions: typeof v === "number" ? v : v[0],
              })
            }
            aria-label="Number of questions"
          />
        </div>

        <div className="space-y-2">
          <label className="cosmic-label">{t("notebook.quiz_.difficulty")}</label>
          <div className="flex flex-col gap-2 sm:flex-row">
            {DIFFICULTIES.map((d) => {
              const active = config.difficulty === d;
              return (
                <button
                  key={d}
                  type="button"
                  onClick={() => onChange({ ...config, difficulty: d })}
                  className={cn(
                    "font-orbitron flex-1 rounded-lg px-4 py-2 text-xs uppercase transition-all duration-200",
                  )}
                  style={{
                    letterSpacing: "0.16em",
                    border: active
                      ? "1px solid var(--accent-gold)"
                      : "1px solid var(--border)",
                    background: active
                      ? "var(--accent-gold-dim)"
                      : "transparent",
                    color: active
                      ? "var(--accent-gold)"
                      : "var(--text-secondary)",
                  }}
                >
                  {difficultyLabels[d]}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      <button
        onClick={onGenerate}
        className="cosmic-btn-primary w-full sm:w-auto"
      >
        <Sparkles className="h-4 w-4" />
        {t("notebook.quiz_.generate")}
      </button>
    </div>
  );
}

function ConfigSkeleton() {
  return (
    <div className="cosmic-card space-y-4 p-6">
      <Skeleton className="h-5 w-40" />
      <Skeleton className="h-3 w-2/3" />
      <Skeleton className="h-2 w-full" />
      <div className="flex gap-2">
        <Skeleton className="h-9 flex-1" />
        <Skeleton className="h-9 flex-1" />
        <Skeleton className="h-9 flex-1" />
      </div>
      <Skeleton className="h-9 w-40" />
    </div>
  );
}

function RunningScreen({
  quiz,
  onComplete,
}: {
  quiz: QuizResponse;
  onComplete: () => void;
}) {
  const { t } = useT();
  const total = quiz.questions.length;
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<(number | null)[]>(() =>
    Array(total).fill(null),
  );
  const [draft, setDraft] = useState<number | null>(null);

  useEffect(() => {
    setDraft(null);
  }, [index]);

  const item = quiz.questions[index];
  const submittedChoice = answers[index];
  const isSubmitted = submittedChoice != null;

  const submit = () => {
    if (draft == null || isSubmitted) return;
    const next = answers.slice();
    next[index] = draft;
    setAnswers(next);
  };

  const next = () => {
    if (index < total - 1) {
      setIndex(index + 1);
      return;
    }
    resultsRef.current = answers.map((a) => (a == null ? -1 : a));
    onComplete();
  };

  const progressPct = ((index + (isSubmitted ? 1 : 0)) / total) * 100;

  return (
    <div className="cosmic-card space-y-5 p-6">
      <div className="space-y-2">
        <div
          className="font-space-mono flex items-center justify-between text-xs uppercase"
          style={{
            color: "var(--text-muted)",
            letterSpacing: "0.16em",
          }}
        >
          <span>
            {t("notebook.quiz_.progress", {
              index: String(index + 1).padStart(2, "0"),
              total: String(total).padStart(2, "0"),
            })}
          </span>
        </div>
        <Progress value={progressPct} />
      </div>

      <h3
        className="font-exo2 text-base font-semibold leading-relaxed sm:text-lg"
        style={{ color: "var(--text-primary)" }}
      >
        {item.question}
      </h3>

      <ul className="space-y-2">
        {item.options.map((opt, i) => (
          <li key={i}>
            <OptionButton
              index={i}
              text={opt}
              draftSelected={draft === i}
              isSubmitted={isSubmitted}
              isCorrect={item.correct_index === i}
              wasSelected={submittedChoice === i}
              onClick={() => {
                if (!isSubmitted) setDraft(i);
              }}
            />
          </li>
        ))}
      </ul>

      {isSubmitted && item.explanation && (
        <motion.div
          variants={fadeInUp}
          initial="initial"
          animate="animate"
          transition={fadeTransition}
          className="rounded-lg p-4"
          style={{
            background: "var(--bg-3)",
            border: "1px solid var(--border)",
          }}
        >
          <p
            className="cosmic-label mb-2"
            style={{ color: "var(--accent-gold)" }}
          >
            {t("notebook.quiz_.explanation")}
          </p>
          <p
            className="font-exo2 text-sm leading-relaxed"
            style={{ color: "var(--text-primary)" }}
          >
            {item.explanation}
          </p>
        </motion.div>
      )}

      <div className="flex justify-end gap-2">
        {!isSubmitted ? (
          <button
            onClick={submit}
            disabled={draft == null}
            className="cosmic-btn-primary"
          >
            {t("notebook.quiz_.submit")}
          </button>
        ) : (
          <button onClick={next} className="cosmic-btn-primary">
            {index === total - 1 ? t("notebook.quiz_.results") : t("notebook.quiz_.next")}
            <ArrowRight className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  );
}

function OptionButton({
  index,
  text,
  draftSelected,
  isSubmitted,
  isCorrect,
  wasSelected,
  onClick,
}: {
  index: number;
  text: string;
  draftSelected: boolean;
  isSubmitted: boolean;
  isCorrect: boolean;
  wasSelected: boolean;
  onClick: () => void;
}) {
  const showCorrect = isSubmitted && isCorrect;
  const showSelectedWrong = isSubmitted && wasSelected && !isCorrect;
  const showCorrectGhost = isSubmitted && !wasSelected && isCorrect;

  let borderColor = "var(--border)";
  let background = "rgba(255,255,255,0.02)";
  let color = "var(--text-primary)";

  if (!isSubmitted && draftSelected) {
    borderColor = "var(--accent-gold)";
    background = "var(--accent-gold-dim)";
  }
  if (showCorrect && wasSelected) {
    borderColor = "rgba(76,175,80,0.5)";
    background = "rgba(76,175,80,0.12)";
    color = "#81c784";
  }
  if (showCorrectGhost) {
    borderColor = "rgba(76,175,80,0.4)";
    color = "#81c784";
  }
  if (showSelectedWrong) {
    borderColor = "rgba(255,112,67,0.5)";
    background = "rgba(255,112,67,0.12)";
    color = "var(--accent-coral)";
  }

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={isSubmitted}
      className={cn(
        "font-exo2 flex w-full items-center gap-3 rounded-lg px-4 py-3 text-left text-sm transition-all duration-200",
        !isSubmitted && !draftSelected && "hover:translate-x-[2px]",
        isSubmitted && "cursor-default",
      )}
      style={{
        background,
        border: `1px solid ${borderColor}`,
        color,
      }}
      aria-pressed={draftSelected || wasSelected}
    >
      <span
        aria-hidden
        className="font-orbitron flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold"
        style={{
          background: draftSelected
            ? "var(--accent-gold)"
            : "transparent",
          color: draftSelected ? "#050500" : "var(--text-muted)",
          border: `1px solid ${draftSelected ? "var(--accent-gold)" : "var(--border)"}`,
        }}
      >
        {String.fromCharCode(65 + index)}
      </span>
      <span className="flex-1">{text}</span>
      {showCorrect && wasSelected && (
        <CheckCircle2
          className="h-4 w-4 shrink-0"
          style={{ color: "#81c784" }}
        />
      )}
      {showCorrectGhost && (
        <CheckCircle2
          className="h-4 w-4 shrink-0 opacity-60"
          style={{ color: "#81c784" }}
        />
      )}
      {showSelectedWrong && (
        <XCircle
          className="h-4 w-4 shrink-0"
          style={{ color: "var(--accent-coral)" }}
        />
      )}
    </button>
  );
}

function ResultsScreen({
  quiz,
  answers,
  onRetrySame,
  onNewConfig,
  isRegenerating,
}: {
  quiz: QuizResponse;
  answers: number[];
  onRetrySame: () => void;
  onNewConfig: () => void;
  isRegenerating: boolean;
}) {
  const { t } = useT();
  const total = quiz.questions.length;
  const correct = quiz.questions.reduce((acc, q, i) => {
    return acc + (answers[i] === q.correct_index ? 1 : 0);
  }, 0);
  const pct = total === 0 ? 0 : Math.round((correct / total) * 100);

  const message = performanceMessage(pct, t);

  return (
    <div className="cosmic-card space-y-6 p-8 text-center">
      <div
        className="mx-auto flex h-16 w-16 items-center justify-center rounded-full"
        style={{ background: "var(--accent-gold-dim)" }}
      >
        <Trophy
          className="h-7 w-7"
          style={{ color: "var(--accent-gold)" }}
        />
      </div>

      <div className="space-y-2">
        <p className="cosmic-label">{t("notebook.quiz_.complete")}</p>
        <h2
          className="font-orbitron text-4xl font-bold tabular-nums"
          style={{
            color: "var(--accent-gold)",
            letterSpacing: "0.06em",
          }}
        >
          {correct}
          <span style={{ color: "var(--text-muted)" }}>/{total}</span>
        </h2>
        <p
          className="font-exo2 text-sm"
          style={{ color: "var(--text-secondary)" }}
        >
          <span
            className="font-space-mono"
            style={{ color: "var(--accent-gold)" }}
          >
            {pct}%
          </span>
          {" — "}
          <span>{message}</span>
        </p>
      </div>

      <Progress value={pct} className="mx-auto max-w-md" />

      <div className="flex flex-col items-center justify-center gap-2 sm:flex-row">
        <button
          onClick={onRetrySame}
          disabled={isRegenerating}
          className="cosmic-btn-primary"
        >
          <RotateCcw className="h-4 w-4" />
          {isRegenerating ? t("common.generating") : t("notebook.quiz_.retry")}
        </button>
        <button
          onClick={onNewConfig}
          disabled={isRegenerating}
          className="cosmic-btn-outline"
        >
          <Settings2 className="h-4 w-4" />
          {t("notebook.quiz_.newConfig")}
        </button>
      </div>
    </div>
  );
}

function performanceMessage(
  pct: number,
  t: ReturnType<typeof useT>["t"],
): string {
  if (pct >= 90) return t("notebook.quiz_.excellent");
  if (pct >= 80) return t("notebook.quiz_.excellent");
  if (pct >= 60) return t("notebook.quiz_.good");
  if (pct >= 40) return t("notebook.quiz_.practice");
  return t("notebook.quiz_.review");
}

export type { QuizItem };
