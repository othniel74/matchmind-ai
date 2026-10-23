import { expect, test, type Page } from "@playwright/test";

const SHOTS = "../.test-work/e2e";

function watchErrors(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(`console: ${message.text()}`);
  });
  return errors;
}

test("landing preview cycles through every language, Arabic right to left", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("/");
  const preview = page.locator(".lp-narrative").first();
  await expect(preview).not.toBeEmpty({ timeout: 20_000 });
  const toggle = page.locator("button.lp-language");
  const seen: Record<string, string> = {};
  let previous = "";
  for (const code of ["EN", "ES", "FR", "PT", "DE", "IT", "AR"]) {
    await expect(toggle).toContainText(code);
    const container = page.locator(`div[lang="${code.toLowerCase()}"]`).first();
    await expect(container).toHaveAttribute("dir", code === "AR" ? "rtl" : "ltr");
    const text = container.locator(".lp-narrative");
    // The preview reloads after each switch; wait for the new language's wording.
    if (previous) await expect(text).not.toHaveText(previous, { timeout: 20_000 });
    await expect(text).not.toBeEmpty();
    seen[code] = previous = (await text.innerText()).trim();
    if (code === "FR" || code === "AR")
      await page.screenshot({ path: `${SHOTS}/landing-${code.toLowerCase()}.png`, fullPage: false });
    await toggle.click();
  }
  // Each language shows its own wording, not a copy of English.
  expect(new Set(Object.values(seen)).size).toBe(7);
  expect(seen.AR).toMatch(/[؀-ۿ]/);
  expect(errors).toEqual([]);
});

test("dashboard replays and shows the new match statistics", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("/app?view=analysis");
  await expect(page.getByText("Possession (time)")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".comparison-row", { hasText: "Expected goals (xG)" })).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/dashboard.png`, fullPage: false });
  expect(errors).toEqual([]);
});

test("broadcast studio renders Arabic overlays right to left", async ({ page }) => {
  // The replay reaches minute 67, the first verified insight, about 70 seconds in.
  test.setTimeout(240_000);
  const errors = watchErrors(page);
  await page.goto("/app?view=studio");
  const picker = page.getByLabel("Language");
  await expect(picker).toBeVisible({ timeout: 30_000 });
  await expect(picker.locator("option")).toHaveCount(7);
  await picker.selectOption("ar");
  const item = page.locator("button.overlay-item strong").first();
  await expect(item).toBeVisible({ timeout: 180_000 });
  await expect(item).toHaveAttribute("dir", "rtl");
  await expect(item).toHaveAttribute("lang", "ar");
  await expect(item).toHaveText(/[؀-ۿ]/);
  await item.click();
  await page.screenshot({ path: `${SHOTS}/studio-ar.png`, fullPage: false });
  expect(errors).toEqual([]);
});

test("personalized experience, recap and live event stream", async ({ page }) => {
  test.setTimeout(240_000);
  const errors = watchErrors(page);
  await page.goto("/app");
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await page.getByLabel("Experience language").selectOption("es");
  await page.getByLabel("Favourite club").selectOption("away");
  await page.getByLabel("Follow one player").selectOption("away-03");
  await page.getByLabel("Track one metric").selectOption("xg");
  await page.getByText("Favourite players").click();
  await page.getByRole("button", { name: "#9 Callum Rhodes" }).click();
  await expect(page.getByRole("button", { name: "#9 Callum Rhodes" })).toHaveAttribute("aria-pressed", "true");

  // Personalized moments arrive in Spanish, with the favourite club's goal flagged.
  const goal = page.locator(".moment.kind-goal strong", { hasText: "Gol de Pedro Valença" }).first();
  await expect(goal).toBeVisible({ timeout: 60_000 });
  await expect(page.locator(".moment.kind-goal.favourite").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Following Pedro Valença" })).toBeVisible();
  await expect(page.locator(".metric-statement")).toContainText("goles esperados (xG)");

  // Recap so far, verified and in Spanish; the AI recap falls back without a configured model.
  await page.getByRole("button", { name: "So far", exact: true }).click();
  await expect(page.locator(".recap h3")).toHaveText("Lo que va de partido");
  await expect(page.locator(".recap-score")).toContainText("Calderbrook");
  await page.getByRole("button", { name: "AI recap" }).click();
  // Without a model this shows the verified recap; with one, the agent run (published or blocked).
  await expect(page.locator(".ai-recap")).toContainText(/verified recap is shown|Fact-checked and published|Blocked: verified recap shown/,
                                                        { timeout: 90_000 });
  await page.screenshot({ path: `${SHOTS}/experience-es.png`, fullPage: true });

  // Event-by-event stream (Live data section): events are ingested and moments appear as they happen.
  await page.getByRole("navigation", { name: "Workspace" }).getByRole("button", { name: "Live data" }).click();
  await page.getByRole("button", { name: "Start live stream" }).click();
  await expect(page.locator(".live-events li").first()).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(".live-moments li").first()).toBeVisible({ timeout: 30_000 });
  await page.screenshot({ path: `${SHOTS}/live-stream.png`, fullPage: false });
  expect(errors).toEqual([]);
});

test("match graph, why-this-moment and ask the match", async ({ page }) => {
  test.setTimeout(180_000);
  const errors = watchErrors(page);
  await page.goto("/app?view=analysis");
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  const graph = page.getByRole("region", { name: "Match graph" });
  await expect(graph.getByTestId("graph-source")).toContainText("NODES", { timeout: 30_000 });
  await expect(graph.locator("svg.pass-network .node").first()).toBeVisible({ timeout: 60_000 });
  await expect(graph.getByRole("table", { name: "xG chain" })).toBeVisible();
  // The network is explorable: a player opens their passing partners, a partner opens that lane.
  await expect(graph.getByTestId("network-card")).toContainText("Network at a glance");
  await graph.locator("svg.pass-network .node").first().click();
  await expect(graph.getByTestId("network-card")).toContainText("Passes most to");
  await graph.getByTestId("network-card").locator(".partners .player-chip").first().click();
  await expect(graph.getByTestId("network-card")).toContainText("evidence event");
  await graph.getByRole("button", { name: "Last 15 min" }).click();
  await page.getByRole("navigation", { name: "Workspace" }).getByRole("button", { name: "Match centre" }).click();
  // The first goal comes in the 9th minute of the replay; its moment offers an explanation.
  const why = page.locator(".why-button").first();
  await expect(why).toBeVisible({ timeout: 120_000 });
  await why.click();
  await expect(page.getByTestId("why-detail")).toContainText("evidence event");
  const ask = page.getByRole("region", { name: "Ask the match" });
  await ask.getByLabel("Your question").fill("Who scored?");
  await ask.getByRole("button", { name: "Ask" }).click();
  await expect(ask.getByTestId("ask-answer")).toContainText(/Goals|No goal/);
  await page.screenshot({ path: `${SHOTS}/graph-explorer.png`, fullPage: true });
  expect(errors).toEqual([]);
});

test("workspace sections: one navigation, shareable URLs, the right panels", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("/app");
  const nav = page.getByRole("navigation", { name: "Workspace" });
  const sections: [string, string | null, string][] = [
    ["Match centre", null, "Your moments"],
    ["Analysis", "analysis", "Match graph"],
    ["Video AI", "video", "Auto-eventing from video"],
    ["Live data", "live", "Live event stream"],
    ["Broadcast Studio", "studio", "Overlay control room"],
  ];
  for (const [label, view, region] of sections) {
    await nav.getByRole("button", { name: label }).click();
    await expect(nav.getByRole("button", { name: label })).toHaveAttribute("aria-current", "page");
    expect(new URL(page.url()).searchParams.get("view")).toBe(view);
    await expect(page.getByRole("heading", { level: 1 })).toContainText(label === "Match centre" ? "Match centre" : label);
    if (region === "Overlay control room") await expect(page.getByText(region)).toBeVisible({ timeout: 20_000 });
    else await expect(page.getByRole("region", { name: region })).toBeVisible({ timeout: 20_000 });
  }
  // Analysis also explains tactical changes and pressing, with the causal caveat.
  await nav.getByRole("button", { name: "Analysis" }).click();
  await expect(page.getByRole("region", { name: "Tactical changes" })).toBeVisible({ timeout: 20_000 });
  // Panels that belong elsewhere are not repeated on the match centre.
  await nav.getByRole("button", { name: "Match centre" }).click();
  await expect(page.getByRole("region", { name: "Match graph" })).toHaveCount(0);
  await expect(page.getByRole("tablist", { name: "Match views" })).toHaveCount(0);
  await page.screenshot({ path: `${SHOTS}/sections.png`, fullPage: false });
  expect(errors).toEqual([]);
});

test("the one idea is easy to find: tour, fact checker and proof", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("/");
  await expect(page.getByText("AI drafts the recap. Code checks its factual claims before publication.")).toBeVisible();
  await page.getByRole("link", { name: "See it in 60 seconds" }).click();
  const tour = page.getByRole("dialog", { name: "Guided tour" });
  await expect(tour).toContainText("Start with a false claim");
  await expect(page.locator("section.tour-focus")).toHaveAttribute("aria-label", "Try to fool the fact checker");
  // The checker answers honestly whether or not a model is configured.
  const checker = page.getByRole("region", { name: "Try to fool the fact checker" });
  await checker.getByRole("button", { name: "Calderbrook won the match." }).click();
  await expect(checker).toContainText(/Blocked: this would never be published|unavailable right now|Verified/, { timeout: 60_000 });
  for (let i = 0; i < 3; i++) await tour.getByRole("button", { name: "Next" }).click();
  await expect(page.getByRole("region", { name: "Proof" })).toContainText("2,605 / 2,605 scores match");
  await tour.getByRole("button", { name: "Finish" }).click();
  await expect(tour).toHaveCount(0);
  expect(errors).toEqual([]);
});
