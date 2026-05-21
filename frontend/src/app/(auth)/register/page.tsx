"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { motion } from "framer-motion";
import Link from "next/link";
import { useForm } from "react-hook-form";

import { fadeInUp, fadeTransition } from "@/animations/fade";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useRegisterMutation } from "@/hooks/useAuth";
import { useT } from "@/hooks/useT";
import { ROUTES } from "@/lib/constants";
import { registerSchema, type RegisterFormValues } from "@/lib/validators";

export default function RegisterPage() {
  const { t } = useT();
  const {
    register: field,
    handleSubmit,
    formState: { errors },
  } = useForm<RegisterFormValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: { email: "", password: "", confirmPassword: "" },
  });

  const registerMutation = useRegisterMutation();

  const onSubmit = (data: RegisterFormValues) => {
    registerMutation.mutate({
      email: data.email,
      password: data.password,
    });
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
            {t("auth.register.title")}
          </h2>
          <p
            className="font-exo2 mt-1 text-sm"
            style={{ color: "var(--text-secondary)" }}
          >
            {t("auth.register.subtitle")}
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
              {...field("email")}
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
              autoComplete="new-password"
              aria-invalid={Boolean(errors.password)}
              className="cosmic-input"
              {...field("password")}
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

          <div className="space-y-2">
            <Label htmlFor="confirmPassword" className="cosmic-label">
              {t("auth.confirmPassword")}
            </Label>
            <Input
              id="confirmPassword"
              type="password"
              autoComplete="new-password"
              aria-invalid={Boolean(errors.confirmPassword)}
              className="cosmic-input"
              {...field("confirmPassword")}
            />
            {errors.confirmPassword && (
              <p
                className="font-exo2 text-xs"
                style={{ color: "var(--accent-coral)" }}
              >
                {errors.confirmPassword.message}
              </p>
            )}
          </div>

          <button
            type="submit"
            disabled={registerMutation.isPending}
            className="cosmic-btn-primary w-full"
          >
            {registerMutation.isPending
              ? t("auth.register.creating")
              : t("auth.register.submit")}
          </button>

          <p
            className="font-exo2 text-center text-sm"
            style={{ color: "var(--text-secondary)" }}
          >
            {t("auth.register.hasAccount")}{" "}
            <Link
              href={ROUTES.login}
              className="font-orbitron uppercase"
              style={{
                color: "var(--accent-gold)",
                letterSpacing: "0.1em",
              }}
            >
              {t("auth.register.signInLink")}
            </Link>
          </p>
        </form>
      </div>
    </motion.div>
  );
}
