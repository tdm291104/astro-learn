"use client";

import { AnimatePresence, motion } from "framer-motion";
import { LogOut, User as UserIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect } from "react";

import { slideInLeft } from "@/animations/slide";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useT } from "@/hooks/useT";
import { useLogout } from "@/hooks/useAuth";
import { ROUTES } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/authStore";
import { useUiStore } from "@/stores/uiStore";

type NavItem = {
  href: string;
  label: string;
  glyph: string;
  disabled?: boolean;
  disabledHint?: string;
};

type NavSection = {
  title: string;
  items: NavItem[];
};

export function Sidebar() {
  const pathname = usePathname();
  const sidebarOpen = useUiStore((s) => s.sidebarOpen);
  const setSidebarOpen = useUiStore((s) => s.setSidebarOpen);
  const isAdmin = useAuthStore((s) => Boolean(s.user?.is_admin));
  const { t } = useT();

  // Built per-render so the labels react to locale changes.
  const navSections: NavSection[] = isAdmin
    ? [
        {
          title: t("nav.admin"),
          items: [
            { href: ROUTES.admin, label: t("nav.dashboard"), glyph: "▣" },
            { href: ROUTES.adminUsers, label: "Users", glyph: "☷" },
            { href: ROUTES.adminAgentRuns, label: "Agent Runs", glyph: "⚙" },
            { href: ROUTES.adminCosts, label: t("nav.costs"), glyph: "$" },
          ],
        },
        {
          title: "Content",
          items: [
            { href: ROUTES.adminNotebooks, label: t("nav.notebooks"), glyph: "📚" },
            { href: ROUTES.adminFits, label: "FITS Files", glyph: "🔭" },
          ],
        },
      ]
    : [
        {
          title: "Workspace",
          items: [
            { href: ROUTES.dashboard, label: t("nav.dashboard"), glyph: "◈" },
            { href: ROUTES.chat, label: t("nav.chat"), glyph: "✦" },
            { href: ROUTES.costs, label: t("nav.costs"), glyph: "$" },
          ],
        },
      ];
  const brandHref = isAdmin ? ROUTES.admin : ROUTES.dashboard;

  // Close drawer on mobile so a persisted desktop "true" doesn't overlay content.
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (window.matchMedia("(max-width: 767px)").matches) {
      setSidebarOpen(false);
    }
  }, [setSidebarOpen]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (window.matchMedia("(max-width: 767px)").matches) {
      setSidebarOpen(false);
    }
  }, [pathname, setSidebarOpen]);

  return (
    <>
      {/* Mobile backdrop — only visible <md when drawer is open. */}
      <AnimatePresence>
        {sidebarOpen && (
          <motion.div
            key="sidebar-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            onClick={() => setSidebarOpen(false)}
            className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm md:hidden"
            aria-hidden
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {sidebarOpen && (
          <motion.aside
            key="sidebar"
            variants={slideInLeft}
            initial="initial"
            animate="animate"
            exit="initial"
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="fixed inset-y-0 left-0 z-50 flex h-screen shrink-0 flex-col border-r md:static md:z-auto"
            style={{
              width: "var(--sidebar-w)",
              background: "var(--bg-1)",
              borderColor: "var(--border)",
            }}
          >
            <div className="flex flex-1 flex-col overflow-y-auto p-5">
              {/* Brand */}
              <Link
                href={brandHref}
                className="font-orbitron mb-8 block text-lg font-extrabold uppercase"
                style={{
                  color: "var(--accent-gold)",
                  letterSpacing: "0.18em",
                }}
              >
                Astronote
              </Link>

              <nav className="flex flex-col gap-6">
                {navSections.map((section) => (
                  <div key={section.title} className="flex flex-col gap-1">
                    <div
                      className="font-orbitron mb-2 px-3 text-[10px] font-semibold uppercase"
                      style={{
                        color: "var(--text-muted)",
                        letterSpacing: "0.2em",
                      }}
                    >
                      {section.title}
                    </div>
                    {section.items.map((item) => (
                      <NavLink
                        key={item.href}
                        item={item}
                        pathname={pathname}
                      />
                    ))}
                  </div>
                ))}
              </nav>
            </div>

            <SidebarUserCard />
          </motion.aside>
        )}
      </AnimatePresence>
    </>
  );
}

function NavLink({ item, pathname }: { item: NavItem; pathname: string }) {
  const { href, label, glyph, disabled, disabledHint } = item;
  const active = pathname === href || pathname.startsWith(href + "/");

  if (disabled) {
    const trigger = (
      <span
        className="font-orbitron flex items-center gap-3 rounded-md px-3 py-2 text-xs uppercase opacity-50"
        style={{
          color: "var(--text-muted)",
          letterSpacing: "0.12em",
        }}
        aria-disabled
      >
        <span className="text-base leading-none">{glyph}</span>
        {label}
      </span>
    );
    if (!disabledHint) return trigger;
    return (
      <Tooltip>
        <TooltipTrigger render={trigger} />
        <TooltipContent side="right">{disabledHint}</TooltipContent>
      </Tooltip>
    );
  }

  return (
    <Link
      href={href}
      className={cn(
        "font-orbitron group relative flex items-center gap-3 rounded-md px-3 py-2 text-xs uppercase transition-all duration-200",
        active ? "font-semibold" : "hover:translate-x-[2px]",
      )}
      style={{
        letterSpacing: "0.12em",
        color: active ? "var(--accent-gold)" : "var(--text-secondary)",
        background: active ? "var(--accent-gold-dim)" : "transparent",
        borderLeft: active
          ? "2px solid var(--accent-gold)"
          : "2px solid transparent",
      }}
      aria-current={active ? "page" : undefined}
    >
      <span
        className="text-base leading-none"
        style={{
          color: active ? "var(--accent-gold)" : "var(--text-muted)",
        }}
      >
        {glyph}
      </span>
      {label}
    </Link>
  );
}

function SidebarUserCard() {
  const user = useAuthStore((s) => s.user);
  const logout = useLogout();
  const { t } = useT();

  const emailHandle = user?.email ? user.email.split("@")[0] : null;
  const displayName = user?.full_name?.trim() || emailHandle || "Observer";
  const initials = computeInitials(user?.full_name, emailHandle);

  return (
    <div
      className="shrink-0 p-4"
      style={{ borderTop: "1px solid var(--border)" }}
    >
      <DropdownMenu>
        <DropdownMenuTrigger
          className="flex w-full items-center gap-3 rounded-lg p-2.5 text-left transition-colors"
          style={{
            background: "rgba(255,255,255,0.03)",
            border: "1px solid transparent",
          }}
          aria-label="Account menu"
        >
          <span
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[13px] font-bold text-white"
            style={{
              background:
                "linear-gradient(135deg, var(--accent-blue), var(--accent-purple))",
            }}
            aria-hidden
          >
            {initials}
          </span>
          <div className="min-w-0 flex-1">
            <div
              className="font-exo2 truncate text-[13px] font-medium"
              style={{ color: "var(--text-primary)" }}
            >
              {displayName}
            </div>
            <div
              className="font-exo2 truncate text-[11px]"
              style={{ color: "var(--text-muted)" }}
            >
              Researcher
            </div>
          </div>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" side="top">
          <DropdownMenuItem render={<Link href={ROUTES.profile} />}>
            <UserIcon className="mr-2 h-4 w-4" />
            {t("nav.profile")}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            variant="destructive"
            onClick={() => logout()}
          >
            <LogOut className="mr-2 h-4 w-4" />
            {t("common.signOut")}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}

// Initials from first two name words, falling back to email handle.
function computeInitials(
  fullName: string | null | undefined,
  emailHandle: string | null,
): string {
  const name = fullName?.trim();
  if (name) {
    const parts = name.split(/\s+/).filter(Boolean);
    const letters = parts.slice(0, 2).map((p) => p[0]?.toUpperCase() ?? "");
    const joined = letters.join("");
    if (joined) return joined;
  }
  if (emailHandle) {
    return emailHandle.slice(0, 2).toUpperCase();
  }
  return "OB";
}
