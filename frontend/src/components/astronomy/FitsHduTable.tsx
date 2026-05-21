"use client";

import { motion } from "framer-motion";

import { staggerContainer, staggerItem } from "@/animations/stagger";
import type { FitsUploadResponse } from "@/types/astronomy.types";

function formatShape(shape: number[] | null): string {
  if (!shape || shape.length === 0) return "—";
  return shape.join(" × ");
}

export function FitsHduTable({
  file,
  selectedHdu,
  onSelectHdu,
}: {
  file: FitsUploadResponse;
  selectedHdu: number;
  onSelectHdu: (index: number) => void;
}) {
  return (
    <div className="cosmic-card overflow-hidden">
      <div
        className="border-b px-4 py-3"
        style={{ borderColor: "var(--border)" }}
      >
        <h3
          className="font-orbitron text-sm font-semibold uppercase"
          style={{
            color: "var(--text-primary)",
            letterSpacing: "0.16em",
          }}
        >
          HDUs
        </h3>
        <p
          className="font-exo2 mt-0.5 text-xs"
          style={{ color: "var(--text-secondary)" }}
        >
          Click a row to choose which HDU to analyse.
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[520px] text-sm">
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border)" }}>
              {["#", "Name", "Type", "Shape", "Keys"].map((label, i) => (
                <th
                  key={label}
                  className="font-orbitron px-3 py-2 text-xs uppercase"
                  style={{
                    color: "var(--text-muted)",
                    letterSpacing: "0.16em",
                    textAlign: i === 4 ? "right" : "left",
                  }}
                >
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <motion.tbody
            variants={staggerContainer}
            initial="initial"
            animate="animate"
          >
            {file.hdus.map((hdu) => {
              const isSelected = hdu.index === selectedHdu;
              return (
                <motion.tr
                  key={hdu.index}
                  variants={staggerItem}
                  onClick={() => onSelectHdu(hdu.index)}
                  className="cursor-pointer transition-colors last:border-b-0"
                  style={{
                    background: isSelected
                      ? "var(--accent-gold-dim)"
                      : "transparent",
                    borderBottom: "1px solid var(--border)",
                  }}
                  aria-selected={isSelected}
                >
                  <td
                    className="font-space-mono px-3 py-2 tabular-nums"
                    style={{
                      color: isSelected
                        ? "var(--accent-gold)"
                        : "var(--text-secondary)",
                    }}
                  >
                    {hdu.index}
                  </td>
                  <td
                    className="font-space-mono px-3 py-2"
                    style={{
                      color: hdu.name
                        ? "var(--accent-teal)"
                        : "var(--text-muted)",
                    }}
                  >
                    {hdu.name ?? "unnamed"}
                  </td>
                  <td
                    className="font-space-mono px-3 py-2 text-xs"
                    style={{ color: "var(--text-secondary)" }}
                  >
                    {hdu.type}
                  </td>
                  <td
                    className="font-space-mono px-3 py-2 text-xs tabular-nums"
                    style={{ color: "var(--accent-gold)" }}
                  >
                    {formatShape(hdu.shape)}
                  </td>
                  <td
                    className="font-space-mono px-3 py-2 text-right tabular-nums"
                    style={{ color: "var(--text-muted)" }}
                  >
                    {hdu.n_keywords}
                  </td>
                </motion.tr>
              );
            })}
          </motion.tbody>
        </table>
      </div>
    </div>
  );
}
