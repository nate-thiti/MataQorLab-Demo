import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";

export default defineConfig({
  resolve: {
    alias: {
      "@/components": fileURLToPath(new URL("./src/components", import.meta.url)),
      "@/hooks": fileURLToPath(new URL("./src/hooks", import.meta.url)),
      "@/lib": fileURLToPath(new URL("./src/lib", import.meta.url)),
      "@/src": fileURLToPath(new URL("./src", import.meta.url)),
      "@": fileURLToPath(new URL(".", import.meta.url)),
    },
  },
  test: {
    include: ["src/**/*.test.js"],
    exclude: ["e2e/**", "node_modules/**"],
  },
});
