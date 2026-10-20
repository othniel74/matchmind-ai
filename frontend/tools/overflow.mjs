// Lists the outermost elements wider than a phone viewport. Usage: node tools/overflow.mjs <url>
import { chromium } from "@playwright/test";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
await page.goto(process.argv[2], { waitUntil: "networkidle" }).catch(() => undefined);
await page.waitForTimeout(8000);
const wide = await page.evaluate(() => {
  const out = [];
  for (const el of document.querySelectorAll("body *")) {
    const r = el.getBoundingClientRect();
    if (r.right > window.innerWidth + 1 && r.width > 0) {
      const parent = el.parentElement?.getBoundingClientRect();
      if (!parent || parent.right <= window.innerWidth + 1)
        out.push(`${el.tagName.toLowerCase()}.${[...el.classList].join(".")} right=${Math.round(r.right)} width=${Math.round(r.width)}`);
    }
  }
  return out;
});
console.log(wide.join("\n") || "no overflow");
await browser.close();
