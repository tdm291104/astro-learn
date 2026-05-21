import { useCallback } from "react";

import {
  DEFAULT_LOCALE,
  MESSAGES,
  type Locale,
  type TranslationKey,
} from "@/lib/i18n/messages";
import { useLocaleStore } from "@/stores/localeStore";

// Walk a "a.b.c" path through the nested dictionary; falls back to en then key.
function resolveString(locale: Locale, key: string): string {
  const segments = key.split(".");
  for (const candidate of [locale, DEFAULT_LOCALE]) {
    let cur: unknown = MESSAGES[candidate];
    let ok = true;
    for (const seg of segments) {
      if (!cur || typeof cur !== "object" || !(seg in (cur as object))) {
        ok = false;
        break;
      }
      cur = (cur as Record<string, unknown>)[seg];
    }
    if (ok && typeof cur === "string") return cur;
  }
  return key;
}

function interpolate(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (_, k) =>
    k in vars ? String(vars[k]) : `{${k}}`,
  );
}

// Returns a translator `t(key, vars?)` + the current locale.
export function useT() {
  const locale = useLocaleStore((s) => s.locale);
  const t = useCallback(
    (key: TranslationKey, vars?: Record<string, string | number>): string => {
      return interpolate(resolveString(locale, key), vars);
    },
    [locale],
  );
  return { t, locale };
}
