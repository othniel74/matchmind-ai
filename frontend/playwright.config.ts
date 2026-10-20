import { defineConfig } from "@playwright/test";

// Browser smoke tests run against their own backend (port 8137, isolated database,
// no .env, so no model calls) and their own Vite server (port 5187).
const API_PORT = "8137";
const WEB_PORT = "5187";

export default defineConfig({
  testDir: "e2e",
  timeout: 90_000,
  retries: 0,
  reporter: [["list"]],
  outputDir: "../.test-work/e2e-results",
  use: { baseURL: `http://127.0.0.1:${WEB_PORT}`, viewport: { width: 1440, height: 900 } },
  webServer: [
    {
      command: `.venv-agents\\Scripts\\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port ${API_PORT}`,
      cwd: "../backend",
      url: `http://127.0.0.1:${API_PORT}/health`,
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        MATCHMIND_SKIP_DOTENV: "1",
        MATCHMIND_FOUNDATION_DB: "../.test-work/e2e-foundation.sqlite3",
      },
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
