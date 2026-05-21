"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { PageLoader } from "@/components/common/PageLoader";
import { ROUTES } from "@/lib/constants";
import { useAuthStore } from "@/stores/authStore";

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const hasExpired = useAuthStore((s) => s.hasExpired);

  // Zustand persist populates after first effect tick; wait to avoid bad redirect.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!mounted) return;
    if (!isAuthenticated || hasExpired()) {
      router.replace(ROUTES.login);
    }
  }, [mounted, isAuthenticated, hasExpired, router]);

  if (!mounted || !isAuthenticated) return <PageLoader />;
  return <>{children}</>;
}
