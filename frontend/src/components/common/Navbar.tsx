"use client";

import { Menu } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { LanguageSwitcher } from "@/components/common/LanguageSwitcher";
import { useT } from "@/hooks/useT";
import { ROUTES } from "@/lib/constants";
import type { TranslationKey } from "@/lib/i18n/messages";
import { useUiStore } from "@/stores/uiStore";

// Map first path segment to an i18n key for the page title.
const TITLE_KEYS: Record<string, TranslationKey> = {
  dashboard: "nav.dashboard",
  chat: "nav.chat",
  notebook: "nav.notebooks",
  notebooks: "nav.notebooks",
  costs: "nav.costs",
  profile: "nav.profile",
  admin: "nav.admin",
};

export function Navbar() {
  const toggleSidebar = useUiStore((s) => s.toggleSidebar);
  const pathname = usePathname();
  const { t } = useT();

  const seg = pathname.split("/").filter(Boolean)[0] ?? "dashboard";
  const titleKey = TITLE_KEYS[seg];
  const title = titleKey ? t(titleKey) : "AstroLearn";

  return (
    <header
      className="flex h-14 items-center justify-between border-b px-4 md:px-6"
      style={{
        background: "var(--bg-1)",
        borderColor: "var(--border)",
      }}
    >
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={toggleSidebar}
          aria-label="Toggle sidebar"
          className="cosmic-icon-btn"
        >
          <Menu className="h-4 w-4" />
        </button>
        <Link
          href={ROUTES.dashboard}
          className="font-orbitron text-sm font-semibold uppercase md:hidden"
          style={{
            color: "var(--accent-gold)",
            letterSpacing: "0.18em",
          }}
        >
          AstroLearn
        </Link>
        <h1
          className="font-orbitron hidden text-sm font-semibold uppercase md:block"
          style={{
            color: "var(--text-primary)",
            letterSpacing: "0.18em",
          }}
        >
          {title}
        </h1>
      </div>

      <div className="flex items-center gap-3">
        <LanguageSwitcher />
        <span
          className="font-space-mono hidden text-[11px] uppercase md:inline"
          style={{
            color: "var(--text-muted)",
            letterSpacing: "0.12em",
          }}
        >
          {new Date().toISOString().slice(0, 10)}
        </span>
      </div>
    </header>
  );
}
