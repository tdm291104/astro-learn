// Mirrors backend schemas/admin_schema.py.
import type {
  DailyUsageItem,
  UsageTotals,
  User,
} from "@/types/auth.types";

export type AdminUserListItem = {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_admin: boolean;
  created_at: string;
};

export type AdminUserListResponse = {
  items: AdminUserListItem[];
  total: number;
  limit: number;
  offset: number;
};

export type AdminUserUpdateRequest = {
  full_name?: string | null;
  is_active?: boolean;
  is_admin?: boolean;
};

export type AdminUserListQuery = {
  q?: string;
  is_active?: boolean;
  is_admin?: boolean;
  limit?: number;
  offset?: number;
};

export type AdminTopUserItem = {
  user_id: string;
  email: string;
  full_name: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
};

export type AdminOverviewResponse = {
  total_users: number;
  active_users: number;
  admin_users: number;
  users_active_in_window: number;
  new_users_in_window: number;
  window_days: number;
  month_total: UsageTotals;
  month_start: string;
  daily: DailyUsageItem[];
  top_users: AdminTopUserItem[];
};

export type AdminUserDetailResponse = {
  user: User;
  month_total: UsageTotals;
  month_start: string;
  window_days: number;
  daily: DailyUsageItem[];
  notebooks_count: number;
  documents_count: number;
  fits_files_count: number;
  analyses_count: number;
};

export type AdminAgentRunStatus =
  | "pending"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";

export type AdminAgentRunItem = {
  id: string;
  user_id: string;
  user_email: string | null;
  agent_name: string;
  status: string;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  progress: number | null;
  current_step: string | null;
  step_count: number;
  created_at: string;
};

export type AdminAgentRunListResponse = {
  items: AdminAgentRunItem[];
  total: number;
  limit: number;
  offset: number;
  status_counts: Record<string, number>;
};

export type AdminAgentRunDetailResponse = {
  run: AdminAgentRunItem;
  task_input: Record<string, unknown>;
  output: Record<string, unknown> | null;
};

export type AdminAgentRunQuery = {
  status?: string;
  agent_name?: string;
  user_id?: string;
  limit?: number;
  offset?: number;
};

export type AdminModelUsageItem = {
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  call_count: number;
  cost_usd: number;
};

export type AdminCostBreakdownResponse = {
  window_days: number;
  since: string;
  total_cost_usd: number;
  total_tokens: number;
  items: AdminModelUsageItem[];
};

export type AdminNotebookItem = {
  id: string;
  owner_id: string;
  owner_email: string | null;
  title: string;
  description: string | null;
  created_at: string;
  updated_at: string;
  is_shared: boolean;
};

export type AdminNotebookListResponse = {
  items: AdminNotebookItem[];
  total: number;
  limit: number;
  offset: number;
};

export type AdminFitsFileItem = {
  id: string;
  owner_id: string;
  owner_email: string | null;
  filename: string;
  size_bytes: number;
  status: string;
  hdu_count: number;
  created_at: string;
};

export type AdminFitsListResponse = {
  items: AdminFitsFileItem[];
  total: number;
  limit: number;
  offset: number;
  total_storage_bytes: number;
};

export type AdminContentQuery = {
  q?: string;
  owner_id?: string;
  limit?: number;
  offset?: number;
};
