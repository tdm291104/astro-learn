import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AxiosError } from "axios";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { ROUTES } from "@/lib/constants";
import { authService } from "@/services/authService";
import { useAuthStore } from "@/stores/authStore";
import type {
  LoginRequest,
  PasswordChangeRequest,
  RegisterRequest,
  User,
  UserUpdateRequest,
} from "@/types/auth.types";

// Normalize FastAPI `detail` (string or validation array).
function extractErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof AxiosError) {
    const detail = (err.response?.data as { detail?: unknown } | undefined)
      ?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d) =>
          typeof d === "object" && d && "msg" in d ? String(d.msg) : "",
        )
        .filter(Boolean)
        .join(", ");
    }
    if (err.message) return err.message;
  }
  if (err instanceof Error) return err.message;
  return fallback;
}

export function useLoginMutation() {
  const router = useRouter();
  const setSession = useAuthStore((s) => s.login);
  const setUser = useAuthStore((s) => s.setUser);
  const qc = useQueryClient();

  return useMutation<User, unknown, LoginRequest>({
    mutationFn: async (data) => {
      // Store token first so interceptor picks it up for /users/me.
      const tokenResponse = await authService.login(data);
      setSession(tokenResponse);
      const user = await authService.getCurrentUser();
      setUser(user);
      qc.setQueryData(["user"], user);
      return user;
    },
    onSuccess: (user) => {
      toast.success("Signed in");
      // Admin accounts skip the regular dashboard.
      router.replace(user.is_admin ? ROUTES.admin : ROUTES.dashboard);
    },
    onError: (err) => {
      toast.error(extractErrorMessage(err, "Login failed"));
    },
  });
}

export function useRegisterMutation() {
  const router = useRouter();

  return useMutation<User, unknown, RegisterRequest>({
    mutationFn: (data) => authService.register(data),
    onSuccess: () => {
      toast.success("Account created — please sign in");
      router.replace(ROUTES.login);
    },
    onError: (err) => {
      toast.error(extractErrorMessage(err, "Registration failed"));
    },
  });
}

export function useCurrentUser() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const setUser = useAuthStore((s) => s.setUser);

  return useQuery<User>({
    queryKey: ["user"],
    queryFn: async () => {
      const user = await authService.getCurrentUser();
      // Mirror into store for non-react consumers.
      setUser(user);
      return user;
    },
    enabled: isAuthenticated,
    staleTime: 5 * 60_000,
  });
}

export function useUpdateProfileMutation() {
  const setUser = useAuthStore((s) => s.setUser);
  const qc = useQueryClient();

  return useMutation<User, unknown, UserUpdateRequest>({
    mutationFn: (payload) => authService.updateProfile(payload),
    onSuccess: (user) => {
      // Mirror to both store and query cache.
      setUser(user);
      qc.setQueryData(["user"], user);
      toast.success("Profile updated");
    },
    onError: (err) => {
      toast.error(extractErrorMessage(err, "Failed to update profile"));
    },
  });
}

export function useChangePasswordMutation() {
  return useMutation<void, unknown, PasswordChangeRequest>({
    mutationFn: (payload) => authService.changePassword(payload),
    onSuccess: () => {
      toast.success("Password changed");
    },
    onError: (err) => {
      toast.error(extractErrorMessage(err, "Failed to change password"));
    },
  });
}

export function useLogout() {
  const logout = useAuthStore((s) => s.logout);
  const router = useRouter();
  const qc = useQueryClient();

  return () => {
    logout();
    qc.clear();
    router.replace(ROUTES.login);
  };
}
