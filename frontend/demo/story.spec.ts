import { readFileSync, writeFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";

// The submission video (under two minutes): one story, recorded live against the deployment.
// With NARRATION=<durations.json> (from tools/narrate.py), each scene lasts as long as its spoken
// line, and the time each caption appears is written to story-timeline.json for the audio mix.
const TIMINGS: Record<string, number> = (() => {
  try { return JSON.parse(readFileSync(process.env.NARRATION ?? "", "utf-8")); } catch { return {}; }
})();
const timeline: { id: string; at: number }[] = [];
let t0 = Date.now();
const holdFor = (id: string, fallback: number) => (TIMINGS[id] ? Math.round(TIMINGS[id] * 1000) + 500 : fallback);

// The recorder's clock drifts from the story's while the page is busy, so each scene also sets a
// 14 px marker in the bottom-right corner to a grey level unique to it, in the same step as its
// caption. tools/mix-narration.py reads the marker to place each line, then paints the corner over.
const level = (scene: number) => 16 + scene * 14;

async function caption(page: Page, id: string, text: string, hold = 3000) {
  hold = holdFor(id, hold);
  await page.evaluate(([t, grey]) => {
    let m = document.getElementById("demo-marker");
    if (!m) {
      m = document.createElement("div");
      m.id = "demo-marker";
      Object.assign(m.style, { position: "fixed", right: "0", bottom: "0", width: "14px", height: "14px",
                               zIndex: "100001", pointerEvents: "none" });
      document.body.appendChild(m);
    }
    m.style.background = `rgb(${grey},${grey},${grey})`;
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
    bar.textContent = t as string;
  }, [text, level(timeline.length + 1)] as const);
  timeline.push({ id, at: Date.now() - t0 });
  await page.waitForTimeout(Math.min(hold, 1200));
  await page.screenshot({ path: `../.test-work/story-shots/${String(++shot).padStart(2, "0")}.png` });
  await page.waitForTimeout(Math.max(0, hold - 1200));
}

let shot = 0;

async function card(page: Page, id: string, title: string, lines: string[], hold = 5000) {
  hold = holdFor(id, hold);
  await page.evaluate(([t, l, grey]) => {
    let m = document.getElementById("demo-marker");
    if (!m) {
      m = document.createElement("div");
      m.id = "demo-marker";
      Object.assign(m.style, { position: "fixed", right: "0", bottom: "0", width: "14px", height: "14px",
                               zIndex: "100001", pointerEvents: "none" });
      document.body.appendChild(m);
    }
    m.style.background = `rgb(${grey},${grey},${grey})`;
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
  }, [title, lines, level(timeline.length + 1)] as const);
  timeline.push({ id, at: Date.now() - t0 });
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

const workspace = (page: Page, name: string) =>
  page.getByRole("navigation", { name: "Workspace" }).getByRole("button", { name }).click();

test("Pitchlight submission story", async ({ page }) => {
  t0 = Date.now();  // the recording starts with the page, just before this line
  // Kick off the Event Hubs feed first: the job takes a little while to start, so the match is
  // streaming live by the time the video reaches the feed panel.
  await page.request.post("/api/feed/kickoff").catch(() => undefined);
  // The full-time AI recap takes 10-25 s to write and check. Request it now (the demo caches it per
  // match state). One at a time: parallel runs share the model's rate limit with Ask the match.
  const recapFor = (audience: "analyst" | "fan" | "broadcast") =>
    page.request.get(`/api/recap/agent?minute=90&language=en&audience=${audience}`, { timeout: 120_000 })
      .then((r) => r.json()).then((v) => ({ audience, published: v?.trace?.engine === "microsoft_agent_framework" }))
      .catch(() => ({ audience, published: false }));
  const prefetched = recapFor("analyst");

  // 1. The problem, then the idea: try to fool the fact checker.
  // The replay runs at 3x so the match reaches the moments this story shows within two minutes.
  await page.goto("/app?speed=3");
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  const checker = page.getByRole("region", { name: "Try to fool the fact checker" });
  await checker.evaluate((el) => el.scrollIntoView({ block: "center" }));
  await checker.getByLabel("A claim about the match").pressSequentially("Calderbrook won thanks to a Pedro Valença hat-trick", { delay: 25 });
  await checker.getByRole("button", { name: "Check" }).click();
  await caption(page, "hook", "AI commentary sounds confident, even when it is wrong. So we tried to fool it.", 4500);
  await expect(checker.getByTestId("factcheck-result")).toBeVisible({ timeout: 60_000 });
  await caption(page, "caught", "Every statement is checked against the match. Blocked: it contradicts the score", 5000);
  await caption(page, "intro", "Pitchlight: AI football commentary you can put on air. Nothing unverified is published", 4500);

  // 2. Live moments that explain why they matter
  const moments = page.getByRole("region", { name: "Your moments" });
  const why = page.locator(".why-button").first();
  await expect(why).toBeVisible({ timeout: 60_000 });
  await show(page, moments);
  await why.click();
  await expect(page.getByTestId("why-detail")).toBeVisible();
  await caption(page, "moment", "Every moment says why it matters: build-up, pass-network roles and the evidence events", 3800);

  // 3. Any language, and questions answered by an agent through MCP
  await show(page, page.getByRole("region", { name: "Personalize your match" }));
  await page.getByLabel("Experience language").selectOption("es");
  const ask = page.getByRole("region", { name: "Ask the match" });
  await show(page, ask);
  await ask.getByLabel("Your question").fill("¿Quién es el jugador clave de Merridge?");
  await ask.getByRole("button", { name: "Ask" }).click();
  await caption(page, "ask", "Seven languages. A Foundry agent picks the intent and calls Pitchlight's own MCP tools", 2500);
  await expect(ask.getByTestId("ask-answer")).toBeVisible({ timeout: 40_000 });
  await expect(ask.getByTestId("ask-answer")).toContainText("Foundry agent via MCP");
  await caption(page, "answer", "The viewer sees the tool's verified answer, never the model's own text", 3200);

  // 4. Event-driven on Azure
  await show(page, page.getByRole("region", { name: "Personalize your match" }));
  await page.getByLabel("Experience language").selectOption("en");
  await workspace(page, "Live data");
  const feed = page.getByRole("region", { name: "Azure Event Hubs feed" });
  await feed.waitFor({ timeout: 20_000 }).catch(() => undefined);
  if (await feed.count()) {
    await show(page, feed);
    // Live once the kickoff is accepted; within the cooldown the panel shows the last run instead.
    await expect(feed.getByText(/Live ·/)).toBeVisible({ timeout: 12_000 }).catch(() => undefined);
    await caption(page, "feed", "A Container Apps Job streams the match through Azure Event Hubs; every event is validated live", 4000);
  }

  // 5. Auto-eventing from video, scored against ground truth
  await workspace(page, "Video AI");
  const vision = page.getByRole("region", { name: "Auto-eventing from video" });
  await show(page, vision);
  await vision.locator("video").evaluate(async (v: HTMLVideoElement) => {
    if (v.readyState < 1) await new Promise((r) => v.addEventListener("loadedmetadata", r, { once: true }));
    v.currentTime = 72;
    await v.play();
  });
  await caption(page, "video", "From broadcast video: players, ball, passes and goals recovered, and scored against perfect ground truth", 4500);

  // 6. The connection graph: explorable, directed, and what changed
  await workspace(page, "Analysis");
  const graph = page.getByRole("region", { name: "Match graph" });
  await show(page, graph);
  await graph.locator("svg.pass-network .node.connector").first().click();
  await expect(graph.getByTestId("network-card")).toContainText("Passes most to");
  await caption(page, "graph", "The pass network: directed lanes, forward passes highlighted. Click a player for their partners", 4000);
  await graph.getByRole("button", { name: "Last 15 min" }).click();
  await graph.getByRole("button", { name: "Show change" }).click();
  await caption(page, "change", "Show change: lanes used more (green) or less (red) than in the previous fifteen minutes", 3500);

  // 7. Tactical change, explained honestly
  const tactics = page.getByRole("region", { name: "Tactical changes" });
  await show(page, tactics);
  await expect(tactics.getByTestId("tactics-findings")).toBeVisible({ timeout: 30_000 }).catch(() => undefined);
  await caption(page, "tactics", "After each substitution: before and after, ranked against the match's own swings, never claimed as the cause", 4500);

  // 8. Recaps written by agents and checked by code, step by step
  await workspace(page, "Match centre");
  let choice = await prefetched;
  if (!choice.published) choice = await recapFor("fan");  // rarely needed: about 1 run in 20 is blocked
  const mode = { analyst: "Analyst", fan: "Fan", broadcast: "Broadcast" }[choice.audience];
  await show(page, page.getByRole("region", { name: "Personalize your match" }));
  await page.getByRole("group", { name: "Viewing mode" }).getByRole("button", { name: mode }).click();
  const recap = page.getByRole("region", { name: "Match recap" });
  await expect(recap.getByRole("button", { name: "Full-time" })).toBeEnabled({ timeout: 60_000 });
  await recap.getByRole("button", { name: "AI recap" }).click();
  const run = recap.getByTestId("agent-run");
  await expect(run).toBeVisible({ timeout: 60_000 });
  await run.locator("summary").click();
  await show(page, run);
  const researcher = run.locator(".run-step").filter({ hasText: "Match researcher" }).first();
  if (await researcher.count()) {
    await researcher.evaluate((el) => el.scrollIntoView({ block: "center" }));
    await caption(page, "research", "A researcher agent decides which MCP tools to call and chooses the angle; code computes the facts", 4500);
  }
  await run.locator(".run-step").filter({ hasText: "Tactical analyst" }).first().evaluate((el) => el.scrollIntoView({ block: "start" }));
  await caption(page, "writers", "Writer agents draft and adapt the recap; a fact checker extracts every statement", 4000);
  await run.locator(".run-step.agent").filter({ hasText: "Fact checker" }).first().evaluate((el) => el.scrollIntoView({ block: "start" }));
  await caption(page, "verify", "Code verifies each statement. Anything unsupported is sent back or blocked, never published", 4200);

  // 9. On screen, alongside the match
  await workspace(page, "Broadcast Studio");
  const picker = page.getByLabel("Language");
  await expect(picker).toBeVisible({ timeout: 30_000 });
  await picker.selectOption("ar");
  const overlay = page.locator("button.overlay-item strong").first();
  await expect(overlay).toBeVisible({ timeout: 60_000 });
  await overlay.click();
  await show(page, page.locator(".broadcast-screen"));
  await page.evaluate(() => window.scrollBy(0, -90));
  await caption(page, "studio", "Broadcast Studio: timed, machine-readable overlays, here in Arabic, right to left", 4000);

  // 10. Measured, not claimed; how it is built
  await card(page, "measured", "Measured", [
    "Live recaps in 7 languages: 20–21 of 21 published in repeated runs; the rest blocked, never published wrong",
    "Fact checker: 0 unsafe passes in 264 live checks  ·  Foundry groundedness 4.71 / 5",
    "Load test: 25 concurrent viewers, 0 errors  ·  Real-data adapter: 81,931 events, 0 rejected  ·  292 tests",
  ], 5500);
  await card(page, "closing", "Pitchlight", [
    "Microsoft Foundry  ·  Agent Framework multi-agent workflow  ·  MCP server  ·  RT-DETR vision",
    "Azure Container Apps  ·  Event Hubs  ·  Container Apps Jobs  ·  Memgraph  ·  Application Insights",
    "Managed identity throughout: no keys  ·  Synthetic data, fictional clubs",
    "github.com/othniel74/pitchlight",
  ], 5000);
  writeFileSync("../.test-work/story-timeline.json", JSON.stringify(timeline, null, 1));
});
