import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { defineConfig } from "@playwright/test";

process.env.WB_E2E_DIR ??= mkdtempSync(join(tmpdir(), "wiredbench-e2e-"));
const PORT = 8765;

export default defineConfig({
  testDir: "e2e",
  workers: 1,
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: { baseURL: `http://127.0.0.1:${PORT}`, trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
  webServer: {
    command: `uv run python ../backend/tests/e2e_server.py ${PORT}`,
    url: `http://127.0.0.1:${PORT}/healthz`,
    reuseExistingServer: false,
    env: { WB_E2E_DIR: process.env.WB_E2E_DIR },
  },
});
