import { defineConfig } from "@playwright/test";

// Records the submission video against a deployed MatchMind (live Foundry model, real Event Hubs).
// Run: MATCHMIND_URL=https://<app> npx playwright test -c playwright.video.config.ts
export default defineConfig({
  testDir: "demo",
  testMatch: "story.spec.ts",
  timeout: 300_000,
  reporter: [["list"]],
  outputDir: "../.test-work/story-video",
  use: {
    baseURL: process.env.MATCHMIND_URL,
    viewport: { width: 1280, height: 720 },
    video: { mode: "on", size: { width: 1280, height: 720 } },
  },
});
