import axios, { AxiosError } from "axios";

import { ROUTES } from "@/lib/constants";
import { useAuthStore } from "@/stores/authStore";

// Routed via Next.js proxy to avoid CORS and hide backend URL.
export const api = axios.create({
  baseURL: "/api/proxy",
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token;
  if (token) {
    config.headers = config.headers ?? {};
    (config.headers as Record<string, string>).Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      useAuthStore.getState().logout();
      if (
        typeof window !== "undefined" &&
        window.location.pathname !== ROUTES.login
      ) {
        window.location.href = ROUTES.login;
      }
    }
    return Promise.reject(error);
  },
);
