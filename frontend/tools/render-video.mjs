// Renders ground-truth tracking as broadcast video frames, with the true camera per frame.
// Usage: node tools/render-video.mjs <rendererUrl> <tracking.json> <outDir> [firstFrame] [count] [step]
// Needs the Vite dev server (render.html). Frames are JPEGs; camera.jsonl has one line per frame.
import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const [url, trackingPath, out, first = "0", count = "100000", step = "1"] = process.argv.slice(2);
fs.mkdirSync(path.join(out, "frames"), { recursive: true });
const tracking = JSON.parse(fs.readFileSync(trackingPath, "utf8"));
const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
page.on("console", (m) => { if (m.type() === "error") console.error("page:", m.text()); });
await page.goto(url, { waitUntil: "networkidle" });
const total = await page.evaluate((t) => window.matchmindRender.load(t), tracking);
const cameras = fs.createWriteStream(path.join(out, "camera.jsonl"));
const start = Date.now();
let written = 0;
for (let i = Number(first); i < Math.min(total, Number(first) + Number(count)); i += Number(step)) {
  const { dataUrl, camera } = await page.evaluate((n) => window.matchmindRender.frame(n), i);
  fs.writeFileSync(path.join(out, "frames", `${String(written).padStart(5, "0")}.jpg`), Buffer.from(dataUrl.split(",")[1], "base64"));
  cameras.write(JSON.stringify({ frame: written, source_frame: i, t: tracking.frames[i].t, ...camera }) + "\n");
  written++;
  if (written % 250 === 0) console.log(`${written} frames, ${((Date.now() - start) / written).toFixed(0)} ms/frame`);
}
cameras.end();
await browser.close();
console.log(`rendered ${written} frames in ${((Date.now() - start) / 1000).toFixed(0)} s`);
