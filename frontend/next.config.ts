import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Barrel-file pruning. lucide-react alone exports 1500+ icons; without
  // this Next imports the whole barrel and tree-shaking is incomplete.
  experimental: {
    optimizePackageImports: [
      "lucide-react",
      "framer-motion",
      "@tanstack/react-query",
    ],
  },
  // Skip Sharp in dev — saves ~50 MB and avoids a native-binary install path.
  images: {
    unoptimized: true,
  },
};

export default nextConfig;
