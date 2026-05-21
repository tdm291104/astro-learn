"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  ChevronLeft,
  ChevronRight,
  RotateCcw,
  Shuffle,
  Sparkles,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { fadeInUp, fadeTransition } from "@/animations/fade";
import { Skeleton } from "@/components/ui/skeleton";
import { Slider } from "@/components/ui/slider";
import {
  useGenerateFlashcardsMutation,
  useNotebookArtifact,
} from "@/hooks/useNotebookQA";
import { useT } from "@/hooks/useT";
import { cn } from "@/lib/utils";
import type { Flashcard, FlashcardRequest } from "@/types/notebook.types";

// Narrow a persisted artifact payload back into Flashcard[].
function asFlashcards(payload: unknown): Flashcard[] | null {
  if (!payload || typeof payload !== "object") return null;
  const p = payload as { cards?: unknown };
  if (!Array.isArray(p.cards)) return null;
  return p.cards as Flashcard[];
}

const DEFAULT_CARDS = 10;
const MIN_CARDS = 1;
const MAX_CARDS = 50;

type Screen = "config" | "deck";

export function FlashcardDeck({ notebookId }: { notebookId: string }) {
  const [screen, setScreen] = useState<Screen>("config");
  const [config, setConfig] = useState<Required<FlashcardRequest>>({
    n_cards: DEFAULT_CARDS,
  });
  const [cards, setCards] = useState<Flashcard[] | null>(null);

  const generate = useGenerateFlashcardsMutation(notebookId);
  // Persisted artifact lets reopen skip the config screen.
  const artifactQuery = useNotebookArtifact(notebookId, "flashcards");

  const seeded = useRef(false);
  useEffect(() => {
    if (seeded.current || artifactQuery.isLoading) return;
    seeded.current = true;
    const art = artifactQuery.data;
    if (!art) return;
    const params = (art.params ?? {}) as { n_cards?: number };
    if (typeof params.n_cards === "number") {
      setConfig({ n_cards: params.n_cards });
    }
    const cached = asFlashcards(art.payload);
    if (cached && cached.length > 0) {
      setCards(cached);
      setScreen("deck");
    }
  }, [artifactQuery.data, artifactQuery.isLoading]);

  const handleGenerate = () => {
    generate.mutate(config, {
      onSuccess: (resp) => {
        setCards(resp.cards);
        setScreen("deck");
      },
    });
  };

  const handleStartOver = () => {
    setCards(null);
    setScreen("config");
  };

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

        {screen === "deck" && cards && (
          <motion.div
            key="deck"
            variants={fadeInUp}
            initial="initial"
            animate="animate"
            exit="exit"
            transition={fadeTransition}
          >
            <DeckScreen cards={cards} onStartOver={handleStartOver} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function ConfigScreen({
  config,
  onChange,
  onGenerate,
}: {
  config: Required<FlashcardRequest>;
  onChange: (c: Required<FlashcardRequest>) => void;
  onGenerate: () => void;
}) {
  const { t } = useT();
  return (
    <div className="cosmic-card space-y-6 p-6">
      <header className="space-y-1">
        <h2
          className="font-orbitron text-lg font-semibold uppercase"
          style={{
            color: "var(--text-primary)",
            letterSpacing: "0.14em",
          }}
        >
          {t("notebook.flashcards_.settings")}
        </h2>
        <p
          className="font-exo2 text-sm"
          style={{ color: "var(--text-secondary)" }}
        >
          {t("notebook.flashcards_.settingsHint")}
        </p>
      </header>

      <div className="space-y-2">
        <label
          htmlFor="n-cards"
          className="cosmic-label flex items-center justify-between"
        >
          <span>{t("notebook.flashcards_.cards")}</span>
          <span
            className="font-space-mono text-xs"
            style={{ color: "var(--accent-gold)" }}
          >
            {config.n_cards}
          </span>
        </label>
        <Slider
          id="n-cards"
          min={MIN_CARDS}
          max={MAX_CARDS}
          step={1}
          value={config.n_cards}
          onValueChange={(v) =>
            onChange({ n_cards: typeof v === "number" ? v : v[0] })
          }
          aria-label="Number of cards"
        />
      </div>

      <button
        onClick={onGenerate}
        className="cosmic-btn-primary w-full sm:w-auto"
      >
        <Sparkles className="h-4 w-4" />
        {t("notebook.flashcards_.generate")}
      </button>
    </div>
  );
}

function ConfigSkeleton() {
  return (
    <div className="cosmic-card space-y-4 p-6">
      <Skeleton className="h-5 w-44" />
      <Skeleton className="h-3 w-2/3" />
      <Skeleton className="h-2 w-full" />
      <Skeleton className="h-9 w-44" />
    </div>
  );
}

function DeckScreen({
  cards: initialCards,
  onStartOver,
}: {
  cards: Flashcard[];
  onStartOver: () => void;
}) {
  const { t } = useT();
  const [cards, setCards] = useState<Flashcard[]>(initialCards);
  const [index, setIndex] = useState(0);
  const [isFlipped, setIsFlipped] = useState(false);

  const total = cards.length;
  const card = cards[index];

  useEffect(() => {
    setIsFlipped(false);
  }, [index]);

  const flip = useCallback(() => setIsFlipped((f) => !f), []);

  const goPrev = useCallback(() => {
    setIndex((i) => Math.max(0, i - 1));
  }, []);

  const goNext = useCallback(() => {
    setIndex((i) => Math.min(total - 1, i + 1));
  }, [total]);

  const shuffle = useCallback(() => {
    setCards((prev) => fisherYates(prev));
    setIndex(0);
    setIsFlipped(false);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (
        t &&
        (t.tagName === "INPUT" ||
          t.tagName === "TEXTAREA" ||
          t.isContentEditable)
      ) {
        return;
      }
      if (e.key === " ") {
        e.preventDefault();
        flip();
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        goPrev();
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        goNext();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [flip, goPrev, goNext]);

  const progress = useMemo(
    () =>
      t("notebook.flashcards_.progress", {
        index: String(index + 1).padStart(2, "0"),
        total: String(total).padStart(2, "0"),
      }),
    [index, total, t],
  );

  if (!card) {
    return (
      <div
        className="cosmic-card font-exo2 p-6 text-center text-sm"
        style={{ color: "var(--text-secondary)" }}
      >
        {t("notebook.flashcards_.noCards")}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <span
          className="font-space-mono text-sm uppercase tabular-nums"
          style={{
            color: "var(--text-secondary)",
            letterSpacing: "0.16em",
          }}
        >
          {progress}
        </span>
        <div className="flex items-center gap-2">
          <button
            onClick={shuffle}
            disabled={total < 2}
            className="cosmic-btn-outline"
            style={{ padding: "0.45rem 0.85rem" }}
          >
            <Shuffle className="h-4 w-4" />
            {t("notebook.flashcards_.shuffle")}
          </button>
          <button onClick={onStartOver} className="cosmic-btn-ghost">
            <RotateCcw className="h-4 w-4" />
            {t("notebook.flashcards_.startOver")}
          </button>
        </div>
      </div>

      <Card3D card={card} isFlipped={isFlipped} onFlip={flip} />

      <div className="flex items-center justify-center gap-3">
        <button
          onClick={goPrev}
          disabled={index === 0}
          className="cosmic-btn-outline"
          style={{ padding: "0.45rem 0.7rem" }}
          aria-label={t("notebook.flashcards_.prevLabel")}
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
        <p
          className="font-exo2 text-xs"
          style={{ color: "var(--text-muted)" }}
        >
          {t("notebook.flashcards_.flipHint")}
        </p>
        <button
          onClick={goNext}
          disabled={index === total - 1}
          className="cosmic-btn-outline"
          style={{ padding: "0.45rem 0.7rem" }}
          aria-label={t("notebook.flashcards_.nextLabel")}
        >
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}

function Card3D({
  card,
  isFlipped,
  onFlip,
}: {
  card: Flashcard;
  isFlipped: boolean;
  onFlip: () => void;
}) {
  const { t } = useT();
  return (
    <div style={{ perspective: "1000px" }} className="mx-auto w-full max-w-2xl">
      <motion.button
        type="button"
        onClick={onFlip}
        animate={{ rotateY: isFlipped ? 180 : 0 }}
        transition={{ type: "spring", stiffness: 260, damping: 26 }}
        style={{ transformStyle: "preserve-3d" }}
        className="relative block h-64 w-full cursor-pointer rounded-2xl text-left focus:outline-none sm:h-72"
        aria-label={isFlipped ? t("notebook.flashcards_.showFront") : t("notebook.flashcards_.showBack")}
        aria-pressed={isFlipped}
      >
        <CardFace
          variant="front"
          label={t("notebook.flashcards_.front")}
          text={card.front}
          style={{ backfaceVisibility: "hidden" }}
        />
        <CardFace
          variant="back"
          label={t("notebook.flashcards_.back")}
          text={card.back}
          style={{
            backfaceVisibility: "hidden",
            transform: "rotateY(180deg)",
          }}
        />
      </motion.button>
    </div>
  );
}

function CardFace({
  variant,
  label,
  text,
  style,
}: {
  variant: "front" | "back";
  label: string;
  text: string;
  style: React.CSSProperties;
}) {
  return (
    <div
      style={{
        ...style,
        background:
          variant === "front"
            ? "linear-gradient(135deg, var(--bg-card), var(--bg-3))"
            : "linear-gradient(135deg, var(--accent-gold-dim), var(--bg-card))",
        border: "1px solid var(--border)",
        backdropFilter: "blur(10px)",
      }}
      className={cn(
        "absolute inset-0 flex flex-col rounded-2xl p-6",
      )}
    >
      <p
        className="cosmic-label"
        style={{
          color:
            variant === "back" ? "var(--accent-gold)" : "var(--text-muted)",
        }}
      >
        {label}
      </p>
      <div className="flex flex-1 items-center justify-center px-4">
        <p
          className="font-exo2 text-center text-lg leading-relaxed sm:text-xl"
          style={{ color: "var(--text-primary)" }}
        >
          {text}
        </p>
      </div>
    </div>
  );
}

function fisherYates<T>(input: readonly T[]): T[] {
  const arr = input.slice();
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}
