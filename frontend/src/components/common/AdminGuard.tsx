"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { PageLoader } from "@/components/common/PageLoader";
import { useCurrentUser } from "@/hooks/useAuth";
import { ROUTES } from "@/lib/constants";
import { useAuthStore } from "@/stores/authStore";

// Nests inside AuthGuard; bounces non-admins to the dashboard.
export function AdminGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  // Resolve /users/me at least once so stale persisted state can't gate access.
  const { data: freshUser, isLoading } = useCurrentUser();
  const resolvedUser = freshUser ?? user;

  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!mounted || isLoading) return;
    if (!resolvedUser) return; // AuthGuard will redirect
    if (!resolvedUser.is_admin) {
      router.replace(ROUTES.dashboard);
    }
  }, [mounted, isLoading, resolvedUser, router]);

  if (!mounted || isLoading || !resolvedUser) return <PageLoader />;
  if (!resolvedUser.is_admin) return <PageLoader />;
  return <>{children}</>;
}
