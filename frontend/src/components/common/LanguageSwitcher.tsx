"use client";

import { Globe } from "lucide-react";

import { SUPPORTED_LOCALES, type Locale } from "@/lib/i18n/messages";
import { useLocaleStore } from "@/stores/localeStore";

const LABELS: Record<Locale, string> = {
  en: "EN",
  vi: "VI",
};

const TITLES: Record<Locale, string> = {
  en: "English",
  vi: "Tiếng Việt",
};

// Compact segmented toggle; rerender re-resolves t() everywhere via useT.
export function LanguageSwitcher() {
  const locale = useLocaleStore((s) => s.locale);
  const setLocale = useLocaleStore((s) => s.setLocale);

  return (
    <div
      className="inline-flex items-center gap-1 rounded-full border px-1.5 py-1"
      style={{
        background: "rgba(255,255,255,0.02)",
        borderColor: "var(--border)",
      }}
    >
      <Globe
        className="h-3 w-3"
        style={{ color: "var(--text-muted)" }}
        aria-hidden
      />
      {SUPPORTED_LOCALES.map((loc) => {
        const active = loc === locale;
        return (
          <button
            key={loc}
            type="button"
            onClick={() => setLocale(loc)}
            title={TITLES[loc]}
            aria-pressed={active}
            className="font-orbitron rounded-full px-2 py-0.5 text-[10px] uppercase transition-colors"
            style={{
              background: active ? "var(--accent-gold-dim)" : "transparent",
              color: active ? "var(--accent-gold)" : "var(--text-muted)",
              letterSpacing: "0.16em",
            }}
          >
            {LABELS[loc]}
          </button>
        );
      })}
    </div>
  );
}
