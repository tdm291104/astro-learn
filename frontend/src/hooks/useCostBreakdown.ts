"use client";

import { useQuery } from "@tanstack/react-query";

import { authService } from "@/services/authService";
import type { CostBreakdownResponse } from "@/types/auth.types";

export const costBreakdownKeys = {
  all: ["cost-breakdown"] as const,
  window: (days: number) => [...costBreakdownKeys.all, days] as const,
};

// Per-user cost breakdown; backend scopes to caller.
export function useCostBreakdown(days = 30) {
  return useQuery<CostBreakdownResponse>({
    queryKey: costBreakdownKeys.window(days),
    queryFn: () => authService.getCostBreakdown(days),
    staleTime: 60_000,
  });
}
