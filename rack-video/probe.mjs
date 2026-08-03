/* Identify what blocks the push-in: hide candidate parts, screenshot end pose. */

import http from "node:http";
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import { launch } from "./browser.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUT = path.join(ROOT, "rack-video", "out");
const MIME = { ".html": "text/html", ".js": "text/javascript", ".glb": "model/gltf-binary" };

const server = await new Promise((resolve) => {
  const s = http.createServer((req, res) => {
    const file = path.join(ROOT, decodeURIComponent(req.url.split("?")[0]));
    if (!file.startsWith(ROOT) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      res.writeHead(404); res.end(); return;
    }
    res.writeHead(200, { "Content-Type": MIME[path.extname(file)] ?? "application/octet-stream" });
    fs.createReadStream(file).pipe(res);
  });
  s.listen(0, () => resolve(s));
});

const browser = await launch({ width: 960, height: 540 });
const page = await browser.newPage();
await page.goto(`http://127.0.0.1:${server.address().port}/rack-video/film.html`);
await page.waitForFunction("window.rigReady === true", { timeout: 60000 });

const t = Number(process.argv[2] ?? 18.5);
const groups = ["FOLDABLE", "Seat", "MainFrame", "CASING", "Support"];
for (const g of groups) {
  const n = await page.evaluate(async ({ g, t }) => {
    const count = window.hideMatching(g);
    await window.seek(t);
    return count;
  }, { g, t });
  await page.screenshot({ path: path.join(OUT, `probe_${g}.png`) });
  console.log(`probe_${g}.png (hidden: ${n})`);
  await page.evaluate(() => window.hideMatching("__RESET__"));
}
await browser.close(); server.close();
