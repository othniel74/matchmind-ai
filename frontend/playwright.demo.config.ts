import { defineConfig } from "@playwright/test";

// Records the demo video. Unlike the smoke tests, this backend loads backend/.env so the
// AI recap shown in the video is real model output. Run: npx playwright test -c playwright.demo.config.ts
const API_PORT = "8138";
const WEB_PORT = "5188";

export default defineConfig({
  testDir: "demo",
  timeout: 300_000,
  reporter: [["list"]],
  outputDir: "../.test-work/demo-video",
  use: {
    baseURL: `http://127.0.0.1:${WEB_PORT}`,
    viewport: { width: 1280, height: 720 },
    video: { mode: "on", size: { width: 1280, height: 720 } },
  },
  webServer: [
    {
      command: `.venv-agents\\Scripts\\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port ${API_PORT}`,
      cwd: "../backend",
      url: `http://127.0.0.1:${API_PORT}/health`,
      reuseExistingServer: false,
      timeout: 60_000,
      env: { MATCHMIND_FOUNDATION_DB: "../.test-work/demo-foundation.sqlite3" },
    },
    {
      command: `npx vite --host 127.0.0.1 --port ${WEB_PORT} --strictPort`,
      url: `http://127.0.0.1:${WEB_PORT}`,
      reuseExistingServer: false,
      timeout: 60_000,
      env: { MATCHMIND_API_PORT: API_PORT },
    },
  ],
});
