import { expect, test, type Page } from "@playwright/test";

// The submission video (under two minutes): one story, recorded live against the deployment.

async function caption(page: Page, text: string, hold = 3000) {
  await page.evaluate((t) => {
    let bar = document.getElementById("demo-caption");
    if (!bar) {
      bar = document.createElement("div");
      bar.id = "demo-caption";
      Object.assign(bar.style, {
        position: "fixed", left: "50%", bottom: "24px", transform: "translateX(-50%)", zIndex: "99999",
        background: "rgba(10,14,12,0.94)", color: "#e9f7d2", border: "1px solid #c5f277", borderRadius: "10px",
        padding: "12px 22px", font: "600 19px Inter, Segoe UI, sans-serif", maxWidth: "1180px", textAlign: "center",
        boxShadow: "0 8px 30px rgba(0,0,0,0.55)", pointerEvents: "none", lineHeight: "1.35",
      });
      document.body.appendChild(bar);
    }
    bar.textContent = t;
  }, text);
  await page.waitForTimeout(Math.min(hold, 1200));
  await page.screenshot({ path: `../.test-work/story-shots/${String(++shot).padStart(2, "0")}.png` });
  await page.waitForTimeout(Math.max(0, hold - 1200));
}

let shot = 0;

async function card(page: Page, title: string, lines: string[], hold = 5000) {
  await page.evaluate(([t, l]) => {
    const el = document.createElement("div");
    el.id = "demo-card";
    Object.assign(el.style, {
      position: "fixed", inset: "0", zIndex: "100000", background: "rgba(9,12,10,0.97)", color: "#e9f7d2",
      display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center", gap: "14px",
      font: "500 22px Inter, Segoe UI, sans-serif", textAlign: "center", padding: "40px",
    });
    el.innerHTML = `<div style="font:700 40px Inter, Segoe UI, sans-serif;color:#c5f277">${t}</div>` +
      (l as string[]).map((x) => `<div>${x}</div>`).join("");
    document.body.appendChild(el);
  }, [title, lines] as const);
  await page.waitForTimeout(1000);
  await page.screenshot({ path: `../.test-work/story-shots/${String(++shot).padStart(2, "0")}.png` });
  await page.waitForTimeout(Math.max(0, hold - 1000));
  await page.evaluate(() => document.getElementById("demo-card")?.remove());
}

async function show(page: Page, locator: ReturnType<Page["locator"]>) {
  await locator.first().scrollIntoViewIfNeeded();
  await locator.first().evaluate((el) => el.scrollIntoView({ behavior: "smooth", block: "start" }));
  await page.waitForTimeout(700);
}

test("MatchMind AI submission story", async ({ page }) => {
  // Kick off the Event Hubs feed first: the job takes a little while to start, so the match is
  // streaming live by the time the video reaches the feed panel.
  await page.request.post("/api/feed/kickoff").catch(() => undefined);

  // 1. What it is
  await page.goto("/");
  await caption(page, "MatchMind AI turns synthetic football events into explainable match intelligence, live, on Azure", 5000);

  // 2. Live moments that explain why they matter
  await page.goto("/app");
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  const moments = page.getByRole("region", { name: "Your moments" });
  await show(page, page.getByRole("region", { name: "Personalize your match" }));
  await caption(page, "Events stream in and are validated one by one. Every moment says why it matters", 3500);
  const why = page.locator(".why-button").first();
  await expect(why).toBeVisible({ timeout: 60_000 });
  await show(page, moments);
  await why.click();
  await expect(page.getByTestId("why-detail")).toBeVisible();
  await caption(page, "Why? The knowledge graph gives the build-up, the players' roles in the pass network and the evidence", 5000);

  // 3. Any language, and questions answered by an agent through MCP
  await show(page, page.getByRole("region", { name: "Personalize your match" }));
  await page.getByLabel("Experience language").selectOption("es");
  await caption(page, "Seven languages. Switch to Spanish: the same verified facts, in the viewer's language", 3500);
  const ask = page.getByRole("region", { name: "Ask the match" });
  await show(page, ask);
  await ask.getByLabel("Your question").fill("¿Quién es el jugador clave de Merridge?");
  await ask.getByRole("button", { name: "Ask" }).click();
  await caption(page, "Ask the match: a Microsoft Foundry agent calls MatchMind's own MCP tools", 2500);
  await expect(ask.getByTestId("ask-answer")).toBeVisible({ timeout: 40_000 });
  await expect(ask.getByTestId("ask-answer")).toContainText("Foundry agent via MCP");
  await caption(page, "The answer comes from the tool's verified facts, never the model's imagination", 4500);

  // 4. Two genuinely different experiences
  await show(page, page.getByRole("region", { name: "Personalize your match" }));
  await page.getByLabel("Experience language").selectOption("en");
  await page.getByLabel("Viewing mode").selectOption("analyst");
  await page.getByLabel("Favourite club").selectOption("away");
  await page.getByLabel("Follow one player").selectOption("away-10");
  await caption(page, "Analyst or fan, favourite club, follow one player: same facts, a different experience", 3000);
  await show(page, page.getByRole("region", { name: "Player focus" }));
  await caption(page, "Player focus: rating, passes, xG, physical data and his role in the team's pass network", 4500);

  // 5. Graph intelligence
  await show(page, page.getByRole("region", { name: "Match graph" }));
  await caption(page, "Pass networks for both teams: hub, key link, PageRank and xG chain, mirrored in a Memgraph database", 5000);

  // 6. Event-driven on Azure
  const feed = page.getByRole("region", { name: "Azure Event Hubs feed" });
  if (await feed.count()) {
    await show(page, feed);
    await expect(feed.getByText(/Live ·/)).toBeVisible({ timeout: 60_000 }).catch(() => undefined);
    await caption(page, "Kick off: a Container Apps Job streams a match through Azure Event Hubs", 3500);
    await caption(page, "The app consumes it live, validates every event and detects moments as they happen", 6000);
  }

  // 7. Recaps written by agents and checked by code
  const recap = page.getByRole("region", { name: "Match recap" });
  await show(page, recap);
  await recap.getByRole("button", { name: "So far", exact: true }).click();
  await caption(page, "Recaps: an Agent Framework workflow drafts, a fact checker verifies every statement, a gate publishes", 5500);

  // 8. Measured, not claimed
  await card(page, "Evaluated in Microsoft Foundry", [
    "21 published outputs in 7 languages, scored by Azure AI Evaluation",
    "Groundedness 4.71 / 5  ·  0 unsupported numbers",
    "8 drafts blocked by the fact checker and replaced with verified text",
    "Agent, model and MCP tool calls traced in Foundry",
  ], 6000);

  // 9. On screen, alongside the match
  await page.goto("/app?view=studio");
  const picker = page.getByLabel("Language");
  await expect(picker).toBeVisible({ timeout: 30_000 });
  await picker.selectOption("ar");
  const overlay = page.locator("button.overlay-item strong").first();
  await expect(overlay).toBeVisible({ timeout: 60_000 });
  await overlay.click();
  await show(page, page.locator(".broadcast-screen"));
  await page.evaluate(() => window.scrollBy(0, -90));
  await caption(page, "Broadcast Studio: timed, machine-readable overlays, here in Arabic, right to left", 6000);

  // 10. How it is built
  await card(page, "MatchMind AI", [
    "Microsoft Foundry  ·  Agent Framework multi-agent workflow  ·  MCP server",
    "Azure Container Apps  ·  Event Hubs  ·  Container Apps Jobs  ·  Memgraph  ·  Application Insights",
    "Managed identity throughout: no keys",
    "Synthetic data, fictional clubs  ·  github.com/othniel74/matchmind-ai",
  ], 6000);
});
