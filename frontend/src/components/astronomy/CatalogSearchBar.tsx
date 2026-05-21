"use client";

import { Search, X } from "lucide-react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useT } from "@/hooks/useT";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { CatalogSource } from "@/types/astronomy.types";

const SOURCE_OPTIONS: { value: CatalogSource; label: string }[] = [
  { value: "simbad", label: "Simbad" },
  { value: "ned", label: "NED" },
  { value: "vizier", label: "VizieR" },
];

export function CatalogSearchBar({
  query,
  onQueryChange,
  source,
  onSourceChange,
  radius,
  onRadiusChange,
}: {
  query: string;
  onQueryChange: (q: string) => void;
  source: CatalogSource;
  onSourceChange: (s: CatalogSource) => void;
  radius: number | null;
  onRadiusChange: (r: number | null) => void;
}) {
  const { t } = useT();
  return (
    // Stacked rows + flex-wrap; viewport-based breakpoints clip narrow rails.
    <div className="cosmic-card flex flex-col gap-3 p-4">
      <div className="space-y-1">
        <Label htmlFor="catalog-query" className="cosmic-label">
          {t("astronomy.catalog.objectLabel")}
        </Label>
        <div className="relative">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2"
            style={{ color: "var(--text-muted)" }}
          />
          <Input
            id="catalog-query"
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            placeholder={t("astronomy.catalog.objectExample")}
            className="cosmic-input pl-9 pr-9"
            aria-label={t("astronomy.catalog.searchLabel")}
          />
          {query && (
            <button
              type="button"
              onClick={() => onQueryChange("")}
              aria-label={t("astronomy.catalog.clearLabel")}
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 transition-colors"
              style={{ color: "var(--text-muted)" }}
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-[120px] flex-1 space-y-1">
          <Label className="cosmic-label">{t("astronomy.catalog.sourceLabel")}</Label>
          <Select
            value={source}
            onValueChange={(v) => onSourceChange(v as CatalogSource)}
          >
            <SelectTrigger className="cosmic-input h-9 w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SOURCE_OPTIONS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="min-w-[120px] flex-1 space-y-1">
          <Label htmlFor="catalog-radius" className="cosmic-label">
            {t("astronomy.catalog.radiusLabel")}
          </Label>
          <Input
            id="catalog-radius"
            type="number"
            min={0}
            max={3600}
            step={1}
            value={radius === null ? "" : radius}
            onChange={(e) => {
              const raw = e.target.value;
              if (raw === "") {
                onRadiusChange(null);
                return;
              }
              const parsed = Number(raw);
              if (Number.isFinite(parsed)) onRadiusChange(parsed);
            }}
            placeholder={t("astronomy.catalog.radiusOptional")}
            className="cosmic-input font-space-mono h-9 w-full"
          />
        </div>

        {(query || radius !== null) && (
          <button
            type="button"
            onClick={() => {
              onQueryChange("");
              onRadiusChange(null);
            }}
            className="cosmic-btn-ghost shrink-0 self-end"
          >
            {t("astronomy.catalog.reset")}
          </button>
        )}
      </div>
    </div>
  );
}
