import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { AxiosError } from "axios";
import { toast } from "sonner";

import { adminService } from "@/services/adminService";
import type {
  AdminAgentRunDetailResponse,
  AdminAgentRunListResponse,
  AdminAgentRunQuery,
  AdminContentQuery,
  AdminCostBreakdownResponse,
  AdminFitsListResponse,
  AdminNotebookListResponse,
  AdminOverviewResponse,
  AdminUserDetailResponse,
  AdminUserListQuery,
  AdminUserListResponse,
  AdminUserUpdateRequest,
} from "@/types/admin.types";
import type { User } from "@/types/auth.types";

const ADMIN_KEY = "admin" as const;

// Unwrap FastAPI `{ error: { message } }` / `{ detail }` shapes.
function adminErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof AxiosError) {
    const data = err.response?.data as
      | { error?: { message?: string } }
      | { detail?: string | unknown[] }
      | undefined;
    const wrapped = (data as { error?: { message?: string } } | undefined)
      ?.error?.message;
    if (typeof wrapped === "string" && wrapped) return wrapped;
    const detail = (data as { detail?: string } | undefined)?.detail;
    if (typeof detail === "string" && detail) return detail;
    if (err.message) return err.message;
  }
  if (err instanceof Error) return err.message;
  return fallback;
}

export function useAdminOverview(days = 30) {
  return useQuery<AdminOverviewResponse>({
    queryKey: [ADMIN_KEY, "overview", days],
    queryFn: () => adminService.getOverview(days),
    staleTime: 30_000,
  });
}

export function useAdminUserList(query: AdminUserListQuery) {
  return useQuery<AdminUserListResponse>({
    queryKey: [ADMIN_KEY, "users", query],
    queryFn: () => adminService.listUsers(query),
    staleTime: 15_000,
    placeholderData: (prev) => prev,
  });
}

export function useAdminUserDetail(id: string | null, days = 30) {
  return useQuery<AdminUserDetailResponse>({
    queryKey: [ADMIN_KEY, "user", id, days],
    queryFn: () => adminService.getUser(id as string, days),
    enabled: Boolean(id),
    staleTime: 30_000,
  });
}

export function useUpdateAdminUser() {
  const qc = useQueryClient();
  return useMutation<
    User,
    unknown,
    { id: string; payload: AdminUserUpdateRequest }
  >({
    mutationFn: ({ id, payload }) => adminService.updateUser(id, payload),
    onSuccess: (user) => {
      qc.invalidateQueries({ queryKey: [ADMIN_KEY] });
      toast.success(`Updated ${user.email}`);
    },
    onError: (err) => {
      toast.error(adminErrorMessage(err, "Update failed"));
    },
  });
}

export function useDeleteAdminUser() {
  const qc = useQueryClient();
  return useMutation<void, unknown, { id: string; email: string }>({
    mutationFn: ({ id }) => adminService.deleteUser(id),
    onSuccess: (_void, { email }) => {
      qc.invalidateQueries({ queryKey: [ADMIN_KEY] });
      toast.success(`Deleted ${email}`);
    },
    onError: (err) => {
      toast.error(adminErrorMessage(err, "Delete failed"));
    },
  });
}

export function useAdminCostBreakdown(days = 30) {
  return useQuery<AdminCostBreakdownResponse>({
    queryKey: [ADMIN_KEY, "cost-breakdown", days],
    queryFn: () => adminService.getCostBreakdown(days),
    staleTime: 30_000,
  });
}

export function useAdminAgentRuns(query: AdminAgentRunQuery) {
  return useQuery<AdminAgentRunListResponse>({
    queryKey: [ADMIN_KEY, "agent-runs", query],
    queryFn: () => adminService.listAgentRuns(query),
    staleTime: 10_000,
    placeholderData: (prev) => prev,
  });
}

export function useAdminAgentRun(id: string | null) {
  return useQuery<AdminAgentRunDetailResponse>({
    queryKey: [ADMIN_KEY, "agent-run", id],
    queryFn: () => adminService.getAgentRun(id as string),
    enabled: Boolean(id),
    staleTime: 10_000,
  });
}

export function useAdminNotebooks(query: AdminContentQuery) {
  return useQuery<AdminNotebookListResponse>({
    queryKey: [ADMIN_KEY, "notebooks", query],
    queryFn: () => adminService.listNotebooks(query),
    staleTime: 15_000,
    placeholderData: (prev) => prev,
  });
}

export function useDeleteAdminNotebook() {
  const qc = useQueryClient();
  return useMutation<void, unknown, { id: string; title: string }>({
    mutationFn: ({ id }) => adminService.deleteNotebook(id),
    onSuccess: (_void, { title }) => {
      qc.invalidateQueries({ queryKey: [ADMIN_KEY] });
      toast.success(`Deleted notebook "${title}"`);
    },
    onError: (err) => {
      toast.error(adminErrorMessage(err, "Delete failed"));
    },
  });
}

export function useAdminFitsFiles(query: AdminContentQuery) {
  return useQuery<AdminFitsListResponse>({
    queryKey: [ADMIN_KEY, "fits", query],
    queryFn: () => adminService.listFitsFiles(query),
    staleTime: 15_000,
    placeholderData: (prev) => prev,
  });
}

export function useDeleteAdminFitsFile() {
  const qc = useQueryClient();
  return useMutation<void, unknown, { id: string; filename: string }>({
    mutationFn: ({ id }) => adminService.deleteFitsFile(id),
    onSuccess: (_void, { filename }) => {
      qc.invalidateQueries({ queryKey: [ADMIN_KEY] });
      toast.success(`Deleted ${filename}`);
    },
    onError: (err) => {
      toast.error(adminErrorMessage(err, "Delete failed"));
    },
  });
}
