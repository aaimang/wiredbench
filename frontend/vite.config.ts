import { defineConfig } from "vitest/config";

export default defineConfig({
  // Fonts must stay files: the Content-Security-Policy refuses data: fonts.
  build: { assetsInlineLimit: 0, sourcemap: false },
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000", "/healthz": "http://127.0.0.1:8000" },
  },
  test: { environment: "jsdom", include: ["src/**/*.test.ts"] },
});
