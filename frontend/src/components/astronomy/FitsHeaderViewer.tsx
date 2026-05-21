"use client";

import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown } from "lucide-react";
import { useMemo, useState } from "react";

import { fadeTransition } from "@/animations/fade";
import { cn } from "@/lib/utils";

const COLLAPSED_ROW_LIMIT = 20;

function formatHeaderValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean")
    return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

export function FitsHeaderViewer({
  headers,
}: {
  headers: Record<string, unknown>;
}) {
  const [open, setOpen] = useState(false);
  const [showAll, setShowAll] = useState(false);

  const entries = useMemo(() => Object.entries(headers ?? {}), [headers]);
  const visible = showAll ? entries : entries.slice(0, COLLAPSED_ROW_LIMIT);
  const hiddenCount = Math.max(0, entries.length - visible.length);

  if (entries.length === 0) {
    return null;
  }

  return (
    <div className="cosmic-card overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
        aria-expanded={open}
      >
        <div>
          <h3
            className="font-orbitron text-sm font-semibold uppercase"
            style={{
              color: "var(--text-primary)",
              letterSpacing: "0.16em",
            }}
          >
            FITS Headers
          </h3>
          <p
            className="font-space-mono mt-0.5 text-[11px] uppercase"
            style={{
              color: "var(--text-muted)",
              letterSpacing: "0.14em",
            }}
          >
            {entries.length} keyword{entries.length === 1 ? "" : "s"} · primary HDU
          </p>
        </div>
        <ChevronDown
          className={cn(
            "h-4 w-4 shrink-0 transition-transform",
            open && "rotate-180",
          )}
          style={{ color: "var(--accent-gold)" }}
        />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={fadeTransition}
            className="overflow-hidden"
            style={{ borderTop: "1px solid var(--border)" }}
          >
            <div className="max-h-96 overflow-auto">
              <table className="w-full min-w-[420px] text-xs">
                <tbody>
                  {visible.map(([key, value]) => (
                    <tr
                      key={key}
                      className="align-top"
                      style={{ borderBottom: "1px solid var(--border)" }}
                    >
                      <th
                        className="font-space-mono w-40 px-3 py-1.5 text-left font-medium"
                        style={{ color: "var(--accent-blue)" }}
                      >
                        {key}
                      </th>
                      <td
                        className="font-space-mono break-all px-3 py-1.5"
                        style={{ color: "var(--text-primary)" }}
                      >
                        {formatHeaderValue(value)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {hiddenCount > 0 && (
              <div
                className="px-3 py-2 text-center"
                style={{ borderTop: "1px solid var(--border)" }}
              >
                <button
                  onClick={() => setShowAll(true)}
                  className="cosmic-btn-ghost"
                >
                  Show {hiddenCount} more
                </button>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
