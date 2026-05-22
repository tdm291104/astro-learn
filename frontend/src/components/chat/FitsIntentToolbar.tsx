"use client";

import {
  BarChart3,
  FileText,
  History,
  Info,
  Sparkles,
} from "lucide-react";

import { useT } from "@/hooks/useT";
import { cn } from "@/lib/utils";
import { type FitsIntent, useChatStore } from "@/stores/chatStore";

type Choice = {
  key: FitsIntent | null;
  labelKey: "auto" | "analyze" | "report" | "discuss" | "qa";
  hintKey:
    | "autoHint"
    | "analyzeHint"
    | "reportHint"
    | "discussHint"
    | "qaHint";
  Icon: typeof Sparkles;
};

// Order = intended user flow: auto-detect first, then progressively heavier
// intents. `discuss` sits between report (heavy) and qa (lightest) because
// it's still a chat-style answer, not a metadata lookup.
const CHOICES: Choice[] = [
  { key: null, labelKey: "auto", hintKey: "autoHint", Icon: Sparkles },
  { key: "analyze", labelKey: "analyze", hintKey: "analyzeHint", Icon: BarChart3 },
  { key: "report", labelKey: "report", hintKey: "reportHint", Icon: FileText },
  { key: "discuss", labelKey: "discuss", hintKey: "discussHint", Icon: History },
  { key: "qa", labelKey: "qa", hintKey: "qaHint", Icon: Info },
];

// Chip strip shown above the chat input in FITS mode. Pins the agent intent
// so the user can force "Generate report" / "Discuss prior" without typing
// the exact verb the backend regex looks for.
export function FitsIntentToolbar() {
  const { t } = useT();
  const fitsIntent = useChatStore((s) => s.fitsIntent);
  const setFitsIntent = useChatStore((s) => s.setFitsIntent);

  return (
    <div
      className="flex flex-wrap items-center gap-1.5"
      role="radiogroup"
      aria-label={t("chat.fitsIntent.label")}
    >
      <span
        className="font-orbitron mr-1 text-[10px] uppercase"
        style={{ color: "var(--text-muted)", letterSpacing: "0.18em" }}
      >
        {t("chat.fitsIntent.label")}
      </span>
      {CHOICES.map(({ key, labelKey, hintKey, Icon }) => {
        const active = fitsIntent === key;
        return (
          <button
            key={key ?? "auto"}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => setFitsIntent(key)}
            title={t(`chat.fitsIntent.${hintKey}` as Parameters<typeof t>[0])}
            className={cn(
              "font-orbitron inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[10px] uppercase transition-colors",
              active ? "" : "hover:bg-white/5",
            )}
            style={{
              background: active ? "rgba(226,201,126,0.12)" : "transparent",
              border: active
                ? "1px solid rgba(226,201,126,0.45)"
                : "1px solid var(--border)",
              color: active ? "var(--accent-gold)" : "var(--text-secondary)",
              letterSpacing: "0.14em",
            }}
          >
            <Icon className="h-3 w-3" aria-hidden />
            {t(`chat.fitsIntent.${labelKey}` as Parameters<typeof t>[0])}
          </button>
        );
      })}
    </div>
  );
}
