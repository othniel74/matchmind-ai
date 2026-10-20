import { defineConfig } from "@playwright/test";

// Runs the smoke tests against a deployed URL: MATCHMIND_URL=https://... npx playwright test -c playwright.remote.config.ts
export default defineConfig({
  testDir: "e2e",
  timeout: 240_000,
  reporter: [["list"]],
  outputDir: "../.test-work/e2e-remote",
  use: { baseURL: process.env.MATCHMIND_URL, viewport: { width: 1440, height: 900 } },
});
