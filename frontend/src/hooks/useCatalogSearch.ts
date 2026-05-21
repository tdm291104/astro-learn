import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";

import { useDebounce } from "@/hooks/useDebounce";
import { astronomyService } from "@/services/astronomyService";
import { useChatStore } from "@/stores/chatStore";
import type {
  CatalogSearchRequest,
  CatalogSearchResponse,
  CatalogSource,
} from "@/types/astronomy.types";

const DEBOUNCE_MS = 400;
const MIN_QUERY_LENGTH = 2;

type Params = {
  query: string;
  source?: CatalogSource;
  radiusArcsec?: number | null;
  limit?: number;
};

// Debounced catalog search; disabled below MIN_QUERY_LENGTH.
export function useCatalogSearch({
  query,
  source = "simbad",
  radiusArcsec = null,
  limit = 20,
}: Params) {
  const debouncedQuery = useDebounce(query, DEBOUNCE_MS);
  const trimmed = debouncedQuery.trim();
  const enabled = trimmed.length >= MIN_QUERY_LENGTH;

  const queryResult = useQuery<CatalogSearchResponse>({
    queryKey: ["astronomy", "catalog", trimmed, source, radiusArcsec, limit] as const,
    queryFn: () => {
      const params: CatalogSearchRequest = {
        query: trimmed,
        source,
        radius_arcsec: radiusArcsec,
        limit,
      };
      return astronomyService.searchCatalog(params);
    },
    enabled,
  });

  // Publish rows to chatStore for CatalogChatAgent grounding; skip empties.
  const setLastCatalogSearch = useChatStore((s) => s.setLastCatalogSearch);
  useEffect(() => {
    if (!queryResult.data) return;
    if (queryResult.data.results.length === 0) return;
    setLastCatalogSearch({
      query: queryResult.data.query,
      source: queryResult.data.source,
      results: queryResult.data.results,
    });
  }, [queryResult.data, setLastCatalogSearch]);

  return {
    ...queryResult,
    debouncedQuery: trimmed,
    isQueryTooShort: !enabled && query.length > 0,
  };
}
