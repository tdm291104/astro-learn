"use client";

import { useQuery } from "@tanstack/react-query";

import { authService } from "@/services/authService";
import type { TokenUsageSummary } from "@/types/auth.types";

export const tokenUsageKeys = {
  all: ["token-usage"] as const,
  summary: (days: number) => [...tokenUsageKeys.all, "summary", days] as const,
};

// Monthly total + daily breakdown; BE clamps days to [1, 90].
export function useTokenUsage(days = 30) {
  return useQuery<TokenUsageSummary>({
    queryKey: tokenUsageKeys.summary(days),
    queryFn: () => authService.getTokenUsage(days),
    staleTime: 60_000,
  });
}
