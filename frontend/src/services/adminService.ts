import { API_ENDPOINTS } from "@/lib/constants";
import { api } from "@/services/api";
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

export const adminService = {
  async listUsers(query: AdminUserListQuery = {}): Promise<AdminUserListResponse> {
    // Omit undefined filters from query params.
    const params: Record<string, string | number | boolean> = {};
    if (query.q && query.q.trim()) params.q = query.q.trim();
    if (query.is_active !== undefined) params.is_active = query.is_active;
    if (query.is_admin !== undefined) params.is_admin = query.is_admin;
    if (query.limit !== undefined) params.limit = query.limit;
    if (query.offset !== undefined) params.offset = query.offset;

    const res = await api.get<AdminUserListResponse>(API_ENDPOINTS.adminUsers, {
      params,
    });
    return res.data;
  },

  async getUser(
    id: string,
    days = 30,
  ): Promise<AdminUserDetailResponse> {
    const res = await api.get<AdminUserDetailResponse>(
      API_ENDPOINTS.adminUser(id),
      { params: { days } },
    );
    return res.data;
  },

  async updateUser(id: string, payload: AdminUserUpdateRequest): Promise<User> {
    // Normalize blank full_name to null (matches authService).
    const body: AdminUserUpdateRequest = {};
    if (payload.full_name !== undefined) {
      const trimmed = payload.full_name?.trim() ?? "";
      body.full_name = trimmed.length > 0 ? trimmed : null;
    }
    if (payload.is_active !== undefined) body.is_active = payload.is_active;
    if (payload.is_admin !== undefined) body.is_admin = payload.is_admin;

    const res = await api.patch<User>(API_ENDPOINTS.adminUser(id), body);
    return res.data;
  },

  async deleteUser(id: string): Promise<void> {
    await api.delete(API_ENDPOINTS.adminUser(id));
  },

  async getOverview(days = 30): Promise<AdminOverviewResponse> {
    const res = await api.get<AdminOverviewResponse>(
      API_ENDPOINTS.adminStatsOverview,
      { params: { days } },
    );
    return res.data;
  },

  async getCostBreakdown(days = 30): Promise<AdminCostBreakdownResponse> {
    const res = await api.get<AdminCostBreakdownResponse>(
      API_ENDPOINTS.adminStatsCostBreakdown,
      { params: { days } },
    );
    return res.data;
  },

  async listAgentRuns(
    query: AdminAgentRunQuery = {},
  ): Promise<AdminAgentRunListResponse> {
    const params: Record<string, string | number> = {};
    if (query.status) params.status = query.status;
    if (query.agent_name) params.agent_name = query.agent_name;
    if (query.user_id) params.user_id = query.user_id;
    if (query.limit !== undefined) params.limit = query.limit;
    if (query.offset !== undefined) params.offset = query.offset;
    const res = await api.get<AdminAgentRunListResponse>(
      API_ENDPOINTS.adminAgentRuns,
      { params },
    );
    return res.data;
  },

  async getAgentRun(id: string): Promise<AdminAgentRunDetailResponse> {
    const res = await api.get<AdminAgentRunDetailResponse>(
      API_ENDPOINTS.adminAgentRun(id),
    );
    return res.data;
  },

  async listNotebooks(
    query: AdminContentQuery = {},
  ): Promise<AdminNotebookListResponse> {
    const params: Record<string, string | number> = {};
    if (query.q && query.q.trim()) params.q = query.q.trim();
    if (query.owner_id) params.owner_id = query.owner_id;
    if (query.limit !== undefined) params.limit = query.limit;
    if (query.offset !== undefined) params.offset = query.offset;
    const res = await api.get<AdminNotebookListResponse>(
      API_ENDPOINTS.adminNotebooks,
      { params },
    );
    return res.data;
  },

  async deleteNotebook(id: string): Promise<void> {
    await api.delete(API_ENDPOINTS.adminNotebook(id));
  },

  async listFitsFiles(
    query: AdminContentQuery = {},
  ): Promise<AdminFitsListResponse> {
    const params: Record<string, string | number> = {};
    if (query.q && query.q.trim()) params.q = query.q.trim();
    if (query.owner_id) params.owner_id = query.owner_id;
    if (query.limit !== undefined) params.limit = query.limit;
    if (query.offset !== undefined) params.offset = query.offset;
    const res = await api.get<AdminFitsListResponse>(
      API_ENDPOINTS.adminFitsFiles,
      { params },
    );
    return res.data;
  },

  async deleteFitsFile(id: string): Promise<void> {
    await api.delete(API_ENDPOINTS.adminFitsFile(id));
  },
};
