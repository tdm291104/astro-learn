import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { AuthState, TokenResponse, User } from "@/types/auth.types";

type AuthStore = AuthState & {
  // Stores JWT+expiry only; /users/me lives in the hook layer.
  login: (token: TokenResponse) => void;
  setUser: (user: User | null) => void;
  logout: () => void;
  hasExpired: () => boolean;
};

const INITIAL: AuthState = {
  token: null,
  user: null,
  expiresAt: null,
  isAuthenticated: false,
};

export const useAuthStore = create<AuthStore>()(
  persist(
    (set, get) => ({
      ...INITIAL,

      login: (token) =>
        set({
          token: token.access_token,
          expiresAt: token.expires_at,
          isAuthenticated: true,
        }),

      setUser: (user) => set({ user }),

      logout: () => set({ ...INITIAL }),

      hasExpired: () => {
        const { expiresAt } = get();
        if (!expiresAt) return true;
        return new Date(expiresAt).getTime() <= Date.now();
      },
    }),
    {
      name: "astrolearn-auth",
      // isAuthenticated is recomputed on rehydration; never persisted.
      partialize: (state) => ({
        token: state.token,
        user: state.user,
        expiresAt: state.expiresAt,
      }),
      onRehydrateStorage: () => (state) => {
        if (!state) return;
        const expired =
          !state.expiresAt ||
          new Date(state.expiresAt).getTime() <= Date.now();
        if (expired) {
          state.token = null;
          state.user = null;
          state.expiresAt = null;
          state.isAuthenticated = false;
        } else {
          state.isAuthenticated = Boolean(state.token);
        }
      },
    },
  ),
);
