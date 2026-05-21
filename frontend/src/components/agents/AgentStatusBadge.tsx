"use client";

import { useT } from "@/hooks/useT";
import type { TranslationKey } from "@/lib/i18n/messages";
import type { AgentStatus } from "@/types/agent.types";

type StatusConfig = {
  labelKey: TranslationKey;
  color: string;
  pulse?: boolean;
};

// Mirrors DocumentList chips for one status grammar.
const STATUS_CONFIG: Record<AgentStatus, StatusConfig> = {
  pending: {
    labelKey: "agent.status.pending",
    color: "var(--text-muted)",
    pulse: true,
  },
  running: {
    labelKey: "agent.status.running",
    color: "var(--accent-blue)",
    pulse: true,
  },
  succeeded: {
    labelKey: "agent.status.succeeded",
    color: "#4caf50",
  },
  failed: {
    labelKey: "agent.status.failed",
    color: "var(--accent-coral)",
  },
  cancelled: {
    labelKey: "agent.status.cancelled",
    color: "var(--accent-gold)",
  },
};

export function AgentStatusBadge({ status }: { status: AgentStatus }) {
  const { t } = useT();
  const cfg = STATUS_CONFIG[status];
  return (
    <span
      className="inline-flex shrink-0 items-center gap-2 rounded-full px-2.5 py-0.5"
      style={{
        background: "rgba(255,255,255,0.02)",
        border: "1px solid var(--border)",
      }}
    >
      <span
        className="cosmic-status-dot"
        style={{
          background: cfg.color,
          animation: cfg.pulse
            ? "cosmic-pulse 1.6s ease-in-out infinite"
            : undefined,
        }}
        aria-hidden
      />
      <span
        className="font-orbitron text-[10px] uppercase"
        style={{
          color: cfg.color,
          letterSpacing: "0.18em",
        }}
      >
        {t(cfg.labelKey)}
      </span>
    </span>
  );
}
