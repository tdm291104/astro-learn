import { create } from "zustand";
import { persist } from "zustand/middleware";

import { DEFAULT_LOCALE, type Locale, SUPPORTED_LOCALES } from "@/lib/i18n/messages";

type LocaleStore = {
  locale: Locale;
  setLocale: (locale: Locale) => void;
};

function pickInitialLocale(): Locale {
  if (typeof navigator === "undefined") return DEFAULT_LOCALE;
  // First Accept-Language match wins; falls back to DEFAULT_LOCALE.
  const candidates = (navigator.languages ?? [navigator.language])
    .map((l) => l?.toLowerCase().split("-")[0])
    .filter((l): l is string => Boolean(l));
  for (const c of candidates) {
    if ((SUPPORTED_LOCALES as readonly string[]).includes(c)) return c as Locale;
  }
  return DEFAULT_LOCALE;
}

export const useLocaleStore = create<LocaleStore>()(
  persist(
    (set) => ({
      locale: pickInitialLocale(),
      setLocale: (locale) => set({ locale }),
    }),
    { name: "astrolearn-locale" },
  ),
);
