import { expect, test, type Page } from "@playwright/test";

// A scripted product tour recorded as video. Captions name the brief's five pipeline stages.

async function caption(page: Page, text: string, hold = 2500) {
  await page.evaluate((t) => {
    let bar = document.getElementById("demo-caption");
    if (!bar) {
      bar = document.createElement("div");
      bar.id = "demo-caption";
      Object.assign(bar.style, {
        position: "fixed", left: "50%", bottom: "28px", transform: "translateX(-50%)", zIndex: "99999",
        background: "rgba(10,14,12,0.92)", color: "#e9f7d2", border: "1px solid #c5f277", borderRadius: "10px",
        padding: "12px 20px", font: "600 18px Inter, Segoe UI, sans-serif", maxWidth: "1100px", textAlign: "center",
        boxShadow: "0 8px 30px rgba(0,0,0,0.5)", pointerEvents: "none",
      });
      document.body.appendChild(bar);
    }
    bar.textContent = t;
  }, text);
  await page.waitForTimeout(hold);
}

async function scrollTo(page: Page, selector: string) {
  await page.locator(selector).first().scrollIntoViewIfNeeded();
  await page.evaluate((s) => document.querySelector(s)?.scrollIntoView({ behavior: "smooth", block: "start" }), selector);
  await page.waitForTimeout(900);
}

test("Pitchlight product tour", async ({ page }) => {
  await page.goto("/");
  await caption(page, "Pitchlight: explainable match intelligence from synthetic football events", 3500);
  await scrollTo(page, ".lp-narrative");
  await caption(page, "Every observation is verified against its source events, in seven languages", 2000);
  await page.locator("button.lp-language").click();
  await page.waitForTimeout(1200);
  await page.locator("button.lp-language").click();
  await page.waitForTimeout(1500);

  await page.goto("/app");
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await caption(page, "1 Ingest · 2 Interpret: a live synthetic match, one match minute per second", 3000);
  await scrollTo(page, ".profile-panel");
  await caption(page, "5 Personalize: favourite club, follow a player, track one metric, any language", 1500);
  await page.getByLabel("Favourite club").selectOption("away");
  await page.waitForTimeout(500);
  await page.getByLabel("Follow one player").selectOption("away-03");
  await page.waitForTimeout(500);
  await page.getByLabel("Track one metric").selectOption("xg");
  await page.waitForTimeout(500);
  await page.getByText("Favourite players").click();
  await page.getByRole("button", { name: "#9 Callum Rhodes" }).click();
  await page.waitForTimeout(800);
  await scrollTo(page, ".moments-panel");
  await expect(page.locator(".moment.kind-goal").first()).toBeVisible({ timeout: 60_000 });
  await caption(page, "3 Explain: why each moment matters (opener, equaliser, chance quality), from verified data", 4000);
  await caption(page, "Player focus: synthetic speed and distance, pass difficulty, rating; the metric tracker follows xG", 4000);

  await scrollTo(page, ".live-panel");
  await page.getByRole("button", { name: "Start live stream" }).click();
  await caption(page, "Event-by-event ingestion: each event validated, interpreted and personalized as it arrives", 6000);
  await page.getByRole("button", { name: "Stop stream" }).click();

  await scrollTo(page, ".recap-panel");
  await expect(page.getByRole("button", { name: "Half-time" })).toBeEnabled({ timeout: 90_000 });
  await page.getByRole("button", { name: "Half-time" }).click();
  await caption(page, "Automated recaps: every number is a validated claim", 3500);
  await page.getByRole("button", { name: "AI recap" }).click();
  await caption(page, "AI recap: Microsoft Agent Framework agents on Azure AI Foundry, fact-checked before publishing", 1000);
  await expect(page.locator(".ai-recap")).toBeVisible({ timeout: 60_000 });
  await caption(page, "AI recap: Microsoft Agent Framework agents on Azure AI Foundry, fact-checked before publishing", 5000);

  await page.getByRole("tab", { name: /Broadcast Studio/ }).click();
  await page.waitForTimeout(1000);
  await scrollTo(page, ".broadcast-screen, .overlay-item");
  await caption(page, "4 Render: timed, machine-readable overlays for the broadcast feed", 3500);
  await page.getByLabel("Language").selectOption("ar");
  await caption(page, "The same verified overlays in Arabic, right to left", 4000);
  await caption(page, "Synthetic data only · fictional clubs and players · every claim traceable to source events", 4000);
});
