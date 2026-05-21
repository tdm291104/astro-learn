// Mirrors backend Pydantic schemas in backend/api/v1/schemas/{user,auth}.py.
export type User = {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_admin: boolean;
  created_at: string; // ISO datetime
};

// OAuth2PasswordRequestForm: username carries email, body is form-urlencoded.
export type LoginRequest = {
  username: string;
  password: string;
};

export type RegisterRequest = {
  email: string;
  password: string;
  full_name?: string | null;
};

export type UserUpdateRequest = {
  // Explicit null clears the column.
  full_name?: string | null;
};

export type PasswordChangeRequest = {
  current_password: string;
  new_password: string;
};

export type TokenResponse = {
  access_token: string;
  token_type: "bearer";
  expires_at: string; // ISO datetime
};

// Persisted shape; isAuthenticated stays in sync with token.
export type AuthState = {
  token: string | null;
  user: User | null;
  expiresAt: string | null;
  isAuthenticated: boolean;
};

// Mirror of backend schemas/token_usage_schema.py.
export type UsageTotals = {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
};

export type DailyUsageItem = {
  date: string; // ISO date (YYYY-MM-DD)
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
};

export type TokenUsageSummary = {
  month_total: UsageTotals;
  month_start: string; // ISO date — first day of current month
  window_days: number;
  daily: DailyUsageItem[];
};

// Mirror of backend schemas/stats_schema.py.
export type UserStatsSummary = {
  notebooks_count: number;
  documents_count: number;
  fits_files_count: number;
  analyses_count: number;
};

// Caller-scoped variant of the admin shape.
export type ModelUsageItem = {
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  call_count: number;
  cost_usd: number;
};

export type CostBreakdownResponse = {
  window_days: number;
  since: string; // ISO datetime
  total_cost_usd: number;
  total_tokens: number;
  items: ModelUsageItem[];
};
