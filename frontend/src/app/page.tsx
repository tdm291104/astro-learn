"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { PageLoader } from "@/components/common/PageLoader";
import { ROUTES } from "@/lib/constants";
import { useAuthStore } from "@/stores/authStore";

// Landing redirect; mounted flag waits for persist hydration.
export default function RootPage() {
  const router = useRouter();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const hasExpired = useAuthStore((s) => s.hasExpired);

  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!mounted) return;
    if (isAuthenticated && !hasExpired()) {
      router.replace(ROUTES.dashboard);
    } else {
      router.replace(ROUTES.login);
    }
  }, [mounted, isAuthenticated, hasExpired, router]);

  return <PageLoader />;
}
