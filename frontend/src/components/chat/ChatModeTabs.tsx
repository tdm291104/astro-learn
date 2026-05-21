"use client";

import { useT } from "@/hooks/useT";
import type { TranslationKey } from "@/lib/i18n/messages";
import { cn } from "@/lib/utils";
import { type ChatMode, useChatStore } from "@/stores/chatStore";

type ModeKey = "general" | "notebook" | "fits" | "catalog";

type ModeDef = {
  value: ChatMode;
  key: ModeKey;
  glyph: string;
};

const MODES: readonly ModeDef[] = [
  { value: "general", key: "general", glyph: "✦" },
  { value: "notebook", key: "notebook", glyph: "◉" },
  { value: "fits", key: "fits", glyph: "◎" },
  { value: "catalog", key: "catalog", glyph: "⌖" },
];

// Segmented control switching the chat's tool rail.
export function ChatModeTabs() {
  const { t } = useT();
  const mode = useChatStore((s) => s.mode);
  const setMode = useChatStore((s) => s.setMode);

  return (
    <div
      role="tablist"
      aria-label={t("chat.modes.label")}
      className="flex shrink-0 items-center gap-1 overflow-x-auto px-1"
    >
      {MODES.map((m) => {
        const active = m.value === mode;
        const label = t(`chat.modes.${m.key}` as TranslationKey);
        const hint = t(`chat.modes.${m.key}Hint` as TranslationKey);
        return (
          <button
            key={m.value}
            role="tab"
            type="button"
            aria-selected={active}
            onClick={() => setMode(m.value)}
            title={hint}
            className={cn(
              "font-orbitron group flex items-center gap-2 whitespace-nowrap rounded-md px-3 py-1.5 text-[11px] uppercase transition-colors",
              active && "font-semibold",
            )}
            style={{
              letterSpacing: "0.16em",
              color: active ? "var(--accent-gold)" : "var(--text-secondary)",
              background: active ? "var(--accent-gold-dim)" : "transparent",
              border: active
                ? "1px solid rgba(226,201,126,0.4)"
                : "1px solid var(--border)",
            }}
          >
            <span
              className="text-sm leading-none"
              style={{
                color: active ? "var(--accent-gold)" : "var(--text-muted)",
              }}
              aria-hidden
            >
              {m.glyph}
            </span>
            {label}
          </button>
        );
      })}
    </div>
  );
}
