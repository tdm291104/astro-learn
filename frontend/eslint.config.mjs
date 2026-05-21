import { dirname } from "path";
import { fileURLToPath } from "url";
import { FlatCompat } from "@eslint/eslintrc";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const compat = new FlatCompat({
  baseDirectory: __dirname,
});

const eslintConfig = [
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    ignores: [
      "node_modules/**",
      ".next/**",
      "out/**",
      "build/**",
      "next-env.d.ts",
    ],
  },
  {
    // Enforce CLAUDE.md's "no direct localStorage / sessionStorage" rule.
    // All persistent client state goes through Zustand's persist middleware
    // (see frontend/src/stores/*); direct Web Storage access bypasses the
    // hydration guard and SSR boundary AuthGuard depends on.
    //
    // Zustand's persist plumbing lives in node_modules, which is already
    // ignored above, so no allowlist is needed here.
    rules: {
      "no-restricted-globals": [
        "error",
        {
          name: "localStorage",
          message:
            "Use Zustand persist middleware instead of direct localStorage access (see CLAUDE.md).",
        },
        {
          name: "sessionStorage",
          message:
            "Use Zustand persist middleware instead of direct sessionStorage access (see CLAUDE.md).",
        },
      ],
      "no-restricted-syntax": [
        "error",
        {
          selector:
            "MemberExpression[object.name='window'][property.name='localStorage']",
          message:
            "Use Zustand persist middleware instead of window.localStorage (see CLAUDE.md).",
        },
        {
          selector:
            "MemberExpression[object.name='window'][property.name='sessionStorage']",
          message:
            "Use Zustand persist middleware instead of window.sessionStorage (see CLAUDE.md).",
        },
      ],
    },
  },
];

export default eslintConfig;
