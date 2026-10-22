import type { NextConfig } from "next";
import path from "path";

const srcDir = path.join(process.cwd(), "src");

const nextConfig: NextConfig = {
  // Local/Docker dev uses .next-local so container-owned dev artifacts never
  // poison the production .next manifest or block host-side development.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  experimental: {
    // The desktop sandbox drops stdout from detached TypeScript CLI children.
    // Use the compiler API so `next build --webpack` can validate types reliably.
    useTypeScriptCli: false,
  },
  turbopack: {
    resolveAlias: {
      "@/src": srcDir,
    },
  },
  webpack: (config) => {
    config.resolve.alias = {
      ...config.resolve.alias,
      "@/src": srcDir,
    };
    return config;
  },
};

export default nextConfig;
