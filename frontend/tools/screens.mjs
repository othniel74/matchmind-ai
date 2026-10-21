// Captures the main pages at desktop and phone width for design review.
// Usage: node tools/screens.mjs <baseUrl> <outDir> [label]
import { chromium } from "@playwright/test";

const [base = "http://127.0.0.1:5190", out = "../.test-work/screens", label = "now"] = process.argv.slice(2);
const pages = [["landing", "/"], ["app", "/app"], ["studio", "/app?view=studio"]];
const sizes = [["desktop", { width: 1440, height: 900 }], ["phone", { width: 390, height: 844 }]];

const browser = await chromium.launch();
for (const [sizeName, viewport] of sizes) {
  const context = await browser.newContext({ viewport, deviceScaleFactor: 1 });
  const page = await context.newPage();
  for (const [name, path] of pages) {
    await page.goto(base + path, { waitUntil: "load" }).catch(() => undefined);
    await page.waitForTimeout(name === "landing" ? 2500 : 12000);
    await page.screenshot({ path: `${out}/${label}-${name}-${sizeName}.png`, fullPage: true });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    const height = await page.evaluate(() => document.documentElement.scrollHeight);
    console.log(`${name}/${sizeName}: height ${height}px, horizontal overflow ${overflow}px`);
  }
  await context.close();
}
await browser.close();
