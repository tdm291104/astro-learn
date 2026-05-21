import { api } from "@/services/api";
import { API_ENDPOINTS } from "@/lib/constants";
import type {
  CostBreakdownResponse,
  LoginRequest,
  PasswordChangeRequest,
  RegisterRequest,
  TokenResponse,
  TokenUsageSummary,
  User,
  UserStatsSummary,
  UserUpdateRequest,
} from "@/types/auth.types";

export const authService = {
  async register(data: RegisterRequest): Promise<User> {
    // Normalize blank full_name to null.
    const payload: RegisterRequest = {
      email: data.email,
      password: data.password,
      full_name: data.full_name?.trim() ? data.full_name.trim() : null,
    };
    const res = await api.post<User>(API_ENDPOINTS.register, payload);
    return res.data;
  },

  async login(data: LoginRequest): Promise<TokenResponse> {
    // OAuth2PasswordRequestForm requires URLSearchParams body.
    const body = new URLSearchParams();
    body.set("username", data.username);
    body.set("password", data.password);

    const res = await api.post<TokenResponse>(API_ENDPOINTS.login, body, {
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });
    return res.data;
  },

  async getCurrentUser(): Promise<User> {
    const res = await api.get<User>(API_ENDPOINTS.me);
    return res.data;
  },

  async updateProfile(payload: UserUpdateRequest): Promise<User> {
    // Normalize blank full_name to null.
    const body: UserUpdateRequest = {};
    if (payload.full_name !== undefined) {
      const trimmed = payload.full_name?.trim() ?? "";
      body.full_name = trimmed.length > 0 ? trimmed : null;
    }
    const res = await api.patch<User>(API_ENDPOINTS.me, body);
    return res.data;
  },

  async changePassword(payload: PasswordChangeRequest): Promise<void> {
    await api.post(API_ENDPOINTS.changePassword, payload);
  },

  async getStats(): Promise<UserStatsSummary> {
    const res = await api.get<UserStatsSummary>(API_ENDPOINTS.meStats);
    return res.data;
  },

  async getTokenUsage(days = 30): Promise<TokenUsageSummary> {
    const res = await api.get<TokenUsageSummary>(API_ENDPOINTS.tokenUsage, {
      params: { days },
    });
    return res.data;
  },

  async getCostBreakdown(days = 30): Promise<CostBreakdownResponse> {
    const res = await api.get<CostBreakdownResponse>(
      API_ENDPOINTS.costBreakdown,
      { params: { days } },
    );
    return res.data;
  },
};
