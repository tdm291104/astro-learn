"use client";

import { useState } from "react";

import { CatalogResultsTable } from "@/components/astronomy/CatalogResultsTable";
import { CatalogSearchBar } from "@/components/astronomy/CatalogSearchBar";
import type { CatalogSource } from "@/types/astronomy.types";

// Catalog-mode left panel: stacked filter + results in one scroll column.
export function CatalogModePanel({
  query,
  source,
  radius,
  onQueryChange,
  onSourceChange,
  onRadiusChange,
}: {
  query: string;
  source: CatalogSource;
  radius: number | null;
  onQueryChange: (q: string) => void;
  onSourceChange: (s: CatalogSource) => void;
  onRadiusChange: (r: number | null) => void;
}) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <header
        className="shrink-0 px-4 pb-3 pt-4"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <h2
          className="font-orbitron text-xs font-semibold uppercase"
          style={{ color: "var(--accent-gold)", letterSpacing: "0.2em" }}
        >
          Catalog Search
        </h2>
        <p
          className="font-exo2 mt-0.5 text-[11px]"
          style={{ color: "var(--text-muted)" }}
        >
          Simbad / NASA cone search · results stream below.
        </p>
      </header>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4">
        <CatalogSearchBar
          query={query}
          onQueryChange={onQueryChange}
          source={source}
          onSourceChange={onSourceChange}
          radius={radius}
          onRadiusChange={onRadiusChange}
        />
        <CatalogResultsTable
          query={query}
          source={source}
          radius={radius}
          limit={20}
        />
      </div>
    </div>
  );
}

export function useCatalogModeState() {
  const [query, setQuery] = useState("");
  const [source, setSource] = useState<CatalogSource>("simbad");
  const [radius, setRadius] = useState<number | null>(null);
  return {
    query,
    source,
    radius,
    setQuery,
    setSource,
    setRadius,
  };
}
