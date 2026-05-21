"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { motion } from "framer-motion";
import Link from "next/link";
import { useForm } from "react-hook-form";

import { fadeInUp, fadeTransition } from "@/animations/fade";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useLoginMutation } from "@/hooks/useAuth";
import { useT } from "@/hooks/useT";
import { ROUTES } from "@/lib/constants";
import { loginSchema, type LoginFormValues } from "@/lib/validators";

export default function LoginPage() {
  const { t } = useT();
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });

  const login = useLoginMutation();

  const onSubmit = (data: LoginFormValues) => {
    // BE OAuth2 form expects `username`; form uses `email` for UX.
    login.mutate({ username: data.email, password: data.password });
  };

  return (
    <motion.div
      variants={fadeInUp}
      initial="initial"
      animate="animate"
      transition={fadeTransition}
      className="flex flex-col items-center"
    >
      <div className="mb-8 flex flex-col items-center gap-2">
        <span
          className="text-3xl"
          style={{ color: "var(--accent-gold)" }}
          aria-hidden
        >
          ◈
        </span>
        <h1
          className="font-orbitron text-2xl font-extrabold uppercase"
          style={{
            color: "var(--accent-gold)",
            letterSpacing: "0.22em",
          }}
        >
          {t("app.name")}
        </h1>
        <p
          className="font-exo2 text-xs uppercase"
          style={{
            color: "var(--text-muted)",
            letterSpacing: "0.18em",
          }}
        >
          {t("app.tagline")}
        </p>
      </div>

      <div
        className="relative w-full overflow-hidden rounded-2xl p-8"
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border)",
          backdropFilter: "blur(10px)",
        }}
      >
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-0 h-px"
          style={{
            background:
              "linear-gradient(90deg, transparent, var(--accent-gold), transparent)",
          }}
        />

        <div className="mb-6">
          <h2
            className="font-orbitron text-xl font-semibold uppercase"
            style={{
              color: "var(--text-primary)",
              letterSpacing: "0.16em",
            }}
          >
            {t("auth.login.title")}
          </h2>
          <p
            className="font-exo2 mt-1 text-sm"
            style={{ color: "var(--text-secondary)" }}
          >
            {t("auth.login.subtitle")}
          </p>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-5" noValidate>
          <div className="space-y-2">
            <Label htmlFor="email" className="cosmic-label">
              {t("auth.email")}
            </Label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              aria-invalid={Boolean(errors.email)}
              className="cosmic-input"
              {...register("email")}
            />
            {errors.email && (
              <p
                className="font-exo2 text-xs"
                style={{ color: "var(--accent-coral)" }}
              >
                {errors.email.message}
              </p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="password" className="cosmic-label">
              {t("auth.password")}
            </Label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              aria-invalid={Boolean(errors.password)}
              className="cosmic-input"
              {...register("password")}
            />
            {errors.password && (
              <p
                className="font-exo2 text-xs"
                style={{ color: "var(--accent-coral)" }}
              >
                {errors.password.message}
              </p>
            )}
          </div>

          <button
            type="submit"
            disabled={login.isPending}
            className="cosmic-btn-primary w-full"
          >
            {login.isPending ? t("auth.login.signingIn") : t("auth.login.submit")}
          </button>

          <p
            className="font-exo2 text-center text-sm"
            style={{ color: "var(--text-secondary)" }}
          >
            {t("auth.login.noAccount")}{" "}
            <Link
              href={ROUTES.register}
              className="font-orbitron uppercase"
              style={{
                color: "var(--accent-gold)",
                letterSpacing: "0.1em",
              }}
            >
              {t("auth.login.createLink")}
            </Link>
          </p>
        </form>
      </div>
    </motion.div>
  );
}
