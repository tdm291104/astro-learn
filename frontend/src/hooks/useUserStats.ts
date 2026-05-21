"use client";

import { useQuery } from "@tanstack/react-query";

import { authService } from "@/services/authService";

import { useTokenUsage } from "./useTokenUsage";

// Per-stat *Loading flag kept for symmetry if the endpoint splits later.
export type UserStats = {
  notebooksCount: number;
  notebooksLoading: boolean;
  documentsCount: number;
  documentsLoading: boolean;
  fitsAnalyzedCount: number;
  fitsAnalyzedLoading: boolean;
  fitsUploadedCount: number;
  fitsUploadedLoading: boolean;
  tokens: { used: number; remaining: number | null } | null;
  tokensLoading: boolean;
};

export function useUserStats(): UserStats {
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ["user-stats"],
    queryFn: () => authService.getStats(),
    staleTime: 30_000,
  });
  const { data: usage, isLoading: usageLoading } = useTokenUsage();

  // No budget cap from BE yet; remaining stays null so card hides it.
  const tokens = usage
    ? { used: usage.month_total.total_tokens, remaining: null }
    : null;

  return {
    notebooksCount: stats?.notebooks_count ?? 0,
    notebooksLoading: statsLoading,
    documentsCount: stats?.documents_count ?? 0,
    documentsLoading: statsLoading,
    fitsAnalyzedCount: stats?.analyses_count ?? 0,
    fitsAnalyzedLoading: statsLoading,
    fitsUploadedCount: stats?.fits_files_count ?? 0,
    fitsUploadedLoading: statsLoading,
    tokens,
    tokensLoading: usageLoading,
  };
}
