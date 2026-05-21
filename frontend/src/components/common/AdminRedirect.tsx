"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { PageLoader } from "@/components/common/PageLoader";
import { ROUTES } from "@/lib/constants";
import { useAuthStore } from "@/stores/authStore";

// Hides children during redirect so user-facing pages don't flash for admins.
export function AdminRedirect({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const isAdmin = useAuthStore((s) => Boolean(s.user?.is_admin));

  useEffect(() => {
    if (isAdmin) router.replace(ROUTES.admin);
  }, [isAdmin, router]);

  if (isAdmin) return <PageLoader />;
  return <>{children}</>;
}
